"""Generate verified GWT scenario source from an Execution Case payload."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
from typing import Any, NoReturn, cast

from .checker import check_program
from .errors import GwtError
from .formatter import format_text
from .payloads import ExecutionCasePayload, JsonObject, JsonValue
from .program_identity import load_program_snapshot
from .runtime import (
    ImportPolicy,
    Program,
    Runtime,
    _literal_union_values,
    _list_item_type,
    _optional_item_type,
    _resolve_type_alias,
    parse_program,
)


_PATH_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_DECIMAL_PATTERN = re.compile(r"^-?\d+(?:\.\d+)?$")
_FORMATTER_SENSITIVE_FIELD_NAMES = {
    "set",
    "add",
    "subtract",
    "append",
    "count",
    "sum",
    "find",
    "exists",
    "print",
    "PROGRAM",
    "USE",
    "TYPE",
    "RECORD",
    "REQUEST",
    "OUTPUT",
    "BACKGROUND",
    "SCENARIO",
    "GIVEN",
    "WHEN",
    "THEN",
    "AND",
    "EXAMPLES",
    "LET",
    "REQUIRE",
    "IF",
    "ELSE",
    "FOR",
    "FIND",
    "DEPENDING",
    "DECIDE",
    "RETURN",
    "PASS",
}


@dataclass(frozen=True)
class ScenarioGenerationResult:
    """Canonical scenario source that has been checked and replay-verified."""

    source: str
    scenario_name: str
    request_name: str
    program_file: str


def _new_field_children() -> dict[str, "_FieldNode"]:
    return {}


@dataclass
class _FieldNode:
    value_type: str | None = None
    children: dict[str, "_FieldNode"] = field(default_factory=_new_field_children)


def generate_scenario(
    case: ExecutionCasePayload,
    program_path: str | Path,
    *,
    scenario_name: str | None = None,
    import_policy: ImportPolicy | None = None,
) -> ScenarioGenerationResult:
    """Generate, format, check, execute, and verify one captured scenario.

    ``case`` is intentionally accepted as an in-memory payload so callers can
    choose their own JSON loader and validation boundary.
    """

    payload = cast(Mapping[str, Any], case)
    _validate_case_header(payload)
    case_program = _required_mapping(payload, "program", "execution case")
    request_payload = _required_mapping(payload, "request", "execution case")
    result_payload = _required_mapping(payload, "result", "execution case")
    redaction = _required_mapping(payload, "redaction", "execution case")
    execution = _required_mapping(payload, "execution", "execution case")
    _validate_full_values(redaction)
    if execution.get("outcome") != "completed":
        _refuse("only completed execution cases can become scenarios")
    execution_budget = _captured_limit(execution, "executionBudget")
    max_call_depth = _captured_limit(execution, "maxCallDepth")

    path = Path(program_path)
    snapshot = load_program_snapshot(path, import_policy=import_policy)
    source = snapshot.entry_source
    identity = snapshot.identity
    expected_hash = _required_string(case_program, "hash", "execution case program")
    if case_program.get("hashScope") != "dependency-closure":
        _refuse("execution case program hash is not a dependency-closure identity")
    embedded_identity = _required_mapping(
        case_program,
        "identity",
        "execution case program",
    )
    embedded_digest = _required_string(
        embedded_identity,
        "digest",
        "execution case program identity",
    )
    if embedded_digest != expected_hash:
        _refuse("execution case program identity digest does not match program.hash")
    if identity.digest != expected_hash:
        _refuse(
            "supplied program does not match the execution case "
            f"(expected {expected_hash}, got {identity.digest})"
        )

    request_name = _required_string(request_payload, "name", "execution case request")
    raw_input = _required_mapping(request_payload, "input", "execution case request")
    input_state = _normalize_path_object(raw_input, "request.input")
    expected_result = _normalize_path_object(result_payload, "result")

    program = parse_program(
        source,
        filename=str(snapshot.entry_path),
        import_policy=import_policy,
        source_loader=snapshot.source_for,
    )
    request = program.requests.get(request_name)
    if request is None:
        _refuse(f"supplied program has no REQUEST named {request_name!r}")

    name = _scenario_name(scenario_name, request_name)
    renderer = _ScenarioRenderer(program)
    given_lines: list[str] = []
    for binding in request.inputs.values():
        present, value = _value_at_path(input_state, binding.path)
        if present:
            renderer.reject_unrepresentable_nulls(
                value,
                binding.value_type,
                f"request.input.{binding.path}",
            )
        optional_item_type = _optional_item_type(renderer._resolve(binding.value_type))
        if optional_item_type is not None and (not present or value is None):
            continue
        if not present:
            _refuse(f"request.input is missing declared input: {binding.path}")
        if value is None:
            _refuse(f"request.input contains null at {binding.path}")
        given_lines.extend(renderer.given(binding.path, value, binding.value_type))

    assertions: list[str] = []
    for binding in request.outputs.values():
        present, value = _value_at_path(expected_result, binding.path)
        if present:
            renderer.reject_unrepresentable_nulls(
                value,
                binding.value_type,
                f"result.{binding.path}",
            )
        optional_item_type = _optional_item_type(renderer._resolve(binding.value_type))
        if optional_item_type is not None and (not present or value is None):
            assertions.append(f"{binding.path} is absent")
            continue
        if not present:
            _refuse(f"result is missing declared output: {binding.path}")
        if value is None:
            _refuse(f"result contains null at {binding.path}")
        assertions.extend(renderer.assertions(binding.path, value, binding.value_type))

    raw_scenario = _scenario_source(name, request_name, given_lines, assertions)
    scenario_source = format_text(raw_scenario, filename="<generated-scenario>")
    combined_source = f"{source.rstrip()}\n\n{scenario_source}"
    combined_program = parse_program(
        combined_source,
        filename=str(snapshot.entry_path),
        import_policy=import_policy,
        source_loader=snapshot.source_for,
    )
    errors = [
        diagnostic
        for diagnostic in check_program(combined_program)
        if diagnostic.severity == "error"
    ]
    if errors:
        _refuse(
            "generated scenario does not check: "
            + errors[0].as_error_message(str(snapshot.entry_path))
        )

    generated = combined_program.scenarios[-1]
    if generated.name != name:
        _refuse("generated scenario could not be identified after formatting")
    combined_program.scenarios = [generated]
    try:
        run_result = Runtime(
            combined_program,
            execution_budget=execution_budget,
            max_call_depth=max_call_depth,
        ).run()
    except GwtError as exc:
        _refuse(f"generated scenario failed replay verification: {exc}", cause=exc)

    actual_result = _jsonable(run_result.scenarios[0].returned_state or {})
    expected_json = _jsonable(expected_result)
    if actual_result != expected_json:
        _refuse(
            "generated scenario did not reproduce the captured result: "
            f"expected {_compact_json(expected_json)}, got {_compact_json(actual_result)}"
        )

    return ScenarioGenerationResult(
        source=scenario_source,
        scenario_name=name,
        request_name=request_name,
        program_file=str(path),
    )


class _ScenarioRenderer:
    def __init__(self, program: Program) -> None:
        self.program = program

    def reject_unrepresentable_nulls(
        self,
        value: Any,
        value_type: str,
        evidence_path: str,
    ) -> None:
        resolved = self._resolve(value_type)
        optional_item_type = _optional_item_type(resolved)
        if optional_item_type is not None:
            if value is None:
                return
            self.reject_unrepresentable_nulls(value, optional_item_type, evidence_path)
            return
        if value is None:
            _refuse(f"execution case contains null data at {evidence_path}")

        record = self.program.records.get(resolved)
        if record is not None and isinstance(value, Mapping):
            record_value = cast(Mapping[str, Any], value)
            for field_path, field_type in record.fields.items():
                present, field_value = _value_at_path(record_value, field_path)
                if present:
                    self.reject_unrepresentable_nulls(
                        field_value,
                        field_type,
                        f"{evidence_path}.{field_path}",
                    )
            return

        item_type = _list_item_type(resolved)
        if item_type is not None and isinstance(value, list):
            list_value = cast(list[Any], value)
            for index, item in enumerate(list_value, start=1):
                self.reject_unrepresentable_nulls(
                    item,
                    item_type,
                    f"{evidence_path}[{index}]",
                )
            return

        # Raw `any` values can contain arbitrary nested host data, but current
        # GWT source still has no literal for a null nested inside that data.
        if isinstance(value, Mapping):
            mapping_value = cast(Mapping[str, Any], value)
            for key, item in mapping_value.items():
                self.reject_unrepresentable_nulls(
                    item,
                    "any",
                    f"{evidence_path}.{key}",
                )
        elif isinstance(value, list):
            list_value = cast(list[Any], value)
            for index, item in enumerate(list_value, start=1):
                self.reject_unrepresentable_nulls(
                    item,
                    "any",
                    f"{evidence_path}[{index}]",
                )

    def given(self, path: str, value: Any, value_type: str) -> list[str]:
        resolved = self._resolve(value_type)
        optional_item_type = _optional_item_type(resolved)
        if optional_item_type is not None:
            if value is None:
                return []
            return self.given(path, value, optional_item_type)
        record = self.program.records.get(resolved)
        if record is not None:
            if not isinstance(value, dict):
                _refuse(f"request.input {path} must be a {value_type} record")
            return self._record_given(path, cast(dict[str, Any], value), value_type, record.fields)

        item_type = _list_item_type(resolved)
        if item_type is not None and self.program.records.get(self._resolve(item_type)) is not None:
            if not isinstance(value, list):
                _refuse(f"request.input {path} must be {value_type}")
            return self._record_table(path, cast(list[Any], value), item_type)

        if resolved in self.program.variants or (
            item_type is not None and self._resolve(item_type) in self.program.variants
        ):
            _refuse(f"one-of input {path} is not supported by scenario generation yet")
        return [f"GIVEN {path} is {self._literal(value, resolved, path)}"]

    def assertions(self, path: str, value: Any, value_type: str) -> list[str]:
        resolved = self._resolve(value_type)
        optional_item_type = _optional_item_type(resolved)
        if optional_item_type is not None:
            if value is None:
                return [f"{path} is absent"]
            return [
                f"{path} is present",
                *self.assertions(path, value, optional_item_type),
            ]
        record = self.program.records.get(resolved)
        if record is not None:
            if not isinstance(value, dict):
                _refuse(f"result {path} must be a {value_type} record")
            lines: list[str] = []
            record_value = cast(dict[str, Any], value)
            for field_path, field_type in record.fields.items():
                present, field_value = _value_at_path(record_value, field_path)
                full_path = f"{path}.{field_path}"
                if _optional_item_type(self._resolve(field_type)) is not None and (
                    not present or field_value is None
                ):
                    lines.append(f"{full_path} is absent")
                    continue
                if not present:
                    _refuse(f"result is missing declared output leaf: {full_path}")
                lines.extend(self.assertions(full_path, field_value, field_type))
            return lines

        item_type = _list_item_type(resolved)
        if item_type is not None and (
            self._resolve(item_type) in self.program.records
            or self._resolve(item_type) in self.program.variants
        ):
            _refuse(f"record-list output {path} cannot be expressed exactly in current GWT assertions")
        if resolved in self.program.variants:
            _refuse(f"one-of output {path} is not supported by scenario generation yet")
        if resolved == "any" and isinstance(value, dict):
            _refuse(
                f"object-valued any output {path} cannot be asserted exactly; "
                "extra keys would not be rejected"
            )
        return [f"{path} == {self._literal(value, resolved, path)}"]

    def _record_given(
        self,
        path: str,
        value: dict[str, Any],
        value_type: str,
        fields: Mapping[str, str],
    ) -> list[str]:
        block_fields: dict[str, str] = {}
        preseeded: list[str] = []
        for field_path, field_type in fields.items():
            if field_path.split(".")[-1] not in _FORMATTER_SENSITIVE_FIELD_NAMES:
                block_fields[field_path] = field_type
                continue
            present, field_value = _value_at_path(value, field_path)
            full_path = f"{path}.{field_path}"
            resolved_field_type = self._resolve(field_type)
            if _optional_item_type(resolved_field_type) is not None and (
                not present or field_value is None
            ):
                continue
            if not present:
                _refuse(f"request.input is missing declared record field: {full_path}")
            preseeded.extend(self.given(full_path, field_value, field_type))

        if not block_fields:
            return preseeded

        tree = _field_tree(block_fields)
        block_lines: list[str] = [f"GIVEN {path} is {value_type}"]
        deferred: list[str] = []
        self._record_field_lines(
            tree,
            value,
            path,
            indent=2,
            output=block_lines,
            deferred=deferred,
        )
        return [*preseeded, *block_lines, *deferred]

    def _record_field_lines(
        self,
        node: _FieldNode,
        value: Mapping[str, Any],
        path: str,
        *,
        indent: int,
        output: list[str],
        deferred: list[str],
    ) -> None:
        for field_name, child in node.children.items():
            full_path = f"{path}.{field_name}"
            if child.value_type is not None:
                resolved = self._resolve(child.value_type)
                if _optional_item_type(resolved) is not None and (
                    field_name not in value or value[field_name] is None
                ):
                    continue
            if field_name not in value:
                _refuse(f"request.input is missing declared record field: {full_path}")
            field_value = value[field_name]
            prefix = " " * indent
            if child.children:
                if not isinstance(field_value, dict):
                    _refuse(f"request.input {full_path} must be a nested record")
                output.append(f"{prefix}{field_name}:")
                self._record_field_lines(
                    child,
                    cast(Mapping[str, Any], field_value),
                    full_path,
                    indent=indent + 2,
                    output=output,
                    deferred=deferred,
                )
                continue

            assert child.value_type is not None
            resolved = self._resolve(child.value_type)
            item_type = _list_item_type(resolved)
            if item_type is not None and self.program.records.get(self._resolve(item_type)) is not None:
                if not isinstance(field_value, list):
                    _refuse(f"request.input {full_path} must be {child.value_type}")
                output.append(f"{prefix}{field_name}: []")
                if field_value:
                    deferred.extend(
                        self._record_table(full_path, cast(list[Any], field_value), item_type)
                    )
                continue
            if resolved in self.program.records or resolved in self.program.variants:
                _refuse(f"nested typed record input {full_path} is not expressible in this scenario slice")
            output.append(
                f"{prefix}{field_name}: {self._literal(field_value, resolved, full_path)}"
            )

    def _record_table(self, path: str, values: list[Any], item_type: str) -> list[str]:
        if not values:
            return [f"GIVEN {path} is []"]
        resolved_item = self._resolve(item_type)
        record = self.program.records.get(resolved_item)
        if record is None:
            _refuse(f"request.input {path} has unsupported list item type: {item_type}")
        if any("." in field_name for field_name in record.fields):
            _refuse(f"record list {path} has nested fields that current GWT tables cannot express")

        headers = list(record.fields)
        rows: list[list[str]] = []
        for index, item in enumerate(values, start=1):
            if not isinstance(item, dict):
                _refuse(f"request.input {path}[{index}] must be a {item_type} record")
            record_value = cast(dict[str, Any], item)
            row: list[str] = []
            for field_name in headers:
                if field_name not in record_value:
                    _refuse(
                        f"request.input is missing declared record field: "
                        f"{path}[{index}].{field_name}"
                    )
                cell = self._literal(
                    record_value[field_name],
                    self._resolve(record.fields[field_name]),
                    f"{path}[{index}].{field_name}",
                )
                if "|" in cell:
                    _refuse(f"request.input {path}[{index}].{field_name} contains a table pipe")
                row.append(cell)
            rows.append(row)

        lines = [f"GIVEN {path} are {item_type}"]
        lines.append("  | " + " | ".join(headers) + " |")
        lines.extend("  | " + " | ".join(row) + " |" for row in rows)
        return lines

    def _literal(self, value: Any, value_type: str, path: str) -> str:
        optional_item_type = _optional_item_type(value_type)
        if optional_item_type is not None:
            if value is None:
                _refuse(f"optional value is absent at {path} and has no source literal")
            return self._literal(value, optional_item_type, path)
        if value is None:
            _refuse(f"value is null at {path}")
        union_values = _literal_union_values(value_type)
        if union_values is not None:
            sample = union_values[0]
            if isinstance(sample, bool):
                return _boolean_literal(value, path)
            if isinstance(sample, int):
                return _integer_literal(value, path)
            if isinstance(sample, Decimal):
                return _decimal_literal(value, path)
            if isinstance(sample, float):
                return _number_literal(value, path)
            return _text_literal(value, path)

        item_type = _list_item_type(value_type)
        if item_type is not None or value_type == "list":
            if not isinstance(value, list):
                _refuse(f"value at {path} must be a list")
            resolved_item = self._resolve(item_type) if item_type is not None else "any"
            if resolved_item in self.program.records or resolved_item in self.program.variants:
                _refuse(f"record list {path} requires typed table setup")
            values = cast(list[Any], value)
            return "[" + ", ".join(
                self._literal(item, resolved_item, f"{path}[{index}]")
                for index, item in enumerate(values, start=1)
            ) + "]"

        if value_type == "boolean":
            return _boolean_literal(value, path)
        if value_type == "integer":
            return _integer_literal(value, path)
        if value_type == "decimal":
            return _decimal_literal(value, path)
        if value_type == "number":
            return _number_literal(value, path)
        if value_type == "text":
            return _text_literal(value, path)
        if value_type == "any":
            if isinstance(value, bool):
                return _boolean_literal(value, path)
            if isinstance(value, int):
                return _integer_literal(value, path)
            if isinstance(value, float):
                _refuse(f"host float at untyped path {path} cannot be preserved exactly in GWT source")
            if isinstance(value, str):
                return _text_literal(value, path)
            if isinstance(value, list):
                return self._literal(value, "list", path)
            _refuse(f"value at untyped path {path} cannot be expressed in GWT source")
        _refuse(f"unsupported type for {path}: {value_type}")

    def _resolve(self, value_type: str | None) -> str:
        if value_type is None:
            return "any"
        return _resolve_type_alias(value_type, self.program.type_aliases)


def _field_tree(fields: Mapping[str, str]) -> _FieldNode:
    root = _FieldNode()
    for path, value_type in fields.items():
        current = root
        for part in path.split("."):
            current = current.children.setdefault(part, _FieldNode())
        current.value_type = value_type
    return root


def _scenario_source(
    name: str,
    request_name: str,
    givens: list[str],
    assertions: list[str],
) -> str:
    lines = [f"SCENARIO {name}", *givens, "", f"REQUEST {request_name}"]
    if assertions:
        lines.append("")
        lines.extend(
            f"{'THEN' if index == 0 else 'AND'} {assertion}"
            for index, assertion in enumerate(assertions)
        )
    return "\n".join(lines) + "\n"


def _scenario_name(explicit: str | None, request_name: str) -> str:
    name = explicit.strip() if explicit is not None else f"captured {request_name}"
    if not name:
        _refuse("scenario name cannot be empty")
    if "\n" in name or "\r" in name or "#" in name:
        _refuse("scenario name must be a single GWT source line without a comment")
    return name


def _validate_case_header(case: Mapping[str, Any]) -> None:
    if case.get("kind") != "gwt.execution-case":
        _refuse("execution case kind must be 'gwt.execution-case'")
    if case.get("schemaVersion") != 1:
        _refuse(f"unsupported execution case schemaVersion: {case.get('schemaVersion')!r}")


def _validate_full_values(redaction: Mapping[str, Any]) -> None:
    redacted_paths = redaction.get("redactedPaths")
    invalid = (
        redaction.get("mode") != "none"
        or redaction.get("valuesIncluded") is not True
        or not isinstance(redacted_paths, list)
    )
    if not invalid and isinstance(redacted_paths, list):
        invalid = bool(cast(list[Any], redacted_paths))
    if invalid:
        _refuse("execution case contains redacted or unavailable values")


def _captured_limit(execution: Mapping[str, Any], key: str) -> int | None:
    if key not in execution:
        _refuse(f"execution case execution is missing required field: {key}")
    value = execution[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        _refuse(f"execution case execution.{key} must be a positive integer or null")
    return value


def _required_mapping(
    value: Mapping[str, Any],
    key: str,
    label: str,
) -> Mapping[str, Any]:
    if key not in value:
        _refuse(f"{label} is missing required field: {key}")
    result = value[key]
    if not isinstance(result, dict):
        _refuse(f"{label}.{key} must be an object")
    return cast(Mapping[str, Any], result)


def _required_string(value: Mapping[str, Any], key: str, label: str) -> str:
    if key not in value:
        _refuse(f"{label} is missing required field: {key}")
    result = value[key]
    if not isinstance(result, str) or not result:
        _refuse(f"{label}.{key} must be a non-empty string")
    return result


def _normalize_path_object(value: Mapping[str, Any], label: str) -> JsonObject:
    normalized: JsonObject = {}
    for path, item in value.items():
        if _PATH_PATTERN.fullmatch(path) is None:
            _refuse(f"{label} has an invalid state path: {path!r}")
        current = normalized
        parts = path.split(".")
        for part in parts[:-1]:
            existing = current.get(part)
            if existing is None:
                nested: JsonObject = {}
                current[part] = nested
                current = nested
            elif isinstance(existing, dict):
                current = cast(JsonObject, existing)
            else:
                _refuse(f"{label} path collides with a scalar: {path}")
        current[parts[-1]] = cast(JsonValue, deepcopy(item))
    return normalized


def _value_at_path(value: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = cast(dict[str, Any], current)[part]
    return True, current


def _boolean_literal(value: Any, path: str) -> str:
    if not isinstance(value, bool):
        _refuse(f"value at {path} must be boolean")
    return "true" if value else "false"


def _integer_literal(value: Any, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        _refuse(f"value at {path} must be integer")
    return str(value)


def _decimal_literal(value: Any, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        _refuse(f"exact decimal at {path} must be a JSON string or integer")
    text = str(value)
    if _DECIMAL_PATTERN.fullmatch(text) is None:
        _refuse(f"exact decimal at {path} cannot be represented as a GWT decimal literal: {text!r}")
    try:
        decimal = Decimal(text)
    except InvalidOperation as exc:
        _refuse(f"invalid exact decimal at {path}: {text!r}", cause=exc)
    if not decimal.is_finite():
        _refuse(f"exact decimal at {path} must be finite")
    return text


def _number_literal(value: Any, path: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _refuse(f"value at {path} must be a JSON number")
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        _refuse(f"number at {path} must be finite")
    text = format(Decimal(repr(value)), "f")
    return text if "." in text else f"{text}.0"


def _text_literal(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _refuse(f"value at {path} must be text")
    unsupported = [
        character
        for character in value
        if ord(character) < 32 and character not in {"\n", "\t"}
    ]
    if unsupported:
        _refuse(f"text at {path} contains a control character GWT cannot preserve")
    return json.dumps(value, ensure_ascii=False)


def _jsonable(value: Any) -> JsonValue:
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return cast(JsonValue, value)
    if isinstance(value, list):
        return cast(JsonValue, [_jsonable(item) for item in cast(list[Any], value)])
    if isinstance(value, dict):
        value_map = cast(dict[object, Any], value)
        return cast(
            JsonValue,
            {str(key): _jsonable(item) for key, item in value_map.items()},
        )
    _refuse(f"runtime produced a value that is not JSON-compatible: {type(value).__name__}")


def _compact_json(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _refuse(message: str, *, cause: BaseException | None = None) -> NoReturn:
    error = GwtError(f"cannot generate scenario: {message}")
    if cause is not None:
        raise error from cause
    raise error
