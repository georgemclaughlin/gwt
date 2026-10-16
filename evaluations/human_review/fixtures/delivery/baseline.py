def decide(state):
    facts = state["facts"]
    if facts["subtotal"] >= 100:
        fee = 0
    else:
        fee = 5
    if facts["express"]:
        fee += 10
    return {"decision": {"fee": fee}}
