from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .api import run_file, run_result_payload
from .checker import Diagnostic
from .debugger import debug_lines_for_file, parse_breakpoint, run_debug_file
from .lsp import run_stdio_server
from .runtime import GwtError, run_source
from .service import analyze_file


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
    if args.command == "lsp":
        return lsp_command(args)
    if args.command == "debug":
        return debug_command(args)
    if args.command == "debug-lines":
        return debug_lines_command(args)

    parser.print_help()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run, test, check, and serve GWT programs.")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a GWT program or request.")
    add_file_arguments(run_parser)
    run_parser.add_argument(
        "--input",
        type=Path,
        help="Path to a GWT request file containing GIVEN/WHEN/THEN steps.",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        help="Print final state as JSON after successful execution.",
    )

    test_parser = subparsers.add_parser("test", help="Run GWT scenarios.")
    add_file_arguments(test_parser)
    test_parser.add_argument(
        "--json",
        action="store_true",
        help="Print scenario results as JSON.",
    )

    check_parser = subparsers.add_parser("check", help="Parse and statically check a GWT file.")
    add_file_arguments(check_parser)
    check_parser.add_argument(
        "--json",
        action="store_true",
        help="Print check result as JSON.",
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


def run_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    request_source = args.input.read_text() if args.input else None
    try:
        execution = run_file(args.file, request_file=args.input)
    except GwtError as exc:
        diagnostic_source = request_source if request_source is not None else source
        diagnostic_file = str(args.input) if args.input else str(args.file)
        print(format_error(exc, diagnostic_source or "", diagnostic_file), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(execution.as_payload(), indent=2, sort_keys=True))
    else:
        print_run_result(execution.result)
    return 0


def test_command(args: argparse.Namespace) -> int:
    source = args.file.read_text()
    try:
        result = run_source(source, filename=str(args.file))
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
    analysis = analyze_file(args.file)
    source = analysis.source
    payload = analysis.as_payload()
    if analysis.diagnostics:
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(
                "\n\n".join(
                    format_diagnostic(diagnostic, source, str(args.file))
                    for diagnostic in analysis.diagnostics
                ),
                file=sys.stderr,
            )
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"OK {args.file} "
            f"({payload['dtos']} DTOs, {payload['behaviors']} behaviors, {payload['scenarios']} scenarios)"
        )
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
    if argv[0] in {"run", "test", "check", "lsp", "debug", "debug-lines", "-h", "--help"}:
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
