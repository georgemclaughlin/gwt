from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import posixpath
import re
import tempfile
from collections.abc import Mapping
from typing import Any, Literal, cast

from .payloads import (
    ExecutionCaseErrorPayload,
    ExecutionCaseEvidencePayload,
    ExecutionCaseNamedValuePayload,
    ExecutionCaseOperandPayload,
    ExecutionCaseOperandsPayload,
    ExecutionCasePayload,
    ExecutionCaseSelectedDecisionPayload,
    ExecutionCaseSourcePayload,
    ExecutionCaseStateChangePayload,
    ExecutionCaseStateValuePayload,
    ExecutionCaseValuePayload,
    ExecutionCaseValueMarkerPayload,
    JsonObject,
    JsonValue,
)
from .program_identity import (
    LoadedProgramSnapshot,
    ProgramIdentityManifest,
    load_program_snapshot,
)
from .runtime import (
    DEFAULT_EXECUTION_BUDGET,
    DEFAULT_MAX_CALL_DEPTH,
    GwtError,
    ImportPolicy,
    Runtime,
    parse_program,
)
from .tracing import GwtTraceRecorder, OtlpSpan
from .version import (
    LANGUAGE_SPEC_VERSION,
    PACKAGE_NAME,
    PAYLOAD_SCHEMA_VERSION,
    current_package_version,
)


EXECUTION_CASE_SCHEMA_VERSION = 1
EXECUTION_CASE_INTEGRITY_ALGORITHM = "gwt-execution-case-sha256-v1"
EXECUTION_CASE_INTEGRITY_SCOPE = "artifact-without-integrity"
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_EXECUTION_CASE_VALUE_DEPTH = 128


@dataclass(frozen=True)
class ExecutionCaseCapturePolicy:
    """Explicit handling of execution errors and captured runtime values."""

    on_error: Literal["raise", "record"] = "raise"
    values: Literal["full", "omit"] = "full"

    def __post_init__(self) -> None:
        if self.on_error not in {"raise", "record"}:
            raise ValueError("execution case on_error must be 'raise' or 'record'")
        if self.values not in {"full", "omit"}:
            raise ValueError("execution case values must be 'full' or 'omit'")

    def as_payload(self) -> dict[str, str]:
        return {"onError": self.on_error, "values": self.values}


@dataclass(frozen=True)
class ExecutionCase:
    """A portable, versioned record of one named-request execution."""

    _payload: ExecutionCasePayload

    def __post_init__(self) -> None:
        payload = cast(dict[str, object], deepcopy(self._payload))
        _validate_execution_case_payload(payload)
        object.__setattr__(self, "_payload", cast(ExecutionCasePayload, payload))

    @classmethod
    def from_payload(cls, payload: object) -> ExecutionCase:
        if not isinstance(payload, dict):
            raise ValueError("execution case must be a JSON object")
        payload_object = cast(dict[str, object], payload)
        return cls(cast(ExecutionCasePayload, payload_object))

    @classmethod
    def load(cls, path: str | Path) -> ExecutionCase:
        case_path = Path(path)
        try:
            payload = json.loads(case_path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{case_path}: invalid execution case JSON at line {exc.lineno}, "
                f"column {exc.colno}: {exc.msg}"
            ) from exc
        return cls.from_payload(payload)

    @property
    def request_name(self) -> str:
        return self._payload["request"]["name"]

    @property
    def input(self) -> JsonObject:
        return deepcopy(self._payload["request"]["input"])

    @property
    def result(self) -> JsonObject:
        return deepcopy(self._payload["result"])

    @property
    def outcome(self) -> str:
        return self._payload["execution"]["outcome"]

    @property
    def status(self) -> ExecutionCaseNamedValuePayload | None:
        status = self._payload["execution"]["status"]
        if status is None or "value" not in status:
            return None
        return deepcopy(status)

    @property
    def reason(self) -> ExecutionCaseNamedValuePayload | None:
        reason = self._payload["execution"]["reason"]
        if reason is None or "value" not in reason:
            return None
        return deepcopy(reason)

    @property
    def selected_decision(self) -> ExecutionCaseSelectedDecisionPayload | None:
        return deepcopy(self._payload["execution"]["selectedDecision"])

    def as_payload(self) -> ExecutionCasePayload:
        return deepcopy(self._payload)

    def write(self, path: str | Path) -> None:
        _validate_execution_case_payload(cast(dict[str, object], self._payload))
        case_path = Path(path)
        rendered = json.dumps(self._payload, indent=2, sort_keys=True) + "\n"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=case_path.parent,
                prefix=f".{case_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(rendered)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, case_path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def load_execution_case(path: str | Path) -> ExecutionCase:
    return ExecutionCase.load(path)


def capture_execution_case(
    path: str | Path,
    json_state: JsonObject,
    *,
    request: str,
    json_file: str | Path | None = None,
    import_policy: ImportPolicy | None = None,
    policy: ExecutionCaseCapturePolicy | None = None,
    execution_budget: int | None = DEFAULT_EXECUTION_BUDGET,
    max_call_depth: int | None = DEFAULT_MAX_CALL_DEPTH,
    _program_snapshot: LoadedProgramSnapshot | None = None,
) -> ExecutionCase:
    snapshot = _program_snapshot or load_program_snapshot(
        path,
        import_policy=import_policy,
    )
    if snapshot.entry_path != Path(path).resolve():
        raise ValueError("program snapshot entry does not match capture path")
    return _capture_execution_case_from_snapshot(
        snapshot,
        json_state,
        request=request,
        program_file=Path(path),
        json_file=json_file,
        import_policy=import_policy,
        policy=policy,
        execution_budget=execution_budget,
        max_call_depth=max_call_depth,
    )


def _capture_execution_case_from_snapshot(
    snapshot: LoadedProgramSnapshot,
    json_state: JsonObject,
    *,
    request: str,
    program_file: Path | None = None,
    json_file: str | Path | None = None,
    import_policy: ImportPolicy | None = None,
    policy: ExecutionCaseCapturePolicy | None = None,
    execution_budget: int | None = DEFAULT_EXECUTION_BUDGET,
    max_call_depth: int | None = DEFAULT_MAX_CALL_DEPTH,
) -> ExecutionCase:
    """Capture against sources already bound to a dependency-closure identity."""

    capture_policy = policy or ExecutionCaseCapturePolicy()
    _validate_execution_limit("execution_budget", execution_budget)
    _validate_execution_limit("max_call_depth", max_call_depth)
    program_path = snapshot.entry_path
    displayed_program_file = program_file or program_path
    identity = snapshot.identity
    program_hash = identity.digest
    _validate_capture_value(json_state, label="request input")
    try:
        input_state = cast(JsonObject, _jsonable(deepcopy(json_state)))
    except RecursionError:
        raise GwtError(
            "execution case input exceeds the supported nesting depth"
        ) from None
    recorder = GwtTraceRecorder(
        program_file=str(program_path),
        program_name=None,
        program_hash=program_hash,
        request_name=request,
        include_values=capture_policy.values == "full",
    )
    try:
        program = parse_program(
            snapshot.entry_source,
            filename=str(program_path),
            import_policy=import_policy,
            source_loader=snapshot.source_for,
        )
    except GwtError as exc:
        recorder.finish(error=str(exc))
        if capture_policy.on_error == "raise":
            raise
        return _build_execution_case(
            program_file=displayed_program_file,
            snapshot=snapshot,
            program_name=None,
            request=request,
            json_file=json_file,
            input_state=input_state,
            recorder=recorder,
            capture_policy=capture_policy,
            execution_budget=execution_budget,
            max_call_depth=max_call_depth,
            declared_result=None,
            failure=exc,
            failure_stage="parse",
        )

    # The program name is known only after parsing; retain it on the root span
    # without changing the trace's ordering or identity.
    if program.name is not None:
        recorder.spans[0].attributes["gwt.program.name"] = program.name
    try:
        result = Runtime(
            program,
            tracer=recorder,
            execution_budget=execution_budget,
            max_call_depth=max_call_depth,
        ).run_json(
            json_state,
            request,
            request_filename="<request>",
            json_filename=str(json_file) if json_file is not None else None,
        )
    except GwtError as exc:
        recorder.finish(error=str(exc))
        if capture_policy.on_error == "raise":
            raise
        return _build_execution_case(
            program_file=displayed_program_file,
            snapshot=snapshot,
            program_name=program.name,
            request=request,
            json_file=json_file,
            input_state=input_state,
            recorder=recorder,
            capture_policy=capture_policy,
            execution_budget=execution_budget,
            max_call_depth=max_call_depth,
            declared_result=None,
            failure=exc,
            failure_stage="execute",
        )
    recorder.finish()

    returned_state = result.scenarios[0].returned_state or {}
    _validate_capture_value(returned_state, label="declared result")
    declared_result = cast(JsonObject, _jsonable(returned_state))
    return _build_execution_case(
        program_file=displayed_program_file,
        snapshot=snapshot,
        program_name=program.name,
        request=request,
        json_file=json_file,
        input_state=input_state,
        recorder=recorder,
        capture_policy=capture_policy,
        execution_budget=execution_budget,
        max_call_depth=max_call_depth,
        declared_result=declared_result,
        failure=None,
        failure_stage=None,
    )


