from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import cast

from .api import (
    generate_json_schema_file,
    generate_openapi_file,
    generate_python_file,
    generate_typescript_file,
    run_file,
    run_json_file,
    run_result_payload,
)
from .checker import Diagnostic
from .case_corpus import (
    CaseCorpusEntrySpec,
    load_case_corpus,
    validate_case_reference,
    write_case_corpus,
)
from .comparison import compare_execution_cases
from .debugger import debug_lines_for_file, parse_breakpoint, run_debug_file
from .execution_case import (
    ExecutionCase,
    ExecutionCaseCapturePolicy,
    FactProvenanceInput,
    capture_execution_case,
    load_execution_case,
)
from .explain import explain_json_file
from .formatter import format_text
from .http_server import DEFAULT_MAX_REQUEST_BODY_BYTES, run_http_server
from .inspection import inspect_file
from .lsp import run_stdio_server
from .payloads import JsonObject, ValidationPayload
from .runtime import (
    DEFAULT_EXECUTION_BUDGET,
    DEFAULT_MAX_CALL_DEPTH,
    GwtError,
    ImportPolicy,
    RunResult,
    run_source,
)
from .scenario_generation import generate_scenario
from .service import analyze_file
from .validation import validate_file
from .version import version_payload
from .workbench import render_workbench_html


