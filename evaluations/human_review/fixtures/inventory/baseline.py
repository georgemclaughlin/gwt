def decide(state):
    facts = state["facts"]
    if facts["stock"] >= facts["requested"]:
        reserved = facts["requested"]
    else:
        reserved = 0
    remaining = facts["stock"] - reserved
    return {"decision": {"reserved": reserved, "remaining": remaining}}