def _build_execution_case(
    *,
    program_file: Path,
    snapshot: LoadedProgramSnapshot,
    program_name: str | None,
    request: str,
    json_file: str | Path | None,
    input_state: JsonObject,
    recorder: GwtTraceRecorder,
    capture_policy: ExecutionCaseCapturePolicy,
    execution_budget: int | None,
    max_call_depth: int | None,
    declared_result: JsonObject | None,
    failure: GwtError | None,
    failure_stage: str | None,
) -> ExecutionCase:
    program_path = snapshot.entry_path
    identity = snapshot.identity
    program_hash = identity.digest
    source_files = _source_file_map(program_path, identity)
    source_texts = {module.path: module.source for module in snapshot.modules}
    evidence = _semantic_evidence(recorder.spans, source_files)
    selected_decision = _selected_decision(evidence)
    values_included = capture_policy.values == "full"
    status: ExecutionCaseNamedValuePayload | ExecutionCaseValueMarkerPayload | None
    reason: ExecutionCaseNamedValuePayload | ExecutionCaseValueMarkerPayload | None
    if failure is None:
        assert declared_result is not None
        # The language has no declaration that names a privileged outcome
        # field. Do not infer one from conventional keys such as ``status`` or
        # ``reason``; the complete declared result remains the factual output.
        status = None
        reason = None
    else:
        status = {"availability": "unavailable"}
        reason = {"availability": "unavailable"}
    root_span = recorder.spans[0]
    execution: dict[str, object] = {
        "outcome": "completed" if failure is None else "failed",
        "traceId": recorder.trace_id,
        "capturedAt": _timestamp_text(root_span.start_time_unix_nano),
        "executionBudget": execution_budget,
        "maxCallDepth": max_call_depth,
        "capturePolicy": capture_policy.as_payload(),
        "status": status,
        "reason": reason,
        "selectedDecision": selected_decision,
    }
    if failure is not None:
        assert failure_stage in {"parse", "execute"}
        execution["error"] = _normalized_error(
            failure,
            stage=failure_stage,
            program_path=program_path,
            source_files=source_files,
            source_texts=source_texts,
            evidence=evidence,
            redact_message=not values_included,
        )
    redaction = _redaction_payload(
        capture_policy,
        outcome="completed" if failure is None else "failed",
        input_file_present=json_file is not None,
    )
    payload_without_integrity: dict[str, object] = {
        "schemaVersion": EXECUTION_CASE_SCHEMA_VERSION,
        "kind": "gwt.execution-case",
        "program": {
            "name": program_name,
            "file": (
                str(program_file)
                if values_included
                else identity.entry
            ),
            "hash": program_hash,
            "hashScope": "dependency-closure",
            "importsDetected": len(identity.modules) > 1,
            "importsIncludedInHash": True,
            "identity": identity.as_payload(),
            "limitations": [],
        },
        "versions": {
            "packageName": PACKAGE_NAME,
            "packageVersion": current_package_version(),
            "languageSpecVersion": LANGUAGE_SPEC_VERSION,
            "payloadSchemaVersion": PAYLOAD_SCHEMA_VERSION,
        },
        "request": {
            "name": request,
            "input": input_state if values_included else {},
            "inputFile": (
                str(json_file)
                if values_included and json_file is not None
                else None
            ),
        },
        "result": declared_result if values_included and declared_result is not None else {},
        "execution": execution,
        "evidence": evidence,
        "stateChanges": _state_changes(
            recorder.spans,
            source_files,
            values_included=values_included,
        ),
        "redaction": redaction,
    }
    payload_without_integrity["integrity"] = _integrity_payload(payload_without_integrity)
    return ExecutionCase.from_payload(payload_without_integrity)


def _redaction_payload(
    policy: ExecutionCaseCapturePolicy,
    *,
    outcome: str,
    input_file_present: bool,
) -> dict[str, object]:
    if policy.values == "full":
        return {
            "mode": "none",
            "valuesIncluded": True,
            "redactedPaths": [],
            "availability": {
                "programFile": "available",
                "requestInputFile": (
                    "available" if input_file_present else "absent"
                ),
                "requestInput": "available",
                "result": "available" if outcome == "completed" else "unavailable",
                "stateChangeValues": "available",
                "operandValues": "available-or-unavailable",
            },
        }
    redacted_paths = [
        "/program/file",
        "/request/inputFile",
        "/request/input",
        "/result",
        "/execution/status/value",
        "/execution/reason/value",
        "/evidence/*/operands/values",
        "/stateChanges/*/before/value",
        "/stateChanges/*/after/value",
        "/stateChanges/*/patch/*/value",
    ]
    if outcome == "failed":
        redacted_paths.append("/execution/error/message")
    return {
        "mode": "omit-values",
        "valuesIncluded": False,
        "redactedPaths": redacted_paths,
        "availability": {
            "programFile": "redacted",
            "requestInputFile": (
                "redacted" if input_file_present else "absent"
            ),
            "requestInput": "redacted",
            "result": "redacted" if outcome == "completed" else "unavailable",
            "stateChangeValues": "redacted",
            "operandValues": "redacted",
        },
    }


def _normalized_error(
    error: GwtError,
    *,
    stage: str,
    program_path: Path,
    source_files: dict[Path, str],
    source_texts: dict[Path, str],
    evidence: list[ExecutionCaseEvidencePayload],
    redact_message: bool,
) -> ExecutionCaseErrorPayload:
    raw = " ".join(str(error).strip().splitlines())
    detail, source = _error_detail_and_source(
        raw,
        program_path,
        source_files,
        source_texts,
    )
    if source is None:
        source = next(
            (
                deepcopy(item["source"])
                for item in reversed(evidence)
                if item["source"] is not None
            ),
            None,
        )
    for physical, logical in source_files.items():
        detail = detail.replace(str(physical), logical)
    detail = detail.replace(str(program_path.resolve()), _entry_specifier(program_path, source_files))
    return {
        "kind": "GwtError",
        "code": "execution-failed",
        "stage": "parse" if stage == "parse" else "execute",
        "message": (
            "GWT execution failed; error detail omitted by capture policy"
            if redact_message
            else detail
        ),
        "messageAvailability": "redacted" if redact_message else "available",
        "source": source,
    }


