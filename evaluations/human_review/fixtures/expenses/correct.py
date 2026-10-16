def decide(state):
    facts = state["facts"]
    status = "approved"
    total = 0
    for line in facts["lines"]:
        if line["amount"] > facts["limit"]:
            status = "review"
        if line["reimbursable"] and line["amount"] <= facts["limit"]:
            total += line["amount"]
    return {"decision": {"status": status, "total": total}}
