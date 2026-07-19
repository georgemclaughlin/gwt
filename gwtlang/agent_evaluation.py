"""Provider-neutral preparation and scoring for agent-authored GWT programs.

The evaluator never calls a model provider. ``prepare`` emits JSONL tasks that
can be sent through any model harness; ``score`` consumes provider-independent
attempt records and verifies them with the ordinary GWT parser, checker,
formatter, runtime, and hidden request probes.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from statistics import median
from typing import Any, Literal, Mapping, Sequence, cast

from .checker import Diagnostic
from .formatter import format_text
from .inspection import inspect_source
from .runtime import GwtError, run_json_request, run_source
from .service import Analysis, analyze_source


EVALUATION_SCHEMA_VERSION = 1
CONTEXT_VARIANTS = ("source-only", "inspect", "guide")
AttemptAction = Literal["code", "clarify"]


@dataclass(frozen=True)
class AttemptAssessment:
    case_id: str
    attempt: int
    action: AttemptAction
    parse_ok: bool
    check_ok: bool
    format_ok: bool
    scenarios_ok: bool
    semantic_ok: bool
    clarification_ok: bool
    diagnostic_codes: tuple[str, ...]
    diagnostic_subcodes: tuple[str, ...]

    @property
    def validation_ok(self) -> bool:
        return self.check_ok and self.format_ok and self.scenarios_ok

    def as_payload(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "action": self.action,
            "parseOk": self.parse_ok,
            "checkOk": self.check_ok,
            "formatOk": self.format_ok,
            "scenariosOk": self.scenarios_ok,
            "validationOk": self.validation_ok,
            "semanticOk": self.semantic_ok,
            "clarificationOk": self.clarification_ok,
            "diagnosticCodes": list(self.diagnostic_codes),
            "diagnosticSubcodes": list(self.diagnostic_subcodes),
        }


def prepare_evaluation(
    manifest_path: str | Path,
    *,
    variant: str,
    guide_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Build provider-neutral task records without exposing hidden probes."""

    if variant not in CONTEXT_VARIANTS:
        raise ValueError(
            f"unknown context variant: {variant}; expected one of {', '.join(CONTEXT_VARIANTS)}"
        )
    manifest_file = Path(manifest_path)
    manifest = _load_manifest(manifest_file)
    root = manifest_file.parent
    guide = ""
    if variant == "guide":
        selected_guide = (
            Path(guide_path)
            if guide_path is not None
            else Path(__file__).resolve().parent.parent / "docs" / "agent-authoring.md"
        )
        guide = selected_guide.read_text()

    prepared: list[dict[str, Any]] = []
    for case in _manifest_cases(manifest):
        source = _context_source(case, root)
        context: dict[str, Any] = {"source": source}
        if variant in {"inspect", "guide"} and source:
            context["inspection"] = inspect_source(
                source,
                filename=f"<agent-eval:{case['id']}>",
            ).as_payload()
        if variant == "guide":
            context["guide"] = guide
        prepared.append(
            {
                "schemaVersion": EVALUATION_SCHEMA_VERSION,
                "caseId": case["id"],
                "kind": case["kind"],
                "task": case["task"],
                "contextVariant": variant,
                "context": context,
                "responseContract": {
                    "attempt": "positive integer",
                    "action": "code or clarify",
                    "source": "required when action is code",
                    "clarifications": "required when action is clarify",
                },
            }
        )
    return prepared


