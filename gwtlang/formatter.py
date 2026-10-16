from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shlex
import textwrap

from .runtime import GwtError, parse_program, _read_source, _split_comment_outside_string


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
    r"^(PROGRAM|USE|TYPE|RECORD|REQUEST|OUTPUT|BACKGROUND|SCENARIO|GIVEN|WHEN|THEN|AND|EXAMPLES|LET|REQUIRE|IF|ELSE|FOR|FIND|DEPENDING|DECIDE|RETURN|PASS)\b(.*)$"
)
BUILTIN_PATTERN = re.compile(r"^(set|add|subtract|append|count|sum|find|exists|print)\b(.*)$")
FIELD_PATTERN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$")


def format_text(source: str, filename: str = "<source>") -> str:
    """Return canonical GWT source text, or raise GwtError for invalid input."""
    normalized = _normalize_newlines(textwrap.dedent(source))
    parse_program(_validation_source(normalized), filename=filename, allow_unknown_records=True,
                  source_loader=_validation_import)
    formatted = _format_lines(normalized)
    parse_program(_validation_source(formatted), filename=filename, allow_unknown_records=True,
                  source_loader=_validation_import)
    return formatted


def _validation_import(path: Path) -> str:
    return _validation_source(_read_source(path))


def _validation_source(source: str) -> str:
    """Project native-only syntax for the Python parser's layout check.

    The formatted source retains the complete annotation. This does not resolve
    kinds or enable them in Python execution; native checking owns that meaning.
    The original source, including constructor fields, is what gets formatted.
    """
    lines: list[str] = []
    for line in _project_record_locals(source).splitlines(keepends=True):
        code, _ = _split_comment_outside_string(line)
        annotation = re.match(
            r'^\s*(?:TYPE\s+\w+\s+is\s+|(?:GIVEN|AND|OUTPUT)\s+\w+\s+is\s+|'
            r'THEN\s+returns\s+|\w+\s*:\s*)(.*?)(\s*)$', code)
        if annotation:
            target = annotation.group(1)
            finite = _finite_type_projection(target)
            if finite is not None:
                start, end = annotation.span(1)
                line = line[:start] + finite.ljust(end - start) + line[end:]
                lines.append(line)
                continue
            selected = re.fullmatch(
                r'((?:(?:list|optional)<)*)([A-Za-z_]\w*) of kind ([A-Za-z_]\w*)(>*)', target)
            if selected and selected.group(1).count('<') == len(selected.group(4)):
                projected = selected.group(1) + selected.group(2) + selected.group(4)
                start, end = annotation.span(1)
                line = line[:start] + projected.ljust(end - start) + line[end:]
        lines.append(line)
    return ''.join(lines)


def _finite_type_projection(target: str) -> str | None:
    """Recognize native scalar annotations without changing the emitted source.

    This validates spelling for the formatter only. Membership, duplicate values,
    mixed numeric/boolean categories and exhaustive use belong to native checking.
    """
    prefix = ''
    while target.startswith(('list<', 'optional<')):
        container, target = target.split('<', 1)
        prefix += container + '<'
    suffix_count = len(target) - len(target.rstrip('>'))
    if suffix_count != prefix.count('<'):
        return None
    body = target[:-suffix_count] if suffix_count else target
    atoms = body.split('|')
    for atom in atoms:
        atom = atom.strip()
        if len(atoms) > 1:
            while atom.startswith('(') and atom.endswith(')'):
                atom = atom[1:-1].strip()
        if not re.fullmatch(r'(?:true|false|-?\s*[0-9]+(?:\.[0-9]+)?)', atom):
            return None
    return prefix + 'integer' + '>' * suffix_count


def _project_record_locals(source: str) -> str:
    """Validate constructor field layout, then hide it from the older parser.

    Field types, names, and expressions are checked by the native compiler.
    This projection is never executed or used as formatted output.
    """
    lines = source.splitlines(keepends=True)
    index = 0
    while index < len(lines):
        code, _ = _split_comment_outside_string(lines[index])
        code = code.rstrip('\r\n')
        header = re.fullmatch(r'( *)(?:(WHEN|AND)\s+)?LET\s+(\w+)\s+be\s+(.+):\s*', code)
        if not header:
            index += 1
            continue
        indent, prefix, name, annotation = header.groups()
        if not re.fullmatch(r'(?:optional<)*[A-Za-z_]\w*(?: of kind [A-Za-z_]\w*)?>*', annotation.strip()) or annotation.count('<') != annotation.count('>'):
            raise GwtError(f'line {index + 1}: constructor requires a record type annotation')
        if len(indent) % 2:
            raise GwtError(f'line {index + 1}: constructor indentation must use two spaces')
        projected = indent + (prefix + ' ' if prefix else '') + f'LET {name} be 0'
        lines[index] = projected.ljust(len(code)) + lines[index][len(code):]
        index += 1
        allowed = [len(indent) + 2]
        while index < len(lines):
            field_code, _ = _split_comment_outside_string(lines[index])
            field_code = field_code.rstrip('\r\n')
            if not field_code.strip():
                index += 1
                continue
            width = len(field_code) - len(field_code.lstrip(' '))
            if width <= len(indent):
                break
            if width not in allowed:
                raise GwtError(f'line {index + 1}: record field is indented too far')
            field = re.fullmatch(r' *[A-Za-z_]\w*\s*:(.*)', field_code)
            if not field:
                raise GwtError(f'line {index + 1}: record field must use name: value')
            value = field.group(1).strip()
            try:
                shlex.split(value)
            except ValueError as error:
                raise GwtError(f'line {index + 1}: {error}') from error
            allowed = [depth for depth in allowed if depth <= width]
            if not value:
                allowed.append(width + 2)
            lines[index] = ' ' * len(field_code) + lines[index][len(field_code):]
            index += 1
    return ''.join(lines)


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
    code, comment = _split_comment_outside_string(raw)
    if comment is None:
        return raw.rstrip(), None
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
        if keyword == "WHEN":
            rest = _normalize_builtin_start(rest)
        elif keyword == "DEPENDING":
            rest = re.sub(r"^ON\s+", "ON ", rest)
        return keyword if not rest else f"{keyword} {rest}"

    builtin = _normalize_builtin_start(statement)
    if builtin != statement:
        return builtin

    field_match = FIELD_PATTERN.match(statement)
    if field_match is not None:
        field, value_type = field_match.groups()
        value_type = value_type.strip()
        return f"{field}:" if not value_type else f"{field}: {value_type}"

    return statement.strip()


def _normalize_builtin_start(statement: str) -> str:
    builtin_match = BUILTIN_PATTERN.match(statement)
    if builtin_match is None:
        return statement
    builtin, rest = builtin_match.groups()
    rest = rest.strip()
    return builtin if not rest else f"{builtin} {rest}"


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
