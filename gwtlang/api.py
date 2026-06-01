from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .checker import Diagnostic
from .runtime import RunResult, ScenarioResult, run_request, run_source
from .service import Analysis, analyze_file, analyze_source


@dataclass(frozen=True)
class CheckResult:
    analysis: Analysis

    @property
    def file(self) -> str:
        return self.analysis.filename

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.analysis.diagnostics)

    @property
    def diagnostics(self) -> list[Diagnostic]:
        return self.analysis.diagnostics

    def as_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            **self.analysis.as_payload(),
        }


@dataclass(frozen=True)
class ExecutionResult:
    result: RunResult
    file: str
    request_file: str | None = None

    @property
    def scenarios(self) -> list[ScenarioResult]:
        return self.result.scenarios

    @property
    def state(self) -> dict[str, Any]:
        return self.result.state

    @property
    def output(self) -> list[str]:
        return self.result.output

    def as_payload(self) -> dict[str, object]:
        return run_result_payload(self.result, file=self.file, request_file=self.request_file)


def run_result_payload(
    result: RunResult,
    *,
    file: str | None = None,
    request_file: str | None = None,
) -> dict[str, object]:
    scenarios = [_scenario_payload(scenario) for scenario in result.scenarios]
    payload: dict[str, object] = {
        "ok": True,
        "file": file,
        "request_file": request_file,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "state": None,
        "result": None,
        "output": None,
    }
    if len(scenarios) == 1:
        payload["state"] = scenarios[0]["state"]
        payload["result"] = scenarios[0]["result"]
        payload["output"] = scenarios[0]["output"]
    return payload


def _scenario_payload(scenario: ScenarioResult) -> dict[str, object]:
    result = scenario.returned_state if scenario.returned_state is not None else scenario.state
    return {
        "name": scenario.name,
        "state": scenario.state,
        "result": result,
        "output": scenario.output,
    }


def check_file(path: str | Path) -> CheckResult:
    return CheckResult(analyze_file(path))


def check_text(source: str, filename: str = "<source>") -> CheckResult:
    return CheckResult(analyze_source(source, filename))


def run_file(path: str | Path, *, request_file: str | Path | None = None) -> ExecutionResult:
    program_path = Path(path)
    source = program_path.read_text()
    if request_file is None:
        return ExecutionResult(run_source(source, filename=str(program_path)), str(program_path))

    request_path = Path(request_file)
    result = run_request(
        source,
        request_path.read_text(),
        filename=str(program_path),
        request_filename=str(request_path),
    )
    return ExecutionResult(result, str(program_path), str(request_path))


def run_text(
    source: str,
    *,
    request_source: str | None = None,
    filename: str = "<source>",
    request_filename: str = "<request>",
) -> ExecutionResult:
    if request_source is None:
        return ExecutionResult(run_source(source, filename=filename), filename)
    return ExecutionResult(
        run_request(source, request_source, filename=filename, request_filename=request_filename),
        filename,
        request_filename,
    )
