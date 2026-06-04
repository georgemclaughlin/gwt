from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import json
from pathlib import Path

from .entries import entry_candidates
from .errors import GwtError
from .runtime import (
    ContractBinding,
    DtoDefinition,
    Program,
    VariantDefinition,
    _list_item_type,
    _literal_union_values,
)
from .service import analyze_source


@dataclass(frozen=True)
class TypeScriptTypesResult:
    source: str
    file: str
    language: str = "typescript"

    def as_payload(self) -> dict[str, object]:
        return {
            "file": self.file,
            "language": self.language,
            "source": self.source,
        }


@dataclass
class _PropertyNode:
    value_type: str | None = None
    children: dict[str, "_PropertyNode"] = field(default_factory=dict)


def generate_typescript_file(path: str | Path) -> TypeScriptTypesResult:
    file_path = Path(path)
    return generate_typescript_text(file_path.read_text(), filename=str(file_path))


def generate_typescript_text(source: str, filename: str = "<source>") -> TypeScriptTypesResult:
    analysis = analyze_source(source, filename)
    if analysis.program is None:
        diagnostic = analysis.diagnostics[0]
        raise GwtError(f"{diagnostic.filename or filename}:{diagnostic.line}: {diagnostic.message}")

    errors = [diagnostic for diagnostic in analysis.diagnostics if diagnostic.severity == "error"]
    if errors:
        diagnostic = errors[0]
        raise GwtError(
            f"{diagnostic.filename or filename}:{diagnostic.line}: "
            f"{diagnostic.code} {diagnostic.message}"
        )

    return TypeScriptTypesResult(_emit_typescript(analysis.program, filename), filename)


def _emit_typescript(program: Program, filename: str) -> str:
    lines = [f"// Generated from {filename}. Do not edit by hand.", ""]

    for dto in program.dtos.values():
        lines.extend(_emit_dto(dto))
        lines.append("")

    for variant in program.variants.values():
        lines.extend(_emit_variant(variant))
        lines.append("")

    if program.inputs:
        lines.extend(_emit_contract_interface("GwtRequest", program.inputs.values()))
        lines.append("")

    if program.outputs:
        lines.extend(_emit_contract_interface("GwtOutput", program.outputs.values()))
        lines.append("")

    entry_lines = _emit_entry_union(program)
    if entry_lines:
        lines.extend(entry_lines)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _emit_dto(dto: DtoDefinition) -> list[str]:
    root = _build_property_tree(dto.fields.items())
    lines = [f"export interface {dto.name} {{"]
    lines.extend(_emit_properties(root.children, 2))
    lines.append("}")
    return lines


def _emit_variant(variant: VariantDefinition) -> list[str]:
    lines = [f"export type {variant.name} ="]
    cases = list(variant.cases.values())
    for index, case in enumerate(cases):
        close = "    };" if index == len(cases) - 1 else "    }"
        lines.append("  | {")
        lines.append(f"      kind: {_literal_type(case.name)};")
        for field_name, value_type in case.fields.items():
            lines.append(f"      {_property_name(field_name)}: {_typescript_type(value_type)};")
        lines.append(close)
    return lines


def _emit_contract_interface(name: str, bindings: Iterable[ContractBinding]) -> list[str]:
    root = _build_property_tree((binding.path, binding.value_type) for binding in bindings)
    lines = [f"export interface {name} {{"]
    lines.extend(_emit_properties(root.children, 2))
    lines.append("}")
    return lines


def _emit_entry_union(program: Program) -> list[str]:
    entries = _entry_texts(program)
    if not entries:
        return []
    if len(entries) == 1:
        return [f"export type GwtEntry = {_literal_type(entries[0])};"]
    lines = ["export type GwtEntry ="]
    for index, entry in enumerate(entries):
        suffix = ";" if index == len(entries) - 1 else ""
        lines.append(f"  | {_literal_type(entry)}{suffix}")
    return lines


def _entry_texts(program: Program) -> list[str]:
    return [candidate.text for candidate in entry_candidates(program)]


def _build_property_tree(bindings: Iterable[tuple[str, str]]) -> _PropertyNode:
    root = _PropertyNode()
    for path, value_type in bindings:
        current = root
        parts = path.split(".")
        traversed: list[str] = []
        for part in parts:
            current = current.children.setdefault(part, _PropertyNode())
            traversed.append(part)
            if current.value_type is not None and traversed != parts:
                ancestor = ".".join(traversed)
                raise GwtError(f"type path {path} overlaps {ancestor}")
        if current.children:
            descendant = f"{path}.{next(iter(current.children))}"
            raise GwtError(f"type path {path} overlaps {descendant}")
        current.value_type = value_type
    return root


def _emit_properties(nodes: dict[str, _PropertyNode], indent: int) -> list[str]:
    lines: list[str] = []
    for name, node in nodes.items():
        lines.extend(_emit_property(name, node, indent))
    return lines


def _emit_property(name: str, node: _PropertyNode, indent: int) -> list[str]:
    space = " " * indent
    property_name = _property_name(name)
    if not node.children:
        return [f"{space}{property_name}: {_typescript_type(node.value_type or 'any')};"]

    if node.value_type is None:
        header = f"{space}{property_name}: {{"
    else:
        header = f"{space}{property_name}: {_typescript_type(node.value_type)} & {{"

    lines = [header]
    lines.extend(_emit_properties(node.children, indent + 2))
    lines.append(f"{space}}};")
    return lines


def _typescript_type(value_type: str) -> str:
    literal_values = _literal_union_values(value_type)
    if literal_values is not None:
        return " | ".join(_literal_type(value) for value in literal_values)

    if value_type == "number":
        return "number"
    if value_type == "text":
        return "string"
    if value_type == "boolean":
        return "boolean"
    if value_type == "list":
        return "unknown[]"
    if value_type == "any":
        return "unknown"

    item_type = _list_item_type(value_type)
    if item_type is not None:
        return f"{_typescript_type(item_type)}[]"

    return value_type


def _literal_type(value: object) -> str:
    return json.dumps(value)


def _property_name(name: str) -> str:
    return name
