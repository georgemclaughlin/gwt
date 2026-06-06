from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .api import (
    generate_python_file,
    generate_typescript_file,
    run_file,
    run_json_file,
    run_result_payload,
)
from .checker import Diagnostic
from .debugger import debug_lines_for_file, parse_breakpoint, run_debug_file
from .formatter import format_text
from .inspection import inspect_file
from .lsp import run_stdio_server
from .runtime import GwtError, ImportPolicy, run_source
from .service import analyze_file
from .validation import validate_file


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
    if args.command == "validate":
        return validate_command(args)
    if args.command == "format":
        return format_command(args)
    if args.command == "types":
        return types_command(args)
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
        description="Run, test, check, format, and generate types for GWT programs."
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a GWT program or request.")
    add_file_arguments(run_parser)
    add_import_policy_arguments(run_parser)
    input_group = run_parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--input",
        type=Path,
        help="Path to a GWT request file containing GIVEN/WHEN/THEN steps.",
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


def _load_json_input(path: Path) -> dict[str, object]:
    if path == Path("-"):
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GwtError(
                f"stdin JSON input is invalid at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise GwtError("stdin JSON input must be an object")
        return payload

    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise GwtError(f"{path}:{exc.lineno}:{exc.colno}: invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise GwtError(f"{path}: JSON input must be an object")
    return payload


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
    analysis = analyze_file(args.file, import_policy=import_policy_from_args(args))
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
            f"({payload['dtos']} records, {payload['requests']} requests, "
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


def _validate_summary(payload: dict[str, object]) -> str:
    phases = payload.get("phases", {})
    if not isinstance(phases, dict):
        return "validated"

    labels: list[str] = []
    for name in ("check", "format", "test"):
        phase = phases.get(name)
        if not isinstance(phase, dict) or not phase.get("checked"):
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


def print_run_result(result: object) -> None:
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
        "validate",
        "format",
        "types",
        "lsp",
        "debug",
        "debug-lines",
    }
    if argv[0] in {*known_commands, "-h", "--help"}:
        return argv
    return ["run", *argv]


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
