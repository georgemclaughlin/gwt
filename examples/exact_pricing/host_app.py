from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

from gwtlang import GwtClient, GwtError


RULES = Path(__file__).with_name("rules.gwt")
EXPORT_NAME = "price_cart_v1"


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
    print_json("public entries", manifest["entryCandidates"])

    rules = client.compile(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )

    request = {
        "cart": {
            "mode": "reserve",
            "quantity": 2,
            "unit_price": "12.30",
            "total": "0.00",
            "status": "pending",
        }
    }
    execution = rules.call_json(EXPORT_NAME, request)
    print_json("result payload", execution.as_payload()["result"])

    total = execution.state["cart"]["total"]
    print(f"runtime total: {total} ({type(total).__name__})")

    try:
        bad_request = {
            "cart": {
                "mode": "reserve",
                "quantity": 2,
                "unit_price": 12.30,
                "total": "0.00",
                "status": "pending",
            }
        }
        rules.call_json(EXPORT_NAME, bad_request)
    except GwtError as exc:
        print(f"float input rejected: {exc}")

    prevalidated_state = {
        "cart": {
            "mode": "quote",
            "quantity": 3,
            "unit_price": Decimal("9.99"),
            "total": Decimal("0.00"),
            "status": "pending",
        }
    }
    trusted = rules.call_trusted_json(EXPORT_NAME, prevalidated_state)
    print_json("trusted prevalidated payload", trusted.as_payload()["result"])

    return 0


def print_json(label: str, value: object) -> None:
    print(f"\n{label}:")
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