def _error_detail_and_source(
    message: str,
    program_path: Path,
    source_files: dict[Path, str],
    source_texts: dict[Path, str],
) -> tuple[str, ExecutionCaseSourcePayload | None]:
    file_match = re.fullmatch(r"(.+):(\d+)(?::(\d+))?:\s*(.*)", message)
    if file_match is not None:
        filename, line_text, column_text, detail = file_match.groups()
        line = int(line_text)
        column = int(column_text) if column_text is not None else 1
        return detail, _error_source(
            filename,
            line,
            column,
            program_path,
            source_files,
            source_texts,
        )

    context_match = re.fullmatch(r"(.+): line (\d+):\s*(.*)", message)
    if context_match is not None:
        context, line_text, detail = context_match.groups()
        return (
            f"{context}: {detail}",
            _error_source(
                str(program_path),
                int(line_text),
                1,
                program_path,
                source_files,
                source_texts,
            ),
        )

    line_match = re.fullmatch(r"line (\d+):\s*(.*)", message)
    if line_match is not None:
        line_text, detail = line_match.groups()
        return (
            detail,
            _error_source(
                str(program_path),
                int(line_text),
                1,
                program_path,
                source_files,
                source_texts,
            ),
        )
    return message, None


def _error_source(
    filename: str,
    line: int,
    column: int,
    program_path: Path,
    source_files: dict[Path, str],
    source_texts: dict[Path, str],
) -> ExecutionCaseSourcePayload | None:
    if line < 1 or column < 1:
        return None
    if filename.startswith("<") and filename.endswith(">"):
        return {"file": filename, "line": line, "column": column, "text": ""}
    physical = program_path.resolve() if filename == "<source>" else Path(filename).resolve()
    logical = source_files.get(physical)
    if logical is None:
        logical_candidates = {value: key for key, value in source_files.items()}
        logical_physical = logical_candidates.get(filename)
        if logical_physical is not None:
            physical = logical_physical
            logical = filename
    if logical is None:
        return {"file": "<request>", "line": line, "column": column, "text": ""}
    lines = source_texts.get(physical, "").splitlines()
    text = lines[line - 1] if line <= len(lines) else ""
    return {"file": logical, "line": line, "column": column, "text": text}


def _entry_specifier(program_path: Path, source_files: dict[Path, str]) -> str:
    return source_files.get(program_path.resolve(), f"./{program_path.name}")


def _validate_execution_limit(name: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer or None")


def execution_case_digest(payload: Mapping[str, object]) -> str:
    """Return the v1 content digest, excluding the ``integrity`` member itself."""

    content = deepcopy(dict(payload))
    content.pop("integrity", None)
    try:
        canonical = json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"execution case contains a non-JSON value: {exc}") from exc
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _integrity_payload(payload: Mapping[str, object]) -> dict[str, str]:
    return {
        "algorithm": EXECUTION_CASE_INTEGRITY_ALGORITHM,
        "scope": EXECUTION_CASE_INTEGRITY_SCOPE,
        "digest": execution_case_digest(payload),
    }


