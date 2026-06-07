from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from gwtlang import GwtClient
from rules_types import (
    ReviewVendorOutput,
    ReviewVendorRequest,
    VendorDecision,
    VendorOnboardingClient,
)


RULES = Path(__file__).with_name("rules.gwt")


@dataclass(frozen=True)
class DecisionProjection:
    status: str
    reason: str
    tier: str
    risk_points: int | float
    missing_requirements: tuple[str, ...]


@dataclass(frozen=True)
class ShadowCase:
    name: str
    request: ReviewVendorRequest


@dataclass(frozen=True)
class ShadowResult:
    name: str
    matched: bool
    legacy: DecisionProjection
    gwt: DecisionProjection
    differences: tuple[str, ...]


def main() -> int:
    client = GwtClient(RULES)
    validation = client.validate(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    if not validation.ok:
        print(json.dumps(validation.as_payload(), indent=2, sort_keys=True))
        return 1

    rules = VendorOnboardingClient(
        client.compile(
            import_roots=[RULES.parent],
            allow_absolute_imports=False,
        )
    )
    results = [run_shadow_case(rules, case) for case in shadow_cases()]
    print_shadow_report(results)
    return 0


def run_shadow_case(rules: VendorOnboardingClient, case: ShadowCase) -> ShadowResult:
    legacy = legacy_review_vendor(case.request)
    gwt = gwt_review_vendor(rules, case.request)
    differences = compare_decisions(legacy, gwt)
    return ShadowResult(
        case.name,
        matched=len(differences) == 0,
        legacy=legacy,
        gwt=gwt,
        differences=tuple(differences),
    )


def legacy_review_vendor(request: ReviewVendorRequest) -> DecisionProjection:
    vendor = request["vendor"]
    required_documents = ["tax_form", "insurance"]
    if vendor["handles_customer_data"]:
        required_documents.append("security_questionnaire")
    if vendor["stores_payment_data"]:
        required_documents.append("pci_attestation")

    document_status = {
        document["name"]: document["status"]
        for document in vendor["documents"]
    }
    missing_requirements: list[str] = []
    risk_points: int | float = 0
    high_signal_count = 0
    tier = "standard"

    for document_name in required_documents:
        status = document_status.get(document_name)
        if status == "provided" or status == "expired":
            continue
        missing_requirements.append(document_name)
        risk_points += 2

    if vendor["annual_spend"] >= 100000:
        risk_points += 2
        tier = "critical"
    if vendor["handles_customer_data"]:
        risk_points += 2
    if vendor["stores_payment_data"]:
        risk_points += 5
        tier = "critical"

    for signal in vendor["risk_signals"]:
        risk_points += signal["points"]
        if signal["severity"] == "high":
            high_signal_count += 1

    if high_signal_count > 0:
        return DecisionProjection(
            "rejected",
            "high_risk_signal",
            tier,
            risk_points,
            tuple(missing_requirements),
        )
    if risk_points >= 12:
        return DecisionProjection(
            "rejected",
            "risk_too_high",
            tier,
            risk_points,
            tuple(missing_requirements),
        )
    if missing_requirements or risk_points >= 6:
        return DecisionProjection(
            "needs_review",
            "manual_review_required",
            tier,
            risk_points,
            tuple(missing_requirements),
        )
    return DecisionProjection(
        "approved",
        "ready_to_onboard",
        tier,
        risk_points,
        tuple(missing_requirements),
    )


def gwt_review_vendor(
    rules: VendorOnboardingClient,
    request: ReviewVendorRequest,
) -> DecisionProjection:
    output: ReviewVendorOutput = rules.review_vendor(request)
    decision: VendorDecision = output["decision"]
    return DecisionProjection(
        decision["status"],
        decision["reason"],
        decision["tier"],
        decision["risk_points"],
        tuple(decision["missing_requirements"]),
    )


def compare_decisions(
    legacy: DecisionProjection,
    gwt: DecisionProjection,
) -> list[str]:
    differences: list[str] = []
    if legacy.status != gwt.status:
        differences.append(f"status legacy={legacy.status} gwt={gwt.status}")
    if legacy.reason != gwt.reason:
        differences.append(f"reason legacy={legacy.reason} gwt={gwt.reason}")
    if legacy.tier != gwt.tier:
        differences.append(f"tier legacy={legacy.tier} gwt={gwt.tier}")
    if legacy.risk_points != gwt.risk_points:
        differences.append(f"risk_points legacy={legacy.risk_points} gwt={gwt.risk_points}")
    if legacy.missing_requirements != gwt.missing_requirements:
        differences.append(
            "missing_requirements "
            f"legacy={list(legacy.missing_requirements)} "
            f"gwt={list(gwt.missing_requirements)}"
        )
    return differences


def print_shadow_report(results: list[ShadowResult]) -> None:
    print("shadow mode comparison:")
    for result in results:
        label = "MATCH" if result.matched else "MISMATCH"
        print(f"- {label} {result.name}")
        for difference in result.differences:
            print(f"  {difference}")

    mismatch_count = sum(1 for result in results if not result.matched)
    print_json(
        "summary",
        {
            "cases": len(results),
            "matches": len(results) - mismatch_count,
            "mismatches": mismatch_count,
            "promotion_ready": mismatch_count == 0,
        },
    )


def print_json(label: str, value: object) -> None:
    print(f"\n{label}:")
    print(json.dumps(value, indent=2, sort_keys=True))


def shadow_cases() -> list[ShadowCase]:
    return [
        ShadowCase(
            "low risk vendor stays approved",
            {
                "vendor": {
                    "vendor_name": "Northwind Office Supplies",
                    "country": "US",
                    "annual_spend": 25000,
                    "handles_customer_data": False,
                    "stores_payment_data": False,
                    "documents": [
                        {"name": "tax_form", "status": "provided"},
                        {"name": "insurance", "status": "provided"},
                    ],
                    "risk_signals": [],
                }
            },
        ),
        ShadowCase(
            "expired insurance exposes legacy gap",
            {
                "vendor": {
                    "vendor_name": "Cloud Ledger",
                    "country": "US",
                    "annual_spend": 125000,
                    "handles_customer_data": True,
                    "stores_payment_data": False,
                    "documents": [
                        {"name": "tax_form", "status": "provided"},
                        {"name": "insurance", "status": "expired"},
                        {"name": "security_questionnaire", "status": "missing"},
                    ],
                    "risk_signals": [
                        {"name": "new_vendor", "severity": "low", "points": 1},
                        {"name": "data_region", "severity": "medium", "points": 2},
                    ],
                }
            },
        ),
    ]


if __name__ == "__main__":
    raise SystemExit(main())
