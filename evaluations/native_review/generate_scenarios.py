"""Generate a mixed native request/scenario review with independent expectations."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--native", type=Path, default=ROOT / "target/debug/gwt-native")
args = parser.parse_args()
directory = args.output / "scenarios"
directory.mkdir(parents=True, exist_ok=True)


def invoke(*arguments):
    result = subprocess.run(
        [str(args.native.resolve()), *map(str, arguments)],
        cwd=ROOT, text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


source = (ROOT / "examples/native_delivery/rules.gwt").read_text() + '''
SCENARIO rejected weight
GIVEN parcel is Parcel
  weight_grams: 0
  member: false

REQUEST quote delivery

THEN false

SCENARIO printed exact integer
WHEN print 9007199254740993

THEN true
'''
baseline = directory / "baseline.gwt"
baseline.write_text(source)
candidate = directory / "candidate.gwt"
candidate.write_text(source.replace("set quote.fee to 9", "set quote.fee to 8").replace(
    "print 9007199254740993", "print 9007199254740994"))
cases = []
for index in range(1, 11):
    name = f"weight and membership determine the quote example {index}"
    cases.append({"id": f"row-{index}", "label": "Delivery boundary example",
                  "case": invoke("capture", baseline, "--scenario", name)})
for id_, name in [("failed-case", "rejected weight"), ("print-case", "printed exact integer")]:
    cases.append({"id": id_, "label": "Scenario observation",
                  "case": invoke("capture", baseline, "--scenario", name)})
input_path = directory / "input.json"
input_path.write_text(json.dumps({"parcel": {"weight_grams": 1001, "member": False}}))
cases.append({"id": "request-case", "label": "Fixed host input",
              "case": invoke("capture", baseline, "--request", "quote delivery", "--input", input_path)})
corpus = directory / "corpus.json"
corpus.write_text(json.dumps({"kind": "gwt.native-corpus", "schemaVersion": 1, "cases": cases}))
report = invoke("review", corpus, "--candidate", candidate, "--html", directory / "review.html")
assert report["complete"] and report["totals"]["compared"] == 13
assert report["totals"]["candidateFailed"] == 3
assert report["totals"]["outcomeChanged"] == 4
rows = {row["id"]: row for row in report["cases"]}
for id_ in ["row-3", "row-4"]:
    run = rows[id_]["comparison"]["candidate"]
    assert run["state"]["quote"]["fee"] == 8 and not run["ok"]
assert rows["request-case"]["comparison"]["candidate"]["result"]["quote"]["fee"] == 8
assert rows["print-case"]["comparison"]["candidate"]["output"] == [9007199254740994]
assert rows["failed-case"]["comparison"]["baseline"]["verified"]
assert not rows["failed-case"]["comparison"]["baseline"]["actual"]["ok"]
(directory / "review.json").write_text(json.dumps(report, ensure_ascii=False))
(args.output / "generation-report.json").write_text(json.dumps(report["totals"], indent=2) + "\n")
print(json.dumps(report["totals"]))
