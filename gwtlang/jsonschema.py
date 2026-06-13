from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .openapi import _GwtSchemaBuilder, _checked_program, _title_from_filename
from .runtime import ImportPolicy
from .version import current_package_version


JSON_SCHEMA_DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True)
class JsonSchemaResult:
    document: dict[str, Any]
    file: str

    def as_payload(self) -> dict[str, Any]:
        return self.document


def generate_json_schema_file(
    path: str | Path,
    *,
    import_policy: ImportPolicy | None = None,
) -> JsonSchemaResult:
    file_path = Path(path)
    return generate_json_schema_text(
        file_path.read_text(),
        filename=str(file_path),
        import_policy=import_policy,
    )


def generate_json_schema_text(
    source: str,
    filename: str = "<source>",
    *,
    import_policy: ImportPolicy | None = None,
) -> JsonSchemaResult:
    program = _checked_program(source, filename, import_policy=import_policy)
    projection = _GwtSchemaBuilder(
        program,
        ref_prefix="#/$defs/",
        include_openapi_discriminator=False,
    ).build()
    requests: dict[str, Any] = {}
    for request in program.requests.values():
        requests[request.name] = {
            "input": {"$ref": f"#/$defs/{projection.request_input_names[request.name]}"},
            "output": {"$ref": f"#/$defs/{projection.request_output_names[request.name]}"},
        }

    return JsonSchemaResult(
        {
            "$schema": JSON_SCHEMA_DRAFT_2020_12,
            "title": program.name or _title_from_filename(filename),
            "$defs": projection.schemas,
            "x-gwt": {
                "file": filename,
                "program": program.name,
                "packageVersion": current_package_version(),
                "requests": requests,
            },
        },
        filename,
    )
