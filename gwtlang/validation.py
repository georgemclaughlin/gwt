from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NotRequired, TypedDict

from .checker import Diagnostic
from .formatter import format_text
from .inspection import SCHEMA_VERSION
from .payloads import ValidationPayload, ValidationPhasePayload
from .runtime import GwtError, ImportPolicy, Program, Scenario, run_source
from .service import Analysis, analyze_file, diagnostic_from_error


class _InternalPhasePayload(ValidationPhasePayload, total=False):
    _diagnostics: NotRequired[list[Diagnostic]]


@dataclass(frozen=True)
class ValidationResult:
    analysis: Analysis
    diagnostics: list[Diagnostic]
    phases: dict[str, ValidationPhasePayload]

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)

    def as_payload(self) -> ValidationPayload:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "ok": self.ok,
            "file": self.analysis.filename,
            "program": self.analysis.program.name if self.analysis.program is not None else None,
            "phases": self.phases,
            "diagnostics": [
                diagnostic.as_payload(self.analysis.filename)
                for diagnostic in self.diagnostics
            ],
        }


def validate_file(
    path: str | Path,
    *,
    import_policy: ImportPolicy | None = None,
    check_format: bool = True,
    run_tests: bool = True,
) -> ValidationResult:
    file_path = Path(path)
    source = file_path.read_text()
    filename = str(file_path)
    analysis = analyze_file(file_path, import_policy=import_policy)
    diagnostics = list(analysis.diagnostics)
    phases: dict[str, ValidationPhasePayload] = {
        "check": _check_phase(analysis),
    }

    if check_format and analysis.program is not None:
        format_phase = _format_phase(source, filename)
        phases["format"] = format_phase
        diagnostics.extend(format_phase.pop("_diagnostics", []))
    elif check_format:
        phases["format"] = {"checked": False, "ok": False, "skipped": "check failed"}
    else:
        phases["format"] = {"checked": False, "ok": True, "skipped": "disabled"}

    check_failed = any(
        diagnostic.severity == "error" for diagnostic in analysis.diagnostics
    )
    if run_tests and not check_failed and analysis.program is not None:
        if not _has_executable_scenarios(analysis.program):
            phases["test"] = {
                "checked": False,
                "ok": True,
                "skipped": "no executable scenarios",
            }
            return ValidationResult(analysis, diagnostics, phases)

        test_phase = _test_phase(source, filename, import_policy)
        phases["test"] = test_phase
        diagnostics.extend(test_phase.pop("_diagnostics", []))
    elif run_tests:
        phases["test"] = {"checked": False, "ok": False, "skipped": "check failed"}
    else:
        phases["test"] = {"checked": False, "ok": True, "skipped": "disabled"}

    return ValidationResult(analysis, diagnostics, phases)


def _has_executable_scenarios(program: Program) -> bool:
    if _scenario_has_steps(program.background):
        return True
    return any(
        scenario.line > 0 or _scenario_has_steps(scenario)
        for scenario in program.scenarios
    )


def _scenario_has_steps(scenario: Scenario) -> bool:
    return bool(scenario.givens or scenario.whens or scenario.thens or scenario.examples)


def _check_phase(analysis: Analysis) -> ValidationPhasePayload:
    errors = [
        diagnostic
        for diagnostic in analysis.diagnostics
        if diagnostic.severity == "error"
    ]
    return {
        "checked": True,
        "ok": not errors,
        "diagnostics": [
            diagnostic.as_payload(analysis.filename)
            for diagnostic in analysis.diagnostics
        ],
    }


def _format_phase(source: str, filename: str) -> _InternalPhasePayload:
    try:
        formatted = format_text(source, filename=filename)
    except GwtError as exc:
        diagnostic = diagnostic_from_error(
            str(exc),
            source,
            filename,
            code="GWT900",
            category="parse",
        )
        return {
            "checked": True,
            "ok": False,
            "changed": None,
            "diagnostics": [diagnostic.as_payload(filename)],
            "_diagnostics": [diagnostic],
        }

    changed = formatted != source
    diagnostics: list[Diagnostic] = []
    if changed:
        diagnostics.append(
            Diagnostic(
                filename,
                1,
                "file is not formatted",
                "GWT901",
                "error",
                1,
                1,
                "format",
                help=f"run `gwt format {filename}`",
            )
        )

    return {
        "checked": True,
        "ok": not changed,
        "changed": changed,
        "diagnostics": [
            diagnostic.as_payload(filename) for diagnostic in diagnostics
        ],
        "_diagnostics": diagnostics,
    }


def _test_phase(
    source: str,
    filename: str,
    import_policy: ImportPolicy | None,
) -> _InternalPhasePayload:
    try:
        result = run_source(source, filename=filename, import_policy=import_policy)
    except GwtError as exc:
        diagnostic = diagnostic_from_error(
            str(exc),
            source,
            filename,
            code="GWT800",
            category="runtime",
        )
        return {
            "checked": True,
            "ok": False,
            "diagnostics": [diagnostic.as_payload(filename)],
            "_diagnostics": [diagnostic],
        }

    return {
        "checked": True,
        "ok": True,
        "scenario_count": len(result.scenarios),
        "diagnostics": [],
    }
