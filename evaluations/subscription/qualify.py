"""Independent integer-domain subscription adaptation checks; no human evidence."""
import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import tempfile

from gwtlang.runtime import Runtime, parse_program


SOURCE = Path("examples/pressure_tests/subscription_entitlements.gwt")
REQUEST = "decide entitlement"


def probes():
    statuses = ("paid", "past_due", "void")
    invoices = [()] + [(s,) for s in statuses] + list(itertools.product(statuses, repeat=2))
    overrides = [(), ((False, True),), ((True, False),), ((True, True),),
                 ((True, False), (True, True)), ((True, True), (True, False)),
                 ((False, True), (True, True))]
    for index, (plan, feature, seats, bills, exceptions) in enumerate(itertools.product(
            ("free", "pro", "enterprise"), ("projects", "automations", "audit_log", "unknown"),
            ((0, 0), (1, 1), (2, 1)), invoices, overrides)):
        yield f"case-{index:04d}", {"account": {
            "account_id": "synthetic", "plan": plan, "requested_feature": feature,
            "active_users": seats[0], "seat_limit": seats[1],
            "invoices": [{"invoice_id": f"invoice-{i}", "status": status,
                          "days_overdue": 0 if status == "past_due" else 9} for i, status in enumerate(bills)],
            "overrides": [{"feature": feature if matches else "unrelated", "active": active,
                           "reason": f"override-{i}"} for i, (matches, active) in enumerate(exceptions)],
        }}


def expected(value):
    """Domain model using set membership and a precedence table, independent of GWT."""
    a = value["account"]
    plan = {"free": 1, "pro": 2, "enterprise": 3}[a["plan"]]
    needed = {"projects": 1, "automations": 2, "audit_log": 3}.get(a["requested_feature"], 99)
    past_due = "past_due" in {invoice["status"] for invoice in a["invoices"]}
    over_seats = a["active_users"] > a["seat_limit"]
    matching = [o for o in a["overrides"] if o["feature"] == a["requested_feature"]]
    override = matching[0] if matching else None
    overridden = override is not None and override["active"]
    alternatives = [
        (overridden, True, "allowed", "manual_override", [override["reason"]] if override else []),
        (past_due, False, "blocked", "past_due_invoice", ["invoice_must_be_paid"]),
        (over_seats, False, "blocked", "seat_limit_exceeded", ["reduce_users_or_buy_seats"]),
        (needed == 99, False, "needs_review", "unknown_feature", ["feature_catalog_missing"]),
        (plan >= needed, True, "allowed", "feature_in_plan", []),
        (True, False, "blocked", "feature_requires_upgrade", ["upgrade_plan"]),
    ]
    _, allowed, status, reason, reasons = next(row for row in alternatives if row[0])
    return {"allowed": allowed, "matched_override": overridden, "has_past_due_invoice": past_due,
            "seat_limit_exceeded": over_seats, "plan_rank": plan, "required_plan_rank": needed,
            "status": status, "reason": reason, "reasons": reasons}


def native_expected(value):
    result = expected(value)
    for field in ("plan_rank", "required_plan_rank"):
        result[field] = str(result[field])
    return result


def python_matches(actual, want):
    if set(actual) != set(want):
        return False
    for key, value in want.items():
        if key in ("plan_rank", "required_plan_rank"):
            if isinstance(actual[key], bool) or not isinstance(actual[key], (int, float, Decimal)):
                return False
            if Decimal(str(actual[key])) != value:
                return False
        elif type(actual[key]) is not type(value) or actual[key] != value:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    native = args.native.resolve()
    before = args.before.read_text()
    after = SOURCE.read_text()
    old, new = [Runtime(parse_program(text, filename=name)) for text, name in
                ((before, str(args.before)), (after, str(SOURCE)))]
    observations = []
    with tempfile.TemporaryDirectory(prefix="gwt-subscription-") as temporary:
        input_path = Path(temporary) / "input.json"
        for name, value in probes():
            oracle = expected(value)
            for label, runtime in (("before", old), ("after", new)):
                actual = runtime.run_json(deepcopy(value), REQUEST).scenarios[0].returned_state["decision"]
                assert python_matches(actual, oracle), (name, label, actual, oracle)
            input_path.write_text(json.dumps(value))
            run = subprocess.run([str(native), "run", str(SOURCE), "--request", REQUEST,
                                  "--input", str(input_path)], capture_output=True, text=True, timeout=15)
            assert run.returncode == 0, (name, run.stderr, run.stdout[:500])
            payload = json.loads(run.stdout)
            assert payload["ok"] and payload["result"] == {"decision": native_expected(value)}, name
            account = deepcopy(value["account"])
            for field in ("active_users", "seat_limit"):
                account[field] = str(account[field])
            for invoice in account["invoices"]:
                invoice["days_overdue"] = str(invoice["days_overdue"])
            assert payload["state"]["account"] == account, name
            observations.append({"id": name, "input": value, "expected": oracle,
                                 "pythonBeforeMatches": True, "pythonAfterMatches": True, "nativeMatches": True})
    assert len(observations) == 3276
    (args.output / "observations.json").write_text(json.dumps(observations, indent=2) + "\n")
    report = {"kind": "subscription-source-adaptation", "cases": len(observations),
              "executions": len(observations) * 3, "nativeInputStatePreserved": len(observations),
              "beforeSha256": hashlib.sha256(before.encode()).hexdigest(),
              "afterSha256": hashlib.sha256(after.encode()).hexdigest(),
              "nativeExecutable": str(native), "nativeSha256": hashlib.sha256(native.read_bytes()).hexdigest(),
              "humanParticipants": 0,
              "limitations": "Finite valid integer-domain inputs; helper contract narrowed; no full engine equivalence or human-benefit claim."}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
