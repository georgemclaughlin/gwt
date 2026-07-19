from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path

from .payloads import (
    BehaviorPayload,
    ContractPayload,
    ImportPayload,
    InspectionPayload,
    OneOfRecordPayload,
    RecordFieldPayload,
    RecordPayload,
    RequestPayload,
    ScenarioInspectionPayload,
    TypeAliasPayload,
)
from .runtime import (
    Action,
    ContractBinding,
    RecordDefinition,
    ImportPolicy,
    Line,
    NamedRequest,
    Scenario,
    TypeAliasDefinition,
    VariantDefinition,
    _signature_parameters,
)
from .program_identity import ProgramIdentityManifest, load_program_snapshot
from .service import Analysis, analyze_source
from .version import PAYLOAD_SCHEMA_VERSION

SCHEMA_VERSION = PAYLOAD_SCHEMA_VERSION


@dataclass(frozen=True)
class InspectionResult:
    analysis: Analysis
    program_identity: ProgramIdentityManifest | None = None

    @property
    def ok(self) -> bool:
        return not any(
            diagnostic.severity == "error" for diagnostic in self.analysis.diagnostics
        )

    def as_payload(self) -> InspectionPayload:
        analysis = self.analysis
        program = analysis.program
        payload: InspectionPayload = {
            "schemaVersion": SCHEMA_VERSION,
            "ok": self.ok,
            "file": analysis.filename,
            "program": program.name if program is not None else None,
            "programHash": _program_hash(analysis.source),
            "programHashScope": "entry-source",
            "programIdentity": (
                self.program_identity.as_payload()
                if self.program_identity is not None
                else None
            ),
            "imports": _direct_imports(analysis.source, analysis.filename),
            "diagnostics": [
                diagnostic.as_payload(analysis.filename)
                for diagnostic in analysis.diagnostics
            ],
            "records": [],
            "typeAliases": [],
            "oneOfRecords": [],
            "requests": [],
            "behaviors": [],
            "scenarios": [],
            "counts": {
                "records": 0,
                "typeAliases": 0,
                "oneOfRecords": 0,
                "requests": 0,
                "behaviors": 0,
                "scenarios": 0,
            },
        }
        if program is None:
            return payload

        records = [_record_payload(record, analysis.filename) for record in program.records.values()]
        aliases = [
            _type_alias_payload(alias, analysis.filename)
            for alias in program.type_aliases.values()
        ]
        variants = [
            _variant_payload(variant, analysis.filename)
            for variant in program.variants.values()
        ]
        behaviors = [
            _behavior_payload(action, analysis.filename)
            for action in program.actions
        ]
        requests = [
            _request_payload(request, analysis.filename)
            for request in program.requests.values()
        ]
        scenarios = [
            _scenario_payload(scenario, analysis.filename)
            for scenario in program.scenarios
        ]

        payload.update(
            {
                "records": records,
                "typeAliases": aliases,
                "oneOfRecords": variants,
                "requests": requests,
                "behaviors": behaviors,
                "scenarios": scenarios,
                "counts": {
                    "records": len(records),
                    "typeAliases": len(aliases),
                    "oneOfRecords": len(variants),
                    "requests": len(requests),
                    "behaviors": len(behaviors),
                    "scenarios": len(scenarios),
                },
            }
        )
        return payload


def inspect_file(
    path: str | Path,
    *,
    import_policy: ImportPolicy | None = None,
) -> InspectionResult:
    snapshot = load_program_snapshot(path, import_policy=import_policy)
    display_path = str(Path(path))
    return InspectionResult(
        analyze_source(
            snapshot.entry_source,
            display_path,
            import_policy=import_policy,
            source_loader=snapshot.source_for,
        ),
        snapshot.identity,
    )


def inspect_source(
    source: str,
    filename: str = "<source>",
    *,
    import_policy: ImportPolicy | None = None,
) -> InspectionResult:
    return InspectionResult(
        analyze_source(source, filename, import_policy=import_policy)
    )


def _program_hash(source: str) -> str:
    return f"sha256:{hashlib.sha256(source.encode('utf-8')).hexdigest()}"


