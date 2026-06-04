from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path

from .entries import entry_candidates
from .runtime import (
    Action,
    ContractBinding,
    DtoDefinition,
    ImportPolicy,
    Line,
    Scenario,
    VariantDefinition,
    _signature_parameters,
)
from .service import Analysis, analyze_file, analyze_source

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class InspectionResult:
    analysis: Analysis

    @property
    def ok(self) -> bool:
        return not any(
            diagnostic.severity == "error" for diagnostic in self.analysis.diagnostics
        )

    def as_payload(self) -> dict[str, object]:
        analysis = self.analysis
        program = analysis.program
        payload: dict[str, object] = {
            "schemaVersion": SCHEMA_VERSION,
            "ok": self.ok,
            "file": analysis.filename,
            "program": program.name if program is not None else None,
            "programHash": _program_hash(analysis.source),
            "imports": _direct_imports(analysis.source, analysis.filename),
            "diagnostics": [
                diagnostic.as_payload(analysis.filename)
                for diagnostic in analysis.diagnostics
            ],
            "records": [],
            "oneOfRecords": [],
            "request": [],
            "output": [],
            "behaviors": [],
            "entryCandidates": [],
            "scenarios": [],
            "counts": {
                "records": 0,
                "oneOfRecords": 0,
                "requestBindings": 0,
                "outputBindings": 0,
                "behaviors": 0,
                "entryCandidates": 0,
                "scenarios": 0,
            },
        }
        if program is None:
            return payload

        records = [_record_payload(dto, analysis.filename) for dto in program.dtos.values()]
        variants = [
            _variant_payload(variant, analysis.filename)
            for variant in program.variants.values()
        ]
        request = [
            _contract_payload(binding, analysis.filename)
            for binding in program.inputs.values()
        ]
        output = [
            _contract_payload(binding, analysis.filename)
            for binding in program.outputs.values()
        ]
        behaviors = [
            _behavior_payload(action, analysis.filename)
            for action in program.actions
        ]
        entries = [
            candidate.as_payload(analysis.filename)
            for candidate in entry_candidates(program)
        ]
        scenarios = [
            _scenario_payload(scenario, analysis.filename)
            for scenario in program.scenarios
        ]

        payload.update(
            {
                "records": records,
                "oneOfRecords": variants,
                "request": request,
                "output": output,
                "behaviors": behaviors,
                "entryCandidates": entries,
                "scenarios": scenarios,
                "counts": {
                    "records": len(records),
                    "oneOfRecords": len(variants),
                    "requestBindings": len(request),
                    "outputBindings": len(output),
                    "behaviors": len(behaviors),
                    "entryCandidates": len(entries),
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
    return InspectionResult(analyze_file(path, import_policy=import_policy))


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


def _direct_imports(source: str, filename: str) -> list[dict[str, object]]:
    imports: list[dict[str, object]] = []
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


def _record_payload(dto: DtoDefinition, fallback_filename: str) -> dict[str, object]:
    return {
        "name": dto.name,
        "kind": "record",
        "file": dto.filename or fallback_filename,
        "line": dto.line,
        "column": dto.column,
        "fields": [
            _record_field_payload(field, value_type, dto.field_lines, fallback_filename)
            for field, value_type in dto.fields.items()
        ],
    }


def _variant_payload(variant: VariantDefinition, fallback_filename: str) -> dict[str, object]:
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
) -> dict[str, object]:
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
) -> dict[str, object]:
    return {
        "path": binding.path,
        "type": binding.value_type,
        "file": binding.line.filename or fallback_filename,
        "line": binding.line.number,
        "column": binding.line.column,
    }


def _behavior_payload(action: Action, fallback_filename: str) -> dict[str, object]:
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


def _scenario_payload(scenario: Scenario, fallback_filename: str) -> dict[str, object]:
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
