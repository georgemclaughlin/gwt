from __future__ import annotations

from typing import Literal, NotRequired, TypeAlias, TypedDict


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class PositionPayload(TypedDict):
    line: int
    character: int


class RangePayload(TypedDict):
    start: PositionPayload
    end: PositionPayload


class SourceRangePayload(TypedDict):
    file: str
    line: int
    column: int
    length: int
    range: RangePayload


class DiagnosticPayload(SourceRangePayload, total=False):
    code: str
    severity: str
    source: str
    path: str
    category: str
    message: str
    expected: str
    actual: str
    help: str


class ScenarioExecutionPayload(TypedDict):
    name: str
    state: JsonValue
    result: JsonValue
    output: JsonValue


class ExecutionPayload(TypedDict):
    ok: bool
    file: str | None
    request_file: str | None
    scenario_count: int
    scenarios: list[ScenarioExecutionPayload]
    state: JsonValue
    result: JsonValue
    output: JsonValue


class SymbolPayload(SourceRangePayload, total=False):
    name: str
    kind: str
    detail: str
    container: str


class AnalysisPayload(TypedDict):
    schemaVersion: int
    file: str
    program: str | None
    requests: int
    dtos: int
    behaviors: int
    scenarios: int
    diagnostics: list[DiagnosticPayload]
    symbols: list[SymbolPayload]


class CompletionItemPayload(TypedDict):
    label: str
    kind: int
    detail: NotRequired[str]


class DebugLinePayload(TypedDict):
    file: str
    line: int
    column: int
    text: str


class CheckPayload(AnalysisPayload):
    ok: bool


class CompiledProgramPayload(TypedDict):
    ok: bool
    file: str
    source_hash: str
    diagnostics: list[DiagnosticPayload]


class ImportPayload(TypedDict):
    path: str
    resolved: str
    file: str
    line: int
    column: int


class RecordFieldPayload(TypedDict):
    path: str
    type: str
    file: str
    line: int
    column: int


class RecordPayload(TypedDict):
    name: str
    kind: Literal["record"]
    file: str
    line: int
    column: int
    fields: list[RecordFieldPayload]


class OneOfRecordCasePayload(TypedDict):
    name: str
    file: str
    line: int
    column: int
    fields: list[RecordFieldPayload]


class OneOfRecordPayload(TypedDict):
    name: str
    kind: Literal["oneOfRecord"]
    file: str
    line: int
    column: int
    cases: list[OneOfRecordCasePayload]


class ContractPayload(TypedDict):
    path: str
    type: str
    file: str
    line: int
    column: int


class BehaviorContractsPayload(TypedDict):
    inputs: dict[str, str]
    returns: str | None


class BehaviorPayload(TypedDict):
    name: str
    signature: list[str]
    signatureText: str
    parameters: list[str]
    contracts: BehaviorContractsPayload
    file: str
    line: int
    column: int
    length: int


class RequestPayload(TypedDict):
    name: str
    file: str
    line: int
    column: int
    length: int
    inputs: list[ContractPayload]
    outputs: list[ContractPayload]
    givens: int
    whens: int
    thens: int


class ScenarioInspectionPayload(TypedDict):
    name: str
    file: str
    line: int
    column: int
    examples: int
    givens: int
    whens: int
    thens: int


class InspectionCountsPayload(TypedDict):
    records: int
    oneOfRecords: int
    requests: int
    behaviors: int
    scenarios: int


class InspectionPayload(TypedDict):
    schemaVersion: int
    ok: bool
    file: str
    program: str | None
    programHash: str
    imports: list[ImportPayload]
    diagnostics: list[DiagnosticPayload]
    records: list[RecordPayload]
    oneOfRecords: list[OneOfRecordPayload]
    requests: list[RequestPayload]
    behaviors: list[BehaviorPayload]
    scenarios: list[ScenarioInspectionPayload]
    counts: InspectionCountsPayload


class ValidationPhasePayload(TypedDict):
    checked: bool
    ok: bool
    diagnostics: NotRequired[list[DiagnosticPayload]]
    changed: NotRequired[bool | None]
    skipped: NotRequired[str]
    scenario_count: NotRequired[int]


class ValidationPayload(TypedDict):
    schemaVersion: int
    ok: bool
    file: str
    program: str | None
    phases: dict[str, ValidationPhasePayload]
    diagnostics: list[DiagnosticPayload]
