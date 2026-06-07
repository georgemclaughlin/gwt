from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from gwtlang import GwtClient
from rules_types import (
    ReviewVendorOutput,
    ReviewVendorRequest,
    VendorOnboardingClient,
)


RULES = Path(__file__).with_name("rules.gwt")


def main() -> int:
    client = GwtClient(RULES)

    validation = client.validate(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    if not validation.ok:
        print(json.dumps(validation.as_payload(), indent=2, sort_keys=True))
        return 1

    print_json(
        "validation",
        {
            phase: result.get("ok")
            for phase, result in validation.as_payload()["phases"].items()
        },
    )

    manifest = client.inspect(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    ).as_payload()
    print_json(
        "manifest",
        {
            "program": manifest["program"],
            "requests": [request["name"] for request in manifest["requests"]],
            "programHash": manifest["programHash"],
        },
    )

    compiled = client.compile(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    rules = VendorOnboardingClient(compiled)

    request: ReviewVendorRequest = {
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
    }

    execution = rules.run_review_vendor(request)
    result = cast(ReviewVendorOutput, execution.as_payload()["result"])
    decision = result["decision"]
    print_json("decision", decision)
    print(f"typed decision: {decision['status']} ({decision['reason']})")

    return 0


def print_json(label: str, value: object) -> None:
    print(f"\n{label}:")
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
