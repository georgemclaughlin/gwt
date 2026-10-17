def decide(state):
    facts = state["facts"]
    if facts["subtotal"] >= 120:
        fee = 0
    else:
        fee = 5
    if facts["express"] and fee > 0:
        fee += 10
    return {"decision": {"fee": fee}}