def main(argv: list[str] | None = None) -> int:
    argv = _normalize_argv(list(sys.argv[1:] if argv is None else argv))
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return run_command(args)
    if args.command == "test":
        return test_command(args)
    if args.command == "check":
        return check_command(args)
    if args.command == "inspect":
        return inspect_command(args)
    if args.command == "explain":
        return explain_command(args)
    if args.command == "capture":
        return capture_command(args)
    if args.command == "scenario-from-run":
        return scenario_from_run_command(args)
    if args.command == "corpus":
        return corpus_command(args)
    if args.command == "compare":
        return compare_command(args)
    if args.command == "workbench":
        return workbench_command(args)
    if args.command == "validate":
        return validate_command(args)
    if args.command == "format":
        return format_command(args)
    if args.command == "types":
        return types_command(args)
    if args.command == "schema":
        return schema_command(args)
    if args.command == "openapi":
        return openapi_command(args)
    if args.command == "serve":
        return serve_command(args)
    if args.command == "version":
        return version_command(args)
    if args.command == "lsp":
        return lsp_command(args)
    if args.command == "debug":
        return debug_command(args)
    if args.command == "debug-lines":
        return debug_lines_command(args)

    parser.print_help()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run, test, check, capture, group, compare, format, and generate "
            "artifacts for GWT programs."
        )
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a GWT program or request.")
    add_file_arguments(run_parser)
    add_import_policy_arguments(run_parser)
    input_group = run_parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--input",
        type=Path,
        help="Path to a GWT request file containing GIVEN/REQUEST/THEN steps.",
    )
    input_group.add_argument(
        "--json-input",
        type=Path,
        help="Path to a JSON object containing initial state for REQUEST contracts, or '-' for stdin.",
    )
    run_parser.add_argument(
        "--request",
        help="Named REQUEST to execute after loading --json-input state.",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        help="Print final state as JSON after successful execution.",
    )

    test_parser = subparsers.add_parser("test", help="Run GWT scenarios.")
    add_file_arguments(test_parser)
    add_import_policy_arguments(test_parser)
    test_parser.add_argument(
        "--json",
        action="store_true",
        help="Print scenario results as JSON.",
    )

    check_parser = subparsers.add_parser("check", help="Parse and statically check a GWT file.")
    add_file_arguments(check_parser)
    add_import_policy_arguments(check_parser)
    check_parser.add_argument(
        "--json",
        action="store_true",
        help="Print check result as JSON.",
    )
    check_parser.add_argument(
        "--lint",
        action="store_true",
        help="Include opt-in lint warnings.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Print a machine-readable manifest for a GWT file.",
    )
    add_file_arguments(inspect_parser)
    add_import_policy_arguments(inspect_parser)
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Print inspect result as JSON. This is currently the only output mode.",
    )

    explain_parser = subparsers.add_parser(
        "explain",
        help="Explain why a JSON REQUEST run produced its result.",
    )
    add_file_arguments(explain_parser)
    add_import_policy_arguments(explain_parser)
    explain_parser.add_argument(
        "--json-input",
        type=Path,
        required=True,
        help="Path to a JSON object containing initial state for REQUEST contracts, or '-' for stdin.",
    )
    explain_parser.add_argument(
        "--request",
        required=True,
        help="Named REQUEST to execute and explain.",
    )
    explain_parser.add_argument(
        "--json",
        action="store_true",
        help="Print a versioned execution case as JSON.",
    )
    add_execution_case_capture_arguments(explain_parser)

    capture_parser = subparsers.add_parser(
        "capture",
        help="Capture a named JSON REQUEST run as an Execution Case.",
    )
    add_file_arguments(capture_parser)
    add_import_policy_arguments(capture_parser)
    capture_parser.add_argument(
        "--json-input",
        type=Path,
        required=True,
        help="Path to a JSON object containing initial state for REQUEST contracts, or '-' for stdin.",
    )
    capture_parser.add_argument(
        "--request",
        required=True,
        help="Named REQUEST to execute and capture.",
    )
    capture_parser.add_argument(
        "--output",
        type=Path,
        help="Write the Execution Case JSON to this path instead of stdout.",
    )
    add_execution_case_capture_arguments(capture_parser)

    scenario_parser = subparsers.add_parser(
        "scenario-from-run",
        help="Generate a verified GWT scenario from an Execution Case.",
    )
    scenario_parser.add_argument(
        "case",
        type=Path,
        help="Path to an Execution Case JSON file.",
    )
    scenario_parser.add_argument(
        "--program",
        type=Path,
        required=True,
        help="Program whose dependency-closure identity must match the Execution Case.",
    )
    scenario_parser.add_argument(
        "--name",
        help="Scenario name. Defaults to 'captured <request name>'.",
    )
    scenario_parser.add_argument(
        "--output",
        type=Path,
        help="Atomically write the canonical scenario to this path instead of stdout.",
    )
    add_import_policy_arguments(scenario_parser)

    corpus_parser = subparsers.add_parser(
        "corpus",
        help="Create or validate a versioned Execution Case Corpus.",
    )
    corpus_subparsers = corpus_parser.add_subparsers(
        dest="corpus_command",
        required=True,
    )
    corpus_create_parser = corpus_subparsers.add_parser(
        "create",
        help="Create a corpus from labeled Execution Case artifacts.",
    )
    corpus_create_parser.add_argument(
        "--name",
        required=True,
        help="Human-readable name for this case selection.",
    )
    corpus_create_parser.add_argument(
        "--case",
        dest="corpus_cases",
        action="append",
        required=True,
        type=_corpus_case_argument,
        metavar="REFERENCE=CASE",
        help=(
            "Reference and Execution Case path; repeat to preserve the desired "
            "corpus order."
        ),
    )
    corpus_create_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Atomically write the Case Corpus JSON to this path.",
    )
    corpus_check_parser = corpus_subparsers.add_parser(
        "check",
        help="Validate a corpus, its members, and all integrity digests.",
    )
    corpus_check_parser.add_argument(
        "corpus",
        type=Path,
        help="Path to a Case Corpus JSON file.",
    )

    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare captured Execution Cases against old and new programs.",
    )
    compare_parser.add_argument(
        "cases",
        type=Path,
        nargs="*",
        metavar="CASE",
        help="Execution Case JSON files; omit when using --corpus.",
    )
    compare_parser.add_argument(
        "--corpus",
        type=Path,
        help="Versioned Case Corpus supplying ordered cases and references.",
    )
    compare_parser.add_argument(
        "--old",
        type=Path,
        required=True,
        help="Baseline program used to capture the cases.",
    )
    compare_parser.add_argument(
        "--new",
        type=Path,
        required=True,
        help="Candidate program to evaluate.",
    )
    add_import_policy_arguments(compare_parser)
    compare_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the versioned comparison payload as canonical pretty JSON.",
    )

    workbench_parser = subparsers.add_parser(
        "workbench",
        help="Build a self-contained local behavior-review dossier.",
    )
    workbench_parser.add_argument(
        "cases",
        type=Path,
        nargs="*",
        metavar="CASE",
        help="Validated Execution Case JSON files; omit when using --corpus.",
    )
    workbench_parser.add_argument(
        "--corpus",
        type=Path,
        help="Versioned Case Corpus supplying ordered cases and references.",
    )
    workbench_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Atomically write the self-contained HTML dossier to this path.",
    )
    workbench_parser.add_argument(
        "--old",
        type=Path,
        help="Optional baseline program; requires --new.",
    )
    workbench_parser.add_argument(
        "--new",
        type=Path,
        help="Optional candidate program; requires --old.",
    )
    workbench_parser.add_argument(
        "--program",
        type=Path,
        help=(
            "Optional program matching the first case; includes a replay-verified "
            "scenario preview."
        ),
    )
    workbench_parser.add_argument(
        "--name",
        help="Scenario name when --program is supplied.",
    )
    workbench_parser.add_argument(
        "--review-notice",
        help="Prominent provenance or scope notice shown in the dossier.",
    )
    workbench_parser.add_argument(
        "--old-label",
        default="Baseline program",
        help="Human-readable provenance label for the baseline program.",
    )
    workbench_parser.add_argument(
        "--new-label",
        default="Candidate program",
        help="Human-readable provenance label for the candidate program.",
    )
    add_import_policy_arguments(workbench_parser)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Run the standard local/CI validation workflow.",
    )
    add_file_arguments(validate_parser)
    add_import_policy_arguments(validate_parser)
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Print validation result as JSON.",
    )
    validate_parser.add_argument(
        "--skip-format",
        action="store_true",
        help="Skip canonical format checking.",
    )
    validate_parser.add_argument(
        "--skip-test",
        action="store_true",
        help="Skip embedded scenario execution.",
    )
    validate_parser.add_argument(
        "--lint",
        action="store_true",
        help="Include opt-in lint warnings in the check phase.",
    )

    format_parser = subparsers.add_parser("format", help="Format a GWT file.")
    add_file_arguments(format_parser)
    format_parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with status 1 if the file is not formatted.",
    )
    format_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print formatted source instead of writing the file.",
    )

    types_parser = subparsers.add_parser(
        "types",
        help="Generate host-language types from GWT contracts.",
    )
    add_file_arguments(types_parser)
    types_parser.add_argument(
        "--language",
        choices=["typescript", "python"],
        default="typescript",
        help="Host language to generate.",
    )
    types_parser.add_argument(
        "--output",
        type=Path,
        help="Write generated types to a file instead of stdout.",
    )

    schema_parser = subparsers.add_parser(
        "schema",
        help="Generate JSON Schema from GWT contracts.",
    )
    add_file_arguments(schema_parser)
    add_import_policy_arguments(schema_parser)
    schema_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON Schema as JSON. This is currently the only stdout mode.",
    )
    schema_parser.add_argument(
        "--output",
        type=Path,
        help="Write generated JSON Schema to a file instead of stdout.",
    )

    openapi_parser = subparsers.add_parser(
        "openapi",
        help="Generate OpenAPI JSON from named REQUEST contracts.",
    )
    add_file_arguments(openapi_parser)
    add_import_policy_arguments(openapi_parser)
    openapi_parser.add_argument(
        "--json",
        action="store_true",
        help="Print OpenAPI as JSON. This is currently the only stdout mode.",
    )
    openapi_parser.add_argument(
        "--output",
        type=Path,
        help="Write generated OpenAPI JSON to a file instead of stdout.",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Serve named REQUEST contracts over HTTP.",
    )
    add_file_arguments(serve_parser)
    add_import_policy_arguments(serve_parser)
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind.",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="TCP port to bind.",
    )
    serve_parser.add_argument(
        "--otlp-endpoint",
        help=(
            "Export experimental request execution traces to an OTLP/HTTP endpoint. "
            "If omitted, OTEL_EXPORTER_OTLP_TRACES_ENDPOINT or OTEL_EXPORTER_OTLP_ENDPOINT is used."
        ),
    )
    serve_parser.add_argument(
        "--trace-values",
        action="store_true",
        help=(
            "Include request output, printed output, and state-change values in exported traces. "
            "By default served traces redact values."
        ),
    )
    serve_parser.add_argument(
        "--otlp-metrics-endpoint",
        help=(
            "Export experimental request metrics to an OTLP/HTTP endpoint. "
            "If omitted, OTEL_EXPORTER_OTLP_METRICS_ENDPOINT or OTEL_EXPORTER_OTLP_ENDPOINT is used."
        ),
    )
    serve_parser.add_argument(
        "--max-body-bytes",
        type=_non_negative_int,
        default=DEFAULT_MAX_REQUEST_BODY_BYTES,
        help=(
            "Maximum accepted POST request body size in bytes "
            f"(default: {DEFAULT_MAX_REQUEST_BODY_BYTES})."
        ),
    )
    serve_parser.add_argument(
        "--capture-dir",
        type=Path,
        help=(
            "Record served request executions as local Execution Case files. "
            "Values and provenance details are omitted by default."
        ),
    )
    serve_parser.add_argument(
        "--capture-request",
        action="append",
        default=[],
        help=(
            "Capture only this exact named REQUEST. Can be repeated; without it, "
            "all named requests are captured."
        ),
    )
    serve_parser.add_argument(
        "--capture-values",
        action="store_true",
        help=(
            "Include request, result, evidence, and provenance values in served "
            "Execution Cases. Review privacy before enabling."
        ),
    )
    serve_parser.add_argument(
        "--fact-provenance",
        type=Path,
        help=(
            "Static server-side fact provenance JSON for captured requests. "
            "Requires --capture-dir."
        ),
    )

    version_parser = subparsers.add_parser(
        "version",
        help="Print GWT package, language, and payload version information.",
    )
    version_parser.add_argument(
        "--json",
        action="store_true",
        help="Print version information as JSON.",
    )

    subparsers.add_parser("lsp", help="Run the GWT language server over stdio.")

    debug_parser = subparsers.add_parser("debug", help="Run a GWT file under the debug protocol.")
    add_file_arguments(debug_parser)
    debug_parser.add_argument(
        "--mode",
        choices=["test", "run"],
        default="test",
        help="Run mode used by the debugger.",
    )
    debug_parser.add_argument(
        "--breakpoint",
        action="append",
        default=[],
        help="Breakpoint as line or file:line. Can be repeated.",
    )

    debug_lines_parser = subparsers.add_parser(
        "debug-lines",
        help="List executable lines that can accept debugger breakpoints.",
    )
    add_file_arguments(debug_lines_parser)
    debug_lines_parser.add_argument(
        "--json",
        action="store_true",
        help="Print executable lines as JSON.",
    )

    return parser


