"""Capture, replay, and review a remainder-selection fault against rational quotas."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from weighted_allocation_oracle import expected


def probe_limits(native, source, output):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for count in [1, 3, 8, 16, 32, 64]:
        budget = {"total": f"0.{count - 1:02d}", "recipients": [
            {"label": str(i), "weight": 1, "eligible": True} for i in range(count)]}
        path = output / f"input-{count}.json"
        path.write_text(json.dumps({"budget": budget}, indent=2) + "\n")
        command = [str(native), "run", str(source), "--request", "allocate budget", "--input", str(path)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=30)
        result = json.loads(process.stdout)
        if count <= 16:
            assert process.returncode == 0 and result["ok"]
            assert result["result"] == expected(budget)
        else:
            assert process.returncode == 1 and not result["ok"]
            assert result["diagnostic"]["code"] == "evidence_limit" and result["result"] is None
        rows.append({"command": command, "recipients": count, "total": budget["total"],
                     "exitCode": process.returncode, "ok": result["ok"], "diagnostic": result["diagnostic"],
                     "steps": result["steps"], "events": len(result["events"]),
                     "hasResult": result["result"] is not None})
    (output / "results.json").write_text(json.dumps(rows, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    native, output = args.native.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / "rules.gwt"
    source.write_text(Path("examples/native_weighted_allocation/rules.gwt").read_text())
    candidate = output / "candidate.gwt"
    needle = "share.remainder_score == largest_remainder"
    assert source.read_text().count(needle) == 1
    candidate.write_text(source.read_text().replace(needle, "share.remainder_score <= largest_remainder"))
    commands = []

    def run(*arguments, exit_code=0):
        command = [str(native), *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        commands.append({"command": command, "exitCode": result.returncode, "stderr": result.stderr})
        save("commands.json", commands)
        assert result.returncode == exit_code, result.stdout + result.stderr
        return json.loads(result.stdout)

    def save(name, data):
        path = output / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        return path

    save("validation.json", run("validate", source))
    validation = run("validate", candidate, exit_code=1)
    assert validation["check"]["status"] == "passed"
    assert validation["scenarios"]["status"] == "failed"
    save("candidate-validation.json", validation)
    save("inspection.json", run("inspect", source))
    configurations = [([1, 1, 1], [True]*3), ([1, 2], [True]*2), ([2, 1], [True]*2),
                      ([100, 1, 2], [False, True, True]), ([0, 0], [True]*2), ([], []),
                      ([1, 3, 3], [True]*3)]
    budgets = [{"total": total, "recipients": [
        {"label": f"recipient {i}", "weight": weight, "eligible": flag}
        for i, (weight, flag) in enumerate(zip(weights, flags))]}
        for total in ["0", "0.01", "0.02", "0.03", "0.04", "1", "1.01"]
        for weights, flags in configurations]
    budgets += [{"total": "-0.01", "recipients": []}, {"total": "0.001", "recipients": []},
                {"total": "0", "recipients": [{"label": "bad", "weight": -1, "eligible": False}]}]
    cases, independent_changes, failures = [], [], 0
    for i, budget in enumerate(budgets):
        input_path = save(f"input-{i}.json", {"budget": budget})
        expectation = expected(budget)
        faulty_expectation = expected(budget, first_eligible=True)
        if expectation != faulty_expectation:
            independent_changes.append(i)
        failures += "failure" in expectation
        for label, program, outcome in [("baseline", source, expectation), ("candidate", candidate, faulty_expectation)]:
            case = run("capture", program, "--request", "allocate budget", "--input", input_path)
            observed = case["record"]["observed"]
            if "failure" in outcome:
                assert not observed["ok"] and observed["diagnostic"]["code"] == outcome["failure"]
                assert observed["state"]["allocation"] == {"shares": [], "total": "0"}
            else:
                assert observed["ok"] and observed["result"] == outcome, (i, label, observed)
            path = save(f"{label}-case-{i}.json", case)
            assert run("replay", path)["verified"]
            if label == "baseline":
                cases.append(path)
    original_hashes = {str(path.name): hashlib.sha256(path.read_bytes()).hexdigest() for path in cases}
    corpus = save("corpus.json", run("corpus", *cases))
    review = run("review", corpus, "--candidate", candidate, "--html", output / "review.html")
    save("review.json", review)
    totals = review["totals"]
    assert totals["compared"] == len(cases)
    assert totals["outcomeChanged"] == totals["stateChanged"] == len(independent_changes), totals
    assert totals["unavailable"] == totals["baselineMismatch"] == 0, totals
    assert totals["candidateFailed"] == failures, totals
    assert original_hashes == {str(path.name): hashlib.sha256(path.read_bytes()).hexdigest() for path in cases}
    save("qualification.json", {"cases": len(cases), "independentChangedCases": independent_changes,
                               "unchangedDomainRejections": failures, "reviewTotals": totals,
                               "allBaselineAndCandidateReplaysVerified": True, "originalCaseHashes": original_hashes,
                               "reviewApproved": False, "nativeSha256": hashlib.sha256(native.read_bytes()).hexdigest()})
    probe_limits(native, source, output / "resource-probes")
    print(json.dumps({"ok": True, "cases": len(cases), "changed": len(independent_changes)}))


if __name__ == "__main__":
    main()