def score_evaluation(
    manifest_path: str | Path,
    attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Score ordered model attempts against ordinary gates and hidden probes."""

    manifest_file = Path(manifest_path)
    manifest = _load_manifest(manifest_file)
    cases = {str(case["id"]): case for case in _manifest_cases(manifest)}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for raw_attempt in attempts:
        case_id = _required_string(raw_attempt, "caseId", "attempt")
        if case_id not in cases:
            raise ValueError(f"attempt refers to unknown case: {case_id}")
        grouped[case_id].append(raw_attempt)

    details: list[dict[str, Any]] = []
    first_parse: list[bool] = []
    first_check: list[bool] = []
    final_validation: list[bool] = []
    semantic_results: list[bool] = []
    clarification_results: list[bool] = []
    repair_iterations: list[int] = []

    for case_id, case in cases.items():
        ordered = sorted(
            grouped.get(case_id, []),
            key=lambda value: _required_positive_integer(value, "attempt", f"attempt for {case_id}"),
        )
        attempt_numbers = [
            _required_positive_integer(value, "attempt", f"attempt for {case_id}")
            for value in ordered
        ]
        if attempt_numbers != list(range(1, len(attempt_numbers) + 1)):
            raise ValueError(f"attempt numbers for {case_id} must be contiguous from 1")
        assessments = [_assess_attempt(case, value) for value in ordered]
        first = assessments[0] if assessments else None
        final = assessments[-1] if assessments else None

        expects_clarification = case["kind"] == "clarify"
        if expects_clarification:
            clarification_ok = bool(final and final.clarification_ok)
            clarification_results.append(clarification_ok)
            case_validation = clarification_ok
            case_semantic = clarification_ok
        else:
            first_parse.append(bool(first and first.parse_ok))
            first_check.append(bool(first and first.check_ok))
            case_validation = bool(final and final.validation_ok)
            case_semantic = bool(final and final.semantic_ok)
            final_validation.append(case_validation)
            semantic_results.append(case_semantic)
            if final is not None and case_validation and case_semantic:
                repair_iterations.append(max(0, final.attempt - 1))

        details.append(
            {
                "caseId": case_id,
                "kind": case["kind"],
                "attemptCount": len(assessments),
                "finalValidationOk": case_validation,
                "finalSemanticOk": case_semantic,
                "attempts": [assessment.as_payload() for assessment in assessments],
            }
        )

    return {
        "schemaVersion": EVALUATION_SCHEMA_VERSION,
        "caseCount": len(cases),
        "attemptedCaseCount": sum(bool(grouped.get(case_id)) for case_id in cases),
        "metrics": {
            "firstPassParseRate": _rate(first_parse),
            "firstPassCheckRate": _rate(first_check),
            "finalValidationRate": _rate(final_validation),
            "scenarioSemanticSuccessRate": _rate(semantic_results),
            "correctClarificationRate": _rate(clarification_results),
            "medianRepairIterations": (
                float(median(repair_iterations)) if repair_iterations else None
            ),
        },
        "cases": details,
    }


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not raw_line.strip():
            continue
        value = json.loads(raw_line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: JSONL record must be an object")
        records.append(cast(dict[str, Any], value))
    return records


def write_jsonl(records: Sequence[Mapping[str, Any]], path: str | Path) -> None:
    rendered = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    Path(path).write_text(rendered)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare or score provider-neutral GWT agent evaluations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Write model-neutral task JSONL.")
    prepare_parser.add_argument("manifest")
    prepare_parser.add_argument("--variant", choices=CONTEXT_VARIANTS, required=True)
    prepare_parser.add_argument("--guide")
    prepare_parser.add_argument("--output", required=True)

    score_parser = subparsers.add_parser("score", help="Score provider-neutral attempt JSONL.")
    score_parser.add_argument("manifest")
    score_parser.add_argument("responses")
    score_parser.add_argument("--output")

    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "prepare":
        records = prepare_evaluation(args.manifest, variant=args.variant, guide_path=args.guide)
        write_jsonl(records, args.output)
        return 0

    payload = score_evaluation(args.manifest, read_jsonl(args.responses))
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered)
    else:
        print(rendered, end="")
    return 0


def _assess_attempt(case: Mapping[str, Any], attempt: Mapping[str, Any]) -> AttemptAssessment:
    case_id = str(case["id"])
    attempt_number = _required_positive_integer(attempt, "attempt", f"attempt for {case_id}")
    action = _required_string(attempt, "action", f"attempt for {case_id}")
    if action not in {"code", "clarify"}:
        raise ValueError(f"attempt for {case_id} has invalid action: {action}")

    if action == "clarify":
        raw_questions = attempt.get("clarifications", [])
        questions = (
            [str(value) for value in cast(list[Any], raw_questions)]
            if isinstance(raw_questions, list)
            else []
        )
        clarification_ok = _clarification_matches(case, questions)
        return AttemptAssessment(
            case_id,
            attempt_number,
            "clarify",
            False,
            False,
            False,
            False,
            False,
            clarification_ok,
            (),
            (),
        )

    source = _required_string(attempt, "source", f"code attempt for {case_id}")
    analysis = analyze_source(source, filename=f"<agent-response:{case_id}>", lint=True)
    errors = _errors(analysis)
    parse_ok = analysis.program is not None
    check_ok = parse_ok and not errors
    format_ok = False
    scenarios_ok = False
    semantic_ok = False
    if check_ok:
        try:
            format_ok = format_text(source, filename=f"<agent-response:{case_id}>") == source
            result = run_source(source, filename=f"<agent-response:{case_id}>")
            raw_minimum = case.get("minimumScenarioCount", 0)
            minimum_scenarios = (
                raw_minimum
                if isinstance(raw_minimum, int) and not isinstance(raw_minimum, bool)
                else 0
            )
            scenarios_ok = len(result.scenarios) >= minimum_scenarios
            semantic_ok = scenarios_ok and _probes_pass(case, source)
        except GwtError:
            pass

    return AttemptAssessment(
        case_id,
        attempt_number,
        "code",
        parse_ok,
        check_ok,
        format_ok,
        scenarios_ok,
        semantic_ok,
        False,
        tuple(diagnostic.code for diagnostic in errors),
        tuple(
            diagnostic.subcode
            for diagnostic in errors
            if diagnostic.subcode is not None
        ),
    )


def _probes_pass(case: Mapping[str, Any], source: str) -> bool:
    raw_probes = case.get("probes", [])
    if not isinstance(raw_probes, list):
        raise ValueError(f"case {case['id']} probes must be a list")
    for index, raw_probe in enumerate(cast(list[Any], raw_probes), start=1):
        if not isinstance(raw_probe, dict):
            raise ValueError(f"case {case['id']} probe {index} must be an object")
        probe = cast(Mapping[str, Any], raw_probe)
        request = _required_string(probe, "request", f"case {case['id']} probe {index}")
        input_value = probe.get("input")
        expected = probe.get("expectedResult")
        if not isinstance(input_value, dict) or not isinstance(expected, dict):
            raise ValueError(f"case {case['id']} probe {index} input/result must be objects")
        try:
            result = run_json_request(
                source,
                cast(dict[str, Any], input_value),
                request=request,
                filename=f"<agent-probe:{case['id']}>",
            )
        except GwtError:
            return False
        actual = result.scenarios[0].returned_state or {}
        if actual != cast(dict[str, Any], expected):
            return False
    return True


def _clarification_matches(case: Mapping[str, Any], questions: Sequence[str]) -> bool:
    if case.get("kind") != "clarify" or not questions:
        return False
    concepts = case.get("requiredConcepts", [])
    if not isinstance(concepts, list):
        return False
    combined = " ".join(questions).lower()
    for raw_options in cast(list[Any], concepts):
        options = cast(list[Any], raw_options) if isinstance(raw_options, list) else [raw_options]
        if not any(str(option).lower() in combined for option in options):
            return False
    return True


def _context_source(case: Mapping[str, Any], root: Path) -> str:
    key = "starterSource" if case.get("kind") == "author" else "brokenSource"
    raw_path = case.get(key)
    if raw_path is None:
        return ""
    if not isinstance(raw_path, str):
        raise ValueError(f"case {case['id']} {key} must be a path")
    return (root / raw_path).read_text()


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("agent evaluation manifest must be an object")
    manifest = cast(dict[str, Any], value)
    if manifest.get("schemaVersion") != EVALUATION_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported agent evaluation schemaVersion: {manifest.get('schemaVersion')}"
        )
    _manifest_cases(manifest)
    return manifest


def _manifest_cases(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("agent evaluation manifest cases must be a list")
    cases: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for index, raw_case in enumerate(cast(list[Any], raw_cases), start=1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"agent evaluation case {index} must be an object")
        case = cast(Mapping[str, Any], raw_case)
        case_id = _required_string(case, "id", f"case {index}")
        _required_string(case, "task", f"case {case_id}")
        kind = _required_string(case, "kind", f"case {case_id}")
        if kind not in {"author", "repair", "clarify"}:
            raise ValueError(f"case {case_id} has invalid kind: {kind}")
        if case_id in seen:
            raise ValueError(f"duplicate agent evaluation case: {case_id}")
        seen.add(case_id)
        cases.append(case)
    return cases


def _errors(analysis: Analysis) -> list[Diagnostic]:
    return [
        diagnostic
        for diagnostic in analysis.diagnostics
        if diagnostic.severity == "error"
    ]


def _rate(values: Sequence[bool]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _required_string(value: Mapping[str, Any], key: str, label: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{label} requires non-empty {key}")
    return raw


def _required_positive_integer(value: Mapping[str, Any], key: str, label: str) -> int:
    raw = value.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw <= 0:
        raise ValueError(f"{label} requires positive integer {key}")
    return raw


if __name__ == "__main__":
    raise SystemExit(main())