def _validate_execution_case_payload(payload: dict[str, object]) -> None:
    required = {
        "schemaVersion",
        "kind",
        "program",
        "versions",
        "request",
        "result",
        "execution",
        "evidence",
        "stateChanges",
        "redaction",
        "integrity",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"execution case is missing required field: {missing[0]}")
    unexpected = sorted(set(payload).difference(required))
    if unexpected:
        raise ValueError(f"execution case has unknown field: {unexpected[0]}")
    if payload.get("kind") != "gwt.execution-case":
        raise ValueError("execution case kind must be 'gwt.execution-case'")
    if payload.get("schemaVersion") != EXECUTION_CASE_SCHEMA_VERSION:
        raise ValueError(
            "unsupported execution case schemaVersion: "
            f"{payload.get('schemaVersion')!r}"
        )

    program = _case_mapping(payload, "program")
    required_program = {
        "name",
        "file",
        "hash",
        "hashScope",
        "importsDetected",
        "importsIncludedInHash",
        "identity",
        "limitations",
    }
    if set(program) != required_program:
        raise ValueError("execution case program fields do not match the v1 schema")
    program_name = program.get("name")
    if program_name is not None and not isinstance(program_name, str):
        raise ValueError("execution case program.name must be a string or null")
    _case_string(program, "file", "program")
    program_hash = _case_string(program, "hash", "program")
    if _SHA256_PATTERN.fullmatch(program_hash) is None:
        raise ValueError("execution case program.hash must be a sha256 digest")
    if program.get("hashScope") != "dependency-closure":
        raise ValueError("execution case program.hashScope must be 'dependency-closure'")
    if program.get("importsIncludedInHash") is not True:
        raise ValueError("execution case program imports must be included in its hash")
    if not isinstance(program.get("importsDetected"), bool):
        raise ValueError("execution case program.importsDetected must be boolean")
    if program.get("limitations") != []:
        raise ValueError("execution case program.limitations must be an empty array")
    identity = _case_mapping(program, "identity", label="program")
    if set(identity) != {"algorithm", "entry", "digest", "modules"}:
        raise ValueError("execution case program.identity fields do not match v1")
    if identity.get("algorithm") != "gwt-program-closure-sha256-v1":
        raise ValueError("execution case program identity algorithm is unsupported")
    if identity.get("digest") != program_hash:
        raise ValueError("execution case program identity digest does not match program.hash")
    _case_string(identity, "entry", "program.identity")
    modules_value = identity.get("modules")
    if not isinstance(modules_value, list) or not modules_value:
        raise ValueError("execution case program.identity.modules must be a non-empty array")
    modules = cast(list[object], modules_value)
    module_specifiers: set[str] = set()
    ordered_specifiers: list[str] = []
    for index, module_value in enumerate(modules):
        if not isinstance(module_value, dict):
            raise ValueError(f"execution case program identity module {index + 1} must be an object")
        module = cast(dict[str, object], module_value)
        if set(module) != {"specifier", "digest", "imports"}:
            raise ValueError(
                f"execution case program identity module {index + 1} has invalid fields"
            )
        specifier = _case_string(
            module,
            "specifier",
            f"program.identity.modules[{index}]",
        )
        if not _is_logical_module_specifier(specifier):
            raise ValueError(
                "execution case program module specifier must be a normalized "
                "logical relative path"
            )
        if specifier in module_specifiers:
            raise ValueError("execution case program module specifiers must be unique")
        module_specifiers.add(specifier)
        ordered_specifiers.append(specifier)
        digest = _case_string(module, "digest", f"program.identity.modules[{index}]")
        if _SHA256_PATTERN.fullmatch(digest) is None:
            raise ValueError("execution case program module digest must be a sha256 digest")
        imports_value = module.get("imports")
        if not isinstance(imports_value, list) or not all(
            isinstance(item, str) for item in cast(list[object], imports_value)
        ):
            raise ValueError("execution case program module imports must be an array of strings")
    if ordered_specifiers != sorted(ordered_specifiers):
        raise ValueError("execution case program modules must be sorted by specifier")
    if identity.get("entry") not in module_specifiers:
        raise ValueError(
            "execution case program.identity.entry must name a captured module"
        )
    for index, module_value in enumerate(modules):
        module = cast(dict[str, object], module_value)
        for imported in cast(list[str], module["imports"]):
            if imported not in module_specifiers:
                raise ValueError(
                    "execution case program identity import references an uncaptured "
                    f"module: {imported}"
                )
    if bool(program.get("importsDetected")) != (len(modules) > 1):
        raise ValueError(
            "execution case program.importsDetected does not match its identity"
        )
    if _program_identity_digest(identity) != program_hash:
        raise ValueError(
            "execution case program identity digest does not match its manifest"
        )

    versions = _case_mapping(payload, "versions")
    if set(versions) != {
        "packageName",
        "packageVersion",
        "languageSpecVersion",
        "payloadSchemaVersion",
    }:
        raise ValueError("execution case versions fields do not match the v1 schema")
    if versions.get("packageName") != PACKAGE_NAME:
        raise ValueError(f"execution case versions.packageName must be {PACKAGE_NAME!r}")
    _case_string(versions, "packageVersion", "versions")
    _case_string(versions, "languageSpecVersion", "versions")
    payload_schema_version = versions.get("payloadSchemaVersion")
    if (
        isinstance(payload_schema_version, bool)
        or not isinstance(payload_schema_version, int)
        or payload_schema_version < 1
    ):
        raise ValueError(
            "execution case versions.payloadSchemaVersion must be a positive integer"
        )

    request = _case_mapping(payload, "request")
    if set(request) != {"name", "input", "inputFile"}:
        raise ValueError("execution case request fields do not match the v1 schema")
    _case_string(request, "name", "request")
    if not isinstance(request.get("input"), dict):
        raise ValueError("execution case request.input must be an object")
    input_file = request.get("inputFile")
    if input_file is not None and not isinstance(input_file, str):
        raise ValueError("execution case request.inputFile must be a string or null")
    if not isinstance(payload.get("result"), dict):
        raise ValueError("execution case result must be an object")

    execution = _case_mapping(payload, "execution")
    required_execution = {
        "outcome",
        "traceId",
        "capturedAt",
        "executionBudget",
        "maxCallDepth",
        "capturePolicy",
        "status",
        "reason",
        "selectedDecision",
    }
    missing_execution = sorted(required_execution.difference(execution))
    if missing_execution:
        raise ValueError(
            "execution case execution is missing required field: "
            f"{missing_execution[0]}"
        )
    unexpected_execution = sorted(
        set(execution).difference({*required_execution, "error"})
    )
    if unexpected_execution:
        raise ValueError(
            "execution case execution has unknown field: "
            f"{unexpected_execution[0]}"
        )
    outcome = execution.get("outcome")
    if outcome not in {"completed", "failed"}:
        raise ValueError(
            "execution case execution.outcome must be 'completed' or 'failed'"
        )
    trace_id = _case_string(execution, "traceId", "execution")
    if _TRACE_ID_PATTERN.fullmatch(trace_id) is None:
        raise ValueError("execution case execution.traceId must be 32 lowercase hex characters")
    _case_string(execution, "capturedAt", "execution")
    _validate_case_limit(execution, "executionBudget")
    _validate_case_limit(execution, "maxCallDepth")
    capture_policy = _case_mapping(execution, "capturePolicy", label="execution")
    if set(capture_policy) != {"onError", "values"}:
        raise ValueError(
            "execution case execution.capturePolicy must contain only "
            "onError and values"
        )
    if capture_policy.get("onError") not in {"raise", "record"}:
        raise ValueError(
            "execution case execution.capturePolicy.onError must be 'raise' or 'record'"
        )
    if capture_policy.get("values") not in {"full", "omit"}:
        raise ValueError(
            "execution case execution.capturePolicy.values must be 'full' or 'omit'"
        )
    _validate_named_or_marked_value(execution.get("status"), "execution.status")
    _validate_named_or_marked_value(execution.get("reason"), "execution.reason")
    error_value = execution.get("error")
    if outcome == "failed":
        if capture_policy.get("onError") != "record":
            raise ValueError(
                "failed execution cases require capturePolicy.onError 'record'"
            )
        if not isinstance(error_value, dict):
            raise ValueError("failed execution case requires execution.error")
        _validate_execution_error(
            cast(dict[str, object], error_value),
            module_specifiers,
        )
        for name in ("status", "reason"):
            marker = execution.get(name)
            if marker != {"availability": "unavailable"}:
                raise ValueError(
                    f"failed execution case {name} must be explicitly unavailable"
                )
    else:
        if "error" in execution:
            raise ValueError("completed execution case must not contain execution.error")
        if execution.get("status") is not None or execution.get("reason") is not None:
            raise ValueError(
                "completed execution case status and reason must be null; "
                "declared outputs are not inferred"
            )

    evidence_value = payload.get("evidence")
    if not isinstance(evidence_value, list):
        raise ValueError("execution case evidence must be an array")
    evidence = cast(list[object], evidence_value)
    _validate_ordered_items(evidence, "evidence")
    _validate_evidence(evidence, module_specifiers)
    _validate_behavior_lifecycle(evidence)
    changes_value = payload.get("stateChanges")
    if not isinstance(changes_value, list):
        raise ValueError("execution case stateChanges must be an array")
    changes = cast(list[object], changes_value)
    _validate_ordered_items(changes, "stateChanges")
    _validate_source_links(changes, "stateChanges", module_specifiers)
    _validate_state_changes(changes)
    selected_decision = execution.get("selectedDecision")
    if selected_decision is not None:
        if not isinstance(selected_decision, dict):
            raise ValueError(
                "execution case execution.selectedDecision must be an object or null"
            )
        selected_payload = cast(dict[str, object], selected_decision)
        if set(selected_payload) != {"condition", "result", "source"}:
            raise ValueError(
                "execution case execution.selectedDecision must contain exactly "
                "condition, result, and source"
            )
        if not isinstance(selected_payload.get("condition"), str):
            raise ValueError(
                "execution case execution.selectedDecision.condition must be a string"
            )
        if selected_payload.get("result") is not True:
            raise ValueError(
                "execution case execution.selectedDecision.result must be true"
            )
        _validate_source_link(
            selected_payload.get("source"),
            "execution.selectedDecision.source",
            module_specifiers,
        )

    redaction = _case_mapping(payload, "redaction")
    _validate_redaction_profile(
        payload,
        redaction,
        capture_policy=capture_policy,
        outcome=cast(str, outcome),
        evidence=evidence,
        changes=changes,
    )

    _validate_json_value(payload, "execution case")
    integrity = _case_mapping(payload, "integrity")
    if integrity.get("algorithm") != EXECUTION_CASE_INTEGRITY_ALGORITHM:
        raise ValueError("execution case integrity algorithm is unsupported")
    if integrity.get("scope") != EXECUTION_CASE_INTEGRITY_SCOPE:
        raise ValueError("execution case integrity scope is unsupported")
    digest = _case_string(integrity, "digest", "integrity")
    if _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError("execution case integrity.digest must be a sha256 digest")
    expected = execution_case_digest(payload)
    if digest != expected:
        raise ValueError(
            "execution case integrity digest mismatch: artifact content was changed "
            "or serialized incorrectly"
        )


def _case_mapping(
    value: Mapping[str, object],
    key: str,
    *,
    label: str = "execution case",
) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ValueError(f"execution case {label}.{key} must be an object")
    return cast(dict[str, object], item)


def _case_string(value: Mapping[str, object], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"execution case {label}.{key} must be a non-empty string")
    return item


