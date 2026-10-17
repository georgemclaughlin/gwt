"""Exercise corpus preservation through a selected native CLI, retaining every artifact."""
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
    args = parser.parse_args()
    native = args.native.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    calls = []

    def save(name, value):
        path = output / name
        path.write_text(json.dumps(value, indent=2) + "\n")
        return path

    def run(name, *arguments, expected=0):
        command = [str(native), *map(str, arguments)]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        (output / f"{name}.stdout.json").write_text(result.stdout)
        (output / f"{name}.stderr.txt").write_text(result.stderr)
        calls.append({"command": command, "expectedExitCode": expected, "exitCode": result.returncode})
        save("commands.json", calls)
        assert result.returncode == expected, (name, result.returncode, result.stderr)
        return json.loads(result.stdout)

    source = (ROOT / "crates/gwt-core/tests/fixtures/invoice.gwt").read_text()
    rules = output / "invoice.gwt"
    rules.write_text(source)
    facts = save("input.json", {"invoice": {"quantity": 3, "unit_price": "10.25"}})
    missing = save("missing-input.json", {})
    rejected = save("rejected-input.json", {"invoice": {"quantity": 0, "unit_price": "10.25"}})
    normal = run("baseline", "run", rules, "--request", "price invoice", "--input", facts)
    assert normal["ok"] and normal["result"]["decision"] == {"total": "36.9", "status": "priced"}
    limits = {"execution": {"steps": 100000, "evidenceBytes": 1048576, "textBytes": 1048576}, "callDepth": 64}
    entries = []
    for name, input_path, setting in [
        ("success", facts, None),
        ("boundary", missing, None),
        ("domain", rejected, None),
        ("at-budget", facts, ("steps", normal["steps"])),
        ("below-budget", facts, ("steps", normal["steps"] - 1)),
        ("zero-steps", facts, ("steps", 0)),
        ("zero-evidence", facts, ("evidenceBytes", 0)),
        ("zero-depth", facts, ("callDepth", 0)),
    ]:
        options = []
        if setting:
            selected = json.loads(json.dumps(limits))
            key, value = setting
            (selected if key == "callDepth" else selected["execution"])[key] = value
            options = ["--limits", save(f"{name}.limits.json", selected)]
        case = run(name, "capture", rules, "--request", "price invoice", "--input", input_path, *options)
        assert case["record"]["observed"]["ok"] == (name in {"success", "at-budget"})
        entries.append({"id": name, "label": name, "case": case})
    scenario = run("scenario", "capture", rules, "--scenario", "three taxable units")
    entries.append({"id": "scenario", "label": "scenario", "case": scenario})
    corpus_path = save("corpus.json", {"kind": "gwt.native-corpus", "schemaVersion": 1, "cases": entries})
    original_corpus = corpus_path.read_bytes()
    results = []
    for variant, candidate_source in [
        ("same", source),
        ("moved", "# changed source positions\n" + source),
        ("tax-change", source.replace("subtotal * 0.2", "subtotal * 0.3")),
        ("early-write", source.replace("  REQUIRE invoice.quantity > 0", '  set decision.status to "priced"\n  REQUIRE invoice.quantity > 0')),
        ("extra-check", source.replace("  LET subtotal", "  REQUIRE true\n  LET subtotal")),
        ("removed-check", source.replace("  REQUIRE invoice.quantity > 0\n", "")),
    ]:
        # Keep the same module filename to isolate content changes from path movement.
        directory = output / variant
        directory.mkdir()
        candidate = directory / "invoice.gwt"
        candidate.write_text(candidate_source)
        for scope in ["outcomes-and-state", "execution"]:
            passed = variant == "same" or (variant == "moved" and scope == "outcomes-and-state")
            report = run(f"{variant}-{scope}", "test-cases", corpus_path, "--candidate", candidate,
                         "--match", scope, expected=0 if passed else 1)
            assert report["passed"] is passed
            assert report["review"]["complete"]
            assert report["totals"]["total"] == 9
            assert report["totals"]["baselineMismatch"] == report["totals"]["unavailable"] == 0
            assert report["totals"]["passed"] + report["totals"]["changed"] == 9
            rows = {row["id"]: row for row in report["cases"]}
            for row, entry in zip(report["cases"], entries):
                assert row["caseIntegrity"] == entry["case"]["integrity"]
                assert row["capturedLimits"] == entry["case"]["record"]["limits"]
            if variant == "same":
                assert report["review"]["totals"]["candidateFailed"] == 6
            if variant == "extra-check":
                assert rows["at-budget"]["status"] == "changed"
            if variant == "removed-check":
                assert rows["below-budget"]["status"] == "changed"
            if variant == "early-write":
                assert rows["domain"]["status"] == "changed"
                changes = report["review"]["cases"][2]["comparison"]["changes"]
                assert not changes["outcome"] and changes["state"]
            results.append({"variant": variant, "scope": scope, "passed": passed, "totals": report["totals"]})
    assert corpus_path.read_bytes() == original_corpus
    summary = {"native": str(native), "nativeSha256": hashlib.sha256(native.read_bytes()).hexdigest(),
               "caseCount": len(entries), "regressionReports": len(results), "checks": results,
               "sourceSha256": hashlib.sha256(source.encode()).hexdigest(), "baselineSteps": normal["steps"],
               "engine": entries[0]["case"]["record"]["engine"], "corpusUnchanged": True}
    save("qualification.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
