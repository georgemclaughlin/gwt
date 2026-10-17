"""Qualify explicit migration with real executables; never promote cases into a live corpus."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--previous-engine", type=Path, required=True)
parser.add_argument("--changed-engine", type=Path,
                    help="optional qualification engine whose assertion message was deliberately changed")
parser.add_argument("--native", type=Path, default=ROOT / "target/debug/gwt")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)


def invoke(engine, *arguments, code=0):
    result = subprocess.run([str(engine.resolve()), *map(str, arguments)],
                            cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert result.returncode == code, (result.returncode, result.stdout[:4096], result.stderr[:4096])
    return json.loads(result.stdout)


def digest(value, domain):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(domain + encoded).hexdigest()


def resign(case):
    case.pop("integrity", None)
    case["integrity"] = digest(case, b"gwt-native-case-sha256-v1\0")
    return case


results = []
engines = [("preserved", args.previous_engine)]
if args.changed_engine:
    engines.append(("changed-message", args.changed_engine))
for variant, engine in engines:
    folder = args.output / variant
    folder.mkdir(exist_ok=True)
    executable_digest = "sha256:" + hashlib.sha256(engine.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="gwt-migration-inputs-") as temporary:
        workspace = Path(temporary)
        stock = ROOT / "examples/native_expected_failures/rules.gwt"
        bad_input = workspace / "invalid.json"
        bad_input.write_text("{}")
        failures = workspace / "failure.gwt"
        failures.write_text('SCENARIO raw failure\nWHEN print "before rejection"\nWHEN REQUIRE false\n')
        policy = workspace / "policy.gwt"
        policy.write_text('REQUEST report\n  GIVEN value is integer\n  WHEN print value\n  OUTPUT value is integer\n')
        imported = workspace / "imported.gwt"
        imported.write_text('USE "policy.gwt"\nSCENARIO imported\nGIVEN value is 9007199254740993\nREQUEST report\nTHEN value == 9007199254740993\n')
        captures = [
            ("invoice", [ROOT / "examples/native_return_values/rules.gwt", "--request", "quote order", "--input", ROOT / "examples/native_return_values/input.json"]),
            ("rejected-request", [stock, "--request", "reserve stock", "--input", ROOT / "examples/native_expected_failures/input.json"]),
            ("invalid-input", [stock, "--request", "reserve stock", "--input", bad_input]),
            ("expected-rejection", [stock, "--scenario", "insufficient stock rejects without reserving"]),
            ("exact-prints", [ROOT / "examples/native_print_expectations/rules.gwt", "--scenario", "receipt preserves its label and exact quantity"]),
            ("raw-failure", [failures, "--scenario", "raw failure"]),
            ("imported", [imported, "--scenario", "imported"]),
        ]
        cases = [(name, invoke(engine, "capture", *arguments)) for name, arguments in captures]
        # Capture actual zero-step observations through old-engine replay, then verify
        # them again. No fabricated observation is used to qualify budget preservation.
        for name, base in [("limited-request", cases[0][1]), ("limited-scenario", cases[3][1])]:
            case = json.loads(json.dumps(base))
            case["record"]["limits"]["execution"]["steps"] = 0
            path = workspace / "limited.case.json"
            path.write_text(json.dumps(resign(case)))
            replay = invoke(engine, "replay", path, code=1)
            assert not replay["verified"] and replay["actual"]["diagnostic"]["code"] == "execution_limit"
            case["record"]["observed"] = replay["actual"]
            path.write_text(json.dumps(resign(case)))
            assert invoke(engine, "replay", path)["verified"]
            cases.append((name, case))
        policy.unlink()
        imported.unlink()
        failures.unlink()
        for name, case in cases:
            case_path = folder / (name + ".original.json")
            case_path.write_text(json.dumps(case, ensure_ascii=False))
            original_bytes = case_path.read_bytes()
            proposal = invoke(args.native, "migrate", case_path, "--previous-engine", engine)
            expected_change = variant == "changed-message" and name in {"rejected-request", "raw-failure", "expected-rejection"}
            expected_outcome = variant == "changed-message" and name in {"rejected-request", "raw-failure"}
            assert proposal["status"] == ("observation_changed" if expected_change else "observation_preserved")
            assert proposal["changes"] == {"source": False, "state": False, "outcome": expected_outcome, "evidence": expected_change}
            assert not proposal["approved"] and proposal["original"] == case
            assert proposal["previousExecutableSha256"] == executable_digest
            assert case_path.read_bytes() == original_bytes
            integrity = proposal["integrity"]
            assert integrity == digest({k: v for k, v in proposal.items() if k != "integrity"}, b"gwt-native-case-migration-sha256-v1\0")
            candidate = proposal["candidate"]
            assert candidate["schemaVersion"] == 3
            for key in ["source", "programIdentity", "input", "limits", "request", "scenario"]:
                assert candidate["record"].get(key) == case["record"].get(key)
            assert candidate["record"]["migration"]["parentCaseIntegrity"] == case["integrity"]
            assert candidate["record"]["engine"] != case["record"]["engine"]
            candidate_path = folder / (name + ".candidate.json")
            candidate_path.write_text(json.dumps(candidate, ensure_ascii=False))
            assert invoke(args.native, "replay", candidate_path)["verified"]
            if name in {"invoice", "rejected-request"}:
                generated = invoke(args.native, "scenario-from-case", candidate_path)
                assert generated["schemaVersion"] == 3
            (folder / (name + ".migration.json")).write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n")
            results.append({"variant": variant, "case": name, "status": proposal["status"],
                            "changes": proposal["changes"], "newCaseReplayVerified": True,
                            "originalEngine": case["record"]["engine"], "targetEngine": candidate["record"]["engine"]})
        forged = json.loads(json.dumps(cases[0][1]))
        forged["record"]["observed"]["result"]["quote"]["total"] = "999"
        path = folder / "forged.case.json"
        path.write_text(json.dumps(resign(forged)))
        refusal = invoke(args.native, "migrate", path, "--previous-engine", engine, code=1)
        assert refusal["phase"] == "previous-engine-replay" and "candidate" not in refusal
        (folder / "forged-refusal.json").write_text(json.dumps(refusal, indent=2) + "\n")
report = {"results": results, "syntheticChangedEngine": bool(args.changed_engine),
          "forgedObservationRefusals": len(engines), "promotedCases": 0}
(args.output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"verifiedMigrations": len(results), "observationChanged": sum(row["status"] == "observation_changed" for row in results),
                  "forgedObservationRefusals": len(engines), "promotedCases": 0}))
