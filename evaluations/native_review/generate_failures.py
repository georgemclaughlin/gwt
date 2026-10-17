"""Review expected-failure scenarios and a raw failed request against independent stock rules."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--native", type=Path, default=ROOT / "target/debug/gwt")
args = parser.parse_args()
directory = args.output / "failures"
directory.mkdir(parents=True, exist_ok=True)


def invoke(*arguments):
    result = subprocess.run([str(args.native.resolve()), *map(str, arguments)],
                            cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


source = ROOT / "examples/native_expected_failures/rules.gwt"
candidate = directory / "candidate.gwt"
candidate.write_text(source.read_text().replace("  REQUIRE stock.available >= order.quantity", "  PASS"))
cases = []
for id_, name in [("shortage", "insufficient stock rejects without reserving"),
                  ("valid", "valid order reserves its quantity"),
                  ("zero", "nonpositive quantity rejects before checking stock example 1")]:
    cases.append({"id": id_, "label": "Scoped failure expectations",
                  "case": invoke("capture", source, "--scenario", name)})
request = invoke("capture", source, "--request", "reserve stock",
                 "--input", ROOT / "examples/native_expected_failures/input.json")
cases.append({"id": "host", "label": "Raw rejected request", "case": request})
corpus = directory / "corpus.json"
corpus.write_text(json.dumps({"kind": "gwt.native-corpus", "schemaVersion": 1, "cases": cases}))
report = invoke("review", corpus, "--candidate", candidate, "--html", directory / "review.html")
rows = {row["id"]: row for row in report["cases"]}
assert report["complete"] and report["totals"]["compared"] == 4
assert report["totals"]["outcomeChanged"] == 2 and report["totals"]["candidateFailed"] == 1
shortage = rows["shortage"]["comparison"]
assert shortage["baseline"]["actual"]["ok"]
assert shortage["baseline"]["actual"]["state"]["stock"]["available"] == 2
assert shortage["baseline"]["actual"]["output"] == ["checking stock"]
assert shortage["candidate"]["diagnostic"]["code"] == "failure_assertion_failed"
assert shortage["candidate"]["state"]["stock"]["available"] == -1
assert shortage["candidate"]["output"] == ["checking stock", "reserved"]
for id_, available in [("valid", 1), ("zero", 3)]:
    assert rows[id_]["comparison"]["candidate"]["ok"]
    assert rows[id_]["comparison"]["candidate"]["state"]["stock"]["available"] == available
assert not rows["host"]["comparison"]["baseline"]["actual"]["ok"]
assert rows["host"]["comparison"]["baseline"]["actual"]["diagnostic"]["code"] == "assertion_failed"
assert rows["host"]["comparison"]["candidate"]["ok"]
assert rows["host"]["comparison"]["candidate"]["result"] == {"stock": {"available": -1}}
(directory / "review.json").write_text(json.dumps(report, ensure_ascii=False))
(args.output / "generation-report.json").write_text(json.dumps(report["totals"], indent=2) + "\n")
print(json.dumps(report["totals"]))
