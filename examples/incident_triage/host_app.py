from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from gwtlang import GwtClient
from rules_types import (
    IncidentTriagePilotClient,
    TriageIncidentOutput,
    TriageIncidentRequest,
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

    compiled = client.compile(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    rules = IncidentTriagePilotClient(compiled)

    request = cast(TriageIncidentRequest, json.loads(REQUEST.read_text()))
    execution = rules.run_triage_incident(request)
    result = cast(TriageIncidentOutput, execution.as_payload()["result"])
    decision = result["decision"]

    print(json.dumps(decision, indent=2, sort_keys=True))
    print(f"typed decision: {decision['status']} ({decision['reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
