from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
import json
import keyword
from pathlib import Path
import re

from .errors import GwtError
from .runtime import (
    ContractBinding,
    RecordDefinition,
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


@dataclass(frozen=True)
class PythonTypesResult:
    source: str
    file: str
    language: str = "python"

    def as_payload(self) -> dict[str, object]:
        return {
            "file": self.file,
            "language": self.language,
            "source": self.source,
        }


@dataclass
class _PropertyNode:
    value_type: str | None = None
    children: dict[str, "_PropertyNode"] = field(
        default_factory=lambda: dict[str, _PropertyNode]()
    )


def generate_typescript_file(path: str | Path) -> TypeScriptTypesResult:
    file_path = Path(path)
    return generate_typescript_text(file_path.read_text(), filename=str(file_path))


def generate_typescript_text(source: str, filename: str = "<source>") -> TypeScriptTypesResult:
    program = _checked_program(source, filename)
    return TypeScriptTypesResult(_emit_typescript(program, filename), filename)


def generate_python_file(path: str | Path) -> PythonTypesResult:
    file_path = Path(path)
    return generate_python_text(file_path.read_text(), filename=str(file_path))


def generate_python_text(source: str, filename: str = "<source>") -> PythonTypesResult:
    program = _checked_program(source, filename)
    return PythonTypesResult(_emit_python(program, filename), filename)


def _checked_program(source: str, filename: str) -> Program:
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

    return analysis.program


def _emit_typescript(program: Program, filename: str) -> str:
    lines = [f"// Generated from {filename}. Do not edit by hand.", ""]

    for alias in program.type_aliases.values():
        lines.extend(_emit_typescript_alias(alias.name, alias.value_type))
        lines.append("")

    for record in program.records.values():
        lines.extend(_emit_record(record))
        lines.append("")

    for variant in program.variants.values():
        lines.extend(_emit_variant(variant))
        lines.append("")

    request_lines = _emit_named_request_types(program)
    if request_lines:
        lines.extend(request_lines)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _emit_typescript_alias(name: str, value_type: str) -> list[str]:
    return [f"export type {name} = {_typescript_type(value_type)};"]


def _emit_record(record: RecordDefinition) -> list[str]:
    root = _build_property_tree(record.fields.items())
    lines = [f"export interface {record.name} {{"]
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


def _emit_named_request_types(program: Program) -> list[str]:
    requests = list(program.requests.values())
    if not requests:
        return []

    lines: list[str] = []
    names: dict[str, tuple[str, str]] = {}
    used_names = {
        *program.type_aliases,
        *program.records,
        *program.variants,
        "GwtRequestName",
        "GwtRequests",
        "GwtOutputs",
        "GwtRequest",
        "GwtOutput",
    }
    for request in requests:
        base = _request_type_base(request.name)
        input_name = _unique_type_name(f"{base}Request", used_names)
        used_names.add(input_name)
        output_name = _unique_type_name(f"{base}Output", used_names)
        used_names.add(output_name)
        names[request.name] = (input_name, output_name)
        lines.extend(_emit_contract_interface(input_name, request.inputs.values()))
        lines.append("")
        lines.extend(_emit_contract_interface(output_name, request.outputs.values()))
        lines.append("")

    request_names = [request.name for request in requests]
    lines.extend(_emit_literal_union("GwtRequestName", request_names))
    lines.append("")
    lines.extend(_emit_request_map("GwtRequests", request_names, {name: pair[0] for name, pair in names.items()}))
    lines.append("")
    lines.extend(_emit_request_map("GwtOutputs", request_names, {name: pair[1] for name, pair in names.items()}))
    lines.append("")
    lines.append("export type GwtRequest = GwtRequests[GwtRequestName];")
    lines.append("export type GwtOutput = GwtOutputs[GwtRequestName];")
    return lines


def _emit_literal_union(name: str, values: list[str]) -> list[str]:
    if len(values) == 1:
        return [f"export type {name} = {_literal_type(values[0])};"]
    lines = [f"export type {name} ="]
    for index, value in enumerate(values):
        suffix = ";" if index == len(values) - 1 else ""
        lines.append(f"  | {_literal_type(value)}{suffix}")
    return lines


def _emit_request_map(name: str, request_names: list[str], type_names: dict[str, str]) -> list[str]:
    lines = [f"export interface {name} {{"]
    for request_name in request_names:
        lines.append(f"  {_literal_type(request_name)}: {type_names[request_name]};")
    lines.append("}")
    return lines


def _request_type_base(name: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", name) if word]
    if not words:
        return "Request"
    base = "".join(word[:1].upper() + word[1:] for word in words)
    if not base[0].isalpha():
        base = f"Request{base}"
    return base


def _unique_type_name(name: str, used: set[str]) -> str:
    candidate = name
    suffix = 2
    while candidate in used:
        candidate = f"{name}{suffix}"
        suffix += 1
    return candidate


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

    if value_type in {"number", "integer"}:
        return "number"
    if value_type == "decimal":
        return "string"
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
    if isinstance(value, Decimal):
        return json.dumps(str(value))
    return json.dumps(value)


def _property_name(name: str) -> str:
    return name


def _emit_python(program: Program, filename: str) -> str:
    return _PythonEmitter(program, filename).emit()


class _PythonEmitter:
    def __init__(self, program: Program, filename: str) -> None:
        self.program = program
        self.filename = filename
        self.used_type_names = {
            "Any",
            "CompiledProgram",
            "ExecutionResult",
            "GwtOutput",
            "GwtOutputs",
            "GwtRequest",
            "GwtRequestName",
            "GwtRequests",
            "Iterable",
            "Literal",
            "Path",
            "TypeAlias",
            "TypedDict",
            "cast",
            "compile_file",
        }
        self.type_names: dict[str, str] = {}
        for alias_name in program.type_aliases:
            self.type_names[alias_name] = self._unique_type_name(_python_type_name(alias_name))
        for record_name in program.records:
            self.type_names[record_name] = self._unique_type_name(_python_type_name(record_name))
        for variant_name in program.variants:
            self.type_names[variant_name] = self._unique_type_name(_python_type_name(variant_name))

    def emit(self) -> str:
        lines = [
            f"# Generated from {self.filename}. Do not edit by hand.",
            "from __future__ import annotations",
            "",
            "from collections.abc import Iterable",
            "from pathlib import Path",
            "from typing import Any, Literal, TypeAlias, TypedDict, cast",
            "",
            "from gwtlang import CompiledProgram, ExecutionResult, compile_file",
            "",
        ]

        for alias in self.program.type_aliases.values():
            lines.append(f"{self.type_names[alias.name]}: TypeAlias = {self._python_type(alias.value_type)}")
            lines.append("")

        for record in self.program.records.values():
            lines.extend(self._emit_record(record))
            lines.append("")

        for variant in self.program.variants.values():
            lines.extend(self._emit_variant(variant))
            lines.append("")

        request_lines = self._emit_named_request_types()
        if request_lines:
            lines.extend(request_lines)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _emit_record(self, record: RecordDefinition) -> list[str]:
        root = _build_property_tree(record.fields.items())
        nested: list[str] = []
        name = self.type_names[record.name]
        fields = self._python_fields(root.children, name, nested)
        return [*nested, *self._emit_typed_dict(name, fields)]

    def _emit_variant(self, variant: VariantDefinition) -> list[str]:
        lines: list[str] = []
        case_names: list[str] = []
        variant_name = self.type_names[variant.name]
        for case in variant.cases.values():
            case_name = self._unique_type_name(f"{variant_name}{_python_type_name(case.name)}")
            case_names.append(case_name)
            root = _build_property_tree(case.fields.items())
            nested: list[str] = []
            fields = [("kind", f"Literal[{_python_literal(case.name)}]")]
            fields.extend(self._python_fields(root.children, case_name, nested))
            lines.extend(nested)
            lines.extend(self._emit_typed_dict(case_name, fields))
            lines.append("")
        union = " | ".join(case_names) if case_names else "Any"
        lines.append(f"{variant_name}: TypeAlias = {union}")
        return lines

    def _emit_named_request_types(self) -> list[str]:
        requests = list(self.program.requests.values())
        if not requests:
            return []

        lines: list[str] = []
        names: dict[str, tuple[str, str, str, str, str]] = {}
        used_methods = {"from_file"}
        used_constants: set[str] = set()
        for request in requests:
            base = _request_type_base(request.name)
            input_name = self._unique_type_name(f"{base}Request")
            output_name = self._unique_type_name(f"{base}Output")
            method_name = _unique_python_identifier(
                _python_method_name(request.name),
                used_methods,
            )
            run_method_name = _unique_python_identifier(
                f"run_{method_name}",
                used_methods,
            )
            constant_name = _unique_python_identifier(
                f"{_python_constant_name(method_name)}_REQUEST",
                used_constants,
            )
            names[request.name] = (
                input_name,
                output_name,
                method_name,
                run_method_name,
                constant_name,
            )
            lines.extend(self._emit_contract_typed_dict(input_name, request.inputs.values()))
            lines.append("")
            lines.extend(self._emit_contract_typed_dict(output_name, request.outputs.values()))
            lines.append("")

        request_names = [request.name for request in requests]
        lines.append(f"GwtRequestName: TypeAlias = {self._python_literal_union(request_names)}")
        request_union = " | ".join(names[name][0] for name in request_names)
        output_union = " | ".join(names[name][1] for name in request_names)
        lines.append(f"GwtRequest: TypeAlias = {request_union}")
        lines.append(f"GwtOutput: TypeAlias = {output_union}")
        lines.append("")
        for request_name in request_names:
            constant_name = names[request_name][4]
            lines.append(f"{constant_name}: GwtRequestName = {_python_literal(request_name)}")
        lines.append("")
        lines.extend(
            self._emit_typed_dict(
                "GwtRequests",
                [(request_name, names[request_name][0]) for request_name in request_names],
                force_functional=True,
            )
        )
        lines.append("")
        lines.extend(
            self._emit_typed_dict(
                "GwtOutputs",
                [(request_name, names[request_name][1]) for request_name in request_names],
                force_functional=True,
            )
        )
        lines.append("")
        lines.extend(self._emit_client(request_names, names))
        return lines

    def _emit_contract_typed_dict(
        self,
        name: str,
        bindings: Iterable[ContractBinding],
    ) -> list[str]:
        root = _build_property_tree((binding.path, binding.value_type) for binding in bindings)
        nested: list[str] = []
        fields = self._python_fields(root.children, name, nested)
        return [*nested, *self._emit_typed_dict(name, fields)]

    def _emit_client(
        self,
        request_names: list[str],
        names: dict[str, tuple[str, str, str, str, str]],
    ) -> list[str]:
        base = _python_type_name(self.program.name or "GwtProgram")
        client_name = self._unique_type_name(f"{base}Client")
        lines = [
            f"class {client_name}:",
            "    def __init__(self, program: CompiledProgram) -> None:",
            "        self._program = program",
            "",
            "    @classmethod",
            "    def from_file(",
            "        cls,",
            "        path: str | Path,",
            "        *,",
            "        import_roots: Iterable[str | Path] | None = None,",
            "        allow_absolute_imports: bool = True,",
            f"    ) -> {client_name}:",
            "        return cls(",
            "            compile_file(",
            "                path,",
            "                import_roots=import_roots,",
            "                allow_absolute_imports=allow_absolute_imports,",
            "            )",
            "        )",
        ]
        for request_name in request_names:
            input_name, output_name, method_name, run_method_name, constant_name = names[request_name]
            lines.extend(
                [
                    "",
                    f"    def {run_method_name}(self, request: {input_name}) -> ExecutionResult:",
                    "        return self._program.run_json(",
                    "            cast(dict[str, Any], request),",
                    f"            request={constant_name},",
                    "        )",
                    "",
                    f"    def {method_name}(self, request: {input_name}) -> {output_name}:",
                    "        return cast(",
                    f"            {output_name},",
                    f"            self.{run_method_name}(request).as_payload()[\"result\"],",
                    "        )",
                ]
            )
        return lines

    def _python_fields(
        self,
        nodes: dict[str, _PropertyNode],
        owner_name: str,
        nested: list[str],
    ) -> list[tuple[str, str]]:
        fields: list[tuple[str, str]] = []
        for name, node in nodes.items():
            if node.children:
                field_type = self._unique_type_name(
                    f"{owner_name}{_python_type_name(name)}"
                )
                child_fields = self._python_fields(node.children, field_type, nested)
                nested.extend(self._emit_typed_dict(field_type, child_fields))
                nested.append("")
            else:
                field_type = self._python_type(node.value_type or "any")
            fields.append((name, field_type))
        return fields

    def _python_type(self, value_type: str) -> str:
        literal_values = _literal_union_values(value_type)
        if literal_values is not None:
            return self._python_literal_union(literal_values)

        if value_type == "number":
            return "int | float"
        if value_type == "integer":
            return "int"
        if value_type == "decimal":
            return "str"
        if value_type == "text":
            return "str"
        if value_type == "boolean":
            return "bool"
        if value_type == "list":
            return "list[Any]"
        if value_type == "any":
            return "Any"

        item_type = _list_item_type(value_type)
        if item_type is not None:
            return f"list[{self._python_type(item_type)}]"

        return self.type_names.get(value_type, value_type)

    def _python_literal_union(self, values: Iterable[object]) -> str:
        return f"Literal[{', '.join(_python_literal(value) for value in values)}]"

    def _emit_typed_dict(
        self,
        name: str,
        fields: list[tuple[str, str]],
        *,
        force_functional: bool = False,
    ) -> list[str]:
        if not force_functional and all(_is_python_field_name(field) for field, _ in fields):
            lines = [f"class {name}(TypedDict):"]
            if not fields:
                lines.append("    pass")
            for field, value_type in fields:
                lines.append(f"    {field}: {value_type}")
            return lines

        lines = [f"{name} = TypedDict("]
        lines.append(f"    {_python_literal(name)},")
        lines.append("    {")
        for field, value_type in fields:
            lines.append(f"        {_python_literal(field)}: {value_type},")
        lines.append("    },")
        lines.append(")")
        return lines

    def _unique_type_name(self, name: str) -> str:
        candidate = name
        suffix = 2
        while candidate in self.used_type_names or keyword.iskeyword(candidate):
            candidate = f"{name}{suffix}"
            suffix += 1
        self.used_type_names.add(candidate)
        return candidate


def _python_type_name(name: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", name) if word]
    if not words:
        return "Generated"
    type_name = "".join(word[:1].upper() + word[1:] for word in words)
    if not type_name[0].isalpha() and type_name[0] != "_":
        type_name = f"Generated{type_name}"
    return type_name


def _python_method_name(name: str) -> str:
    words = [word.lower() for word in re.split(r"[^A-Za-z0-9]+", name) if word]
    method_name = "_".join(words) if words else "request"
    if not method_name[0].isalpha() and method_name[0] != "_":
        method_name = f"request_{method_name}"
    return method_name


def _python_constant_name(name: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    if not text:
        text = "REQUEST"
    if not text[0].isalpha() and text[0] != "_":
        text = f"REQUEST_{text}"
    return text


def _unique_python_identifier(name: str, used: set[str]) -> str:
    candidate = name
    suffix = 2
    while candidate in used or keyword.iskeyword(candidate):
        candidate = f"{name}_{suffix}" if name.islower() else f"{name}{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _is_python_field_name(name: str) -> bool:
    return name.isidentifier() and not keyword.iskeyword(name)


def _python_literal(value: object) -> str:
    if isinstance(value, Decimal):
        return ascii(str(value))
    if isinstance(value, str):
        return ascii(value)
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    return repr(value)
