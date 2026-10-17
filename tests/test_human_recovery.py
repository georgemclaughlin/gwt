"""Checkpoint protocol tests; synthetic observations, not participant evidence."""
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import unittest

from evaluations.human_review.adjudication import prepare_assessment
from evaluations.human_review.study import prepare, render, score, validate_key, validate_response
from tests.test_human_review import synthetic_response


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "evaluations/human_review/session-recovery.js"


def javascript(code, value):
    result = subprocess.run(
        ["node", "-e", "require(process.argv[1]); const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8')); " + code,
         str(SCRIPT)], input=json.dumps(value), capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def partial(packet, key):
    response = synthetic_response(packet, key)
    response["finished"] = False
    response["exportedAt"] = "2026-10-16T00:00:00.000Z"
    response["tasks"][1]["status"] = "skipped"
    response["tasks"][2]["status"] = "draft"
    response["tasks"][2]["rationale"] = 'Saved partial rationale <script> & Unicode 🍂'
    response["tasks"][3].update(status="unseen", predictions={"q1": None, "q2": None},
                                recommendation=None, rationale="", confidence=None, activeMs=None, wallMs=None)
    return response


class HumanRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.packet, self.key = prepare(0, "checkpoint-test")
        self.saved = partial(self.packet, self.key)

    def restore(self, saved=None):
        return javascript("console.log(JSON.stringify(GwtReviewRecovery.restore(input.packet, input.saved)));",
                          {"packet": self.packet, "saved": saved or self.saved})

    def test_restore_preserves_frozen_answers_identity_profile_and_partial_work(self):
        original = deepcopy(self.saved)
        restored = self.restore()
        response = restored["response"]
        self.assertEqual(restored["index"], 2)
        self.assertEqual(response["tasks"][:2], original["tasks"][:2])
        self.assertEqual(response["tasks"][3], original["tasks"][3])
        self.assertEqual(response["profile"], original["profile"])
        self.assertEqual(response["responseId"], original["responseId"])
        self.assertEqual(response["tasks"][2], {**original["tasks"][2], "resumeCount": 1})
        self.assertNotIn("exportedAt", response)
        validate_response(self.packet, response)
        again = self.restore(response)["response"]
        self.assertEqual(again["tasks"][2]["resumeCount"], 2)
        self.assertEqual(self.saved, original)
        validate_response(self.packet, again)

    def test_clock_retains_observed_segments_without_inventing_recovery_gap(self):
        results = javascript("""
          const r = GwtReviewRecovery;
          const clock = r.startClock(input, 100, false);
          const samples = [[1100,false],[2100,true],[2300,false],[2600,false],
                           [2800,true],[3000,false],[4000,false]].map(([now,on]) => r.tick(clock,now,on));
          const next = r.startClock({activeMs:null, wallMs:null}, 5000, true);
          console.log(JSON.stringify({samples, next:r.tick(next,5100,true)}));
        """, self.saved["tasks"][2])
        self.assertEqual(results["samples"], [
            {"activeMs": 1000, "wallMs": 2200}, {"activeMs": 1000, "wallMs": 3200},
            {"activeMs": 1200, "wallMs": 3400}, {"activeMs": 1200, "wallMs": 3700},
            {"activeMs": 1200, "wallMs": 3900}, {"activeMs": 1400, "wallMs": 4100},
            {"activeMs": 1400, "wallMs": 5100},
        ])
        self.assertEqual(results["next"], {"activeMs": 100, "wallMs": 100})

    def test_browser_and_scorer_reject_invalid_identity_order_answers_and_times(self):
        mutations = [
            lambda r: r.update(packetId="other"), lambda r: r.update(assignmentId="other"),
            lambda r: r.update(purpose="participant"), lambda r: r.update(schemaVersion=1),
            lambda r: r.update(schemaVersion=True), lambda r: r.update(responseId="not a valid id"),
            lambda r: r.update(profile=[]), lambda r: r["profile"].update(gwtFamiliarity=True),
            lambda r: r["tasks"].reverse(), lambda r: r["tasks"].pop(),
            lambda r: r["tasks"][1].update(status="draft"),
            lambda r: r["tasks"][0].update(rationale=" "),
            lambda r: r["tasks"][2].update(resumeCount=-1),
            lambda r: r["tasks"][2].update(resumeCount=True),
            lambda r: r["tasks"][2].update(resumeCount=1.2),
            lambda r: r["tasks"][2].update(resumeCount=1000001),
            lambda r: r["tasks"][2].pop("resumeCount"),
            lambda r: r["tasks"][2].update(activeMs=1201),
            lambda r: r["tasks"][2].update(wallMs=-1),
            lambda r: r["tasks"][2].update(rationale="x" * 10001),
            lambda r: r["tasks"][2].update(confidence=True),
            lambda r: r["tasks"][2]["predictions"].update(q1="missing"),
            lambda r: r["tasks"][2]["sourceDigests"].update(proposed="changed"),
            lambda r: r["tasks"][3].update(resumeCount=1),
            lambda r: r["tasks"][3].update(activeMs=0),
            lambda r: r["tasks"][3].update(rationale="unseen answer"),
        ]
        bad = []
        for mutate in mutations:
            response = deepcopy(self.saved)
            mutate(response)
            bad.append(response)
            with self.subTest(mutation=len(bad)), self.assertRaises(ValueError):
                validate_response(self.packet, response)
        refused = javascript("""
          console.log(JSON.stringify(input.bad.map(saved => {
            try { GwtReviewRecovery.restore(input.packet,saved); return false; }
            catch { return true; }
          })));
        """, {"packet": self.packet, "bad": bad})
        self.assertEqual(refused, [True] * len(bad))

    def test_complete_records_score_but_cannot_reopen_and_resume_counts_do_not_credit_answers(self):
        response = synthetic_response(self.packet, self.key)
        response["tasks"][0].update(resumeCount=1, activeMs=100000, wallMs=200000)
        report = score([self.key], [response])
        total = report["summaries"]["rehearsal"]["overall"]
        self.assertEqual(total["correctSubmittedPredictions"], 8)
        self.assertEqual(total["resumedTasks"], 1)
        self.assertEqual(total["resumedSessions"], 1)
        self.assertTrue(all(row["sessionResumed"] for row in report["observations"]))
        self.assertEqual(total["submittedTimingEligibleTasks"], 3)
        self.assertEqual(total["medianSubmittedActiveMs"], 1000)
        self.assertEqual(report["observations"][0]["activeMs"], 100000)
        self.assertTrue(report["observations"][0]["timingInterrupted"])
        with self.assertRaises(subprocess.CalledProcessError):
            self.restore(response)
        for row in response["tasks"]:
            row["resumeCount"] = 1
        total = score([self.key], [response])["summaries"]["rehearsal"]["overall"]
        self.assertEqual(total["submittedTasks"], 4)
        self.assertEqual(total["submittedTimingEligibleTasks"], 0)
        self.assertIsNone(total["medianSubmittedActiveMs"])
        sheet = prepare_assessment([self.key], [response], "a", assessors=["a", "b"])
        self.assertEqual(len(sheet["rows"]), 4)
        with self.assertRaises(ValueError):
            score([self.key], [self.saved, self.restore()["response"]])

    def test_frozen_legacy_records_still_score_but_cannot_resume_under_new_packet(self):
        old = ROOT / "evaluations/human_review/2026-10-16"
        key = json.loads((old / "desktop/facilitator-key.json").read_text())
        response = json.loads((old / "browser/complete-1440.json").read_text())
        packet = validate_key(key)
        validate_response(packet, response)
        total = score([key], [response])["summaries"]["rehearsal"]["overall"]
        self.assertEqual(total["submittedTasks"], 4)
        self.assertEqual(total["resumedTasks"], 0)
        self.assertEqual(total["submittedTimingEligibleTasks"], 4)
        with self.assertRaises(ValueError):
            validate_response(self.packet, response)
        response["tasks"][0]["resumeCount"] = 1
        with self.assertRaises(ValueError):
            validate_response(packet, response)

    def test_render_embeds_recovery_without_external_script_or_remaining_markers(self):
        html = render(self.packet)
        self.assertNotIn("__RECOVERY_JS__", html)
        self.assertNotIn("__PACKET_JSON__", html)
        self.assertNotRegex(html, r"<script[^>]+src=")
        scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
        self.assertEqual(len(scripts), 2)
        result = javascript("for (const source of input) new Function(source); console.log('true');", scripts)
        self.assertTrue(result)
        self.assertNotIn("localStorage", html)


if __name__ == "__main__":
    unittest.main()
