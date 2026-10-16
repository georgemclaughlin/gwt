"""Deterministic refund decision over normalized host facts."""


def decide(state: dict) -> dict:
    facts = state["facts"]
    if facts["damaged"]:
        return {"decision": {"status": "approved", "reason": "damaged"}}
    if not facts["receipt"]:
        return {"decision": {"status": "rejected", "reason": "missing_receipt"}}
    if facts["days"] <= 30:
        return {"decision": {"status": "approved", "reason": "within_window"}}
    return {"decision": {"status": "rejected", "reason": "expired"}}