def _program_identity_digest(identity: Mapping[str, object]) -> str:
    canonical = {
        "algorithm": identity["algorithm"],
        "entry": identity["entry"],
        "modules": identity["modules"],
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _is_logical_module_specifier(value: str) -> bool:
    if "\\" in value or not value.startswith(("./", "../")):
        return False
    normalized = posixpath.normpath(value)
    expected = f"./{normalized}" if value.startswith("./") else normalized
    return value == expected


def _validate_case_limit(execution: Mapping[str, object], key: str) -> None:
    value = execution.get(key)
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(
            f"execution case execution.{key} must be a positive integer or null"
        )


def _validate_named_or_marked_value(value: object, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError(f"execution case {label} must be an object or null")
    item = cast(dict[str, object], value)
    if set(item) == {"availability"}:
        if item.get("availability") not in {"redacted", "unavailable"}:
            raise ValueError(
                f"execution case {label}.availability must be 'redacted' or "
                "'unavailable'"
            )
        return
    if set(item) != {"path", "value"}:
        raise ValueError(
            f"execution case {label} must contain path and value, or an "
            "availability marker"
        )
    _case_string(item, "path", label)


def _validate_execution_error(
    error: dict[str, object],
    module_specifiers: set[str],
) -> None:
    required = {
        "kind",
        "code",
        "stage",
        "message",
        "messageAvailability",
        "source",
    }
    if set(error) != required:
        raise ValueError(
            "execution case execution.error must contain exactly kind, code, "
            "stage, message, messageAvailability, and source"
        )
    if error.get("kind") != "GwtError" or error.get("code") != "execution-failed":
        raise ValueError("execution case execution.error kind or code is unsupported")
    if error.get("stage") not in {"parse", "execute"}:
        raise ValueError(
            "execution case execution.error.stage must be 'parse' or 'execute'"
        )
    _case_string(error, "message", "execution.error")
    if error.get("messageAvailability") not in {"available", "redacted"}:
        raise ValueError(
            "execution case execution.error.messageAvailability must be "
            "'available' or 'redacted'"
        )
    _validate_source_link(
        error.get("source"),
        "execution.error.source",
        module_specifiers,
    )


def _validate_state_changes(changes: list[object]) -> None:
    for index, value in enumerate(changes):
        item = cast(dict[str, object], value)
        required = {
            "sequence",
            "path",
            "pointer",
            "operation",
            "before",
            "after",
            "patch",
            "source",
        }
        if set(item) != required:
            missing = sorted(required.difference(item))
            unexpected = sorted(set(item).difference(required))
            if missing:
                raise ValueError(
                    f"execution case stateChanges[{index}] is missing required "
                    f"field: {missing[0]}"
                )
            raise ValueError(
                f"execution case stateChanges[{index}] has unknown field: "
                f"{unexpected[0]}"
            )
        for field in ("path", "pointer"):
            if not isinstance(item.get(field), str):
                raise ValueError(
                    f"execution case stateChanges[{index}].{field} must be a string"
                )
        if item.get("operation") not in {"add", "replace", "remove"}:
            raise ValueError(
                f"execution case stateChanges[{index}].operation is unsupported"
            )
        for field in ("before", "after"):
            state_value = item.get(field)
            if not isinstance(state_value, dict):
                raise ValueError(
                    f"execution case stateChanges[{index}].{field} must be an object"
                )
            state = cast(dict[str, object], state_value)
            if set(state) == {"availability"}:
                if state.get("availability") not in {"redacted", "unavailable"}:
                    raise ValueError(
                        "execution case state value availability must be "
                        "'redacted' or 'unavailable'"
                    )
                continue
            if "present" not in state or set(state).difference({"present", "value"}):
                raise ValueError(
                    f"execution case stateChanges[{index}].{field} must contain "
                    "present and optional value"
                )
            present = state.get("present")
            if not isinstance(present, bool):
                raise ValueError(
                    f"execution case stateChanges[{index}].{field}.present must be boolean"
                )
            if present != ("value" in state):
                raise ValueError(
                    f"execution case stateChanges[{index}].{field} must include value "
                    "exactly when present is true"
                )
        patch = item.get("patch")
        if not isinstance(patch, list):
            raise ValueError(
                f"execution case stateChanges[{index}].patch must be an array"
            )
        for patch_index, operation_value in enumerate(cast(list[object], patch)):
            if not isinstance(operation_value, dict):
                raise ValueError(
                    f"execution case stateChanges[{index}].patch[{patch_index}] "
                    "must be an object"
                )
            operation = cast(dict[str, object], operation_value)
            if set(operation).difference({"op", "path", "value"}):
                raise ValueError("execution case JSON Patch operation has unknown fields")
            if operation.get("op") not in {"add", "replace", "remove"}:
                raise ValueError("execution case JSON Patch operation is unsupported")
            if not isinstance(operation.get("path"), str):
                raise ValueError("execution case JSON Patch path must be a string")
            if operation.get("op") in {"add", "replace"} and "value" not in operation:
                raise ValueError("execution case JSON Patch add/replace requires value")
            if operation.get("op") == "remove" and "value" in operation:
                raise ValueError("execution case JSON Patch remove must not contain value")


def _validate_redaction_profile(
    payload: Mapping[str, object],
    redaction: dict[str, object],
    *,
    capture_policy: Mapping[str, object],
    outcome: str,
    evidence: list[object],
    changes: list[object],
) -> None:
    if set(redaction) != {
        "mode",
        "valuesIncluded",
        "redactedPaths",
        "availability",
    }:
        raise ValueError(
            "execution case redaction must contain exactly mode, valuesIncluded, "
            "redactedPaths, and availability"
        )
    paths_value = redaction.get("redactedPaths")
    if not isinstance(paths_value, list) or not all(
        isinstance(item, str) for item in cast(list[object], paths_value)
    ):
        raise ValueError("execution case redaction.redactedPaths must be strings")
    availability = _case_mapping(redaction, "availability", label="redaction")
    request_payload = _case_mapping(payload, "request")
    full_values = capture_policy.get("values") == "full"
    if outcome == "failed" and payload.get("result") != {}:
        raise ValueError("failed execution case result must be an empty placeholder")
    if not full_values and availability.get("requestInputFile") not in {
        "redacted",
        "absent",
    }:
        raise ValueError(
            "omit-value execution case requestInputFile availability must be "
            "'redacted' or 'absent'"
        )
    expected_availability = {
        "programFile": "available" if full_values else "redacted",
        "requestInputFile": (
            "available"
            if full_values and request_payload.get("inputFile") is not None
            else "absent"
            if full_values
            else availability.get("requestInputFile")
        ),
        "requestInput": "available" if full_values else "redacted",
        "result": (
            "available"
            if outcome == "completed" and full_values
            else "redacted"
            if outcome == "completed"
            else "unavailable"
        ),
        "stateChangeValues": (
            "available" if full_values else "redacted"
        ),
        "operandValues": (
            "available-or-unavailable"
            if full_values
            else "redacted"
        ),
    }
    if availability != expected_availability:
        raise ValueError(
            "execution case redaction.availability does not match the capture profile"
        )

    execution = _case_mapping(payload, "execution")
    if full_values:
        if (
            redaction.get("mode") != "none"
            or redaction.get("valuesIncluded") is not True
            or paths_value != []
        ):
            raise ValueError(
                "full-value execution case requires redaction mode 'none'"
            )
        if any(
            isinstance(item, dict)
            and isinstance(cast(dict[str, object], item).get("operands"), dict)
            and cast(dict[str, object], cast(dict[str, object], item)["operands"]).get(
                "availability"
            )
            == "redacted"
            for item in evidence
        ):
            raise ValueError("full-value execution case contains redacted operands")
        if outcome == "failed":
            error = cast(dict[str, object], execution["error"])
            if error.get("messageAvailability") != "available":
                raise ValueError(
                    "full-value failed execution requires an available error message"
                )
        return

    if (
        redaction.get("mode") != "omit-values"
        or redaction.get("valuesIncluded") is not False
        or not paths_value
    ):
        raise ValueError(
            "omit-value execution case requires redaction mode 'omit-values'"
        )
    program = _case_mapping(payload, "program")
    identity = _case_mapping(program, "identity", label="program")
    if program.get("file") != identity.get("entry"):
        raise ValueError(
            "omit-value execution case program.file must use the logical identity entry"
        )
    if (
        request_payload.get("input") != {}
        or request_payload.get("inputFile") is not None
        or payload.get("result") != {}
    ):
        raise ValueError("omit-value execution case input and result must be empty placeholders")
    for name in ("status", "reason"):
        value = execution.get(name)
        if outcome == "failed":
            expected_marker: object = {"availability": "unavailable"}
            if value != expected_marker:
                raise ValueError(f"failed execution case {name} must be unavailable")
        elif value is not None and value != {"availability": "redacted"}:
            raise ValueError(
                f"omit-value execution case {name} must be redacted or absent"
            )
    for item in evidence:
        if not isinstance(item, dict):
            continue
        operands = cast(dict[str, object], item).get("operands")
        if operands is not None and operands != {"availability": "redacted"}:
            raise ValueError("omit-value execution case operands must be redacted")
    for item in changes:
        change = cast(dict[str, object], item)
        if (
            change.get("before") != {"availability": "redacted"}
            or change.get("after") != {"availability": "redacted"}
            or change.get("patch") != []
        ):
            raise ValueError(
                "omit-value execution case state changes must contain only redacted "
                "value markers"
            )
    if outcome == "failed":
        error = cast(dict[str, object], execution["error"])
        if (
            error.get("messageAvailability") != "redacted"
            or error.get("message")
            != "GWT execution failed; error detail omitted by capture policy"
        ):
            raise ValueError(
                "omit-value failed execution must contain the fixed redacted error message"
            )


def _validate_ordered_items(values: list[object], label: str) -> None:
    previous = 0
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise ValueError(f"execution case {label}[{index}] must be an object")
        item = cast(dict[str, object], value)
        sequence = item.get("sequence")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ValueError(f"execution case {label}[{index}].sequence must be a positive integer")
        if sequence <= previous:
            raise ValueError(f"execution case {label} sequences must be strictly increasing")
        previous = sequence


def _validate_evidence(
    evidence: list[object],
    module_specifiers: set[str],
) -> None:
    allowed_kinds = {"contract", "condition", "branch", "assertion", "behavior"}
    allowed_fields = {
        "sequence",
        "kind",
        "summary",
        "source",
        "label",
        "path",
        "valueType",
        "expression",
        "result",
        "branchKind",
        "branchLabel",
        "selected",
        "startLine",
        "endLine",
        "operands",
        "phase",
        "signature",
        "callId",
        "parentCallId",
        "depth",
        "behaviorOutcome",
    }
    for index, value in enumerate(evidence):
        item = cast(dict[str, object], value)
        missing_base = {"sequence", "kind", "summary", "source"}.difference(item)
        if missing_base:
            raise ValueError(
                f"execution case evidence[{index}] is missing required field: "
                f"{sorted(missing_base)[0]}"
            )
        unexpected = set(item).difference(allowed_fields)
        if unexpected:
            raise ValueError(
                f"execution case evidence[{index}] has unknown field: "
                f"{sorted(unexpected)[0]}"
            )
        if not isinstance(item.get("summary"), str):
            raise ValueError(
                f"execution case evidence[{index}].summary must be a string"
            )
        _validate_source_link(
            item.get("source"),
            f"evidence[{index}].source",
            module_specifiers,
        )
        kind = item.get("kind")
        if kind not in allowed_kinds:
            raise ValueError(
                f"execution case evidence[{index}].kind is unsupported: {kind!r}"
            )
        required_for_kind = {
            "contract": {"label", "path", "valueType", "result"},
            "condition": {"expression", "result", "operands"},
            "branch": {
                "branchKind",
                "branchLabel",
                "expression",
                "selected",
                "startLine",
                "endLine",
            },
            "assertion": {"expression", "result", "operands"},
            "behavior": {"phase", "signature", "callId", "parentCallId", "depth"},
        }[cast(str, kind)]
        missing_kind = required_for_kind.difference(item)
        if missing_kind:
            raise ValueError(
                f"execution case evidence[{index}] is missing required {kind} field: "
                f"{sorted(missing_kind)[0]}"
            )
        for field in (
            "label",
            "path",
            "valueType",
            "expression",
            "branchKind",
            "branchLabel",
        ):
            if field in item and not isinstance(item[field], str):
                raise ValueError(
                    f"execution case evidence[{index}].{field} must be a string"
                )
        for field in ("result", "selected"):
            if field in item and not isinstance(item[field], bool):
                raise ValueError(
                    f"execution case evidence[{index}].{field} must be boolean"
                )
        if kind == "branch":
            start_line = item.get("startLine")
            end_line = item.get("endLine")
            if (
                not isinstance(start_line, int)
                or isinstance(start_line, bool)
                or not isinstance(end_line, int)
                or isinstance(end_line, bool)
                or start_line < 1
                or end_line < start_line
            ):
                raise ValueError(
                    f"execution case evidence[{index}] branch range is invalid"
                )
        if kind in {"condition", "assertion"}:
            _validate_operand_evidence(item, index)
        if kind == "behavior":
            _validate_behavior_evidence(item, index)


def _validate_source_links(
    values: list[object],
    label: str,
    module_specifiers: set[str],
) -> None:
    for index, value in enumerate(values):
        item = cast(dict[str, object], value)
        _validate_source_link(
            item.get("source"),
            f"{label}[{index}].source",
            module_specifiers,
        )


def _validate_source_link(
    value: object,
    label: str,
    module_specifiers: set[str],
) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError(f"execution case {label} must be an object or null")
    source = cast(dict[str, object], value)
    filename = _case_string(source, "file", label)
    if not (
        filename in module_specifiers
        or (filename.startswith("<") and filename.endswith(">"))
    ):
        raise ValueError(
            f"execution case {label}.file must name a program identity module "
            "or pseudo source"
        )
    for field in ("line", "column"):
        position = source.get(field)
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position < 1
        ):
            raise ValueError(
                f"execution case {label}.{field} must be a positive integer"
            )
    if not isinstance(source.get("text"), str):
        raise ValueError(f"execution case {label}.text must be a string")


def _validate_operand_evidence(item: dict[str, object], index: int) -> None:
    operands = item.get("operands")
    if not isinstance(operands, dict):
        raise ValueError(
            f"execution case evidence[{index}].operands must be an object"
        )
    operand_payload = cast(dict[str, object], operands)
    availability = operand_payload.get("availability")
    if availability == "available":
        values = operand_payload.get("values")
        if not isinstance(values, list):
            raise ValueError(
                f"execution case evidence[{index}].operands.values must be an array"
            )
        for operand_index, operand_value in enumerate(cast(list[object], values)):
            if not isinstance(operand_value, dict):
                raise ValueError(
                    "execution case "
                    f"evidence[{index}].operands.values[{operand_index}] "
                    "must be an object"
                )
            operand = cast(dict[str, object], operand_value)
            _case_string(
                operand,
                "name",
                f"evidence[{index}].operands.values[{operand_index}]",
            )
            _case_string(
                operand,
                "valueType",
                f"evidence[{index}].operands.values[{operand_index}]",
            )
            if "value" not in operand:
                raise ValueError(
                    "execution case "
                    f"evidence[{index}].operands.values[{operand_index}].value "
                    "is required"
                )
        return
    if availability == "unavailable":
        _case_string(operand_payload, "reason", f"evidence[{index}].operands")
        return
    if availability == "redacted":
        if set(operand_payload) != {"availability"}:
            raise ValueError(
                f"execution case evidence[{index}].operands redacted marker "
                "must not contain values"
            )
        return
    raise ValueError(
        "execution case "
        f"evidence[{index}].operands.availability must be 'available', "
        "'unavailable', or 'redacted'"
    )


def _validate_behavior_evidence(item: dict[str, object], index: int) -> None:
    phase = item.get("phase")
    if phase not in {"enter", "exit"}:
        raise ValueError(
            f"execution case evidence[{index}].phase must be 'enter' or 'exit'"
        )
    _case_string(item, "signature", f"evidence[{index}]")
    _case_string(item, "callId", f"evidence[{index}]")
    parent_call_id = item.get("parentCallId")
    if parent_call_id is not None and (
        not isinstance(parent_call_id, str) or not parent_call_id
    ):
        raise ValueError(
            f"execution case evidence[{index}].parentCallId must be a string or null"
        )
    depth = item.get("depth")
    if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
        raise ValueError(
            f"execution case evidence[{index}].depth must be a non-negative integer"
        )
    if phase == "exit" and item.get("behaviorOutcome") not in {
        "completed",
        "failed",
    }:
        raise ValueError(
            "execution case "
            f"evidence[{index}].behaviorOutcome must be 'completed' or 'failed'"
        )


def _validate_behavior_lifecycle(evidence: list[object]) -> None:
    stack: list[tuple[str, str | None, int]] = []
    seen: set[str] = set()
    for index, value in enumerate(evidence):
        item = cast(dict[str, object], value)
        if item.get("kind") != "behavior":
            continue
        call_id = cast(str, item["callId"])
        parent = cast(str | None, item["parentCallId"])
        depth = cast(int, item["depth"])
        if item.get("phase") == "enter":
            if call_id in seen:
                raise ValueError("execution case behavior call IDs must be unique")
            expected_parent = stack[-1][0] if stack else None
            if parent != expected_parent or depth != len(stack):
                raise ValueError(
                    f"execution case evidence[{index}] has inconsistent behavior nesting"
                )
            seen.add(call_id)
            stack.append((call_id, parent, depth))
            continue
        if not stack or stack[-1] != (call_id, parent, depth):
            raise ValueError(
                f"execution case evidence[{index}] exits a behavior out of order"
            )
        stack.pop()
    if stack:
        raise ValueError("execution case evidence has behavior calls without exit facts")


def _validate_json_value(value: object, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite JSON number")
        return
    if isinstance(value, list):
        for index, item in enumerate(cast(list[object], value)):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string object key")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains a non-JSON value: {type(value).__name__}")


def _validate_capture_value(value: object, *, label: str) -> None:
    stack: list[tuple[object, int, str]] = [(value, 1, label)]
    while stack:
        current, depth, path = stack.pop()
        if depth > MAX_EXECUTION_CASE_VALUE_DEPTH:
            raise GwtError(
                f"{label} exceeds the maximum supported nesting depth of "
                f"{MAX_EXECUTION_CASE_VALUE_DEPTH}"
            )
        if current is None or isinstance(current, (str, bool, int)):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise GwtError(f"{path} contains a non-finite number")
            continue
        if isinstance(current, Decimal):
            if not current.is_finite():
                raise GwtError(f"{path} contains a non-finite exact number")
            continue
        if isinstance(current, list):
            for index, item in enumerate(cast(list[object], current)):
                stack.append((item, depth + 1, f"{path}[{index}]"))
            continue
        if isinstance(current, dict):
            for key, item in cast(dict[object, object], current).items():
                if not isinstance(key, str):
                    raise GwtError(f"{path} contains a non-string object key")
                stack.append((item, depth + 1, f"{path}.{key}"))
            continue
        raise GwtError(
            f"{path} contains an unsupported value: {type(current).__name__}"
        )


def _semantic_evidence(
    spans: list[OtlpSpan],
    source_files: dict[Path, str],
) -> list[ExecutionCaseEvidencePayload]:
    evidence: list[ExecutionCaseEvidencePayload] = []
    for event_name, attributes in _ordered_events(spans):
        sequence = _integer(attributes.get("gwt.event.sequence"))
        if sequence is None:
            continue
        if event_name not in {
            "gwt.contract.checked",
            "gwt.condition.evaluated",
            "gwt.branch.selected",
            "gwt.branch.skipped",
            "gwt.assertion.checked",
            "gwt.behavior.entered",
            "gwt.behavior.exited",
        }:
            continue
        source_link = _source_link(attributes, source_files)
        summary = str(attributes.get("gwt.event.summary") or "")
        item: ExecutionCaseEvidencePayload
        if event_name == "gwt.contract.checked":
            item = {
                "sequence": sequence,
                "kind": "contract",
                "summary": summary,
                "source": source_link,
                "label": str(attributes.get("gwt.contract.label") or ""),
                "path": str(attributes.get("gwt.contract.path") or ""),
                "valueType": str(attributes.get("gwt.contract.type") or ""),
                "result": bool(attributes.get("gwt.contract.passed")),
            }
        elif event_name == "gwt.condition.evaluated":
            item = {
                "sequence": sequence,
                "kind": "condition",
                "summary": summary,
                "source": source_link,
                "expression": str(attributes.get("gwt.condition.text") or ""),
                "result": bool(attributes.get("gwt.condition.result")),
                "operands": _operand_evidence(attributes),
            }
        elif event_name in {"gwt.branch.selected", "gwt.branch.skipped"}:
            item = {
                "sequence": sequence,
                "kind": "branch",
                "summary": summary,
                "source": source_link,
                "branchKind": str(attributes.get("gwt.branch.kind") or ""),
                "branchLabel": str(attributes.get("gwt.branch.label") or ""),
                "expression": str(attributes.get("gwt.branch.condition") or ""),
                "selected": bool(attributes.get("gwt.branch.selected")),
                "startLine": _integer(attributes.get("gwt.branch.start_line")) or 0,
                "endLine": _integer(attributes.get("gwt.branch.end_line")) or 0,
            }
        elif event_name == "gwt.assertion.checked":
            item = {
                "sequence": sequence,
                "kind": "assertion",
                "summary": summary,
                "source": source_link,
                "expression": str(attributes.get("gwt.assertion.text") or ""),
                "result": bool(attributes.get("gwt.assertion.result")),
                "operands": _operand_evidence(attributes),
            }
        elif event_name in {"gwt.behavior.entered", "gwt.behavior.exited"}:
            phase = "enter" if event_name == "gwt.behavior.entered" else "exit"
            parent_call_id = attributes.get("gwt.behavior.parent_call_id")
            item = {
                "sequence": sequence,
                "kind": "behavior",
                "summary": summary,
                "source": source_link,
                "phase": phase,
                "signature": str(attributes.get("gwt.behavior.signature") or ""),
                "callId": str(attributes.get("gwt.behavior.call_id") or ""),
                "parentCallId": (
                    str(parent_call_id) if parent_call_id is not None else None
                ),
                "depth": _integer(attributes.get("gwt.behavior.depth")) or 0,
            }
            if phase == "exit":
                item["behaviorOutcome"] = (
                    "failed"
                    if attributes.get("gwt.behavior.outcome") == "failed"
                    else "completed"
                )
        else:
            continue
        evidence.append(item)
    return evidence


def _operand_evidence(attributes: dict[str, Any]) -> ExecutionCaseOperandsPayload:
    availability = attributes.get("gwt.expression.operands.availability")
    if availability == "redacted":
        return {"availability": "redacted"}
    if availability != "available":
        reason = attributes.get("gwt.expression.operands.unavailable_reason")
        return {
            "availability": "unavailable",
            "reason": str(reason or "not-observed"),
        }

    encoded = attributes.get("gwt.expression.operands")
    if not isinstance(encoded, str):
        return {
            "availability": "unavailable",
            "reason": "malformed-trace-value",
        }
    try:
        decoded = json.loads(encoded)
    except json.JSONDecodeError:
        return {
            "availability": "unavailable",
            "reason": "malformed-trace-value",
        }
    if not isinstance(decoded, list):
        return {
            "availability": "unavailable",
            "reason": "malformed-trace-value",
        }
    values: list[ExecutionCaseOperandPayload] = []
    for value in cast(list[object], decoded):
        if not isinstance(value, dict):
            return {
                "availability": "unavailable",
                "reason": "malformed-trace-value",
            }
        operand = cast(dict[str, object], value)
        name = operand.get("name")
        value_type = operand.get("valueType")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(value_type, str)
            or not value_type
            or "value" not in operand
        ):
            return {
                "availability": "unavailable",
                "reason": "malformed-trace-value",
            }
        values.append(
            {
                "name": name,
                "valueType": value_type,
                "value": cast(JsonValue, operand["value"]),
            }
        )
    return {"availability": "available", "values": values}


