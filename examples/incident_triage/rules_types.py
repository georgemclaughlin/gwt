# Generated from examples/incident_triage/rules.gwt. Do not edit by hand.
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, TypeAlias, TypedDict, cast

from gwtlang import CompiledProgram, ExecutionResult, compile_file

IncidentSeverity: TypeAlias = Literal['low', 'medium', 'high', 'critical']

IncidentStatus: TypeAlias = Literal['new', 'watch', 'investigate', 'page', 'major_incident']

IncidentReason: TypeAlias = Literal['new', 'low_impact', 'runbook_missing', 'customer_impact', 'critical_system_down', 'security_signal']

class IncidentSignal(TypedDict):
    name: str
    severity: Literal['low', 'medium', 'high']
    active: bool

class IncidentRequest(TypedDict):
    incident_id: str
    service: str
    severity: IncidentSeverity
    customer_count: int
    revenue_at_risk: bool
    security_related: bool
    runbook_present: bool
    minutes_open: int
    signals: list[IncidentSignal]

class TriageDecision(TypedDict):
    status: IncidentStatus
    reason: IncidentReason
    escalation_level: int
    page_on_call: bool
    open_major_incident: bool
    required_actions: list[str]
    active_signal_count: int
    high_signal_count: int

class TriageIncidentRequest(TypedDict):
    incident: IncidentRequest

class TriageIncidentOutput(TypedDict):
    decision: TriageDecision

GwtRequestName: TypeAlias = Literal['triage incident']
GwtRequest: TypeAlias = TriageIncidentRequest
GwtOutput: TypeAlias = TriageIncidentOutput

TRIAGE_INCIDENT_REQUEST: GwtRequestName = 'triage incident'

GwtRequests = TypedDict(
    'GwtRequests',
    {
        'triage incident': TriageIncidentRequest,
    },
)

GwtOutputs = TypedDict(
    'GwtOutputs',
    {
        'triage incident': TriageIncidentOutput,
    },
)

class IncidentTriagePilotClient:
    def __init__(self, program: CompiledProgram) -> None:
        self._program = program

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        import_roots: Iterable[str | Path] | None = None,
        allow_absolute_imports: bool = True,
    ) -> IncidentTriagePilotClient:
        return cls(
            compile_file(
                path,
                import_roots=import_roots,
                allow_absolute_imports=allow_absolute_imports,
            )
        )

    def run_triage_incident(self, request: TriageIncidentRequest) -> ExecutionResult:
        return self._program.run_json(
            cast(dict[str, Any], request),
            request=TRIAGE_INCIDENT_REQUEST,
        )

    def triage_incident(self, request: TriageIncidentRequest) -> TriageIncidentOutput:
        return cast(
            TriageIncidentOutput,
            self.run_triage_incident(request).as_payload()["result"],
        )
