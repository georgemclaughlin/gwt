"""Check whether native saved decisions bind otherwise invisible budget changes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-binding", choices=["missing", "present"], required=True)
    args = parser.parse_args()
    native = args.native.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    calls = []

    def save(name, data):
        path = out / name
        path.write_text(json.dumps(data, indent=2) + "\n")
        return path

    def run(name, *arguments, expected=0):
        command = [str(native), *map(str, arguments)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        (out / f"{name}.json").write_text(result.stdout)
        (out / f"{name}.stderr.txt").write_text(result.stderr)
        calls.append({"command": command, "expectedExitCode": expected, "exitCode": result.returncode})
        save("commands.json", calls)
        assert result.returncode == expected, (name, result.returncode, result.stderr)
        return json.loads(result.stdout)

    rules = out / "invoice.gwt"
    rules.write_bytes((ROOT / "crates/gwt-core/tests/fixtures/invoice.gwt").read_bytes())
    input_path = save("input.json", {"invoice": {"quantity": 3, "unit_price": "10.25"}})
    default = {"execution": {"steps": 100000, "evidenceBytes": 1048576, "textBytes": 1048576}, "callDepth": 64}
    observations = []
    reports = []
    identities = []
    changed_assessments = []
    for name, key, value in [
        ("default", "steps", 100000), ("steps", "steps", 99999),
        ("evidence", "evidenceBytes", 1048575), ("text", "textBytes", 1),
        ("depth", "callDepth", 63),
    ]:
        limits = json.loads(json.dumps(default))
        (limits if key == "callDepth" else limits["execution"])[key] = value
        limits_path = save(f"{name}.limits.json", limits)
        case = run(f"{name}.case", "capture", rules, "--request", "price invoice", "--input", input_path, "--limits", limits_path)
        observation = case["record"]["observed"]
        assert observation["ok"] and observation["result"]["decision"]["total"] == "36.9"
        observations.append(observation)
        corpus = save(f"{name}.corpus.json", {"kind": "gwt.native-corpus", "schemaVersion": 1,
                     "cases": [{"id": "invoice", "label": "Synthetic invoice budget review", "case": case}]})
        template = out / f"{name}.template.json"
        report = run(f"{name}.review", "review", corpus, "--candidate", rules,
                     "--decisions-template", template, "--html", out / f"{name}.html")
        reports.append(report)
        identity = json.loads(template.read_text())["reportIdentity"]
        identities.append(identity)
        if name == "default":
            choices = json.loads(template.read_text())
            choices["reviewer"] = "Synthetic identity regression fixture"
            choices["decisions"][0].update(status="accept", note="Test fixture only; no project approval.")
            decision_path = save("synthetic-decisions.json", choices)
            assessment = run("default.assessment", "assess-review", corpus, "--candidate", rules, "--decisions", decision_path)
            assert assessment["allAccepted"]
        else:
            stale = args.expect_binding == "present"
            assessment = run(f"{name}.assessment", "assess-review", corpus, "--candidate", rules,
                             "--decisions", decision_path, expected=1 if stale else 0)
            if stale:
                assert assessment["diagnostic"]["code"] == "decisions_stale"
                assert identity != identities[0]
                assert report["cases"][0]["capturedLimits"] == limits
                assert report["cases"][0]["caseIntegrity"] == case["integrity"]
            else:
                assert assessment["allAccepted"] and identity == identities[0]
                assert report == reports[0]
            changed_assessments.append({"budget": name, "stale": stale})
    assert all(value == observations[0] for value in observations)
    summary = {"native": str(native), "nativeSha256": hashlib.sha256(native.read_bytes()).hexdigest(),
               "engine": reports[0]["engine"], "expectedBinding": args.expect_binding,
               "identicalExecutionObservations": len(observations), "changedBudgetAssessments": changed_assessments,
               "realHumanApprovals": 0}
    save("qualification.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
