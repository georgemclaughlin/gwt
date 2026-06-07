# Generated from examples/vendor_onboarding/rules.gwt. Do not edit by hand.
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, TypeAlias, TypedDict, cast

from gwtlang import CompiledProgram, ExecutionResult, compile_file

class VendorDocument(TypedDict):
    name: str
    status: Literal['provided', 'missing', 'expired']

class VendorRiskSignal(TypedDict):
    name: str
    severity: Literal['low', 'medium', 'high']
    points: int | float

class VendorRequest(TypedDict):
    vendor_name: str
    country: str
    annual_spend: int | float
    handles_customer_data: bool
    stores_payment_data: bool
    documents: list[VendorDocument]
    risk_signals: list[VendorRiskSignal]

class VendorDecision(TypedDict):
    required_document_count: int | float
    missing_document_count: int | float
    expired_document_count: int | float
    high_signal_count: int | float
    risk_points: int | float
    missing_requirements: list[str]
    reasons: list[str]
    data_review_required: bool
    tier: Literal['new', 'standard', 'critical']
    status: Literal['new', 'approved', 'needs_review', 'rejected']
    reason: Literal['new', 'ready_to_onboard', 'manual_review_required', 'high_risk_signal', 'risk_too_high']

class ReviewVendorRequest(TypedDict):
    vendor: VendorRequest

class ReviewVendorOutput(TypedDict):
    decision: VendorDecision

GwtRequestName: TypeAlias = Literal['review vendor']
GwtRequest: TypeAlias = ReviewVendorRequest
GwtOutput: TypeAlias = ReviewVendorOutput

REVIEW_VENDOR_REQUEST: GwtRequestName = 'review vendor'

GwtRequests = TypedDict(
    'GwtRequests',
    {
        'review vendor': ReviewVendorRequest,
    },
)

GwtOutputs = TypedDict(
    'GwtOutputs',
    {
        'review vendor': ReviewVendorOutput,
    },
)

class VendorOnboardingClient:
    def __init__(self, program: CompiledProgram) -> None:
        self._program = program

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        import_roots: Iterable[str | Path] | None = None,
        allow_absolute_imports: bool = True,
    ) -> VendorOnboardingClient:
        return cls(
            compile_file(
                path,
                import_roots=import_roots,
                allow_absolute_imports=allow_absolute_imports,
            )
        )

    def run_review_vendor(self, request: ReviewVendorRequest) -> ExecutionResult:
        return self._program.run_json(
            cast(dict[str, Any], request),
            request=REVIEW_VENDOR_REQUEST,
        )

    def review_vendor(self, request: ReviewVendorRequest) -> ReviewVendorOutput:
        return cast(
            ReviewVendorOutput,
            self.run_review_vendor(request).as_payload()["result"],
        )
