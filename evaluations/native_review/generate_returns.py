"""Generate a small return-value review from independently specified pricing cases."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--native", type=Path, default=ROOT / "target/debug/gwt-native")
parser.add_argument("--value-arguments", action="store_true", help="exercise copied expression arguments")
args = parser.parse_args()
directory = args.output / ("arguments" if args.value_arguments else "returns")
directory.mkdir(parents=True, exist_ok=True)


def invoke(*arguments):
    result = subprocess.run([str(args.native.resolve()), *map(str, arguments)],
                            cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


source = ROOT / ("examples/native_value_arguments/rules.gwt" if args.value_arguments else "examples/native_return_values/rules.gwt")
candidate = directory / "candidate.gwt"
old, new = ("at 0.1", "at 0.2") if args.value_arguments else ("RETURN 0.1", "RETURN 0.2")
candidate.write_text(source.read_text().replace(old, new))
input_name = "basket" if args.value_arguments else "order"
request_name = "quote " + input_name
cases = []
for id_, member, quantity in [("member", True, 2), ("ordinary", False, 2), ("invalid", True, 0)]:
    input_path = directory / (id_ + ".json")
    input_path.write_text(json.dumps({input_name: {"unit_price": "19.95", "quantity": quantity, "member": member}}))
    case = invoke("capture", source, "--request", request_name, "--input", input_path)
    cases.append({"id": id_, "label": "Copied expression arguments" if args.value_arguments else "Returned pricing values", "case": case})
corpus = directory / "corpus.json"
corpus.write_text(json.dumps({"kind": "gwt.native-corpus", "schemaVersion": 1, "cases": cases}))
report = invoke("review", corpus, "--candidate", candidate, "--html", directory / "review.html")
rows = {row["id"]: row for row in report["cases"]}
assert report["complete"] and report["totals"]["compared"] == 3
assert report["totals"]["outcomeChanged"] == 1 and report["totals"]["candidateFailed"] == 1
assert rows["member"]["comparison"]["baseline"]["actual"]["result"]["quote"]["total"] == "35.91"
assert rows["member"]["comparison"]["candidate"]["result"]["quote"]["total"] == "31.92"
assert rows["ordinary"]["comparison"]["candidate"]["result"]["quote"]["total"] == "39.9"
assert rows["invalid"]["comparison"]["candidate"]["diagnostic"]["code"] == "assertion_failed"
assert any(event["operation"] == "return" for event in rows["member"]["comparison"]["candidate"]["events"])
if args.value_arguments:
    run = rows["member"]["comparison"]["candidate"]
    assert run["state"]["basket"] == {"unit_price": "19.95", "quantity": 2, "member": True}
    assert any(event["operation"] == "argument value" for event in run["events"])
    assert any(event["operation"] == "subtract" and event["value"]["path"] == "amount (value)" for event in run["events"])
(directory / "review.json").write_text(json.dumps(report, ensure_ascii=False))
(args.output / "generation-report.json").write_text(json.dumps(report["totals"], indent=2) + "\n")
print(json.dumps(report["totals"]))
