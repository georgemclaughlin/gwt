"""Independent exact quota/sort oracle for the illustrative allocation policy."""

import argparse
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import random


def cents_text(cents):
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    return sign + (f"{whole}.{fraction:02d}".rstrip("0").rstrip(".") if fraction else str(whole))


def expected(budget, *, first_eligible=False):
    """Use rational quotas and one stable sort, not GWT's repeated scans."""
    total = Fraction(budget["total"])
    recipients = budget["recipients"]
    if total < 0 or (total * 100).denominator != 1:
        return {"failure": "assertion_failed"}
    if any(row["weight"] < 0 for row in recipients):
        return {"failure": "assertion_failed"}
    weights = [row["weight"] if row["eligible"] else 0 for row in recipients]
    weight_sum = sum(weights)
    if total > 0 and weight_sum == 0:
        return {"failure": "assertion_failed"}
    total_cents = int(total * 100)
    quotas = [Fraction(total_cents * weight, weight_sum) if weight_sum else Fraction(0)
              for weight in weights]
    bases = [quota.numerator // quota.denominator for quota in quotas]
    ranking = sorted((i for i, weight in enumerate(weights) if weight > 0),
                     key=lambda i: (0 if first_eligible else -(quotas[i] - bases[i]), i))
    winners = set(ranking[:total_cents - sum(bases)])
    shares = [
        {"label": row["label"], "participates": weights[i] > 0,
         "amount": cents_text(bases[i] + (i in winners)),
         "remainder_score": cents_text(total_cents * weights[i] - bases[i] * weight_sum),
         "received_extra_cent": i in winners}
        for i, row in enumerate(recipients)
    ]
    assert sum(Fraction(row["amount"]) for row in shares) == total
    return {"allocation": {"shares": shares, "total": cents_text(total_cents)}}


def fixtures():
    budgets = []
    # Exhaustive small weights and eligibility masks exercise overlapping policies.
    for weights in product(range(3), repeat=3):
        for eligible in product([False, True], repeat=3):
            for cents in [0, 1, 2, 7]:
                budgets.append({"total": cents_text(cents), "recipients": [
                    {"label": label, "weight": weight, "eligible": flag}
                    for label, weight, flag in zip(["Z", "A", "A"], weights, eligible)
                ]})
    rng = random.Random(416)
    for _ in range(128):
        budgets.append({"total": cents_text(rng.choice([0, 1, 2, 99, 100, 101, 10001, 10**40 + 1])),
                        "recipients": [{"label": f"café {i} 😀", "weight": rng.choice([0, 1, 2, 7, 10**30 + 3]),
                                        "eligible": rng.choice([False, True])}
                                       for i in range(rng.randrange(9))]})
    for total in ["0", "0.01", "-0.01", "0.001"]:
        for rows in [[], [{"label": "bad", "weight": -1, "eligible": False}],
                     [{"label": "good", "weight": 1, "eligible": True}]]:
            budgets.append({"total": total, "recipients": rows})
    return {"policy": "largest rational remainder; input order breaks ties; whole cents",
            "cases": [{"input": {"budget": budget}, "expected": expected(budget)} for budget in budgets]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = fixtures()
    args.output.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"cases": len(data["cases"]), "output": str(args.output)}))


if __name__ == "__main__":
    main()
