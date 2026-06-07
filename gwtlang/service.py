from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path

from .checker import Diagnostic, check_program
from .errors import GwtError
from .payloads import AnalysisPayload, CompletionItemPayload
from .runtime import (
    Action,
    ImportPolicy,
    Program,
    parse_program,
    _is_builtin_statement,
    _signature_matches as _runtime_signature_matches,
    _tokens,
)
from .symbols import SourceRange, Symbol, SymbolTable, build_symbol_table

SCHEMA_VERSION = 3


@dataclass(frozen=True)
class Analysis:
    source: str
    filename: str
    program: Program | None
    diagnostics: list[Diagnostic]
    symbols: SymbolTable

    def as_payload(self) -> AnalysisPayload:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "file": self.filename,
            "program": self.program.name if self.program is not None else None,
            "requests": len(self.program.requests) if self.program is not None else 0,
            "records": len(self.program.records) if self.program is not None else 0,
            "typeAliases": len(self.program.type_aliases) if self.program is not None else 0,
            "behaviors": len(self.program.actions) if self.program is not None else 0,
            "scenarios": len(self.program.scenarios) if self.program is not None else 0,
            "diagnostics": [diagnostic.as_payload(self.filename) for diagnostic in self.diagnostics],
            "symbols": self.symbols.as_payload(self.filename),
        }


@dataclass(frozen=True)
class Hover:
    contents: str
    source_range: SourceRange


def analyze_source(
    source: str,
    filename: str = "<source>",
    *,
    import_policy: ImportPolicy | None = None,
    lint: bool = False,
) -> Analysis:
    try:
        program = parse_program(source, filename=filename, import_policy=import_policy)
    except GwtError as exc:
        return Analysis(
            source,
            filename,
            None,
            [diagnostic_from_error(str(exc), source, filename)],
            SymbolTable([]),
        )

    return Analysis(source, filename, program, check_program(program, lint=lint), build_symbol_table(program))


def analyze_file(
    path: str | Path,
    *,
    import_policy: ImportPolicy | None = None,
    lint: bool = False,
) -> Analysis:
    file_path = Path(path)
    return analyze_source(
        file_path.read_text(),
        str(file_path),
        import_policy=import_policy,
        lint=lint,
    )


def symbol_at(analysis: Analysis, line: int, character: int) -> Symbol | None:
    for symbol in analysis.symbols.symbols:
        if _range_contains(symbol.source_range, line, character):
            return symbol
    return None


def hover_at(analysis: Analysis, line: int, character: int) -> Hover | None:
    symbol = symbol_at(analysis, line, character)
    if symbol is not None:
        return Hover(_hover_text(symbol), symbol.source_range)

    word = _word_at(analysis.source, line, character)
    if word is None:
        return None
    symbol = _find_named_symbol(analysis, word)
    if symbol is None:
        return None
    return Hover(_hover_text(symbol), symbol.source_range)


def definition_at(analysis: Analysis, line: int, character: int) -> SourceRange | None:
    if analysis.program is None:
        return None

    request_text = _request_text_at(analysis.source, line)
    if request_text is not None:
        request = analysis.program.requests.get(request_text)
        if request is not None:
            return SourceRange(request.line.filename, request.line.number, request.line.column, request.line.length)

    call_text = _call_text_at(analysis.source, line)
    if call_text is not None:
        action = _matching_action(analysis.program.actions, call_text)
        if action is not None:
            return SourceRange(action.filename, action.line, action.column, action.length)

    word = _word_at(analysis.source, line, character)
    if word is None:
        return None
    symbol = _find_named_symbol(analysis, word)
    return symbol.source_range if symbol is not None else None


def completion_items(analysis: Analysis) -> list[CompletionItemPayload]:
    items: list[CompletionItemPayload] = []
    seen: set[tuple[str, str]] = set()
    for symbol in analysis.symbols.symbols:
        if symbol.kind not in {"behavior", "request", "record", "type_alias", "record_field", "parameter", "local", "contract"}:
            continue
        key = (symbol.name, symbol.kind)
        if key in seen:
            continue
        seen.add(key)
        item: CompletionItemPayload = {
            "label": symbol.name,
            "kind": _completion_kind(symbol.kind),
        }
        detail = _hover_text(symbol)
        if detail:
            item["detail"] = detail
        items.append(item)
    return items


