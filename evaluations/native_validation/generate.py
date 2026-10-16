"""Generate native validation views from bounded synthetic acceptance fixtures."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path)
parser.add_argument("--native", type=Path, default=Path("target/debug/gwt-native"))
args = parser.parse_args()
native = args.native.resolve()
args.output.mkdir(parents=True, exist_ok=False)

mixed = '''# café 😀 </script><img src=x onerror=alert(1)>
USE "helpers.gwt"
SCENARIO exact receipt
GIVEN amount is 9007199254740993
WHEN touch amount
WHEN print amount
THEN prints [9007199254740993]
AND amount == 9007199254740993
SCENARIO action only
WHEN print 0
SCENARIO failing expectation
THEN false
AND true
SCENARIO café rows
GIVEN amount is <value>
THEN amount == <expected>
EXAMPLES
  | value | expected |
  | 1 | 1 |
  | 2 | 0 |
SCENARIO </script><script>alert(2)</script>
THEN true
'''
fixtures = {
    "mixed": mixed,
    "clean": "SCENARIO works\nTHEN true\n",
    "declarations": "TYPE Amount is integer\n",
    "check-failure": "SCENARIO invalid\nTHEN unknown == 1\n",
    "format-failure": "SCENARIO   bad formatting\nTHEN true\n",
    "many": "".join(f"WHEN helper{i}\n  PASS\n" for i in range(105)) + "SCENARIO only\nTHEN true\n",
    "load-failure": None,
}
summaries = {}
for name, source in fixtures.items():
    directory = args.output / name
    directory.mkdir()
    entry = directory / "main.gwt"
    if source is not None:
        entry.write_text(source)
    if name == "mixed":
        (directory / "helpers.gwt").write_text("WHEN touch <amount>\n  GIVEN amount is integer\n  PASS\nWHEN unused <amount>\n  GIVEN amount is integer\n  PASS\n")
        subprocess.run([str(native), "format", str(entry), "--write"], check=True, capture_output=True)
        # The viewer must interpret byte spans after both multibyte text and CRLF.
        entry.write_bytes(entry.read_text().replace("\n", "\r\n").encode())
    command = [str(native), "validate", str(entry), "--html", str(directory / "review.html")]
    if name == "declarations":
        command += ["--allow-no-scenarios"]
    result = subprocess.run(command, text=True, capture_output=True)
    report = json.loads(result.stdout)
    (directory / "report.json").write_text(result.stdout)
    assert result.returncode == (0 if report["ok"] else 1), result.stderr
    summaries[name] = {"ok": report["ok"], "scenarioCount": len(report["results"]), "warnings": [item["code"] for item in report["warnings"]]}
    if name == "mixed":
        assert report["evidence"]["scenarioExpectations"] == {"declared": 7, "passed": 4, "failed": 2, "notObserved": 1}
        assert len(report["results"]) == 6
        assert report["evidence"]["callables"][0]["recordedEntries"] == 1
        assert report["evidence"]["callables"][1]["recordedEntries"] == 0
    elif name == "many":
        assert len(report["evidence"]["callables"]) == 105
    elif name == "load-failure":
        assert report["load"]["status"] == "failed"
    elif name == "check-failure":
        assert report["check"]["status"] == "failed"
    elif name == "format-failure":
        assert report["format"]["status"] == "failed" and report["scenarios"]["status"] == "passed"
    elif name == "declarations":
        assert report["ok"] and report["scenarios"]["status"] == "notExercised"
    else:
        assert report["ok"] and not report["warnings"]
(args.output / "generation.json").write_text(json.dumps(summaries, indent=2) + "\n")
print(json.dumps(summaries))
