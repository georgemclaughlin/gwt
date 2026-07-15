"""Deterministic old/new comparison over captured GWT Execution Cases."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Literal, NotRequired, TypedDict, cast

from .case_corpus import validate_case_reference
from .execution_case import (
    ExecutionCase,
    ExecutionCaseCapturePolicy,
    capture_execution_case,
)
from .payloads import ExecutionCaseOperandsPayload, JsonObject, JsonValue
from .program_identity import LoadedProgramSnapshot, load_program_snapshot
from .runtime import GwtError, ImportPolicy


COMPARISON_SCHEMA_VERSION = 1

ComparisonClassification = Literal[
    "unavailable",
    "baseline_mismatch",
    "unchanged",
    "path_changed",
    "output_changed",
    "new_failure",
    "resolved_failure",
    "failure_changed",
    "incompatible",
]


class ComparedValuePayload(TypedDict):
    present: bool
    value: NotRequired[JsonValue]


class OutputDifferencePayload(TypedDict):
    path: str
    old: ComparedValuePayload
    new: ComparedValuePayload
    oldLastChangeSource: ComparisonSourcePayload | None
    newLastChangeSource: ComparisonSourcePayload | None


class ComparisonSourcePayload(TypedDict):
    file: str
    line: int
    column: int
    text: str


class ComparisonErrorSourcePayload(TypedDict):
    file: str
    line: int
    column: int


class ComparisonErrorPayload(TypedDict):
    kind: Literal["GwtError"]
    message: str
    source: ComparisonErrorSourcePayload | None


class ComparisonSelectedDecisionPayload(TypedDict):
    condition: str
    result: bool
    source: ComparisonSourcePayload | None


class ComparisonEvaluatedConditionPayload(TypedDict):
    expression: str
    result: bool
    operands: ExecutionCaseOperandsPayload
    source: ComparisonSourcePayload | None


class CaseComparisonPayload(TypedDict):
    id: str
    reference: NotRequired[str]
    executionCaseId: NotRequired[str]
    index: int
    request: str
    classification: ComparisonClassification
    recordedProgramHash: str
    detail: str | None
    outputDifferences: list[OutputDifferencePayload]
    capturedSelectedDecision: ComparisonSelectedDecisionPayload | None
    oldSelectedDecision: ComparisonSelectedDecisionPayload | None
    newSelectedDecision: ComparisonSelectedDecisionPayload | None
    capturedEvaluatedConditions: list[ComparisonEvaluatedConditionPayload]
    oldEvaluatedConditions: list[ComparisonEvaluatedConditionPayload]
    newEvaluatedConditions: list[ComparisonEvaluatedConditionPayload]
    capturedEvidenceDigest: str
    oldEvidenceDigest: str | None
    newEvidenceDigest: str | None
    oldError: ComparisonErrorPayload | None
    newError: ComparisonErrorPayload | None


class ComparisonProgramPayload(TypedDict):
    hash: str
    entry: str


class ComparisonTotalsPayload(TypedDict):
    cases: int
    unavailable: int
    baselineMismatch: int
    unchanged: int
    pathChanged: int
    outputChanged: int
    newFailure: int
    resolvedFailure: int
    failureChanged: int
    incompatible: int


class ComparisonPayload(TypedDict):
    schemaVersion: int
    kind: Literal["gwt.comparison"]
    oldProgram: ComparisonProgramPayload
    newProgram: ComparisonProgramPayload
    totals: ComparisonTotalsPayload
    cases: list[CaseComparisonPayload]


@dataclass(frozen=True)
class ComparedValue:
    """An immutable, exact JSON value with explicit missing-value state."""

    present: bool
    _encoded: str | None = None

    @classmethod
    def missing(cls) -> ComparedValue:
        return cls(False)

    @classmethod
    def of(cls, value: JsonValue) -> ComparedValue:
        return cls(True, _canonical_json(value))

    @property
    def value(self) -> JsonValue | None:
        if self._encoded is None:
            return None
        return cast(JsonValue, json.loads(self._encoded))

    def as_payload(self) -> ComparedValuePayload:
        payload: ComparedValuePayload = {"present": self.present}
        if self.present:
            payload["value"] = self.value
        return payload


@dataclass(frozen=True)
class OutputDifference:
    path: str
    old: ComparedValue
    new: ComparedValue
    old_last_change_source: ComparisonSource | None = None
    new_last_change_source: ComparisonSource | None = None

    def as_payload(self) -> OutputDifferencePayload:
        return {
            "path": self.path,
            "old": self.old.as_payload(),
            "new": self.new.as_payload(),
            "oldLastChangeSource": (
                self.old_last_change_source.as_payload()
                if self.old_last_change_source is not None
                else None
            ),
            "newLastChangeSource": (
                self.new_last_change_source.as_payload()
                if self.new_last_change_source is not None
                else None
            ),
        }


@dataclass(frozen=True)
class ComparisonSource:
    file: str
    line: int
    column: int
    text: str

    def as_payload(self) -> ComparisonSourcePayload:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "text": self.text,
        }


@dataclass(frozen=True)
class ComparisonErrorSource:
    file: str
    line: int
    column: int

    def as_payload(self) -> ComparisonErrorSourcePayload:
        return {"file": self.file, "line": self.line, "column": self.column}


@dataclass(frozen=True)
class ComparisonError:
    kind: Literal["GwtError"]
    message: str
    source: ComparisonErrorSource | None

    def as_payload(self) -> ComparisonErrorPayload:
        return {
            "kind": self.kind,
            "message": self.message,
            "source": self.source.as_payload() if self.source is not None else None,
        }


@dataclass(frozen=True)
class ComparisonSelectedDecision:
    condition: str
    result: bool
    source: ComparisonSource | None

    def as_payload(self) -> ComparisonSelectedDecisionPayload:
        return {
            "condition": self.condition,
            "result": self.result,
            "source": self.source.as_payload() if self.source is not None else None,
        }


@dataclass(frozen=True)
class ComparisonEvaluatedCondition:
    expression: str
    result: bool
    _operands_encoded: str
    source: ComparisonSource | None

    @property
    def operands(self) -> ExecutionCaseOperandsPayload:
        return cast(ExecutionCaseOperandsPayload, json.loads(self._operands_encoded))

    def as_payload(self) -> ComparisonEvaluatedConditionPayload:
        return {
            "expression": self.expression,
            "result": self.result,
            "operands": self.operands,
            "source": self.source.as_payload() if self.source is not None else None,
        }


@dataclass(frozen=True)
class CaseComparison:
    id: str
    index: int
    request: str
    classification: ComparisonClassification
    recorded_program_hash: str
    detail: str | None
    output_differences: tuple[OutputDifference, ...]
    captured_selected_decision: ComparisonSelectedDecision | None
    old_selected_decision: ComparisonSelectedDecision | None
    new_selected_decision: ComparisonSelectedDecision | None
    captured_evaluated_conditions: tuple[ComparisonEvaluatedCondition, ...]
    old_evaluated_conditions: tuple[ComparisonEvaluatedCondition, ...]
    new_evaluated_conditions: tuple[ComparisonEvaluatedCondition, ...]
    captured_evidence_digest: str
    old_evidence_digest: str | None
    new_evidence_digest: str | None
    old_error: ComparisonError | None
    new_error: ComparisonError | None
    reference: str | None = None
    execution_case_id: str | None = None

    def __post_init__(self) -> None:
        if (self.reference is None) != (self.execution_case_id is None):
            raise ValueError(
                "comparison reference and execution case ID must be supplied together"
            )
        if self.reference is not None:
            validate_case_reference(self.reference)
        if self.execution_case_id is not None and re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.execution_case_id
        ) is None:
            raise ValueError("comparison execution case ID must be a sha256 digest")

    def as_payload(self) -> CaseComparisonPayload:
        payload: CaseComparisonPayload = {
            "id": self.id,
            "index": self.index,
            "request": self.request,
            "classification": self.classification,
            "recordedProgramHash": self.recorded_program_hash,
            "detail": self.detail,
            "outputDifferences": [
                difference.as_payload() for difference in self.output_differences
            ],
            "capturedSelectedDecision": (
                self.captured_selected_decision.as_payload()
                if self.captured_selected_decision is not None
                else None
            ),
            "oldSelectedDecision": (
                self.old_selected_decision.as_payload()
                if self.old_selected_decision is not None
                else None
            ),
            "newSelectedDecision": (
                self.new_selected_decision.as_payload()
                if self.new_selected_decision is not None
                else None
            ),
            "capturedEvaluatedConditions": [
                condition.as_payload()
                for condition in self.captured_evaluated_conditions
            ],
            "oldEvaluatedConditions": [
                condition.as_payload() for condition in self.old_evaluated_conditions
            ],
            "newEvaluatedConditions": [
                condition.as_payload() for condition in self.new_evaluated_conditions
            ],
            "capturedEvidenceDigest": self.captured_evidence_digest,
            "oldEvidenceDigest": self.old_evidence_digest,
            "newEvidenceDigest": self.new_evidence_digest,
            "oldError": self.old_error.as_payload() if self.old_error is not None else None,
            "newError": self.new_error.as_payload() if self.new_error is not None else None,
        }
        if self.reference is not None:
            payload["reference"] = self.reference
        if self.execution_case_id is not None:
            payload["executionCaseId"] = self.execution_case_id
        return payload


@dataclass(frozen=True)
class ComparisonTotals:
    cases: int
    unavailable: int
    baseline_mismatch: int
    unchanged: int
    path_changed: int
    output_changed: int
    new_failure: int
    resolved_failure: int
    failure_changed: int
    incompatible: int

    def as_payload(self) -> ComparisonTotalsPayload:
        return {
            "cases": self.cases,
            "unavailable": self.unavailable,
            "baselineMismatch": self.baseline_mismatch,
            "unchanged": self.unchanged,
            "pathChanged": self.path_changed,
            "outputChanged": self.output_changed,
            "newFailure": self.new_failure,
            "resolvedFailure": self.resolved_failure,
            "failureChanged": self.failure_changed,
            "incompatible": self.incompatible,
        }


@dataclass(frozen=True)
class ComparisonResult:
    """Immutable, versioned comparison of one case corpus against two programs."""

    old_program_hash: str
    old_program_entry: str
    new_program_hash: str
    new_program_entry: str
    totals: ComparisonTotals
    cases: tuple[CaseComparison, ...]

    def as_payload(self) -> ComparisonPayload:
        return {
            "schemaVersion": COMPARISON_SCHEMA_VERSION,
            "kind": "gwt.comparison",
            "oldProgram": {
                "hash": self.old_program_hash,
                "entry": self.old_program_entry,
            },
            "newProgram": {
                "hash": self.new_program_hash,
                "entry": self.new_program_entry,
            },
            "totals": self.totals.as_payload(),
            "cases": [case.as_payload() for case in self.cases],
        }

    def as_text(self) -> str:
        lines = [
            f"{self.totals.cases} cases compared",
            f"old {self.old_program_hash}",
            f"new {self.new_program_hash}",
            _totals_text(self.totals),
        ]
        for case in self.cases:
            reference = f" ({case.reference})" if case.reference is not None else ""
            lines.extend(
                ("", f"{case.id}{reference} [{case.classification}] {case.request}")
            )
            if case.detail:
                lines.append(f"  {case.detail}")
            for difference in case.output_differences:
                lines.append(
                    f"  {difference.path}: "
                    f"{_display_compared_value(difference.old)} -> "
                    f"{_display_compared_value(difference.new)}"
                )
                if difference.old_last_change_source is not None:
                    source = difference.old_last_change_source
                    lines.append(
                        f"    old last change: {source.file}:{source.line}:{source.column}"
                    )
                if difference.new_last_change_source is not None:
                    source = difference.new_last_change_source
                    lines.append(
                        f"    new last change: {source.file}:{source.line}:{source.column}"
                    )
            if case.classification in {"path_changed", "output_changed"}:
                lines.extend(
                    _condition_text("old predicate", case.old_evaluated_conditions)
                )
                lines.extend(
                    _condition_text("new predicate", case.new_evaluated_conditions)
                )
            if case.classification == "path_changed":
                lines.extend(_decision_change_text(case))
            if case.old_error is not None:
                lines.append(f"  old error: {_display_error(case.old_error)}")
            if case.new_error is not None:
                lines.append(f"  new error: {_display_error(case.new_error)}")
        return "\n".join(lines) + "\n"


def _condition_text(
    label: str,
    conditions: tuple[ComparisonEvaluatedCondition, ...],
) -> list[str]:
    lines: list[str] = []
    for condition in conditions:
        location = ""
        if condition.source is not None:
            source = condition.source
            location = f" at {source.file}:{source.line}:{source.column}"
        lines.append(
            f"  {label}: {condition.expression} -> "
            f"{str(condition.result).lower()}{location}"
        )
        operands = condition.operands
        if operands["availability"] == "available":
            for operand in operands.get("values", []):
                lines.append(
                    f"    {operand['name']} = {_canonical_json(operand['value'])} "
                    f"({operand['valueType']})"
                )
        elif operands["availability"] != "redacted":
            lines.append(
                f"    operands unavailable: {operands.get('reason', 'not recorded')}"
            )
    return lines


@dataclass(frozen=True)
class _CaseContext:
    id: str
    reference: str | None
    execution_case_id: str | None
    index: int
    request: str
    recorded_program_hash: str
    captured_selected_decision: ComparisonSelectedDecision | None
    captured_evaluated_conditions: tuple[ComparisonEvaluatedCondition, ...]
    captured_evidence_digest: str


def compare_execution_cases(
    old_program_path: str | Path,
    new_program_path: str | Path,
    cases: Iterable[ExecutionCase],
    *,
    import_policy: ImportPolicy | None = None,
    case_references: Iterable[str] | None = None,
) -> ComparisonResult:
    """Compare captured inputs against old and new real GWT programs.

    The original case's dependency-closure hash must match ``old_program_path``
    before either result is attributed to a program change. Every comparable
    case is re-executed through :func:`capture_execution_case` for both sides.
    """

    old_path = Path(old_program_path)
    new_path = Path(new_program_path)
    old_snapshot = load_program_snapshot(old_path, import_policy=import_policy)
    new_snapshot = load_program_snapshot(new_path, import_policy=import_policy)
    old_identity = old_snapshot.identity
    new_identity = new_snapshot.identity
    loaded_cases = tuple(cases)
    references = tuple(case_references) if case_references is not None else None
    if references is not None:
        if len(references) != len(loaded_cases):
            raise ValueError("case references must align one-for-one with cases")
        references = tuple(validate_case_reference(reference) for reference in references)
        if len(set(references)) != len(references):
            raise ValueError("case references must be unique")

    compared = tuple(
        _compare_case(
            index,
            execution_case,
            old_path=old_path,
            new_path=new_path,
            old_snapshot=old_snapshot,
            new_snapshot=new_snapshot,
            old_hash=old_identity.digest,
            import_policy=import_policy,
            comparison_reference=(
                references[index - 1]
                if references is not None
                else None
            ),
        )
        for index, execution_case in enumerate(loaded_cases, start=1)
    )
    totals = _comparison_totals(compared)
    return ComparisonResult(
        old_program_hash=old_identity.digest,
        old_program_entry=old_identity.entry,
        new_program_hash=new_identity.digest,
        new_program_entry=new_identity.entry,
        totals=totals,
        cases=compared,
    )


def _compare_case(
    index: int,
    captured: ExecutionCase,
    *,
    old_path: Path,
    new_path: Path,
    old_snapshot: LoadedProgramSnapshot,
    new_snapshot: LoadedProgramSnapshot,
    old_hash: str,
    import_policy: ImportPolicy | None,
    comparison_reference: str | None,
) -> CaseComparison:
    captured_payload = captured.as_payload()
    request = captured.request_name
    recorded_hash = captured_payload["program"]["hash"]
    captured_root = Path(captured_payload["program"]["file"]).parent
    captured_decision = _selected_decision(captured, captured_root)
    captured_evidence = _evidence_digest(captured)
    context = _CaseContext(
        id=_case_id(index, request),
        reference=comparison_reference,
        execution_case_id=(
            captured_payload["integrity"]["digest"]
            if comparison_reference is not None
            else None
        ),
        index=index,
        request=request,
        recorded_program_hash=recorded_hash,
        captured_selected_decision=captured_decision,
        captured_evaluated_conditions=_evaluated_conditions(
            captured,
            captured_root,
        ),
        captured_evidence_digest=captured_evidence,
    )

    execution = captured_payload["execution"]
    redaction = captured_payload["redaction"]
    if redaction["mode"] != "none" or redaction["valuesIncluded"] is not True:
        return _case_comparison(
            context,
            classification="unavailable",
            detail=(
                "captured input or result values were omitted; old/new comparison "
                "was not run"
            ),
            output_differences=(),
            old_selected_decision=None,
            new_selected_decision=None,
            old_evidence_digest=None,
            new_evidence_digest=None,
            old_error=None,
            new_error=None,
        )

    execution_budget = execution["executionBudget"]
    max_call_depth = execution["maxCallDepth"]

    if recorded_hash != old_hash:
        return _case_comparison(
            context,
            classification="baseline_mismatch",
            detail="captured program hash does not match the old program",
            output_differences=(),
            old_selected_decision=None,
            new_selected_decision=None,
            old_evidence_digest=None,
            new_evidence_digest=None,
            old_error=None,
            new_error=None,
        )

    try:
        old_case = capture_execution_case(
            old_path,
            captured.input,
            request=request,
            import_policy=import_policy,
            policy=ExecutionCaseCapturePolicy(on_error="record"),
            execution_budget=execution_budget,
            max_call_depth=max_call_depth,
            _program_snapshot=old_snapshot,
        )
    except GwtError as exc:
        old_error = _normalize_error(exc, old_path)
        classification: ComparisonClassification = (
            "incompatible" if _is_incompatible_error(exc) else "baseline_mismatch"
        )
        return _case_comparison(
            context,
            classification=classification,
            detail="captured case cannot be reproduced by the old program",
            output_differences=(),
            old_selected_decision=None,
            new_selected_decision=None,
            old_evidence_digest=None,
            new_evidence_digest=None,
            old_error=old_error,
            new_error=None,
        )

    old_payload = old_case.as_payload()
    old_decision = _selected_decision(old_case, old_path.parent)
    old_conditions = _evaluated_conditions(old_case, old_path.parent)
    old_evidence = _evidence_digest(old_case)
    old_case_error = _case_error(old_case, old_path.parent)
    if old_payload["program"]["hash"] != old_hash:
        return _case_comparison(
            context,
            classification="baseline_mismatch",
            detail="old replay did not retain the loaded program identity",
            output_differences=(),
            old_selected_decision=old_decision,
            new_selected_decision=None,
            old_evidence_digest=old_evidence,
            new_evidence_digest=None,
            old_error=old_case_error,
            new_error=None,
            old_evaluated_conditions=old_conditions,
        )
    if old_case.outcome != captured.outcome:
        return _case_comparison(
            context,
            classification="baseline_mismatch",
            detail="captured execution outcome does not reproduce against the old program",
            output_differences=(),
            old_selected_decision=old_decision,
            new_selected_decision=None,
            old_evidence_digest=old_evidence,
            new_evidence_digest=None,
            old_error=old_case_error,
            new_error=None,
            old_evaluated_conditions=old_conditions,
        )
    if captured.outcome == "completed" and not _json_equal(
        captured.result,
        old_case.result,
    ):
        return _case_comparison(
            context,
            classification="baseline_mismatch",
            detail="captured result does not reproduce against the old program",
            output_differences=(),
            old_selected_decision=old_decision,
            new_selected_decision=None,
            old_evidence_digest=old_evidence,
            new_evidence_digest=None,
            old_error=None,
            new_error=None,
            old_evaluated_conditions=old_conditions,
        )
    if captured.outcome == "failed" and _failure_fingerprint(
        captured,
    ) != _failure_fingerprint(old_case):
        return _case_comparison(
            context,
            classification="baseline_mismatch",
            detail="captured failure does not reproduce against the old program",
            output_differences=(),
            old_selected_decision=old_decision,
            new_selected_decision=None,
            old_evidence_digest=old_evidence,
            new_evidence_digest=None,
            old_error=old_case_error,
            new_error=None,
            old_evaluated_conditions=old_conditions,
        )
    if captured_evidence != old_evidence:
        return _case_comparison(
            context,
            classification="baseline_mismatch",
            detail=(
                "captured material execution evidence does not reproduce "
                "against the old program"
            ),
            output_differences=(),
            old_selected_decision=old_decision,
            new_selected_decision=None,
            old_evidence_digest=old_evidence,
            new_evidence_digest=None,
            old_error=old_case_error,
            new_error=None,
            old_evaluated_conditions=old_conditions,
        )

    try:
        new_case = capture_execution_case(
            new_path,
            captured.input,
            request=request,
            import_policy=import_policy,
            policy=ExecutionCaseCapturePolicy(on_error="record"),
            execution_budget=execution_budget,
            max_call_depth=max_call_depth,
            _program_snapshot=new_snapshot,
        )
    except GwtError as exc:
        new_error = _normalize_error(exc, new_path)
        classification = "incompatible" if _is_incompatible_error(exc) else "new_failure"
        return _case_comparison(
            context,
            classification=classification,
            detail=(
                "case is incompatible with the new request contract"
                if classification == "incompatible"
                else "new program failed for a previously successful case"
            ),
            output_differences=(),
            old_selected_decision=old_decision,
            new_selected_decision=None,
            old_evidence_digest=old_evidence,
            new_evidence_digest=None,
            old_error=None,
            new_error=new_error,
            old_evaluated_conditions=old_conditions,
        )

    new_decision = _selected_decision(new_case, new_path.parent)
    new_conditions = _evaluated_conditions(new_case, new_path.parent)
    new_evidence = _evidence_digest(new_case)
    new_case_error = _case_error(new_case, new_path.parent)
    if new_case.outcome == "failed":
        if _is_incompatible_case_error(new_case):
            classification = "incompatible"
            detail = "case is incompatible with the new request contract"
        elif captured.outcome == "completed":
            classification = "new_failure"
            detail = "new program failed for a previously successful case"
        elif _failure_fingerprint(old_case) != _failure_fingerprint(new_case):
            classification = "failure_changed"
            detail = "failure changed under the new program"
        elif old_evidence != new_evidence:
            classification = "path_changed"
            detail = "failure reproduced through different material execution evidence"
        else:
            classification = "unchanged"
            detail = "baseline failure reproduced unchanged"
        return _case_comparison(
            context,
            classification=cast(ComparisonClassification, classification),
            detail=detail,
            output_differences=(),
            old_selected_decision=old_decision,
            new_selected_decision=new_decision,
            old_evidence_digest=old_evidence,
            new_evidence_digest=new_evidence,
            old_error=old_case_error,
            new_error=new_case_error,
            old_evaluated_conditions=old_conditions,
            new_evaluated_conditions=new_conditions,
        )
    if captured.outcome == "failed":
        return _case_comparison(
            context,
            classification="resolved_failure",
            detail=(
                "previously failing case completed under the new program; "
                "completion does not imply approval"
            ),
            output_differences=(),
            old_selected_decision=old_decision,
            new_selected_decision=new_decision,
            old_evidence_digest=old_evidence,
            new_evidence_digest=new_evidence,
            old_error=old_case_error,
            new_error=None,
            old_evaluated_conditions=old_conditions,
            new_evaluated_conditions=new_conditions,
        )
    differences = _output_differences(old_case.result, new_case.result)
    differences = tuple(
        OutputDifference(
            difference.path,
            difference.old,
            difference.new,
            _last_change_source(old_case, difference.path, old_path.parent),
            _last_change_source(new_case, difference.path, new_path.parent),
        )
        for difference in differences
    )
    if differences:
        classification = "output_changed"
        detail = "declared output changed"
    elif old_evidence != new_evidence:
        classification = "path_changed"
        detail = "material execution evidence changed with identical output"
    else:
        classification = "unchanged"
        detail = None

    return _case_comparison(
        context,
        classification=classification,
        detail=detail,
        output_differences=differences,
        old_selected_decision=old_decision,
        new_selected_decision=new_decision,
        old_evidence_digest=old_evidence,
        new_evidence_digest=new_evidence,
        old_error=None,
        new_error=None,
        old_evaluated_conditions=old_conditions,
        new_evaluated_conditions=new_conditions,
    )


def _case_comparison(
    context: _CaseContext,
    *,
    classification: ComparisonClassification,
    detail: str | None,
    output_differences: tuple[OutputDifference, ...],
    old_selected_decision: ComparisonSelectedDecision | None,
    new_selected_decision: ComparisonSelectedDecision | None,
    old_evidence_digest: str | None,
    new_evidence_digest: str | None,
    old_error: ComparisonError | None,
    new_error: ComparisonError | None,
    old_evaluated_conditions: tuple[ComparisonEvaluatedCondition, ...] = (),
    new_evaluated_conditions: tuple[ComparisonEvaluatedCondition, ...] = (),
) -> CaseComparison:
    return CaseComparison(
        id=context.id,
        reference=context.reference,
        execution_case_id=context.execution_case_id,
        index=context.index,
        request=context.request,
        classification=classification,
        recorded_program_hash=context.recorded_program_hash,
        detail=detail,
        output_differences=output_differences,
        captured_selected_decision=context.captured_selected_decision,
        old_selected_decision=old_selected_decision,
        new_selected_decision=new_selected_decision,
        captured_evaluated_conditions=context.captured_evaluated_conditions,
        old_evaluated_conditions=old_evaluated_conditions,
        new_evaluated_conditions=new_evaluated_conditions,
        captured_evidence_digest=context.captured_evidence_digest,
        old_evidence_digest=old_evidence_digest,
        new_evidence_digest=new_evidence_digest,
        old_error=old_error,
        new_error=new_error,
    )


def _output_differences(old: JsonObject, new: JsonObject) -> tuple[OutputDifference, ...]:
    differences: list[OutputDifference] = []
    _collect_output_differences(old, new, "", differences)
    return tuple(differences)


def _collect_output_differences(
    old: JsonValue,
    new: JsonValue,
    path: str,
    differences: list[OutputDifference],
) -> None:
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            child_path = f"{path}/{_pointer_escape(key)}"
            if key not in old:
                differences.append(
                    OutputDifference(
                        child_path,
                        ComparedValue.missing(),
                        ComparedValue.of(new[key]),
                    )
                )
            elif key not in new:
                differences.append(
                    OutputDifference(
                        child_path,
                        ComparedValue.of(old[key]),
                        ComparedValue.missing(),
                    )
                )
            else:
                _collect_output_differences(old[key], new[key], child_path, differences)
        return

    if isinstance(old, list) and isinstance(new, list):
        for index in range(max(len(old), len(new))):
            child_path = f"{path}/{index}"
            if index >= len(old):
                differences.append(
                    OutputDifference(
                        child_path,
                        ComparedValue.missing(),
                        ComparedValue.of(new[index]),
                    )
                )
            elif index >= len(new):
                differences.append(
                    OutputDifference(
                        child_path,
                        ComparedValue.of(old[index]),
                        ComparedValue.missing(),
                    )
                )
            else:
                _collect_output_differences(old[index], new[index], child_path, differences)
        return

    if not _json_equal(old, new):
        differences.append(
            OutputDifference(
                path or "/",
                ComparedValue.of(old),
                ComparedValue.of(new),
            )
        )


def _json_equal(left: JsonValue, right: JsonValue) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _json_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_equal(old, new) for old, new in zip(left, right)
        )
    return left == right


def _evidence_digest(execution_case: ExecutionCase) -> str:
    payload = execution_case.as_payload()
    evidence: list[dict[str, object]] = []
    for item in payload["evidence"]:
        evidence.append(
            {
                key: deepcopy(value)
                for key, value in item.items()
                if key not in {
                    "sequence",
                    "summary",
                    "source",
                    "startLine",
                    "endLine",
                }
            }
        )
    state_changes: list[dict[str, object]] = []
    for change in payload["stateChanges"]:
        state_changes.append(
            {
                key: deepcopy(value)
                for key, value in change.items()
                if key not in {"sequence", "source"}
            }
        )
    material = {"evidence": evidence, "stateChanges": state_changes}
    encoded = _canonical_json(cast(JsonValue, material)).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _last_change_source(
    execution_case: ExecutionCase,
    output_pointer: str,
    program_root: Path,
) -> ComparisonSource | None:
    normalized_output = "" if output_pointer == "/" else output_pointer
    for change in reversed(execution_case.as_payload()["stateChanges"]):
        source_payload = change["source"]
        if source_payload is None or not _related_pointers(
            normalized_output,
            change["pointer"],
        ):
            continue
        return ComparisonSource(
            file=_logical_file(source_payload["file"], program_root),
            line=source_payload["line"],
            column=source_payload["column"],
            text=source_payload["text"],
        )
    return None


def _evaluated_conditions(
    execution_case: ExecutionCase,
    program_root: Path,
) -> tuple[ComparisonEvaluatedCondition, ...]:
    conditions: list[ComparisonEvaluatedCondition] = []
    for item in execution_case.as_payload()["evidence"]:
        if item["kind"] != "condition":
            continue
        source_payload = item["source"]
        source = None
        if source_payload is not None:
            source = ComparisonSource(
                file=_logical_file(source_payload["file"], program_root),
                line=source_payload["line"],
                column=source_payload["column"],
                text=source_payload["text"],
            )
        operands = item.get("operands")
        expression = item.get("expression")
        result = item.get("result")
        if operands is None or not isinstance(expression, str) or not isinstance(result, bool):
            raise ValueError("validated condition evidence is incomplete")
        conditions.append(
            ComparisonEvaluatedCondition(
                expression=expression,
                result=result,
                _operands_encoded=_canonical_json(cast(JsonValue, operands)),
                source=source,
            )
        )
    return tuple(conditions)


def _related_pointers(first: str, second: str) -> bool:
    if first == second:
        return True
    if not first or not second:
        return True
    return first.startswith(f"{second}/") or second.startswith(f"{first}/")


def _selected_decision(
    execution_case: ExecutionCase,
    program_root: Path,
) -> ComparisonSelectedDecision | None:
    selected = execution_case.selected_decision
    if selected is None:
        return None
    source_payload = selected["source"]
    source = None
    if source_payload is not None:
        source = ComparisonSource(
            file=_logical_file(source_payload["file"], program_root),
            line=source_payload["line"],
            column=source_payload["column"],
            text=source_payload["text"],
        )
    return ComparisonSelectedDecision(
        condition=selected["condition"],
        result=selected["result"],
        source=source,
    )


def _normalize_error(error: GwtError, program_path: Path) -> ComparisonError:
    text = " ".join(str(error).strip().splitlines())
    match = re.fullmatch(r"(.+):(\d+)(?::(\d+))?:\s*(.*)", text)
    if match is not None:
        filename, line_text, column_text, message = match.groups()
        source = ComparisonErrorSource(
            file=_logical_file(filename, program_path.parent),
            line=int(line_text),
            column=int(column_text) if column_text is not None else 1,
        )
        return ComparisonError("GwtError", message, source)

    entry_line = re.fullmatch(r"line (\d+):\s*(.*)", text)
    if entry_line is not None:
        line_text, message = entry_line.groups()
        source = ComparisonErrorSource(
            file=_logical_file(str(program_path), program_path.parent),
            line=int(line_text),
            column=1,
        )
        return ComparisonError("GwtError", message, source)
    return ComparisonError("GwtError", text, None)


def _case_error(
    execution_case: ExecutionCase,
    program_root: Path,
) -> ComparisonError | None:
    error = execution_case.as_payload()["execution"].get("error")
    if error is None:
        return None
    source_payload = error["source"]
    source = None
    if source_payload is not None:
        source = ComparisonErrorSource(
            file=_logical_file(source_payload["file"], program_root),
            line=source_payload["line"],
            column=source_payload["column"],
        )
    return ComparisonError("GwtError", error["message"], source)


def _failure_fingerprint(execution_case: ExecutionCase) -> str | None:
    error = execution_case.as_payload()["execution"].get("error")
    if error is None:
        return None
    source = error["source"]
    normalized_source = None
    if source is not None:
        normalized_source = {
            "line": source["line"],
            "column": source["column"],
            "text": source["text"],
        }
    material = {
        "code": error["code"],
        "stage": error["stage"],
        "message": error["message"],
        "messageAvailability": error["messageAvailability"],
        "source": normalized_source,
    }
    return _canonical_json(cast(JsonValue, material))


def _is_incompatible_case_error(execution_case: ExecutionCase) -> bool:
    error = execution_case.as_payload()["execution"].get("error")
    if error is None:
        return False
    message = error["message"]
    return (
        message.startswith("unknown request:")
        or message == "request name is required for JSON input"
        or message.startswith("REQUEST contract failed for ")
    )


def _is_incompatible_error(error: GwtError) -> bool:
    message = " ".join(str(error).strip().splitlines())
    located = re.fullmatch(r".+:\d+(?::\d+)?:\s*(.*)", message)
    detail = located.group(1) if located is not None else message
    return (
        detail.startswith("unknown request:")
        or detail == "request name is required for JSON input"
        or detail.startswith("REQUEST contract failed for ")
    )


def _logical_file(filename: str, program_root: Path) -> str:
    if filename.startswith("<") and filename.endswith(">"):
        return filename
    # Execution Case v1 source links already use dependency-manifest logical
    # specifiers. Re-resolving them against the process cwd would turn a
    # portable ``./rules.gwt`` identity back into a workstation path.
    if filename.startswith("./") or filename.startswith("../"):
        return filename
    path = Path(filename)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    root = program_root
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    else:
        root = root.resolve()
    relative = Path(os.path.relpath(path, start=root)).as_posix()
    return relative if relative.startswith("../") else f"./{relative}"


def _comparison_totals(cases: tuple[CaseComparison, ...]) -> ComparisonTotals:
    counts: dict[ComparisonClassification, int] = {
        "unavailable": 0,
        "baseline_mismatch": 0,
        "unchanged": 0,
        "path_changed": 0,
        "output_changed": 0,
        "new_failure": 0,
        "resolved_failure": 0,
        "failure_changed": 0,
        "incompatible": 0,
    }
    for case in cases:
        counts[case.classification] += 1
    return ComparisonTotals(
        cases=len(cases),
        unavailable=counts["unavailable"],
        baseline_mismatch=counts["baseline_mismatch"],
        unchanged=counts["unchanged"],
        path_changed=counts["path_changed"],
        output_changed=counts["output_changed"],
        new_failure=counts["new_failure"],
        resolved_failure=counts["resolved_failure"],
        failure_changed=counts["failure_changed"],
        incompatible=counts["incompatible"],
    )


def _case_id(index: int, request: str) -> str:
    label = re.sub(r"[^a-z0-9]+", "-", request.lower()).strip("-") or "request"
    return f"case-{index:04d}-{label}"


def _canonical_json(value: JsonValue) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _totals_text(totals: ComparisonTotals) -> str:
    parts = [
        f"{count} {label}"
        for count, label in (
            (totals.unavailable, "unavailable"),
            (totals.unchanged, "unchanged"),
            (totals.path_changed, "path changed"),
            (totals.output_changed, "output changed"),
            (totals.new_failure, "new failure"),
            (totals.resolved_failure, "resolved failure"),
            (totals.failure_changed, "failure changed"),
            (totals.incompatible, "incompatible"),
            (totals.baseline_mismatch, "baseline mismatch"),
        )
        if count
    ]
    return ", ".join(parts) if parts else "no cases"


def _display_compared_value(value: ComparedValue) -> str:
    if not value.present:
        return "<missing>"
    return _canonical_json(value.value)


def _decision_change_text(case: CaseComparison) -> list[str]:
    old = case.old_selected_decision
    new = case.new_selected_decision
    if old == new:
        return ["  execution evidence changed; selected decision is unchanged"]
    return [
        f"  old decision: {_display_decision(old)}",
        f"  new decision: {_display_decision(new)}",
    ]


def _display_decision(decision: ComparisonSelectedDecision | None) -> str:
    if decision is None:
        return "<none>"
    location = ""
    if decision.source is not None:
        location = f" at {decision.source.file}:{decision.source.line}"
    return f"{decision.condition}{location}"


def _display_error(error: ComparisonError) -> str:
    if error.source is None:
        return error.message
    return f"{error.source.file}:{error.source.line}: {error.message}"
