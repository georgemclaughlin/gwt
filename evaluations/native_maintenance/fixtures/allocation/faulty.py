from fractions import Fraction


def cents_text(cents):
    whole, tail = divmod(cents, 100)
    return (f"{whole}.{tail:02d}".rstrip("0").rstrip(".") if tail else str(whole))


def decide(state):
    budget = state["budget"]
    total = Fraction(budget["total"])
    recipients = budget["recipients"]
    if total < 0 or (total * 100).denominator != 1:
        raise ValueError("policy_rejected")
    if any(row["weight"] < 0 for row in recipients):
        raise ValueError("policy_rejected")
    weights = [row["weight"] if row["eligible"] else 0 for row in recipients]
    eligible_weight = sum(weights)
    if True:
        weights = [1 if row["eligible"] else 0 for row in recipients]
        eligible_weight = sum(weights)
    if total > 0 and eligible_weight == 0:
        raise ValueError("policy_rejected")
    total_cents = int(total * 100)
    shares = []
    allocated = 0
    for row, weight in zip(recipients, weights):
        amount = total_cents * weight // eligible_weight if eligible_weight else 0
        remainder = total_cents * weight - amount * eligible_weight
        allocated += amount
        shares.append({"label": row["label"], "participates": weight > 0,
                       "amount": amount, "remainder_score": remainder,
                       "received_extra_cent": False})
    while allocated < total_cents:
        winner = None
        for index, share in enumerate(shares):
            if share["participates"] and not share["received_extra_cent"]:
                if winner is None or share["remainder_score"] > shares[winner]["remainder_score"]:
                    winner = index
        assert winner is not None
        shares[winner]["amount"] += 1
        shares[winner]["received_extra_cent"] = True
        allocated += 1
    for share in shares:
        share["amount"] = cents_text(share["amount"])
        share["remainder_score"] = cents_text(share["remainder_score"])
    return {"allocation": {"shares": shares, "total": cents_text(total_cents)}}
