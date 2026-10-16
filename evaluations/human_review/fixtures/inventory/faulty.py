def decide(state):
    facts = state["facts"]
    if facts["stock"] >= facts["requested"]:
        reserved = facts["requested"]
    else:
        reserved = facts["stock"]
    remaining = facts["stock"] - facts["requested"]
    return {"decision": {"reserved": reserved, "remaining": remaining}}
