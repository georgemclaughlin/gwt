from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from .checker import Diagnostic, check_program
from .runtime import (
    GwtError,
    ImportPolicy,
    Program,
    RunResult,
    Runtime,
    ScenarioResult,
    parse_program,
    run_json_request,
    run_request,
    run_source,
)
from .service import Analysis, analyze_file, analyze_source
from .typegen import TypeScriptTypesResult, generate_typescript_file, generate_typescript_text


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


@dataclass(frozen=True)
class CompiledProgram:
    """Checked, reusable GWT program for embedded host applications."""

    source: str
    file: str
    program: Program
    diagnostics: list[Diagnostic]
    source_hash: str

    @property
    def ok(self) -> bool:
        return not any(diagnostic.severity == "error" for diagnostic in self.diagnostics)

    def as_payload(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "file": self.file,
            "source_hash": self.source_hash,
            "diagnostics": [
                diagnostic.as_payload(self.file) for diagnostic in self.diagnostics
            ],
        }

    def run_json(
        self,
        json_state: dict[str, Any],
        *,
        entry: str,
        json_file: str | Path | None = None,
    ) -> ExecutionResult:
        if not self.ok:
            errors = [
                diagnostic
                for diagnostic in self.diagnostics
                if diagnostic.severity == "error"
            ]
            diagnostic = errors[0]
            raise GwtError(diagnostic.as_error_message(self.file))
        return ExecutionResult(
            Runtime(self.program).run_json(json_state, entry),
            self.file,
            str(json_file) if json_file is not None else None,
        )


@dataclass(frozen=True)
class GwtClient:
    """Reference host-language client for one GWT program file."""

    path: str | Path

    def check(self) -> CheckResult:
        return check_file(self.path)

    def run(self, *, request_file: str | Path | None = None) -> ExecutionResult:
        return run_file(self.path, request_file=request_file)

    def run_json(
        self,
        json_state: dict[str, Any],
        *,
        entry: str,
        json_file: str | Path | None = None,
    ) -> ExecutionResult:
        return run_json_file(self.path, json_state, entry=entry, json_file=json_file)

    def compile(
        self,
        *,
        import_roots: Iterable[str | Path] | None = None,
        allow_absolute_imports: bool = True,
    ) -> CompiledProgram:
        return compile_file(
            self.path,
            import_roots=import_roots,
            allow_absolute_imports=allow_absolute_imports,
        )

    def typescript_types(self) -> TypeScriptTypesResult:
        return generate_typescript_file(self.path)


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


def check_file(
    path: str | Path,
    *,
    import_roots: Iterable[str | Path] | None = None,
    allow_absolute_imports: bool = True,
) -> CheckResult:
    return CheckResult(
        analyze_file(
            path,
            import_policy=_import_policy(import_roots, allow_absolute_imports),
        )
    )


def check_text(
    source: str,
    filename: str = "<source>",
    *,
    import_roots: Iterable[str | Path] | None = None,
    allow_absolute_imports: bool = True,
) -> CheckResult:
    return CheckResult(
        analyze_source(
            source,
            filename,
            import_policy=_import_policy(import_roots, allow_absolute_imports),
        )
    )


def compile_file(
    path: str | Path,
    *,
    import_roots: Iterable[str | Path] | None = None,
    allow_absolute_imports: bool = True,
) -> CompiledProgram:
    file_path = Path(path)
    return compile_text(
        file_path.read_text(),
        filename=str(file_path),
        import_roots=import_roots,
        allow_absolute_imports=allow_absolute_imports,
    )


def compile_text(
    source: str,
    filename: str = "<source>",
    *,
    import_roots: Iterable[str | Path] | None = None,
    allow_absolute_imports: bool = True,
) -> CompiledProgram:
    import_policy = _import_policy(import_roots, allow_absolute_imports)
    program = parse_program(source, filename=filename, import_policy=import_policy)
    diagnostics = check_program(program)
    errors = [diagnostic for diagnostic in diagnostics if diagnostic.severity == "error"]
    if errors:
        raise GwtError(errors[0].as_error_message(filename))
    return CompiledProgram(
        source,
        filename,
        program,
        diagnostics,
        _source_hash(source),
    )


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


def run_json_file(
    path: str | Path,
    json_state: dict[str, Any],
    *,
    entry: str,
    json_file: str | Path | None = None,
) -> ExecutionResult:
    program_path = Path(path)
    result = run_json_request(
        program_path.read_text(),
        json_state,
        entry=entry,
        filename=str(program_path),
    )
    return ExecutionResult(
        result,
        str(program_path),
        str(json_file) if json_file is not None else None,
    )


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


def run_json_text(
    source: str,
    json_state: dict[str, Any],
    *,
    entry: str,
    filename: str = "<source>",
    entry_filename: str = "<entry>",
) -> ExecutionResult:
    return ExecutionResult(
        run_json_request(source, json_state, entry=entry, filename=filename, entry_filename=entry_filename),
        filename,
    )


def _import_policy(
    import_roots: Iterable[str | Path] | None,
    allow_absolute_imports: bool,
) -> ImportPolicy | None:
    if import_roots is None and allow_absolute_imports:
        return None
    roots = tuple(Path(root).resolve() for root in import_roots or ())
    return ImportPolicy(roots, allow_absolute_imports)


def _source_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()
