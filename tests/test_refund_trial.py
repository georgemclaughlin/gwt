import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from gwtlang.case_corpus import load_case_corpus


class RefundTrialTests(unittest.TestCase):
    def test_rehearsal_preserves_evidence_without_fabricating_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "trial"
            result = subprocess.run(
                [sys.executable, "examples/refund_review/run_trial.py", str(destination)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertFalse(report["externalPilot"])
            self.assertFalse(report["humanReviewCompleted"])
            self.assertEqual([item["comparison"]["outputChanged"] for item in report["rounds"]], [6, 6, 3])
            for item in report["rounds"]:
                self.assertEqual(item["acceptance"], {"gwt": 112, "python": 112})
                corpus = load_case_corpus(destination / item["task"] / "corpus.json")
                self.assertEqual(len(corpus.cases), item["reviewCases"])
                self.assertTrue((destination / item["task"] / "observed-baseline.gwt").exists())
            self.assertEqual(json.loads((destination / "acceptance-manifest.json").read_text()), json.loads(Path("evaluations/maintenance/manifest.json").read_text()))
            with (destination / "human-review.csv").open() as stream:
                observations = list(csv.DictReader(stream))
            self.assertEqual(len(observations), 6)
            self.assertTrue(all(not row["reviewer"] and not row["verdict"] and not row["review_seconds"] for row in observations))
            repeated = subprocess.run(
                [sys.executable, "examples/refund_review/run_trial.py", str(destination)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(json.loads((destination / "report.json").read_text()), report)