def add_file_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", type=Path, help="Path to a .gwt file")


def add_import_policy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--import-root",
        type=Path,
        action="append",
        default=[],
        help="Allow USE imports only under this root. Can be repeated.",
    )
    parser.add_argument(
        "--no-absolute-imports",
        action="store_true",
        help="Reject absolute USE import paths.",
    )


def add_execution_case_capture_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fact-provenance",
        type=Path,
        help=(
            "Path to optional host fact provenance JSON keyed by declared "
            "request input path."
        ),
    )
    parser.add_argument(
        "--record-failures",
        action="store_true",
        help=(
            "Return a failed Execution Case for a GWT parse or execution error "
            "instead of exiting without an artifact."
        ),
    )
    parser.add_argument(
        "--omit-values",
        action="store_true",
        help=(
            "Execute normally but omit input, result, state-change, operand, and "
            "error-detail values from the artifact."
        ),
    )
    parser.add_argument(
        "--execution-budget",
        type=_positive_limit_or_none,
        default=DEFAULT_EXECUTION_BUDGET,
        metavar="N|none",
        help=(
            f"Maximum execution work units (default: {DEFAULT_EXECUTION_BUDGET}); "
            "use 'none' to disable."
        ),
    )
    parser.add_argument(
        "--max-call-depth",
        type=_positive_limit_or_none,
        default=DEFAULT_MAX_CALL_DEPTH,
        metavar="N|none",
        help=(
            f"Maximum nested behavior calls (default: {DEFAULT_MAX_CALL_DEPTH}); "
            "use 'none' to disable."
        ),
    )


