"""Qualify installed optional-branch behavior and a policy revision review."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    native, output = args.native.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / "rules.gwt"
    original = Path("examples/native_presence/rules.gwt").read_text()
    source.write_text(original)
    candidate = output / "candidate.gwt"
    candidate.write_text(original.replace("facts.amount > facts.policy.limit", "facts.amount >= facts.policy.limit"))
    commands = []

    def run(*arguments):
        command = [str(native), *map(str, arguments)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        commands.append({"command": command, "exitCode": result.returncode})
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return json.loads(result.stdout)

    def write(name, value):
        (output / name).write_text(json.dumps(value, indent=2) + "\n")

    write("validation.json", run("validate", source, "--html", output / "validation.html"))
    cases = []
    for name, facts, expected in [
        ("missing-both", {"amount": 0}, ("review", "missing_policy", 0, "not recorded")),
        ("missing-receipt", {"amount": 50, "policy": {"limit": 100}}, ("review", "missing_receipt", 0, "not recorded")),
        ("missing-reference", {"amount": 50, "policy": {"limit": 100}, "receipt": {"verified": True}}, ("approved", "within_limit", 50, "not recorded")),
        ("approved-boundary", {"amount": 100, "policy": {"limit": 100}, "receipt": {"verified": True, "reference": "R"}}, ("approved", "within_limit", 100, "R")),
        ("empty-reference", {"amount": 100, "policy": {"limit": 100}, "receipt": {"verified": True, "reference": ""}}, ("approved", "within_limit", 100, "")),
        ("over-limit", {"amount": 101, "policy": {"limit": 100}, "receipt": {"verified": True, "reference": "R"}}, ("denied", "over_limit", 0, "R")),
        ("unverified", {"amount": 50, "policy": {"limit": 100}, "receipt": {"verified": False, "reference": "R"}}, ("denied", "unverified_receipt", 0, "R")),
        ("missing-policy", {"amount": 50, "receipt": {"verified": True, "reference": "R"}}, ("review", "missing_policy", 0, "R")),
    ]:
        input_path = output / f"{name}-input.json"
        input_path.write_text(json.dumps({"facts": facts}) + "\n")
        case = run("capture", source, "--request", "review reimbursement", "--input", input_path)
        assert case["record"]["observed"]["ok"]
        assert case["record"]["observed"]["result"] == {"decision": dict(zip(["status", "reason", "payable", "reference"], expected))}
        path = output / f"{name}.json"
        write(path.name, case)
        replay = run("replay", path)
        assert replay["verified"]
        write(f"{name}-replay.json", replay)
        cases.append(path)
    write("corpus.json", run("corpus", *cases))
    review = run("review", output / "corpus.json", "--candidate", candidate, "--html", output / "presence-review.html")
    write("presence-review.json", review)
    totals = review["totals"]
    assert totals["compared"] == 8 and totals["outcomeChanged"] == 2, totals
    assert totals["baselineMismatch"] == totals["unavailable"] == totals["candidateFailed"] == 0, totals

    guarded = output / "guarded-alias.gwt"
    guarded.write_text('RECORD Box\n  value: optional<integer>\nREQUEST replace\n  GIVEN box is Box\n  GIVEN replacement is Box\n  WHEN replace box through box with replacement\n  OUTPUT box is Box\nWHEN replace <box> through <alias> with <replacement>\n  GIVEN box is Box\n  AND alias is Box\n  AND replacement is Box\n  IF box.value is present\n    set alias to replacement\n')
    write("guarded-alias-input.json", {"box": {"value": 4}, "replacement": {}})
    failed = run("capture", guarded, "--request", "replace", "--input", output / "guarded-alias-input.json")
    observed = failed["record"]["observed"]
    assert not observed["ok"] and observed["diagnostic"]["code"] == "presence_mutation"
    assert observed["state"]["box"]["value"] == 4
    assert not any(e["operation"] == "set" for e in observed["events"])
    write("guarded-alias-case.json", failed)
    replay = run("replay", output / "guarded-alias-case.json")
    assert replay["verified"]
    write("guarded-alias-replay.json", replay)
    write("qualification.json", {"native": str(native), "nativeSha256": hashlib.sha256(native.read_bytes()).hexdigest(),
                                  "verifiedPolicyReplays": 8, "guardFailureVerified": True,
                                  "reviewTotals": totals, "commands": commands})
    print(json.dumps({"ok": True, "output": str(output), "totals": totals, "guardFailureVerified": True}))


if __name__ == "__main__":
    main()
