from collections import Counter
from copy import deepcopy
import json
import math
import re
import unittest

from evaluations.human_review.corpus import DOMAINS, expected, probes
from evaluations.human_review.study import assignments, prepare, render, score, validate_response


def synthetic_response(packet, key):
    """Synthetic fixture only; never relabel its output as participant data."""
    return {"schemaVersion": packet.get("responseSchemaVersion", 1), "packetId": packet["packetId"], "assignmentId": packet["assignmentId"],
            "purpose": packet["purpose"], "responseId": packet["assignmentId"] + "-synthetic", "finished": True,
            "profile": {"role": "developer", "priorExposure": "yes", "gwtFamiliarity": 3, "pythonFamiliarity": 3},
            "tasks": [{"id": t["id"], "sourceDigests": t["sourceDigests"], "status": "submitted",
                       "predictions": deepcopy(a["predictions"]), "recommendation": a["recommendation"],
                       "rationale": "Synthetic response for scorer testing only.", "confidence": 5,
                       "activeMs": 1000, "wallMs": 1200,
                       **({"resumeCount": 0} if packet.get("responseSchemaVersion") == 2 else {})}
                      for t, a in zip(packet["tasks"], key["answers"])]}


class HumanReviewTests(unittest.TestCase):
    def test_schedules_balance_position_language_validity_and_adjacent_domains(self):
        counts, adjacency = Counter(), Counter()
        for group in range(16):
            rows = assignments(group)
            self.assertEqual(set(d for d, _, _ in rows), set(DOMAINS))
            self.assertEqual(Counter(l for _, l, _ in rows), {"gwt": 2, "python": 2})
            self.assertEqual(Counter(v for _, _, v in rows), {"correct": 2, "faulty": 2})
            for position, (domain, language, revision) in enumerate(rows):
                counts[domain, position, language, revision] += 1
            adjacency.update((rows[i][0], rows[i + 1][0]) for i in range(3))
        self.assertEqual(len(counts), 64)
        self.assertEqual(set(counts.values()), {1})
        self.assertEqual(len(adjacency), 12)
        self.assertEqual(set(adjacency.values()), {4})
        for invalid in (-1, 16, True, 1.2):
            with self.assertRaises(ValueError):
                assignments(invalid)

    def test_private_answers_absent_and_serialization_cannot_close_script(self):
        packet, key = prepare(0, "test")
        html = render(packet)
        embedded = re.search(r'<script type="application/json" id="packet">(.*?)</script>', html, re.S)[1]
        self.assertEqual(json.loads(embedded), packet)
        for forbidden in ("rationaleRubric", '"revision"', '"correct"', '"faulty"', "facilitator-key"):
            self.assertNotIn(forbidden, embedded)
        packet["tasks"][0]["sources"]["proposed"] += '</script><script>alert("x")</script>'
        embedded = re.search(r'<script type="application/json" id="packet">(.*?)</script>', render(packet), re.S)[1]
        self.assertEqual(json.loads(embedded), packet)
        self.assertNotIn("<", embedded)
        self.assertEqual(prepare(0, "test")[1], key)
        self.assertNotEqual(prepare(0, "other")[0]["packetId"], key["packet"]["packetId"])

    def test_every_question_key_matches_independent_candidate_behavior(self):
        for group in range(16):
            packet, key = prepare(group, f"assignment-{group}")
            for task, answer in zip(packet["tasks"], key["answers"]):
                for q in task["questions"]:
                    choice = next(c for c in q["choices"] if c["id"] == answer["predictions"][q["id"]])
                    self.assertEqual(choice["value"], expected(task["domain"], answer["revision"], q["input"]["facts"]))
        for domain in DOMAINS:
            cases = probes(domain)
            changed = [expected(domain, "baseline", f) != expected(domain, "correct", f) for f in cases]
            faulty = [expected(domain, "correct", f) != expected(domain, "faulty", f) for f in cases]
            self.assertIn(True, changed)
            self.assertIn(False, changed)
            self.assertIn(True, faulty)

    def test_rehearsal_separate_missing_participants_retained_and_no_defect_claim(self):
        packet, key = prepare(0, "rehearsal")
        _, missing_key = prepare(1, "planned-human", "participant")
        report = score([key, missing_key], [synthetic_response(packet, key)])
        participant = report["summaries"]["participant"]["overall"]
        self.assertEqual(participant["plannedTasks"], 4)
        self.assertEqual(participant["statusCounts"], {"missing_session": 4})
        self.assertEqual(participant["correctSubmittedDecisions"], 0)
        self.assertIsNone(participant["medianSubmittedActiveMs"])
        rehearsal = report["summaries"]["rehearsal"]["overall"]
        self.assertEqual(rehearsal["correctSubmittedDecisions"], 4)
        self.assertEqual(rehearsal["correctSubmittedPredictions"], 8)
        self.assertTrue(all(r["rationaleAssessment"] == "pending_manual_review" for r in report["observations"]))

    def test_partial_skipped_unknown_and_unsure_do_not_become_success(self):
        packet, key = prepare(0, "partial")
        response = synthetic_response(packet, key)
        response["finished"] = False
        response["tasks"][0].update(recommendation="unsure", predictions={"q1": "unsure", "q2": "unsure"})
        response["tasks"][1]["status"] = "skipped"
        response["tasks"][2]["status"] = "draft"
        response["tasks"][3].update(status="unseen", activeMs=None, wallMs=None,
                                     predictions={"q1": None, "q2": None}, recommendation=None, rationale="", confidence=None)
        report = score([key], [response])["summaries"]["rehearsal"]["overall"]
        self.assertEqual(report["plannedTasks"], 4)
        self.assertEqual(report["plannedPredictions"], 8)
        self.assertEqual(report["submittedTasks"], 1)
        self.assertEqual(report["correctSubmittedPredictions"], 0)
        self.assertEqual(report["correctSubmittedDecisions"], 0)

    def test_reject_mismatched_identity_duplicate_snapshots_invalid_timing_and_order(self):
        packet, key = prepare(0, "validation")
        original = synthetic_response(packet, key)
        mutations = [lambda r: r.update(packetId="unknown"), lambda r: r.update(purpose="participant"),
                     lambda r: r["tasks"].reverse(), lambda r: r["tasks"].pop(),
                     lambda r: r.update(finished=False), lambda r: r["tasks"][0].update(status="draft"),
                     lambda r: r["tasks"][0].update(recommendation="accept"),
                     lambda r: r["tasks"][0].update(rationale=" "),
                     lambda r: r["tasks"][0]["predictions"].update(q1="nonexistent"),
                     lambda r: r["tasks"][0]["sourceDigests"].update(proposed="forged")]
        mutations += [lambda r, v=v: r["tasks"][0].update(activeMs=v) for v in (-1, math.nan, math.inf, True, 1201)]
        for mutate in mutations:
            response = deepcopy(original)
            mutate(response)
            with self.assertRaises(ValueError):
                validate_response(packet, response)
        with self.assertRaises(ValueError):
            score([key], [original, original])
        with self.assertRaises(ValueError):
            score([key, key], [])
        altered_key = deepcopy(key)
        altered_key["packet"]["tasks"][0]["policy"] = "Changed later"
        with self.assertRaises(ValueError):
            score([altered_key], [])


if __name__ == "__main__":
    unittest.main()
