from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
import re
from typing import Any

from .checker import Diagnostic
from .errors import GwtError
from .runtime import (
    ContractBinding,
    ImportPolicy,
    Program,
    RecordDefinition,
    TypeAliasDefinition,
    VariantDefinition,
    _list_item_type,
    _literal_union_values,
)
from .service import analyze_source
from .version import current_package_version


@dataclass(frozen=True)
class OpenApiResult:
    document: dict[str, Any]
    file: str

    def as_payload(self) -> dict[str, Any]:
        return self.document


@dataclass
class _PropertyNode:
    value_type: str | None = None
    children: dict[str, "_PropertyNode"] = field(
        default_factory=lambda: dict[str, _PropertyNode]()
    )


def generate_openapi_file(
    path: str | Path,
    *,
    import_policy: ImportPolicy | None = None,
) -> OpenApiResult:
    file_path = Path(path)
    return generate_openapi_text(
        file_path.read_text(),
        filename=str(file_path),
        import_policy=import_policy,
    )


def generate_openapi_text(
    source: str,
    filename: str = "<source>",
    *,
    import_policy: ImportPolicy | None = None,
) -> OpenApiResult:
    program = _checked_program(source, filename, import_policy=import_policy)
    return OpenApiResult(_OpenApiBuilder(program, filename).build(), filename)


def _checked_program(
    source: str,
    filename: str,
    *,
    import_policy: ImportPolicy | None,
) -> Program:
    analysis = analyze_source(source, filename, import_policy=import_policy)
    if analysis.program is None:
        diagnostic = analysis.diagnostics[0]
        raise GwtError(_diagnostic_message(diagnostic, filename))

    errors = [diagnostic for diagnostic in analysis.diagnostics if diagnostic.severity == "error"]
    if errors:
        raise GwtError(_diagnostic_message(errors[0], filename))

    return analysis.program


def _diagnostic_message(diagnostic: Diagnostic, fallback_filename: str) -> str:
    return (
        f"{diagnostic.filename or fallback_filename}:{diagnostic.line}: "
        f"{diagnostic.code} {diagnostic.message}"
    )


