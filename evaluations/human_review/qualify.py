"""Verify review fixtures and prediction keys against independent policy models."""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from gwtlang.maintenance_evaluation import evaluate_candidate
from .corpus import DOMAINS, FIXTURES, REVISIONS, TASKS, expected, probes
from .study import write_json


def matches(actual, wanted):
    # Native exact integers serialize as decimal strings. Coerce numeric leaves
    # only; text, booleans, shape and missing fields remain exact.
    if type(wanted) is int:
        try:
            return type(actual) in (int, str) and Decimal(str(actual)) == wanted
        except InvalidOperation:
            return False
    if isinstance(wanted, dict):
        return isinstance(actual, dict) and actual.keys() == wanted.keys() and all(
            matches(actual[k], value) for k, value in wanted.items())
    return type(actual) is type(wanted) and actual == wanted


def qualify(native):
    native = Path(native).resolve(strict=True)
    observations, checks = [], []
    with tempfile.TemporaryDirectory(prefix="gwt-human-review-") as directory:
        input_path = Path(directory) / "input.json"
        for domain in DOMAINS:
            facts = probes(domain) + TASKS[domain]["inputs"]
            changes = sum(expected(domain, "baseline", f) != expected(domain, "correct", f) for f in facts)
            regressions = sum(expected(domain, "correct", f) != expected(domain, "faulty", f) for f in facts)
            if not 0 < changes < len(facts) or not regressions:
                raise AssertionError("corpus must expose both changed/preserved behavior and each defect")
            for revision in REVISIONS:
                acceptance = [{"input": {"facts": f}, "expected": expected(domain, revision, f)} for f in facts]
                for language, suffix in (("gwt", "gwt"), ("python", "py")):
                    path = FIXTURES / domain / f"{revision}.{suffix}"
                    result = evaluate_candidate(path.read_text(), language, "assess", acceptance)
                    checks.append({"domain": domain, "revision": revision, "engine": f"python-{language}",
                                   "probes": len(acceptance), **result})
                    if result["error"] or not all(result["passed"]):
                        raise AssertionError(checks[-1])
                path = FIXTURES / domain / f"{revision}.gwt"
                for probe_index, probe in enumerate(acceptance):
                    input_path.write_text(json.dumps(probe["input"]))
                    result = subprocess.run([str(native), "run", str(path), "--request", "assess",
                                             "--input", str(input_path)], text=True, capture_output=True, timeout=10)
                    value = json.loads(result.stdout)
                    passed = result.returncode == 0 and value.get("ok") is True and matches(value.get("result"), probe["expected"])
                    observations.append({"domain": domain, "revision": revision, "probe": probe_index,
                                         **probe, "actual": value.get("result"), "passed": passed,
                                         "programIdentity": value.get("programIdentity")})
                    if not passed:
                        raise AssertionError(observations[-1])
                checks.append({"domain": domain, "revision": revision, "engine": "native-gwt",
                               "probes": len(acceptance), "passed": [True] * len(acceptance), "error": None})
    root = Path(__file__).parent
    paths = sorted(p for p in root.rglob("*") if p.suffix in (".py", ".gwt", ".html") and "__pycache__" not in p.parts)
    return {"kind": "synthetic-fixture-qualification", "humanParticipants": 0,
            "nativeExecutable": str(native), "nativeSha256": hashlib.sha256(native.read_bytes()).hexdigest(),
            "fixtureProbesPerRevision": sum(len(probes(d)) for d in DOMAINS),
            "additionalQuestionProbesPerRevision": sum(len(TASKS[d]["inputs"]) for d in DOMAINS),
            "executions": sum(c["probes"] for c in checks), "checks": checks, "nativeObservations": observations,
            "sourceDigests": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.native)
    write_json(args.output, result)
    print(json.dumps({k: result[k] for k in ("kind", "humanParticipants", "executions", "nativeSha256")}))


if __name__ == "__main__":
    main()
