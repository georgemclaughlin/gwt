"""Qualify checkpoint/scorer interoperability without claiming browser or human evidence."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .qualify_adjudication import synthetic_response
from .study import validate_response, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    root = parser.parse_args().output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    commands = []

    def cli(module, *arguments):
        command = [sys.executable, "-m", module, *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True)
        commands.append({"argv": command, "exitCode": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
        write_json(root / f"command-{len(commands)}.json", commands[-1])
        if result.returncode:
            raise RuntimeError(result.stderr)

    for group, label in ((0, "resumed"), (1, "missing")):
        cli("evaluations.human_review.study", "prepare", "--group", group,
            "--assignment", "recovery-rehearsal-" + label, "--output", root / label)
    key_path = root / "resumed/facilitator-key.json"
    missing_key = root / "missing/facilitator-key.json"
    key = json.loads(key_path.read_text())
    packet = key["packet"]
    saved = synthetic_response(packet, key)
    saved["finished"] = False
    saved["tasks"][1]["status"] = "skipped"
    saved["tasks"][2].update(status="draft", rationale="Synthetic checkpoint: partial explanation 🍂")
    saved["tasks"][3].update(status="unseen", activeMs=None, wallMs=None, rationale="",
                             confidence=None, recommendation=None, predictions={"q1": None, "q2": None})
    write_json(root / "checkpoint.json", saved)
    original = deepcopy(saved)
    script = Path(__file__).with_name("session-recovery.js").resolve()
    snapshots = []
    for _ in range(2):
        process = subprocess.run(["node", "-e", """
            require(process.argv[1]);
            const input = JSON.parse(require('node:fs').readFileSync(0,'utf8'));
            const restored = GwtReviewRecovery.restore(input.packet,input.saved);
            const row = restored.response.tasks[restored.index];
            const clock = GwtReviewRecovery.startClock(row,100,false);
            GwtReviewRecovery.tick(clock,1100,true);
            Object.assign(row,GwtReviewRecovery.tick(clock,1600,false));
            console.log(JSON.stringify(restored.response));
        """, str(script)], input=json.dumps({"packet": packet, "saved": saved}),
            text=True, capture_output=True, check=True)
        saved = json.loads(process.stdout)
        validate_response(packet, saved)
        snapshots.append(saved)
        write_json(root / f"restored-{len(snapshots)}.json", saved)
        assert saved["tasks"][:2] == original["tasks"][:2]
        assert saved["responseId"] == original["responseId"]
    assert saved["tasks"][2]["resumeCount"] == 2
    assert saved["tasks"][2]["activeMs"] == 2000
    assert saved["tasks"][2]["wallMs"] == 4500
    cli("evaluations.human_review.study", "score", "--keys", key_path, missing_key,
        "--responses", root / "restored-2.json", "--output", root / "partial-report.json")

    finished = synthetic_response(packet, key)
    finished["tasks"][:3] = deepcopy(saved["tasks"][:3])
    finished["tasks"][2]["status"] = "submitted"
    write_json(root / "complete.json", finished)
    cli("evaluations.human_review.study", "score", "--keys", key_path, missing_key,
        "--responses", root / "complete.json", "--output", root / "complete-report.json")
    report = json.loads((root / "complete-report.json").read_text())
    summary = report["summaries"]["rehearsal"]["overall"]
    assert summary["plannedTasks"] == 8 and summary["submittedTasks"] == 3
    assert summary["resumedTasks"] == 1 and summary["submittedTimingEligibleTasks"] == 2
    assert summary["medianSubmittedActiveMs"] == 1000
    cli("evaluations.human_review.adjudication", "prepare", "--keys", key_path, missing_key,
        "--responses", root / "complete.json", "--assessor", "a", "--assessors", "a", "b",
        "--output", root / "assessment.json")
    sources = [Path(__file__).with_name(name) for name in (
        "study.py", "session.html", "session-recovery.js", "qualify_recovery.py", "qualify_adjudication.py")]
    verification = {"kind": "synthetic-checkpoint-recovery", "humanParticipants": 0,
                    "browserValidation": "pending", "recoveries": 2, "commands": len(commands),
                    "summary": summary,
                    "sourceHashes": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    write_json(root / "verification.json", verification)
    print(json.dumps(verification))


if __name__ == "__main__":
    main()