class _OpenApiBuilder:
    def __init__(self, program: Program, filename: str) -> None:
        self.program = program
        self.filename = filename
        self.schema_names: dict[str, str] = {}
        self.used_schema_names: set[str] = set()
        for name in (
            *program.type_aliases,
            *program.records,
            *program.variants,
        ):
            self.schema_names[name] = self._unique_schema_name(name)
        self.error_schema_name = self._unique_schema_name("GwtErrorResponse")

    def build(self) -> dict[str, Any]:
        components = self._component_schemas()
        request_schemas = self._request_schemas()
        components.update(request_schemas)
        components[self.error_schema_name] = self._error_schema()

        return {
            "openapi": "3.1.0",
            "info": {
                "title": self.program.name or _title_from_filename(self.filename),
                "version": current_package_version(),
            },
            "paths": self._paths(),
            "components": {
                "schemas": components,
            },
            "x-gwt": {
                "file": self.filename,
                "program": self.program.name,
            },
        }

    def _component_schemas(self) -> dict[str, Any]:
        schemas: dict[str, Any] = {}
        for alias in self.program.type_aliases.values():
            schemas[self.schema_names[alias.name]] = self._alias_schema(alias)
        for record in self.program.records.values():
            schemas[self.schema_names[record.name]] = self._record_schema(record)
        for variant in self.program.variants.values():
            schemas[self.schema_names[variant.name]] = self._variant_schema(variant)
        return schemas

    def _request_schemas(self) -> dict[str, Any]:
        schemas: dict[str, Any] = {}
        for request in self.program.requests.values():
            base = _request_component_base(request.name)
            input_name = self._unique_schema_name(f"{base}Request")
            output_name = self._unique_schema_name(f"{base}Output")
            self.schema_names[f"request:{request.name}:input"] = input_name
            self.schema_names[f"request:{request.name}:output"] = output_name
            schemas[input_name] = self._contract_schema(request.inputs.values())
            schemas[output_name] = self._contract_schema(request.outputs.values())
        return schemas

    def _paths(self) -> dict[str, Any]:
        paths: dict[str, Any] = {}
        used_paths: set[str] = set()
        used_operation_ids: set[str] = set()
        for request in self.program.requests.values():
            path = _unique_path(f"/requests/{_slug(request.name)}", used_paths)
            operation_id = _unique_operation_id(_operation_id(request.name), used_operation_ids)
            input_name = self.schema_names[f"request:{request.name}:input"]
            output_name = self.schema_names[f"request:{request.name}:output"]
            paths[path] = {
                "post": {
                    "summary": request.name,
                    "operationId": operation_id,
                    "x-gwt-request-name": request.name,
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{input_name}"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Declared GWT OUTPUT values.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": f"#/components/schemas/{output_name}"}
                                }
                            },
                        },
                        "400": {
                            "description": "Invalid JSON input or GWT request contract failure.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": f"#/components/schemas/{self.error_schema_name}"}
                                }
                            },
                        },
                        "500": {
                            "description": "GWT request assertion, output contract, or runtime failure.",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": f"#/components/schemas/{self.error_schema_name}"}
                                }
                            },
                        },
                    },
                }
            }
        return paths

    def _alias_schema(self, alias: TypeAliasDefinition) -> dict[str, Any]:
        schema = self._schema_for_type(alias.value_type)
        return {
            **schema,
            "title": alias.name,
            "x-gwt-type": "typeAlias",
        }

    def _record_schema(self, record: RecordDefinition) -> dict[str, Any]:
        schema = self._object_schema(_build_property_tree(record.fields.items()))
        schema["title"] = record.name
        schema["x-gwt-type"] = "record"
        return schema

    def _variant_schema(self, variant: VariantDefinition) -> dict[str, Any]:
        cases: list[dict[str, Any]] = []
        for case in variant.cases.values():
            root = _build_property_tree(case.fields.items())
            schema = self._object_schema(root)
            schema["properties"] = {
                "kind": {
                    "type": "string",
                    "enum": [case.name],
                },
                **schema["properties"],
            }
            schema["required"] = ["kind", *schema["required"]]
            cases.append(schema)
        return {
            "title": variant.name,
            "oneOf": cases,
            "discriminator": {
                "propertyName": "kind",
            },
            "x-gwt-type": "oneOfRecord",
        }

    def _contract_schema(self, bindings: Iterable[ContractBinding]) -> dict[str, Any]:
        return self._object_schema(
            _build_property_tree((binding.path, binding.value_type) for binding in bindings)
        )

    def _error_schema(self) -> dict[str, Any]:
        return {
            "title": self.error_schema_name,
            "type": "object",
            "properties": {
                "ok": {
                    "type": "boolean",
                    "description": "Always false for service error responses.",
                },
                "error": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "required": ["code", "message"],
                    "additionalProperties": False,
                },
            },
            "required": ["ok", "error"],
            "additionalProperties": False,
        }

    def _object_schema(self, root: _PropertyNode) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, node in root.children.items():
            properties[name] = self._property_schema(node)
            required.append(name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def _property_schema(self, node: _PropertyNode) -> dict[str, Any]:
        if node.children:
            if node.value_type is not None:
                raise GwtError("OpenAPI schema path has both scalar and nested fields")
            return self._object_schema(node)
        return self._schema_for_type(node.value_type or "any")

    def _schema_for_type(self, value_type: str) -> dict[str, Any]:
        literal_values = _literal_union_values(value_type)
        if literal_values is not None:
            return _literal_union_schema(literal_values)

        if value_type == "number":
            return {"type": "number"}
        if value_type == "integer":
            return {"type": "integer"}
        if value_type == "decimal":
            return _decimal_schema()
        if value_type == "text":
            return {"type": "string"}
        if value_type == "boolean":
            return {"type": "boolean"}
        if value_type == "list":
            return {"type": "array", "items": {}}
        if value_type == "any":
            return {}

        item_type = _list_item_type(value_type)
        if item_type is not None:
            return {
                "type": "array",
                "items": self._schema_for_type(item_type),
            }

        schema_name = self.schema_names.get(value_type)
        if schema_name is not None:
            return {"$ref": f"#/components/schemas/{schema_name}"}

        raise GwtError(f"unknown GWT type for OpenAPI schema: {value_type}")

    def _unique_schema_name(self, preferred: str) -> str:
        base = _schema_name(preferred)
        candidate = base
        suffix = 2
        while candidate in self.used_schema_names:
            candidate = f"{base}{suffix}"
            suffix += 1
        self.used_schema_names.add(candidate)
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
                raise GwtError(f"OpenAPI schema path {path} overlaps {ancestor}")
        if current.children:
            descendant = f"{path}.{next(iter(current.children))}"
            raise GwtError(f"OpenAPI schema path {path} overlaps {descendant}")
        current.value_type = value_type
    return root


def _literal_union_schema(values: tuple[Any, ...]) -> dict[str, Any]:
    if any(isinstance(value, Decimal) for value in values):
        return _decimal_literal_union_schema(values)

    enum_values = [_json_literal(value) for value in values]
    schema_type = _json_schema_type(enum_values[0])
    return {
        "type": schema_type,
        "enum": enum_values,
    }


def _decimal_schema() -> dict[str, Any]:
    return {
        "anyOf": [
            {"type": "string", "format": "decimal"},
            {"type": "integer"},
        ],
        "x-gwt-json-input": "decimal string or integer",
        "x-gwt-json-output": "decimal string",
    }


def _decimal_literal_union_schema(values: tuple[Any, ...]) -> dict[str, Any]:
    schemas: list[dict[str, Any]] = [{"type": "string", "format": "decimal"}]
    integer_values = [
        int(value)
        for value in values
        if isinstance(value, Decimal) and value == value.to_integral_value()
    ]
    if integer_values:
        schemas.append({"type": "integer", "enum": integer_values})
    return {
        "anyOf": schemas,
        "x-gwt-literal-values": [str(value) for value in values],
        "x-gwt-json-input": "decimal string or matching integer",
        "x-gwt-json-output": "decimal string",
    }


def _json_literal(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _json_schema_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return "string"


def _title_from_filename(filename: str) -> str:
    if filename == "<source>":
        return "GWT API"
    stem = Path(filename).stem
    return stem.replace("_", " ").replace("-", " ").title() or "GWT API"


def _request_component_base(name: str) -> str:
    return _schema_name(name) or "Request"


def _schema_name(name: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", name) if word]
    if not words:
        return "Schema"
    base = "".join(word[:1].upper() + word[1:] for word in words)
    if not base[0].isalpha():
        base = f"Schema{base}"
    return base


def _slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "request"


def _unique_path(preferred: str, used: set[str]) -> str:
    candidate = preferred
    suffix = 2
    while candidate in used:
        candidate = f"{preferred}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _operation_id(name: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", name) if word]
    if not words:
        return "runRequest"
    first, *rest = words
    candidate = first[:1].lower() + first[1:] + "".join(
        word[:1].upper() + word[1:] for word in rest
    )
    if not candidate[0].isalpha():
        candidate = f"run{candidate[:1].upper()}{candidate[1:]}"
    return candidate


def _unique_operation_id(preferred: str, used: set[str]) -> str:
    candidate = preferred
    suffix = 2
    while candidate in used:
        candidate = f"{preferred}{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate
