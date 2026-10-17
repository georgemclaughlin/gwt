def decide(state):
    facts = state["facts"]
    if not facts["receipt"]:
        status = "review"
    elif facts["defective"] and facts["days"] <= 44:
        status = "refund"
    elif not facts["defective"] and facts["days"] <= 14:
        status = "refund"
    else:
        status = "deny"
    return {"decision": {"status": status}}
