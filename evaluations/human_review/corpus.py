"""Facilitator-only task definitions and independent integer-domain oracles.

Do not distribute this file with participant packets. These small constructed
tasks test source review, not production adoption or the explanation workbench.
"""
from itertools import product
from pathlib import Path

FIXTURES = Path(__file__).with_name("fixtures")
DOMAINS = ("refund", "delivery", "expenses", "inventory")
REVISIONS = ("baseline", "correct", "faulty")
GUIDES = {
    "gwt": (
        "RECORD declares fields. REQUEST supplies facts, initializes decision, "
        "calls a WHEN behavior, and exposes OUTPUT. GIVEN/AND in a behavior "
        "declare its parameter types. set replaces a value; add increases it. "
        "DECIDE takes the first matching WHEN, or ELSE. IF/ELSE selects a branch; "
        "separate IF statements are evaluated independently. FOR visits every "
        "list item in order. Dotted paths access fields. and, not, <= and >= "
        "have their ordinary logical/comparison meanings. Indentation groups steps."
    ),
    "python": (
        "def declares a function. state supplies facts; decide returns decision. "
        "Square brackets access dictionary fields. = assigns a value; += "
        "increases it. if/elif/else takes the first matching branch; separate "
        "if statements are evaluated independently. for visits every list item "
        "in order. and, not, <= and >= have their ordinary logical/comparison "
        "meanings. Indentation groups statements. Curly braces construct dictionaries."
    ),
}

TASKS = {
    "refund": {
        "title": "Refund eligibility",
        "policy": "Without a receipt, send the claim for review regardless of age or defect. "
                  "With a receipt, refund defective goods through day 30 inclusive and "
                  "nondefective goods through day 14 inclusive. Deny other claims.",
        "change": "Extend only the defective-goods deadline to day 45 inclusive. Preserve all other rules.",
        "schema": "facts: days (nonnegative integer), defective (boolean), receipt (boolean). "
                  "decision: status (review, refund, or deny).",
        "inputs": [{"days": 45, "defective": True, "receipt": True},
                   {"days": 20, "defective": False, "receipt": True}],
        "options": [[{"status": s} for s in ("review", "refund", "deny")]] * 2,
        "defect": "The defective-goods deadline is 44; a receipted defective claim on day 45 is wrongly denied.",
    },
    "delivery": {
        "title": "Delivery fees",
        "policy": "The base delivery fee is 0 at a subtotal of 100 or more, otherwise 5. "
                  "Express delivery always adds 10, including when the base fee is 0.",
        "change": "Raise the free base-delivery threshold to 120 inclusive. Preserve the express surcharge.",
        "schema": "facts: subtotal (nonnegative integer), express (boolean). decision: fee (integer).",
        "inputs": [{"subtotal": 120, "express": True}, {"subtotal": 110, "express": False}],
        "options": [[{"fee": n} for n in (0, 5, 10, 15)]] * 2,
        "defect": "Express delivery is wrongly free at or above subtotal 120; the surcharge must always apply.",
    },
    "expenses": {
        "title": "Expense review",
        "policy": "Send an expense report for review if a reimbursable line exceeds its limit. "
                  "Otherwise approve it. Independently, total only reimbursable lines at or "
                  "below the limit. This total is still reported when the status is review.",
        "change": "Send the report for review if any line exceeds the limit, even if that line "
                  "is not reimbursable. Preserve the total calculation.",
        "schema": "facts: limit (nonnegative integer), lines (ordered list of amount: nonnegative "
                  "integer and reimbursable: boolean). decision: status (approved or review), total (integer).",
        "inputs": [{"limit": 100, "lines": [{"amount": 50, "reimbursable": True},
                                               {"amount": 20, "reimbursable": False}]},
                   {"limit": 100, "lines": [{"amount": 101, "reimbursable": False}]}],
        "options": [[{"status": s, "total": t} for s, t in
                     [("approved", 50), ("approved", 70), ("review", 50), ("review", 70)]],
                    [{"status": s, "total": t} for s, t in
                     [("approved", 0), ("approved", 101), ("review", 0), ("review", 101)]]],
        "defect": "The total wrongly includes nonreimbursable lines at or below the limit.",
    },
    "inventory": {
        "title": "Inventory reservation",
        "policy": "Reserve the requested quantity if enough stock is available; otherwise reserve "
                  "nothing. Remaining stock is starting stock minus the amount reserved.",
        "change": "Allow partial fulfillment: reserve all available stock when stock is insufficient. "
                  "Keep remaining stock equal to starting stock minus the amount actually reserved.",
        "schema": "facts: stock and requested (nonnegative integers). decision: reserved and remaining (integers).",
        "inputs": [{"stock": 3, "requested": 5}, {"stock": 5, "requested": 3}],
        "options": [[{"reserved": r, "remaining": m} for r, m in [(3, 0), (3, -2), (0, 3), (5, -2)]],
                    [{"reserved": r, "remaining": m} for r, m in [(3, 2), (5, 0), (0, 5), (3, 5)]]],
        "defect": "Remaining stock subtracts requested instead of reserved, becoming negative on a shortfall.",
    },
}


def expected(domain, revision, facts):
    """Direct policy model; deliberately independent of either source parser."""
    if domain not in DOMAINS or revision not in REVISIONS:
        raise ValueError("unknown domain or revision")
    if domain == "refund":
        deadline = {"baseline": 30, "correct": 45, "faulty": 44}[revision]
        eligible = facts["days"] <= (deadline if facts["defective"] else 14)
        decision = {"status": "review" if not facts["receipt"] else "refund" if eligible else "deny"}
    elif domain == "delivery":
        free = facts["subtotal"] >= (100 if revision == "baseline" else 120)
        surcharge = facts["express"] and (not free or revision != "faulty")
        decision = {"fee": (0 if free else 5) + (10 if surcharge else 0)}
    elif domain == "expenses":
        review = any(line["amount"] > facts["limit"] and
                     (revision != "baseline" or line["reimbursable"]) for line in facts["lines"])
        total = sum(line["amount"] for line in facts["lines"] if line["amount"] <= facts["limit"]
                    and (line["reimbursable"] or revision == "faulty"))
        decision = {"status": "review" if review else "approved", "total": total}
    else:
        stock, requested = facts["stock"], facts["requested"]
        reserved = (requested if stock >= requested else 0) if revision == "baseline" else min(stock, requested)
        decision = {"reserved": reserved, "remaining": stock - (requested if revision == "faulty" else reserved)}
    return {"decision": decision}


def probes(domain):
    if domain == "refund":
        return [dict(days=d, defective=b, receipt=r)
                for d, b, r in product([0, 14, 15, 30, 31, 44, 45, 46], [False, True], [False, True])]
    if domain == "delivery":
        return [dict(subtotal=s, express=e) for s, e in product([0, 99, 100, 119, 120, 121], [False, True])]
    if domain == "expenses":
        lines = [dict(amount=a, reimbursable=r) for a, r in product([0, 50, 100, 101], [False, True])]
        return [dict(limit=100, lines=list(items)) for n in range(3) for items in product(lines, repeat=n)]
    if domain == "inventory":
        return [dict(stock=s, requested=r) for s, r in product([0, 1, 3, 5], [0, 1, 3, 5, 6])]
    raise ValueError("unknown domain")