def _selected_decision(
    evidence: list[ExecutionCaseEvidencePayload],
) -> ExecutionCaseSelectedDecisionPayload | None:
    selected = [
        item
        for item in evidence
        if item["kind"] == "branch"
        and item.get("branchKind") == "DECIDE"
        and item.get("selected") is True
    ]
    if len(selected) != 1:
        return None
    item = selected[0]
    return {
        "condition": item.get("expression", ""),
        "result": True,
        "source": item["source"],
    }


def _state_changes(
    spans: list[OtlpSpan],
    source_files: dict[Path, str],
    *,
    values_included: bool,
) -> list[ExecutionCaseStateChangePayload]:
    # Reconstruct the actual runtime state in event order. BACKGROUND GIVEN
    # setup and the JSON overlay both happen before ``gwt.input.applied``;
    # their patches establish the effective input baseline but are not review
    # changes. Starting from ``input_state`` would lose background-only fields
    # and give the wrong "before" value when JSON overrides a default.
    document: JsonObject = {}
    baseline_applied = False
    changes: list[ExecutionCaseStateChangePayload] = []
    for event_name, attributes in _ordered_events(spans):
        if event_name == "gwt.input.applied":
            baseline_applied = True
            continue
        if event_name != "gwt.state.changed":
            continue
        sequence = _integer(attributes.get("gwt.event.sequence"))
        if sequence is None:
            continue
        pointer = str(attributes.get("gwt.state.pointer") or "")
        patch = _patch_payload(attributes.get("gwt.state.patch"))
        before: ExecutionCaseStateValuePayload
        after: ExecutionCaseStateValuePayload
        if values_included:
            before_present, before_value = _value_at_pointer(document, pointer)
            _apply_patch(document, patch)
            after_present, after_value = _value_at_pointer(document, pointer)
            if not baseline_applied:
                continue
            before_value_payload: ExecutionCaseValuePayload = {
                "present": before_present
            }
            if before_present:
                before_value_payload["value"] = deepcopy(before_value)
            after_value_payload: ExecutionCaseValuePayload = {
                "present": after_present
            }
            if after_present:
                after_value_payload["value"] = deepcopy(after_value)
            before = before_value_payload
            after = after_value_payload
        else:
            if not baseline_applied:
                continue
            before = {"availability": "redacted"}
            after = {"availability": "redacted"}
            patch = []
        changes.append(
            {
                "sequence": sequence,
                "path": str(attributes.get("gwt.state.path") or ""),
                "pointer": pointer,
                "operation": str(attributes.get("gwt.state.operation") or ""),
                "before": before,
                "after": after,
                "patch": patch,
                "source": _source_link(attributes, source_files),
            }
        )
    return changes