def diagnostic_from_error(
    message: str,
    source: str,
    fallback_filename: str,
    *,
    code: str = "GWT900",
    category: str | None = None,
) -> Diagnostic:
    filename = fallback_filename
    line = 1
    detail = message
    match = re.match(r"^(.+):(\d+):\s*(.+)$", message)
    if match:
        filename = fallback_filename if match.group(1) == "<source>" else match.group(1)
        line = int(match.group(2))
        detail = match.group(3)
    else:
        scenario_match = re.match(r"^(.+): line (\d+):\s*(.+)$", message)
        if scenario_match:
            line = int(scenario_match.group(2))
            detail = f"{scenario_match.group(1)}: {scenario_match.group(3)}"
        else:
            line_match = re.match(r"^line (\d+):\s*(.+)$", message)
            if line_match:
                line = int(line_match.group(1))
                detail = line_match.group(2)

    source_lines = source.splitlines()
    column = 1
    length = 1
    if 1 <= line <= len(source_lines):
        source_line = source_lines[line - 1]
        column = len(source_line) - len(source_line.lstrip(" ")) + 1
        length = max(1, len(source_line.strip()))

    return Diagnostic(filename, line, detail, code, "error", column, length, category)


def _range_contains(source_range: SourceRange, line: int, character: int) -> bool:
    start_line = source_range.line - 1
    if line != start_line:
        return False
    start = max(0, source_range.column - 1)
    end = start + max(1, source_range.length)
    return start <= character <= end


def _hover_text(symbol: Symbol) -> str:
    label = "record" if symbol.kind == "record" else symbol.kind.replace("_", " ")
    parts = [f"{label}: {symbol.name}"]
    if symbol.detail:
        parts.append(symbol.detail)
    if symbol.container:
        parts.append(f"in {symbol.container}")
    return "\n".join(parts)


def _find_named_symbol(analysis: Analysis, name: str) -> Symbol | None:
    for symbol in analysis.symbols.symbols:
        if symbol.name == name and symbol.kind in {"behavior", "request", "record", "type_alias", "record_field", "parameter", "local", "contract"}:
            return symbol
    return None


def _word_at(source: str, line: int, character: int) -> str | None:
    lines = source.splitlines()
    if line < 0 or line >= len(lines):
        return None
    source_line = lines[line]
    if character < 0 or character > len(source_line):
        return None

    left = character
    while left > 0 and _is_word_char(source_line[left - 1]):
        left -= 1
    right = character
    while right < len(source_line) and _is_word_char(source_line[right]):
        right += 1
    if left == right:
        return None
    return source_line[left:right]


def _is_word_char(char: str) -> bool:
    return char.isalnum() or char in "_."


def _call_text_at(source: str, line: int) -> str | None:
    lines = source.splitlines()
    if line < 0 or line >= len(lines):
        return None
    raw = lines[line].split("#", 1)[0]
    indent = len(raw) - len(raw.lstrip(" "))
    text = raw.strip()
    if not text:
        return None
    if indent >= 4 and text.startswith("WHEN "):
        return None
    if text.startswith("WHEN "):
        return text.removeprefix("WHEN ").strip()
    if text.startswith("LET ") and " be " in text:
        return text.split(" be ", 1)[1].strip()
    if text.startswith("RETURN "):
        return text.removeprefix("RETURN ").strip()
    if text == "PASS":
        return None
    if text == "DECIDE":
        return None
    if text.startswith(("REQUIRE ", "IF ", "FOR ", "FIND ", "DECIDE ", "GIVEN ", "THEN ", "REQUEST ", "OUTPUT ")):
        return None
    if _is_builtin_statement(_tokens(text, "<source>", line + 1), text):
        return None
    return text


def _request_text_at(source: str, line: int) -> str | None:
    lines = source.splitlines()
    if line < 0 or line >= len(lines):
        return None
    text = lines[line].split("#", 1)[0].strip()
    if not text.startswith("REQUEST "):
        return None
    name = text.removeprefix("REQUEST ").strip()
    return name or None


def _matching_action(actions: list[Action], call_text: str) -> Action | None:
    try:
        call = _tokens(call_text, "<source>", 1)
    except GwtError:
        return None
    for action in reversed(actions):
        if _signature_matches(action.signature, call):
            return action
    return None


def _signature_matches(signature: list[str], call: list[str]) -> bool:
    return _runtime_signature_matches(signature, call)


def _completion_kind(symbol_kind: str) -> int:
    return {
        "behavior": 3,
        "request": 2,
        "record": 7,
        "type_alias": 7,
        "record_field": 5,
        "parameter": 6,
        "local": 6,
        "contract": 6,
    }.get(symbol_kind, 1)
