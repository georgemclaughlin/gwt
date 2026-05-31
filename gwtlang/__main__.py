from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .runtime import GwtError, run_request, run_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a GWT program.")
    parser.add_argument("file", type=Path, help="Path to a .gwt file")
    parser.add_argument(
        "--input",
        type=Path,
        help="Path to a GWT request file containing GIVEN/WHEN/THEN steps.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print final state as JSON after successful execution.",
    )
    args = parser.parse_args(argv)

    source = args.file.read_text()
    request_source = args.input.read_text() if args.input else None
    try:
        if args.input:
            result = run_request(
                source,
                request_source or "",
                filename=str(args.file),
                request_filename=str(args.input),
            )
        else:
            result = run_source(source, filename=str(args.file))
    except GwtError as exc:
        diagnostic_source = request_source if request_source is not None else source
        diagnostic_file = str(args.input) if args.input else str(args.file)
        print(format_error(exc, diagnostic_source or "", diagnostic_file), file=sys.stderr)
        return 1

    if args.json:
        if len(result.scenarios) == 1:
            payload = result.scenarios[0].state
        else:
            payload = {
                scenario.name: {"state": scenario.state, "output": scenario.output}
                for scenario in result.scenarios
            }
        print(json.dumps(payload, indent=2, sort_keys=True))

    return 0


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