def _ordered_events(spans: list[OtlpSpan]) -> list[tuple[str, dict[str, Any]]]:
    events = [
        (event.name, dict(event.attributes))
        for span in spans
        for event in span.events
    ]
    return sorted(events, key=lambda item: _integer(item[1].get("gwt.event.sequence")) or 0)


def _source_link(
    attributes: dict[str, Any],
    source_files: dict[Path, str],
) -> ExecutionCaseSourcePayload | None:
    line = _integer(attributes.get("code.line.number"))
    column = _integer(attributes.get("code.column.number"))
    file = attributes.get("code.file.path")
    if file is None or line is None or line < 1 or column is None or column < 1:
        return None
    file_text = str(file)
    if file_text.startswith("<") and file_text.endswith(">"):
        logical_file = file_text
    else:
        resolved_file = Path(file_text).resolve()
        try:
            logical_file = source_files[resolved_file]
        except KeyError as exc:
            raise ValueError(
                "execution trace source is outside the captured program identity: "
                f"{file_text}"
            ) from exc
    return {
        "file": logical_file,
        "line": line,
        "column": column,
        "text": str(attributes.get("gwt.source.text") or ""),
    }


def _source_file_map(
    program_path: Path,
    identity: ProgramIdentityManifest,
) -> dict[Path, str]:
    root = program_path.resolve().parent
    return {
        (root / module.specifier).resolve(): module.specifier
        for module in identity.modules
    }