def _direct_imports(source: str, filename: str) -> list[ImportPayload]:
    imports: list[ImportPayload] = []
    base = Path(filename).parent if filename != "<source>" else Path.cwd()
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped.startswith("USE "):
            continue
        match = re.match(r'^USE\s+"([^"]+)"', stripped)
        raw_path = (
            match.group(1)
            if match is not None
            else stripped.removeprefix("USE ").strip()
        )
        raw = Path(raw_path)
        resolved = raw if raw.is_absolute() else (base / raw).resolve()
        column = raw_line.find("USE") + 1
        imports.append(
            {
                "path": raw_path,
                "resolved": str(resolved),
                "file": filename,
                "line": line_number,
                "column": max(1, column),
            }
        )
    return imports


def _record_payload(record: RecordDefinition, fallback_filename: str) -> RecordPayload:
    return {
        "name": record.name,
        "kind": "record",
        "file": record.filename or fallback_filename,
        "line": record.line,
        "column": record.column,
        "fields": [
            _record_field_payload(field, value_type, record.field_lines, fallback_filename)
            for field, value_type in record.fields.items()
        ],
    }


def _type_alias_payload(alias: TypeAliasDefinition, fallback_filename: str) -> TypeAliasPayload:
    return {
        "name": alias.name,
        "kind": "typeAlias",
        "type": alias.value_type,
        "file": alias.filename or fallback_filename,
        "line": alias.line,
        "column": alias.column,
    }


def _variant_payload(variant: VariantDefinition, fallback_filename: str) -> OneOfRecordPayload:
    return {
        "name": variant.name,
        "kind": "oneOfRecord",
        "file": variant.filename or fallback_filename,
        "line": variant.line,
        "column": variant.column,
        "cases": [
            {
                "name": case.name,
                "file": case.filename or fallback_filename,
                "line": case.line,
                "column": case.column,
                "fields": [
                    _record_field_payload(
                        field,
                        value_type,
                        case.field_lines,
                        fallback_filename,
                    )
                    for field, value_type in case.fields.items()
                ],
            }
            for case in variant.cases.values()
        ],
    }


def _record_field_payload(
    field: str,
    value_type: str,
    field_lines: dict[str, Line],
    fallback_filename: str,
) -> RecordFieldPayload:
    line = field_lines.get(field)
    return {
        "path": field,
        "type": value_type,
        "file": getattr(line, "filename", None) or fallback_filename,
        "line": getattr(line, "number", 1),
        "column": getattr(line, "column", 1),
    }


def _contract_payload(
    binding: ContractBinding,
    fallback_filename: str,
) -> ContractPayload:
    return {
        "path": binding.path,
        "type": binding.value_type,
        "file": binding.line.filename or fallback_filename,
        "line": binding.line.number,
        "column": binding.line.column,
    }


def _behavior_payload(action: Action, fallback_filename: str) -> BehaviorPayload:
    return {
        "name": action.name,
        "signature": list(action.signature),
        "signatureText": action.signature_text,
        "parameters": _signature_parameters(action.signature),
        "contracts": {
            "inputs": dict(action.contract.inputs),
            "returns": action.contract.return_type,
        },
        "file": action.filename or fallback_filename,
        "line": action.line,
        "column": action.column,
        "length": action.length,
    }


def _request_payload(request: NamedRequest, fallback_filename: str) -> RequestPayload:
    line = request.line
    return {
        "name": request.name,
        "file": line.filename or fallback_filename,
        "line": line.number,
        "column": line.column,
        "length": line.length,
        "inputs": [
            _contract_payload(binding, fallback_filename)
            for binding in request.inputs.values()
        ],
        "outputs": [
            _contract_payload(binding, fallback_filename)
            for binding in request.outputs.values()
        ],
        "givens": len(request.givens),
        "whens": len(request.whens),
        "thens": len(request.thens),
    }


def _scenario_payload(scenario: Scenario, fallback_filename: str) -> ScenarioInspectionPayload:
    return {
        "name": scenario.name,
        "file": scenario.filename or fallback_filename,
        "line": scenario.line,
        "column": scenario.column,
        "examples": len(scenario.examples),
        "givens": len(scenario.givens),
        "whens": len(scenario.whens),
        "thens": len(scenario.thens),
    }
