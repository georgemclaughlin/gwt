"""Generate exact printed-output review cases with independent receipt expectations."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--native", type=Path, default=ROOT / "target/debug/gwt")
args = parser.parse_args()
directory = args.output / "prints"
directory.mkdir(parents=True, exist_ok=True)


def invoke(*arguments):
    result = subprocess.run([str(args.native.resolve()), *map(str, arguments)],
                            cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


source = ROOT / "examples/native_print_expectations/rules.gwt"
candidate = directory / "candidate.gwt"
candidate.write_text(source.read_text().replace("  print parcel.quantity", "  print parcel.quantity + 1"))
cases = []
for id_, name in [("receipt", "receipt preserves its label and exact quantity"),
                  ("quiet", "empty output is explicit")]:
    cases.append({"id": id_, "label": "Expected printed output",
                  "case": invoke("capture", source, "--scenario", name)})
request_case = invoke("capture", source, "--request", "print receipt",
                      "--input", ROOT / "examples/native_print_expectations/input.json")
cases.append({"id": "host", "label": "Fixed host receipt input", "case": request_case})
corpus = directory / "corpus.json"
corpus.write_text(json.dumps({"kind": "gwt.native-corpus", "schemaVersion": 1, "cases": cases}))
report = invoke("review", corpus, "--candidate", candidate, "--html", directory / "review.html")
rows = {row["id"]: row for row in report["cases"]}
assert report["complete"] and report["totals"]["compared"] == 3
assert report["totals"]["outcomeChanged"] == 2 and report["totals"]["candidateFailed"] == 1
expected = ["Packing receipt", {"label": "fragile # café", "quantity": 9007199254740993}, 9007199254740993]
for id_ in ["receipt", "host"]:
    comparison = rows[id_]["comparison"]
    assert comparison["baseline"]["actual"]["output"] == expected
    assert comparison["candidate"]["output"] == [*expected[:2], 9007199254740994]
assert rows["receipt"]["comparison"]["candidate"]["diagnostic"]["code"] == "print_assertion_failed"
assert rows["quiet"]["comparison"]["candidate"]["ok"]
assert rows["quiet"]["comparison"]["candidate"]["output"] == []
(directory / "review.json").write_text(json.dumps(report, ensure_ascii=False))
(args.output / "generation-report.json").write_text(json.dumps(report["totals"], indent=2) + "\n")
print(json.dumps(report["totals"]))
