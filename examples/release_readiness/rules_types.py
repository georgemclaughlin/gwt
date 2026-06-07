# Generated from examples/release_readiness/rules.gwt. Do not edit by hand.
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, TypeAlias, TypedDict, cast

from gwtlang import CompiledProgram, ExecutionResult, compile_file

ReleaseEnvironment: TypeAlias = Literal['staging', 'production']

ReleaseStatus: TypeAlias = Literal['new', 'approved', 'needs_review', 'blocked']

ReleaseReason: TypeAlias = Literal['new', 'ready', 'failing_checks', 'missing_evidence', 'missing_approval', 'missing_rollback', 'active_incident', 'risky_flags']

CheckStatus: TypeAlias = Literal['passed', 'failed', 'skipped']

ApprovalStatus: TypeAlias = Literal['approved', 'missing']

class ReleaseCheck(TypedDict):
    name: str
    required: bool
    status: CheckStatus

class ReleaseApproval(TypedDict):
    name: str
    required: bool
    status: ApprovalStatus

class FeatureFlag(TypedDict):
    name: str
    enabled: bool
    risky: bool

class ReleaseRequest(TypedDict):
    version: str
    environment: ReleaseEnvironment
    rollback_plan_present: bool
    active_incident_count: int
    checks: list[ReleaseCheck]
    approvals: list[ReleaseApproval]
    feature_flags: list[FeatureFlag]

class ReleaseDecision(TypedDict):
    status: ReleaseStatus
    reason: ReleaseReason
    blockers: list[str]
    warnings: list[str]
    ready_checks: int
    failed_checks: int
    missing_approval_count: int

class ReviewReleaseRequest(TypedDict):
    release: ReleaseRequest

class ReviewReleaseOutput(TypedDict):
    decision: ReleaseDecision

GwtRequestName: TypeAlias = Literal['review release']
GwtRequest: TypeAlias = ReviewReleaseRequest
GwtOutput: TypeAlias = ReviewReleaseOutput

REVIEW_RELEASE_REQUEST: GwtRequestName = 'review release'

GwtRequests = TypedDict(
    'GwtRequests',
    {
        'review release': ReviewReleaseRequest,
    },
)

GwtOutputs = TypedDict(
    'GwtOutputs',
    {
        'review release': ReviewReleaseOutput,
    },
)

class ReleaseReadinessClient:
    def __init__(self, program: CompiledProgram) -> None:
        self._program = program

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        import_roots: Iterable[str | Path] | None = None,
        allow_absolute_imports: bool = True,
    ) -> ReleaseReadinessClient:
        return cls(
            compile_file(
                path,
                import_roots=import_roots,
                allow_absolute_imports=allow_absolute_imports,
            )
        )

    def run_review_release(self, request: ReviewReleaseRequest) -> ExecutionResult:
        return self._program.run_json(
            cast(dict[str, Any], request),
            request=REVIEW_RELEASE_REQUEST,
        )

    def review_release(self, request: ReviewReleaseRequest) -> ReviewReleaseOutput:
        return cast(
            ReviewReleaseOutput,
            self.run_review_release(request).as_payload()["result"],
        )
