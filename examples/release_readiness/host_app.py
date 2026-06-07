from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from gwtlang import GwtClient
from rules_types import (
    ReleaseReadinessClient,
    ReviewReleaseOutput,
    ReviewReleaseRequest,
)


RULES = Path(__file__).with_name("rules.gwt")
REQUEST = Path(__file__).with_name("request.json")


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
    rules = ReleaseReadinessClient(compiled)

    request = cast(ReviewReleaseRequest, json.loads(REQUEST.read_text()))
    execution = rules.run_review_release(request)
    result = cast(ReviewReleaseOutput, execution.as_payload()["result"])
    decision = result["decision"]

    print_json("decision", decision)
    print(f"typed decision: {decision['status']} ({decision['reason']})")

    return 0


def print_json(label: str, value: object) -> None:
    print(f"\n{label}:")
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
