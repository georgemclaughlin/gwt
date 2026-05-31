from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import textwrap

from .runtime import parse_program


@dataclass(frozen=True)
class FormatResult:
    formatted: str
    changed: bool


@dataclass(frozen=True)
class _FormattedLine:
    kind: str
    text: str = ""
    indent: str = ""
    cells: tuple[str, ...] = ()
    comment: str | None = None


KEYWORD_PATTERN = re.compile(
    r"^(PROGRAM|USE|DTO|REQUEST|OUTPUT|BACKGROUND|SCENARIO|GIVEN|WHEN|THEN|AND|EXAMPLES|LET|REQUIRE|IF|ELSE|FOR|RETURN)\b(.*)$"
)
FIELD_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$")


def format_text(source: str, filename: str = "<source>") -> str:
    """Return canonical GWT source text, or raise GwtError for invalid input."""
    normalized = _normalize_newlines(textwrap.dedent(source))
    parse_program(normalized, filename=filename, allow_unknown_dtos=True)
    formatted = _format_lines(normalized)
    parse_program(formatted, filename=filename, allow_unknown_dtos=True)
    return formatted


def format_file(path: str | Path, *, write: bool = True) -> FormatResult:
    file_path = Path(path)
    source = file_path.read_text()
    formatted = format_text(source, filename=str(file_path))
    changed = formatted != source
    if write and changed:
        file_path.write_text(formatted)
    return FormatResult(formatted, changed)


def is_formatted(source: str, filename: str = "<source>") -> bool:
    return format_text(source, filename=filename) == _normalize_newlines(source)


def _format_lines(source: str) -> str:
    lines = [_line_parts(line) for line in source.split("\n")]
    lines = _trim_outer_blank_lines(lines)
    lines = _collapse_blank_lines(lines)
    lines = _align_table_blocks(lines)
    rendered = [line.text if line.kind != "table" else _render_table_line(line) for line in lines]
    return "\n".join(rendered) + ("\n" if rendered else "")


def _line_parts(raw: str) -> _FormattedLine:
    if raw.strip() == "":
        return _FormattedLine("blank")

    code, comment = _split_comment(raw.rstrip())
    if code.strip() == "":
        indent = _indent(code if code else raw)
        return _FormattedLine("comment", f"{indent}{comment}")

    indent = _indent(code)
    statement = _normalize_statement(code.strip())
    if _is_table_row(statement):
        return _FormattedLine("table", indent=indent, cells=_table_cells(statement), comment=comment)

    text = f"{indent}{statement}"
    if comment is not None:
        text = f"{text}  {comment}"
    return _FormattedLine("code", text)


def _split_comment(raw: str) -> tuple[str, str | None]:
    if "#" not in raw:
        return raw.rstrip(), None
    code, comment = raw.split("#", 1)
    comment_text = comment.strip()
    return code.rstrip(), "#" if not comment_text else f"# {comment_text}"


def _indent(text: str) -> str:
    width = len(text) - len(text.lstrip(" "))
    return " " * width


def _normalize_statement(statement: str) -> str:
    if _is_table_row(statement):
        return statement

    keyword_match = KEYWORD_PATTERN.match(statement)
    if keyword_match is not None:
        keyword, rest = keyword_match.groups()
        rest = rest.strip()
        return keyword if not rest else f"{keyword} {rest}"

    field_match = FIELD_PATTERN.match(statement)
    if field_match is not None:
        field, value_type = field_match.groups()
        value_type = value_type.strip()
        return f"{field}:" if not value_type else f"{field}: {value_type}"

    return statement.strip()


def _is_table_row(statement: str) -> bool:
    return statement.startswith("|") and statement.endswith("|")


def _table_cells(statement: str) -> tuple[str, ...]:
    return tuple(cell.strip() for cell in statement.strip("|").split("|"))


def _trim_outer_blank_lines(lines: list[_FormattedLine]) -> list[_FormattedLine]:
    start = 0
    end = len(lines)
    while start < end and lines[start].kind == "blank":
        start += 1
    while end > start and lines[end - 1].kind == "blank":
        end -= 1
    return lines[start:end]


def _collapse_blank_lines(lines: list[_FormattedLine]) -> list[_FormattedLine]:
    collapsed: list[_FormattedLine] = []
    previous_blank = False
    for line in lines:
        if line.kind == "blank":
            if not previous_blank:
                collapsed.append(line)
            previous_blank = True
            continue
        collapsed.append(line)
        previous_blank = False
    return collapsed


def _align_table_blocks(lines: list[_FormattedLine]) -> list[_FormattedLine]:
    aligned: list[_FormattedLine] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.kind != "table":
            aligned.append(line)
            index += 1
            continue

        table: list[_FormattedLine] = []
        while index < len(lines) and lines[index].kind == "table":
            table.append(lines[index])
            index += 1
        aligned.extend(_align_table(table))
    return aligned


def _align_table(table: list[_FormattedLine]) -> list[_FormattedLine]:
    width = max(len(line.cells) for line in table)
    column_widths = [0] * width
    for line in table:
        for index, cell in enumerate(line.cells):
            column_widths[index] = max(column_widths[index], len(cell))

    aligned: list[_FormattedLine] = []
    for line in table:
        cells = tuple(cell.ljust(column_widths[index]) for index, cell in enumerate(line.cells))
        aligned.append(_FormattedLine("table", indent=line.indent, cells=cells, comment=line.comment))
    return aligned


def _render_table_line(line: _FormattedLine) -> str:
    text = f"{line.indent}| {' | '.join(line.cells)} |"
    if line.comment is not None:
        text = f"{text}  {line.comment}"
    return text


def _normalize_newlines(source: str) -> str:
    return source.replace("\r\n", "\n").replace("\r", "\n")
