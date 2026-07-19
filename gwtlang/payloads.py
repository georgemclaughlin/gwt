from __future__ import annotations

from typing import TYPE_CHECKING, Literal, NotRequired, Required, TypeAlias, TypedDict

if TYPE_CHECKING:
    from .program_identity import ProgramIdentityPayload


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
    subcode: str
    expected: str
    actual: str
    help: str
    candidates: list[str]


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
    records: int
    typeAliases: int
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


class TypeAliasPayload(TypedDict):
    name: str
    kind: Literal["typeAlias"]
    type: str
    file: str
    line: int
    column: int


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
    typeAliases: int
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
    programHashScope: Literal["entry-source"]
    programIdentity: ProgramIdentityPayload | None
    imports: list[ImportPayload]
    diagnostics: list[DiagnosticPayload]
    records: list[RecordPayload]
    typeAliases: list[TypeAliasPayload]
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


class ExecutionCaseSourcePayload(TypedDict):
    file: str
    line: int
    column: int
    text: str


class ExecutionCaseModuleIdentityPayload(TypedDict):
    specifier: str
    digest: str
    imports: list[str]


class ExecutionCaseProgramIdentityPayload(TypedDict):
    algorithm: Literal["gwt-program-closure-sha256-v1"]
    entry: str
    digest: str
    modules: list[ExecutionCaseModuleIdentityPayload]


class ExecutionCaseProgramPayload(TypedDict):
    name: str | None
    file: str
    hash: str
    hashScope: Literal["dependency-closure"]
    importsDetected: bool
    importsIncludedInHash: bool
    identity: ExecutionCaseProgramIdentityPayload
    limitations: list[str]


class ExecutionCaseVersionsPayload(TypedDict):
    packageName: str
    packageVersion: str
    languageSpecVersion: str
    payloadSchemaVersion: int


class ExecutionCaseRequestPayload(TypedDict):
    name: str
    input: JsonObject
    inputFile: str | None


class ExecutionCaseFactProvenancePayload(TypedDict, total=False):
    path: Required[str]
    source: Required[str]
    description: str


class ExecutionCaseNamedValuePayload(TypedDict):
    path: str
    value: JsonValue


class ExecutionCaseValueMarkerPayload(TypedDict):
    availability: Literal["redacted", "unavailable"]


class ExecutionCaseSelectedDecisionPayload(TypedDict):
    condition: str
    result: bool
    source: ExecutionCaseSourcePayload | None


class ExecutionCaseErrorPayload(TypedDict):
    kind: Literal["GwtError"]
    code: Literal["execution-failed"]
    stage: Literal["parse", "execute"]
    message: str
    messageAvailability: Literal["available", "redacted"]
    source: ExecutionCaseSourcePayload | None


class ExecutionCaseCapturePolicyPayload(TypedDict):
    onError: Literal["raise", "record"]
    values: Literal["full", "omit"]


class ExecutionCaseExecutionPayload(TypedDict, total=False):
    outcome: Required[Literal["completed", "failed"]]
    traceId: Required[str]
    capturedAt: Required[str]
    executionBudget: Required[int | None]
    maxCallDepth: Required[int | None]
    capturePolicy: Required[ExecutionCaseCapturePolicyPayload]
    status: Required[
        ExecutionCaseNamedValuePayload | ExecutionCaseValueMarkerPayload | None
    ]
    reason: Required[
        ExecutionCaseNamedValuePayload | ExecutionCaseValueMarkerPayload | None
    ]
    selectedDecision: Required[ExecutionCaseSelectedDecisionPayload | None]
    error: ExecutionCaseErrorPayload


class ExecutionCaseOperandPayload(TypedDict):
    name: str
    valueType: str
    value: JsonValue


class ExecutionCaseOperandsPayload(TypedDict, total=False):
    availability: Required[Literal["available", "unavailable", "redacted"]]
    values: list[ExecutionCaseOperandPayload]
    reason: str


class ExecutionCaseEvidencePayload(TypedDict, total=False):
    sequence: Required[int]
    kind: Required[
        Literal["contract", "condition", "branch", "assertion", "behavior"]
    ]
    summary: Required[str]
    source: Required[ExecutionCaseSourcePayload | None]
    label: str
    path: str
    valueType: str
    expression: str
    result: bool
    branchKind: str
    branchLabel: str
    selected: bool
    startLine: int
    endLine: int
    operands: ExecutionCaseOperandsPayload
    phase: Literal["enter", "exit"]
    signature: str
    callId: str
    parentCallId: str | None
    depth: int
    behaviorOutcome: Literal["completed", "failed"]


class ExecutionCaseValuePayload(TypedDict, total=False):
    present: Required[bool]
    value: JsonValue


ExecutionCaseStateValuePayload: TypeAlias = (
    ExecutionCaseValuePayload | ExecutionCaseValueMarkerPayload
)


class ExecutionCaseStateChangePayload(TypedDict):
    sequence: int
    path: str
    pointer: str
    operation: str
    before: ExecutionCaseStateValuePayload
    after: ExecutionCaseStateValuePayload
    patch: list[JsonObject]
    source: ExecutionCaseSourcePayload | None


class ExecutionCaseValueAvailabilityPayload(TypedDict):
    programFile: Literal["available", "redacted"]
    requestInputFile: Literal["available", "absent", "redacted"]
    requestInput: Literal["available", "redacted"]
    result: Literal["available", "redacted", "unavailable"]
    stateChangeValues: Literal["available", "redacted"]
    operandValues: Literal["available-or-unavailable", "redacted"]


class ExecutionCaseRedactionPayload(TypedDict, total=False):
    mode: Required[Literal["none", "omit-values"]]
    valuesIncluded: Required[bool]
    redactedPaths: Required[list[str]]
    availability: Required[ExecutionCaseValueAvailabilityPayload]


class ExecutionCaseIntegrityPayload(TypedDict):
    algorithm: Literal["gwt-execution-case-sha256-v1"]
    scope: Literal["artifact-without-integrity"]
    digest: str


class ExecutionCasePayload(TypedDict):
    schemaVersion: int
    kind: Literal["gwt.execution-case"]
    program: ExecutionCaseProgramPayload
    versions: ExecutionCaseVersionsPayload
    request: ExecutionCaseRequestPayload
    factProvenance: NotRequired[list[ExecutionCaseFactProvenancePayload]]
    result: JsonObject
    execution: ExecutionCaseExecutionPayload
    evidence: list[ExecutionCaseEvidencePayload]
    stateChanges: list[ExecutionCaseStateChangePayload]
    redaction: ExecutionCaseRedactionPayload
    integrity: ExecutionCaseIntegrityPayload
