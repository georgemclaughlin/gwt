"""Versioned collections of human-referenced GWT Execution Cases."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Literal, TypedDict, cast

from .execution_case import ExecutionCase


CASE_CORPUS_SCHEMA_VERSION = 1
CASE_CORPUS_INTEGRITY_ALGORITHM = "gwt-case-corpus-sha256-v1"
CASE_CORPUS_INTEGRITY_SCOPE = "artifact-without-integrity"
MAX_CORPUS_NAME_LENGTH = 200
MAX_CASE_REFERENCE_LENGTH = 256
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_UNSAFE_DISPLAY_CHARACTER = re.compile(
    r"[\x00-\x1f\x7f-\x9f\u061c\u200b-\u200f\u2028-\u202e\u2060-\u206f\ufeff]"
)


class CaseCorpusEntryPayload(TypedDict):
    reference: str
    caseId: str
    artifact: str


class CaseCorpusIntegrityPayload(TypedDict):
    algorithm: Literal["gwt-case-corpus-sha256-v1"]
    scope: Literal["artifact-without-integrity"]
    digest: str


class CaseCorpusPayload(TypedDict):
    schemaVersion: int
    kind: Literal["gwt.case-corpus"]
    name: str
    cases: list[CaseCorpusEntryPayload]
    integrity: CaseCorpusIntegrityPayload


@dataclass(frozen=True)
class CaseCorpusEntrySpec:
    """One reference-to-artifact mapping supplied when writing a corpus."""

    reference: str
    case_id: str
    artifact: str

    def as_payload(self) -> CaseCorpusEntryPayload:
        return {
            "reference": self.reference,
            "caseId": self.case_id,
            "artifact": self.artifact,
        }


@dataclass(frozen=True)
class CaseCorpusEntry:
    """A validated corpus entry and its integrity-checked Execution Case."""

    reference: str
    case_id: str
    artifact: str
    execution_case: ExecutionCase

    def as_payload(self) -> CaseCorpusEntryPayload:
        return {
            "reference": self.reference,
            "caseId": self.case_id,
            "artifact": self.artifact,
        }


@dataclass(frozen=True)
class CaseCorpus:
    """A strict, portable selection of labeled Execution Case artifacts."""

    name: str
    entries: tuple[CaseCorpusEntry, ...]
    path: Path
    _payload: CaseCorpusPayload

    @property
    def cases(self) -> tuple[ExecutionCase, ...]:
        return tuple(entry.execution_case for entry in self.entries)

    @property
    def references(self) -> tuple[str, ...]:
        return tuple(entry.reference for entry in self.entries)

    def as_payload(self) -> CaseCorpusPayload:
        return deepcopy(self._payload)


def load_case_corpus(path: str | Path) -> CaseCorpus:
    corpus_path = Path(path)
    try:
        payload = json.loads(
            corpus_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_object,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{corpus_path}: invalid case corpus JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc
    return _load_case_corpus_payload(payload, corpus_path)


def write_case_corpus(
    path: str | Path,
    *,
    name: str,
    entries: list[CaseCorpusEntrySpec],
) -> CaseCorpus:
    """Validate and atomically write a corpus that references existing cases."""

    corpus_path = Path(path)
    payload_without_integrity: dict[str, object] = {
        "schemaVersion": CASE_CORPUS_SCHEMA_VERSION,
        "kind": "gwt.case-corpus",
        "name": name,
        "cases": [entry.as_payload() for entry in entries],
    }
    payload: dict[str, object] = {
        **payload_without_integrity,
        "integrity": _integrity_payload(payload_without_integrity),
    }
    corpus = _load_case_corpus_payload(payload, corpus_path)
    destination = corpus_path.resolve()
    root = corpus_path.parent.resolve()
    for entry in corpus.entries:
        if _resolve_artifact_path(root, entry.artifact) == destination:
            raise ValueError(
                "case corpus cannot overwrite a referenced artifact: "
                f"{entry.artifact}"
            )
    rendered = json.dumps(corpus.as_payload(), indent=2, sort_keys=True) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=corpus_path.parent,
            prefix=f".{corpus_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, corpus_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return corpus


def case_corpus_digest(payload: object) -> str:
    """Return the canonical digest for a corpus payload or unsigned mapping."""

    if not isinstance(payload, dict):
        raise ValueError("case corpus digest input must be a JSON object")
    unsigned = deepcopy(cast(dict[object, object], payload))
    unsigned.pop("integrity", None)
    try:
        canonical = json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"case corpus contains a non-JSON value: {exc}") from exc
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def validate_case_reference(value: object) -> str:
    """Validate untrusted reference text before terminal or HTML presentation."""

    return _validate_display_text(
        value,
        label="case reference",
        maximum=MAX_CASE_REFERENCE_LENGTH,
    )


def _load_case_corpus_payload(payload: object, corpus_path: Path) -> CaseCorpus:
    corpus = _validated_payload(payload)
    root = corpus_path.parent.resolve()
    loaded_entries: list[CaseCorpusEntry] = []
    for item in corpus["cases"]:
        artifact_path = _resolve_artifact_path(root, item["artifact"])
        try:
            execution_case = ExecutionCase.load(artifact_path)
        except OSError as exc:
            raise ValueError(
                f"case corpus artifact cannot be read: {item['artifact']}: {exc}"
            ) from exc
        artifact_digest = execution_case.as_payload()["integrity"]["digest"]
        if artifact_digest != item["caseId"]:
            raise ValueError(
                f"case corpus caseId does not match artifact: {item['reference']}"
            )
        loaded_entries.append(
            CaseCorpusEntry(
                reference=item["reference"],
                case_id=item["caseId"],
                artifact=item["artifact"],
                execution_case=execution_case,
            )
        )
    return CaseCorpus(
        name=corpus["name"],
        entries=tuple(loaded_entries),
        path=corpus_path,
        _payload=corpus,
    )


def _validated_payload(payload: object) -> CaseCorpusPayload:
    if not isinstance(payload, dict):
        raise ValueError("case corpus must be a JSON object")
    value = cast(dict[object, object], payload)
    expected = {"schemaVersion", "kind", "name", "cases", "integrity"}
    if set(value) != expected:
        raise ValueError("case corpus must contain only schemaVersion, kind, name, cases, and integrity")
    if (
        type(value["schemaVersion"]) is not int
        or value["schemaVersion"] != CASE_CORPUS_SCHEMA_VERSION
    ):
        raise ValueError(
            f"unsupported case corpus schemaVersion: {value['schemaVersion']!r}"
        )
    if value["kind"] != "gwt.case-corpus":
        raise ValueError("case corpus kind must be 'gwt.case-corpus'")
    name = value["name"]
    name = _validate_display_text(
        name,
        label="case corpus name",
        maximum=MAX_CORPUS_NAME_LENGTH,
    )
    cases_value = value["cases"]
    if not isinstance(cases_value, list) or not cases_value:
        raise ValueError("case corpus cases must be a non-empty array")
    case_items = cast(list[object], cases_value)

    cases: list[CaseCorpusEntryPayload] = []
    references: set[str] = set()
    case_ids: set[str] = set()
    for index, item_value in enumerate(case_items, start=1):
        if not isinstance(item_value, dict):
            raise ValueError(f"case corpus entry {index} must be an object")
        item = cast(dict[object, object], item_value)
        if set(item) != {"reference", "caseId", "artifact"}:
            raise ValueError(
                f"case corpus entry {index} must contain only reference, caseId, and artifact"
            )
        reference = item["reference"]
        case_id = item["caseId"]
        artifact = item["artifact"]
        try:
            reference = validate_case_reference(reference)
        except ValueError as exc:
            raise ValueError(f"case corpus entry {index}: {exc}") from exc
        if reference in references:
            raise ValueError(f"duplicate case corpus reference: {reference}")
        references.add(reference)
        if not isinstance(case_id, str) or _SHA256_PATTERN.fullmatch(case_id) is None:
            raise ValueError(f"case corpus entry {index} caseId must be a sha256 digest")
        if case_id in case_ids:
            raise ValueError(f"duplicate case corpus caseId: {case_id}")
        case_ids.add(case_id)
        if not isinstance(artifact, str):
            raise ValueError(f"case corpus entry {index} artifact must be text")
        _validate_artifact_path(artifact, index=index)
        cases.append(
            {"reference": reference, "caseId": case_id, "artifact": artifact}
        )

    integrity_value = value["integrity"]
    if not isinstance(integrity_value, dict):
        raise ValueError("case corpus integrity must be an object")
    integrity = cast(dict[object, object], integrity_value)
    if set(integrity) != {"algorithm", "scope", "digest"}:
        raise ValueError("case corpus integrity must contain algorithm, scope, and digest")
    if integrity["algorithm"] != CASE_CORPUS_INTEGRITY_ALGORITHM:
        raise ValueError("unsupported case corpus integrity algorithm")
    if integrity["scope"] != CASE_CORPUS_INTEGRITY_SCOPE:
        raise ValueError("unsupported case corpus integrity scope")
    digest = integrity["digest"]
    if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError("case corpus integrity digest must be a sha256 digest")
    expected_digest = case_corpus_digest(value)
    if digest != expected_digest:
        raise ValueError("case corpus integrity digest mismatch")

    normalized: CaseCorpusPayload = {
        "schemaVersion": CASE_CORPUS_SCHEMA_VERSION,
        "kind": "gwt.case-corpus",
        "name": name,
        "cases": cases,
        "integrity": {
            "algorithm": CASE_CORPUS_INTEGRITY_ALGORITHM,
            "scope": CASE_CORPUS_INTEGRITY_SCOPE,
            "digest": digest,
        },
    }
    return deepcopy(normalized)


def _validate_artifact_path(artifact: str, *, index: int) -> None:
    if (
        not artifact
        or "\\" in artifact
        or _UNSAFE_DISPLAY_CHARACTER.search(artifact) is not None
    ):
        raise ValueError(
            f"case corpus entry {index} artifact must be a normalized relative POSIX path"
        )
    path = PurePosixPath(artifact)
    if (
        path.is_absolute()
        or str(path) != artifact
        or path == PurePosixPath(".")
        or ".." in path.parts
    ):
        raise ValueError(
            f"case corpus entry {index} artifact must be a normalized relative POSIX path"
        )


def _validate_display_text(value: object, *, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    if value != value.strip():
        raise ValueError(f"{label} must not have leading or trailing whitespace")
    if len(value) > maximum:
        raise ValueError(f"{label} exceeds {maximum} characters")
    if _UNSAFE_DISPLAY_CHARACTER.search(value) is not None:
        raise ValueError(f"{label} contains unsafe control or formatting characters")
    return value


def _reject_duplicate_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"case corpus JSON contains duplicate object key: {key}")
        value[key] = item
    return value


def _resolve_artifact_path(root: Path, artifact: str) -> Path:
    relative = PurePosixPath(artifact)
    candidate = root
    for part in relative.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError(
                f"case corpus artifacts must not use symbolic links: {artifact}"
            )
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"case corpus artifact resolves outside corpus directory: {artifact}")
    if not resolved.is_file():
        raise ValueError(f"case corpus artifact does not exist: {artifact}")
    return resolved


def _integrity_payload(payload: object) -> CaseCorpusIntegrityPayload:
    return {
        "algorithm": CASE_CORPUS_INTEGRITY_ALGORITHM,
        "scope": CASE_CORPUS_INTEGRITY_SCOPE,
        "digest": case_corpus_digest(payload),
    }