def _patch_payload(value: object) -> list[JsonObject]:
    if not isinstance(value, str):
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        return []
    return cast(list[JsonObject], parsed)


def _value_at_pointer(document: JsonValue, pointer: str) -> tuple[bool, JsonValue | None]:
    if pointer == "":
        return True, document
    current: JsonValue = document
    for part in _pointer_parts(pointer):
        if isinstance(current, dict):
            if part not in current:
                return False, None
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError:
                return False, None
            if index < 0 or index >= len(current):
                return False, None
            current = current[index]
            continue
        return False, None
    return True, current


def _apply_patch(document: JsonObject, patch: list[JsonObject]) -> None:
    for operation in patch:
        op = operation.get("op")
        path = operation.get("path")
        if not isinstance(op, str) or not isinstance(path, str):
            raise ValueError("invalid JSON Patch operation in execution trace")
        parts = _pointer_parts(path)
        if not parts:
            raise ValueError("root JSON Patch operations are not supported in execution cases")
        parent: JsonValue = document
        for part in parts[:-1]:
            if isinstance(parent, dict):
                parent = parent[part]
            elif isinstance(parent, list):
                parent = parent[int(part)]
            else:
                raise ValueError(f"JSON Patch parent is not a container: {path}")
        key = parts[-1]
        if op in {"add", "replace"}:
            value = deepcopy(operation.get("value"))
            if isinstance(parent, dict):
                parent[key] = value
            elif isinstance(parent, list):
                if op == "add" and key == "-":
                    parent.append(value)
                elif op == "add":
                    parent.insert(int(key), value)
                else:
                    parent[int(key)] = value
            else:
                raise ValueError(f"JSON Patch parent is not a container: {path}")
        elif op == "remove":
            if isinstance(parent, dict):
                del parent[key]
            elif isinstance(parent, list):
                del parent[int(key)]
            else:
                raise ValueError(f"JSON Patch parent is not a container: {path}")
        else:
            raise ValueError(f"unsupported JSON Patch operation in execution trace: {op}")


def _pointer_parts(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        if pointer == "":
            return []
        raise ValueError(f"invalid JSON Pointer in execution trace: {pointer}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def _timestamp_text(unix_nano: int) -> str:
    timestamp = datetime.fromtimestamp(unix_nano / 1_000_000_000, tz=timezone.utc)
    return timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _integer(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _jsonable(value: object) -> JsonValue:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in cast(list[object], value)]
    if isinstance(value, dict):
        return {
            str(key): _jsonable(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return cast(JsonValue, value)
