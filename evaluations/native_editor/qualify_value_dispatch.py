"""Capture an installed engine's scalar-dispatch policy and revision review."""
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
    original = Path("examples/native_value_dispatch/rules.gwt").read_text()
    source = output / "rules.gwt"
    source.write_text(original)
    candidate = output / "candidate.gwt"
    candidate.write_text(original.replace("set decision.delay to 15", "set decision.delay to 25"))
    commands = []

    def run(*arguments):
        command = [str(native), *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        commands.append({"command": command, "exitCode": result.returncode})
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return json.loads(result.stdout)

    def write(name, value):
        (output / name).write_text(json.dumps(value, indent=2) + "\n")

    validation = run("validate", source, "--html", output / "validation.html")
    write("validation.json", validation)
    cases = []
    for index, (status, attempt, notify, action, delay, notice) in enumerate([
        ("sent", 1, True, "done", 0, "done"),
        ("retry", 1, True, "retry", 5, "retry"),
        ("retry", 2, True, "retry", 15, "retry"),
        ("retry", 2, False, "retry", 15, "silent"),
        ("retry", 3, True, "manual", 0, "manual"),
        ("failed", 1, False, "manual", 0, "silent"),
    ], 1):
        input_path = output / f"input-{index}.json"
        input_path.write_text(json.dumps({"facts": {"status": status, "attempt": attempt, "notify": notify}}) + "\n")
        case = run("capture", source, "--request", "review delivery", "--input", input_path)
        assert case["record"]["observed"]["result"] == {"decision": {"action": action, "delay": delay, "notice": notice}}
        case_path = output / f"case-{index}.json"
        write(case_path.name, case)
        replay = run("replay", case_path)
        assert replay["verified"]
        write(f"replay-{index}.json", replay)
        cases.append(case_path)
    corpus = run("corpus", *cases)
    write("corpus.json", corpus)
    review = run("review", output / "corpus.json", "--candidate", candidate,
                 "--html", output / "delivery-review.html")
    write("delivery-review.json", review)
    totals = review["totals"]
    assert totals["compared"] == 6 and totals["outcomeChanged"] == 2, totals
    assert totals["baselineMismatch"] == 0 and totals["unavailable"] == 0, totals
    write("qualification.json", {"native": str(native), "nativeSha256": hashlib.sha256(native.read_bytes()).hexdigest(),
                                  "cases": 6, "verifiedReplays": 6, "reviewTotals": totals, "commands": commands})
    print(json.dumps({"ok": True, "output": str(output), "totals": totals}))


if __name__ == "__main__":
    main()