def run_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    request_source = args.input.read_text() if args.input else None
    if args.json_input is not None and not args.request:
        print("gwt: --request is required with --json-input", file=sys.stderr)
        return 2
    if args.request and args.json_input is None:
        print("gwt: --request requires --json-input", file=sys.stderr)
        return 2

    try:
        if args.json_input is not None:
            json_state = _load_json_input(args.json_input)
            execution = run_json_file(
                args.file,
                json_state,
                request=args.request,
                json_file=args.json_input,
                import_roots=args.import_root,
                allow_absolute_imports=not args.no_absolute_imports,
            )
        else:
            execution = run_file(
                args.file,
                request_file=args.input,
                import_roots=args.import_root,
                allow_absolute_imports=not args.no_absolute_imports,
            )
    except GwtError as exc:
        if args.json_input is not None and str(exc).startswith("<request>:"):
            print(format_error(exc, f"{args.request}\n", "<request>"), file=sys.stderr)
        else:
            diagnostic_source = request_source if request_source is not None else source
            diagnostic_file = str(args.input) if args.input else str(args.file)
            print(format_error(exc, diagnostic_source or "", diagnostic_file), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(execution.as_payload(), indent=2, sort_keys=True))
    else:
        print_run_result(execution.result)
    return 0


def _load_json_input(path: Path) -> JsonObject:
    if path == Path("-"):
        raw = sys.stdin.read()
        try:
            _validate_json_nesting(raw)
            payload = json.loads(raw, parse_constant=_reject_json_constant)
        except json.JSONDecodeError as exc:
            raise GwtError(
                f"stdin JSON input is invalid at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        except ValueError as exc:
            raise GwtError(f"stdin JSON input is invalid: {exc}") from exc
        if not isinstance(payload, dict):
            raise GwtError("stdin JSON input must be an object")
        return cast(JsonObject, payload)

    try:
        raw = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        raise GwtError(f"{path}: JSON input is not valid UTF-8") from None
    try:
        _validate_json_nesting(raw)
        payload = json.loads(raw, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise GwtError(f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}") from exc
    except ValueError as exc:
        raise GwtError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise GwtError(f"{path}: JSON input must be an object")
    return cast(JsonObject, payload)


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite number {value!r} is not valid JSON")


def _validate_json_nesting(raw: str, *, maximum: int = 128) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in raw:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > maximum:
                raise ValueError(
                    f"maximum nesting depth of {maximum} exceeded"
                )
        elif character in "]}":
            depth = max(0, depth - 1)


def test_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    try:
        result = run_source(
            source,
            filename=str(args.file),
            import_policy=import_policy_from_args(args),
        )
    except GwtError as exc:
        print(format_error(exc, source, str(args.file)), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(run_result_payload(result, file=str(args.file)), indent=2, sort_keys=True))
    else:
        for scenario in result.scenarios:
            print(f"PASS {scenario.name}")
    return 0


def check_command(args: argparse.Namespace) -> int:
    analysis = analyze_file(args.file, import_policy=import_policy_from_args(args), lint=args.lint)
    source = analysis.source
    errors = [diagnostic for diagnostic in analysis.diagnostics if diagnostic.severity == "error"]
    payload = {"ok": not errors, **analysis.as_payload()}
    if errors:
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(
                "\n\n".join(
                    format_diagnostic(diagnostic, source, str(args.file))
                    for diagnostic in errors
                ),
                file=sys.stderr,
            )
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if analysis.diagnostics:
            print(
                "\n\n".join(
                    format_diagnostic(diagnostic, source, str(args.file))
                    for diagnostic in analysis.diagnostics
                ),
                file=sys.stderr,
            )
        print(
            f"OK {args.file} "
            f"({payload['records']} records, {payload['requests']} requests, "
            f"{payload['behaviors']} behaviors, {payload['scenarios']} scenarios)"
        )
    return 0


def inspect_command(args: argparse.Namespace) -> int:
    result = inspect_file(args.file, import_policy=import_policy_from_args(args))
    payload = result.as_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.ok else 1


def validate_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    result = validate_file(
        args.file,
        import_policy=import_policy_from_args(args),
        check_format=not args.skip_format,
        run_tests=not args.skip_test,
        lint=args.lint,
    )
    payload = result.as_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif result.ok:
        print(f"OK {args.file} ({_validate_summary(payload)})")
    else:
        errors = [
            diagnostic
            for diagnostic in result.diagnostics
            if diagnostic.severity == "error"
        ]
        print(
            "\n\n".join(
                format_diagnostic(diagnostic, source, str(args.file))
                for diagnostic in errors
            ),
            file=sys.stderr,
        )
    return 0 if result.ok else 1


def _validate_summary(payload: ValidationPayload) -> str:
    labels: list[str] = []
    for name in ("check", "format", "test"):
        phase = payload["phases"].get(name)
        if phase is None or not phase.get("checked"):
            continue
        if name == "test":
            scenario_count = phase.get("scenario_count", 0)
            labels.append(f"test; {scenario_count} scenarios")
        else:
            labels.append(name)
    return ", ".join(labels) if labels else "validated"


def import_policy_from_args(args: argparse.Namespace) -> ImportPolicy | None:
    import_roots = tuple(args.import_root or ())
    if not import_roots and not args.no_absolute_imports:
        return None
    return ImportPolicy(import_roots, allow_absolute=not args.no_absolute_imports)


def _execution_case_policy_from_args(
    args: argparse.Namespace,
) -> ExecutionCaseCapturePolicy:
    return ExecutionCaseCapturePolicy(
        on_error="record" if args.record_failures else "raise",
        values="omit" if args.omit_values else "full",
    )


def _fact_provenance_from_args(
    args: argparse.Namespace,
) -> FactProvenanceInput | None:
    path = args.fact_provenance
    if path is None:
        return None
    if path == Path("-"):
        raise ValueError("--fact-provenance must name a file, not stdin")
    return cast(FactProvenanceInput, _load_json_input(path))


def format_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    try:
        formatted = format_text(source, filename=str(args.file))
    except GwtError as exc:
        print(format_error(exc, source, str(args.file)), file=sys.stderr)
        return 1

    changed = formatted != source
    if args.check:
        if changed:
            print(f"gwt: {args.file} needs formatting", file=sys.stderr)
            return 1
        print(f"OK {args.file}")
        return 0

    if args.stdout:
        print(formatted, end="")
        return 0

    if changed:
        args.file.write_text(formatted)
        print(f"Formatted {args.file}")
    else:
        print(f"OK {args.file}")
    return 0


def explain_command(args: argparse.Namespace) -> int:
    source = ""
    try:
        json_state = _load_json_input(args.json_input)
        explanation = explain_json_file(
            args.file,
            json_state,
            request=args.request,
            fact_provenance=_fact_provenance_from_args(args),
            json_file=args.json_input if args.json_input != Path("-") else None,
            import_policy=import_policy_from_args(args),
            policy=_execution_case_policy_from_args(args),
            execution_budget=args.execution_budget,
            max_call_depth=args.max_call_depth,
        )
    except OSError as exc:
        print(f"gwt: {exc}", file=sys.stderr)
        return 1
    except GwtError as exc:
        if str(exc).startswith("<request>:"):
            print(format_error(exc, f"{args.request}\n", "<request>"), file=sys.stderr)
        else:
            print(format_error(exc, source, str(args.file)), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"gwt: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(explanation.as_payload(), indent=2, sort_keys=True))
    else:
        print(explanation.as_text(), end="")
    return 0


def capture_command(args: argparse.Namespace) -> int:
    source = ""
    try:
        json_state = _load_json_input(args.json_input)
        execution_case = capture_execution_case(
            args.file,
            json_state,
            request=args.request,
            fact_provenance=_fact_provenance_from_args(args),
            json_file=args.json_input if args.json_input != Path("-") else None,
            import_policy=import_policy_from_args(args),
            policy=_execution_case_policy_from_args(args),
            execution_budget=args.execution_budget,
            max_call_depth=args.max_call_depth,
        )
    except OSError as exc:
        print(f"gwt: {exc}", file=sys.stderr)
        return 1
    except GwtError as exc:
        if str(exc).startswith("<request>:"):
            print(format_error(exc, f"{args.request}\n", "<request>"), file=sys.stderr)
        else:
            print(format_error(exc, source, str(args.file)), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"gwt: {exc}", file=sys.stderr)
        return 1

    if args.output is not None:
        try:
            execution_case.write(args.output)
        except OSError as exc:
            print(f"gwt: could not write Execution Case to {args.output}: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote {args.output}")
        return 0

    print(json.dumps(execution_case.as_payload(), indent=2, sort_keys=True))
    return 0


def scenario_from_run_command(args: argparse.Namespace) -> int:
    try:
        execution_case = load_execution_case(args.case)
        generated = generate_scenario(
            execution_case.as_payload(),
            args.program,
            scenario_name=args.name,
            import_policy=import_policy_from_args(args),
        )
    except (GwtError, OSError, ValueError) as exc:
        print(f"gwt: {exc}", file=sys.stderr)
        return 1

    if args.output is not None:
        try:
            _write_text_atomically(args.output, generated.source)
        except OSError as exc:
            print(f"gwt: could not write scenario to {args.output}: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote {args.output}")
        return 0

    print(generated.source, end="")
    return 0


def corpus_command(args: argparse.Namespace) -> int:
    try:
        if args.corpus_command == "create":
            entries = _corpus_entry_specs(args.output, args.corpus_cases)
            corpus = write_case_corpus(
                args.output,
                name=args.name,
                entries=entries,
            )
            payload = corpus.as_payload()
            print(
                f"Wrote {args.output} "
                f"({len(corpus.entries)} cases, {payload['integrity']['digest']})"
            )
            return 0

        corpus = load_case_corpus(args.corpus)
        payload = corpus.as_payload()
        print(
            f"OK {args.corpus} "
            f"({len(corpus.entries)} cases, {payload['integrity']['digest']})"
        )
        return 0
    except (OSError, ValueError) as exc:
        print(f"gwt: {exc}", file=sys.stderr)
        return 1


def _corpus_entry_specs(
    output_path: Path,
    cases: list[tuple[str, Path]],
) -> list[CaseCorpusEntrySpec]:
    root = output_path.parent.resolve()
    entries: list[CaseCorpusEntrySpec] = []
    for reference, case_path in cases:
        resolved = case_path.resolve()
        try:
            artifact = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"case artifact must be beneath the corpus directory: {case_path}"
            ) from exc
        try:
            execution_case = ExecutionCase.load(resolved)
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"case {reference!r} cannot be loaded from {case_path}: {exc}"
            ) from exc
        case_id = execution_case.as_payload()["integrity"]["digest"]
        entries.append(CaseCorpusEntrySpec(reference, case_id, artifact))
    return entries


def compare_command(args: argparse.Namespace) -> int:
    if bool(args.cases) == (args.corpus is not None):
        print("gwt: supply CASE files or --corpus, but not both", file=sys.stderr)
        return 2
    try:
        cases, references = _case_selection(args.cases, args.corpus)
        result = compare_execution_cases(
            args.old,
            args.new,
            cases,
            import_policy=import_policy_from_args(args),
            case_references=references,
        )
    except (GwtError, OSError, ValueError) as exc:
        print(f"gwt: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.as_payload(), indent=2, sort_keys=True))
    else:
        print(result.as_text(), end="")
    return 0


def workbench_command(args: argparse.Namespace) -> int:
    if bool(args.cases) == (args.corpus is not None):
        print("gwt: supply CASE files or --corpus, but not both", file=sys.stderr)
        return 2
    if (args.old is None) != (args.new is None):
        print("gwt: --old and --new must be supplied together", file=sys.stderr)
        return 2
    if args.name is not None and args.program is None:
        print("gwt: --name requires --program", file=sys.stderr)
        return 2
    if len(args.cases) > 1 and args.old is None and args.new is None:
        print(
            "gwt: multiple CASE files require --old and --new; the dossier uses "
            "the first CASE as its primary case",
            file=sys.stderr,
        )
        return 2
    try:
        cases, references = _case_selection(args.cases, args.corpus)
        if len(cases) > 1 and args.old is None and args.new is None:
            print(
                "gwt: multiple corpus cases require --old and --new; the dossier "
                "uses the first case as its primary case",
                file=sys.stderr,
            )
            return 2
        comparison = None
        if args.old is not None and args.new is not None:
            comparison = compare_execution_cases(
                args.old,
                args.new,
                cases,
                import_policy=import_policy_from_args(args),
                case_references=references,
            )
        verified_scenario = None
        if args.program is not None:
            generated = generate_scenario(
                cases[0].as_payload(),
                args.program,
                scenario_name=args.name,
                import_policy=import_policy_from_args(args),
            )
            verified_scenario = generated.source
        rendered = render_workbench_html(
            cases[0],
            comparison=comparison,
            verified_scenario=verified_scenario,
            review_notice=args.review_notice,
            old_label=args.old_label,
            new_label=args.new_label,
            case_reference=(references[0] if references is not None else None),
        )
        _write_text_atomically(args.output, rendered)
    except (GwtError, OSError, ValueError) as exc:
        print(f"gwt: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.output}")
    return 0


def _case_selection(
    case_paths: list[Path],
    corpus_path: Path | None,
) -> tuple[list[ExecutionCase], tuple[str, ...] | None]:
    if corpus_path is not None:
        corpus = load_case_corpus(corpus_path)
        return list(corpus.cases), corpus.references
    return [load_execution_case(path) for path in case_paths], None


def _write_text_atomically(path: Path, rendered: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def types_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    try:
        if args.language == "python":
            result = generate_python_file(args.file)
        else:
            result = generate_typescript_file(args.file)
    except GwtError as exc:
        print(format_error(exc, source, str(args.file)), file=sys.stderr)
        return 1

    if args.output is not None:
        args.output.write_text(result.source)
        print(f"Wrote {args.output}")
        return 0

    print(result.source, end="")
    return 0


def openapi_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    try:
        result = generate_openapi_file(
            args.file,
            import_roots=args.import_root,
            allow_absolute_imports=not args.no_absolute_imports,
        )
    except GwtError as exc:
        print(format_error(exc, source, str(args.file)), file=sys.stderr)
        return 1

    rendered = json.dumps(result.as_payload(), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(rendered)
        print(f"Wrote {args.output}")
        return 0

    print(rendered, end="")
    return 0


def schema_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    try:
        result = generate_json_schema_file(
            args.file,
            import_roots=args.import_root,
            allow_absolute_imports=not args.no_absolute_imports,
        )
    except GwtError as exc:
        print(format_error(exc, source, str(args.file)), file=sys.stderr)
        return 1

    rendered = json.dumps(result.as_payload(), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(rendered)
        print(f"Wrote {args.output}")
        return 0

    print(rendered, end="")
    return 0


def serve_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    try:
        if args.capture_dir is None and (
            args.capture_request
            or args.capture_values
            or args.fact_provenance is not None
        ):
            raise ValueError(
                "--capture-request, --capture-values, and --fact-provenance "
                "require --capture-dir"
            )
        return run_http_server(
            args.file,
            host=args.host,
            port=args.port,
            import_roots=args.import_root,
            allow_absolute_imports=not args.no_absolute_imports,
            otlp_endpoint=args.otlp_endpoint,
            trace_values=args.trace_values,
            otlp_metrics_endpoint=args.otlp_metrics_endpoint,
            max_request_body_bytes=args.max_body_bytes,
            capture_directory=args.capture_dir,
            capture_request_names=(
                args.capture_request if args.capture_request else None
            ),
            capture_values=args.capture_values,
            fact_provenance=(
                _fact_provenance_from_args(args)
                if args.capture_dir is not None
                else None
            ),
        )
    except GwtError as exc:
        print(format_error(exc, source, str(args.file)), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"gwt: failed to start HTTP server: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"gwt: failed to configure HTTP server: {exc}", file=sys.stderr)
        return 1


def version_command(args: argparse.Namespace) -> int:
    payload = version_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"{payload['packageName']} {payload['packageVersion']}")
        print(
            f"language spec {payload['languageSpecVersion']} "
            f"({payload['languageSpecPath']})"
        )
        print(f"payload schema {payload['payloadSchemaVersion']}")
    return 0


def lsp_command(args: argparse.Namespace) -> int:
    return run_stdio_server()


def debug_command(args: argparse.Namespace) -> int:
    breakpoints = [parse_breakpoint(text, args.file) for text in args.breakpoint]
    return run_debug_file(args.file, mode=args.mode, breakpoints=breakpoints)


def debug_lines_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    try:
        lines = debug_lines_for_file(args.file)
    except GwtError as exc:
        print(format_error(exc, source, str(args.file)), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"lines": [line.as_payload() for line in lines]}, indent=2, sort_keys=True))
    else:
        for line in lines:
            print(f"{line.filename}:{line.line}:{line.column}: {line.text}")
    return 0


def print_run_result(result: RunResult) -> None:
    scenarios = result.scenarios
    if len(scenarios) == 1:
        print(f"PASS {scenarios[0].name}")
    else:
        for scenario in scenarios:
            print(f"PASS {scenario.name}")


def _normalize_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    known_commands = {
        "run",
        "test",
        "check",
        "inspect",
        "explain",
        "capture",
        "scenario-from-run",
        "corpus",
        "compare",
        "workbench",
        "validate",
        "format",
        "types",
        "schema",
        "openapi",
        "serve",
        "version",
        "lsp",
        "debug",
        "debug-lines",
    }
    if argv[0] in {*known_commands, "-h", "--help"}:
        return argv
    return ["run", *argv]


def _corpus_case_argument(value: str) -> tuple[str, Path]:
    reference, separator, case_path = value.partition("=")
    if not separator or not case_path:
        raise argparse.ArgumentTypeError("expected REFERENCE=CASE")
    try:
        reference = validate_case_reference(reference)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return reference, Path(case_path)


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("expected a non-negative integer")
    return parsed


def _positive_limit_or_none(value: str) -> int | None:
    if value.lower() == "none":
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected a positive integer or 'none'"
        ) from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("expected a positive integer or 'none'")
    return parsed


def format_error(error: GwtError, source: str, filename: str) -> str:
    message = str(error)
    location = _parse_location(message, filename)
    if location is None:
        return f"gwt: {message}"

    error_file, line_number, detail = location
    source_lines = _source_lines_for(error_file, filename, source)
    header = f"gwt: {error_file}:{line_number}: {detail}"
    if line_number < 1 or line_number > len(source_lines):
        return header

    source_line = source_lines[line_number - 1]
    caret_start, caret_width = _diagnostic_span(source_line, detail)
    caret = " " * caret_start + "^" * caret_width
    return f"{header}\n  {source_line}\n  {caret}"


def format_diagnostic(diagnostic: Diagnostic, source: str, filename: str) -> str:
    error_file = diagnostic.filename or filename
    source_lines = _source_lines_for(error_file, filename, source)
    header = f"gwt: {error_file}:{diagnostic.line}:{diagnostic.column}: {diagnostic.code} {diagnostic.message}"
    if diagnostic.line < 1 or diagnostic.line > len(source_lines):
        return header

    source_line = source_lines[diagnostic.line - 1]
    caret_start = max(0, min(len(source_line), diagnostic.column - 1))
    caret_width = max(1, min(diagnostic.length, max(1, len(source_line) - caret_start)))
    caret = " " * caret_start + "^" * caret_width
    return f"{header}\n  {source_line}\n  {caret}"


def _source_lines_for(error_file: str, fallback_filename: str, fallback_source: str) -> list[str]:
    if error_file == fallback_filename:
        return fallback_source.splitlines()
    try:
        return Path(error_file).read_text().splitlines()
    except OSError:
        return fallback_source.splitlines()


def _parse_location(message: str, fallback_filename: str) -> tuple[str, int, str] | None:
    file_match = re.match(r"^(.+):(\d+):\s*(.+)$", message)
    if file_match:
        filename = file_match.group(1)
        if filename == "<source>":
            filename = fallback_filename
        return filename, int(file_match.group(2)), file_match.group(3)

    scenario_match = re.match(r"^(.+): line (\d+):\s*(.+)$", message)
    if scenario_match:
        detail = f"{scenario_match.group(1)}: {scenario_match.group(3)}"
        return fallback_filename, int(scenario_match.group(2)), detail

    line_match = re.match(r"^line (\d+):\s*(.+)$", message)
    if line_match:
        return fallback_filename, int(line_match.group(1)), line_match.group(2)

    return None


def _diagnostic_span(source_line: str, detail: str) -> tuple[int, int]:
    token_patterns = [
        r"unknown name: ([A-Za-z_][A-Za-z0-9_.]*)",
        r"unknown path: ([A-Za-z_][A-Za-z0-9_.]*)",
        r"no value for (<[A-Za-z_][A-Za-z0-9_]*>)",
    ]
    for pattern in token_patterns:
        match = re.search(pattern, detail)
        if match:
            token = match.group(1)
            index = source_line.find(token)
            if index >= 0:
                return index, max(1, len(token))

    first_non_space = len(source_line) - len(source_line.lstrip(" "))
    return first_non_space, 1


if __name__ == "__main__":
    raise SystemExit(main())
