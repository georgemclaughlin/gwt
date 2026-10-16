import json
from pathlib import Path
import tempfile
import unittest

from gwtlang.maintenance_evaluation import (
    evaluate_candidate, prepare_maintenance, public_feedback, score_maintenance,
)


MANIFEST = Path("evaluations/maintenance/manifest.json")


class MaintenanceEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text())

    def responses(self, language, *, baseline=False):
        responses = []
        for task, case in zip(prepare_maintenance(MANIFEST, language=language, repeats=1), self.manifest["cases"]):
            response = {"caseId": task["caseId"], "attempt": 1}
            if case["kind"] == "clarify":
                response.update(action="clarify", clarifications=["What eligibility criteria apply, which rules can it override, and what reason/status should be returned?"])
            else:
                source = MANIFEST.parent / case["starter" if baseline else "gold"][language]
                response.update(action="code", source=source.read_text())
            responses.append(response)
        return responses

    def test_paired_gold_passes_and_unchanged_baselines_fail_requested_changes(self):
        for language in ("gwt", "python"):
            with self.subTest(language=language):
                gold = score_maintenance(MANIFEST, self.responses(language), language=language, repeats=1)
                self.assertEqual(gold["metrics"]["finalSuccessRate"], 1)
                self.assertEqual(gold["metrics"]["clarificationRate"], 1)
                baseline = score_maintenance(MANIFEST, self.responses(language, baseline=True), language=language, repeats=1)
                self.assertEqual(baseline["metrics"]["finalSuccessRate"], 0)
                for case in baseline["cases"][:3]:
                    assessment = case["attempts"][0]
                    self.assertGreater(assessment["changedCount"], 0)
                    self.assertEqual(assessment["changedPassed"], 0)
                    self.assertEqual(assessment["preservedPassed"], assessment["preservedCount"])

    def test_preparation_withholds_gold_and_hidden_probes_and_pairs_repeats(self):
        for language in ("gwt", "python"):
            tasks = prepare_maintenance(MANIFEST, language=language)
            self.assertEqual(len(tasks), 12)
            self.assertEqual(len({t["caseId"] for t in tasks}), 12)
            for task in tasks:
                self.assertNotIn("gold", task)
                self.assertNotIn("probes", task)
                self.assertLessEqual(len(task["context"]["publicProbes"]), 2)
                self.assertNotIn("expected", task["context"]["source"])

    def test_missing_duplicate_and_unknown_attempts_do_not_inflate_scores(self):
        report = score_maintenance(MANIFEST, [], language="python", repeats=1)
        self.assertEqual(report["metrics"]["finalSuccessRate"], 0)
        response = self.responses("python")[0]
        for responses in ([response, response], [{**response, "attempt": 2}], [{**response, "caseId": "unknown"}]):
            with self.assertRaises(ValueError):
                score_maintenance(MANIFEST, responses, language="python", repeats=1)

    def test_repair_accounting_and_public_feedback(self):
        responses = self.responses("python", baseline=True)
        gold = self.responses("python")
        responses.extend({**response, "attempt": 2} for response in gold[:3])
        report = score_maintenance(MANIFEST, responses, language="python", repeats=1)
        self.assertEqual(report["metrics"]["firstPassSuccessRate"], 0)
        self.assertEqual(report["metrics"]["repairRecoveryRate"], 1)
        self.assertEqual(report["metrics"]["medianSuccessfulRepairIterations"], 1)
        task = prepare_maintenance(MANIFEST, language="python", repeats=1)[0]
        feedback = public_feedback(task, responses[0])
        self.assertEqual(len(feedback), 1)
        self.assertEqual(feedback[0]["input"], task["context"]["publicProbes"][0]["input"])

    def test_timeout_exception_output_noise_and_exact_boolean_results(self):
        probes = [{"input": {}, "expected": {"value": True}}]
        self.assertEqual(evaluate_candidate('def decide(state):\n    return {"value": 1}\n', "python", "unused", probes)["passed"], [False])
        self.assertEqual(evaluate_candidate('print("noise")\ndef decide(state):\n    return {"value": True}\n', "python", "unused", probes)["passed"], [True])
        self.assertEqual(evaluate_candidate('def decide(state):\n    raise ValueError("oops")\n', "python", "unused", probes)["passed"], [False])
        result = evaluate_candidate('while True:\n    pass\n', "python", "unused", probes, timeout=0.2)
        self.assertEqual(result["error"], "candidate timed out")

    def test_worker_snapshots_reused_output_objects_between_calls(self):
        source = 'result = {}\ndef decide(state):\n    result["value"] = state["value"]\n    return result\n'
        probes = [{"input": {"value": value}, "expected": {"value": value}} for value in (1, 2)]
        self.assertEqual(evaluate_candidate(source, "python", "unused", probes)["passed"], [True, True])

    def test_empty_acceptance_sets_cannot_produce_vacuous_success(self):
        for field in ("probes", "requiredConcepts"):
            manifest = json.loads(MANIFEST.read_text())
            case = manifest["cases"][0 if field == "probes" else -1]
            case[field] = []
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "manifest.json"
                path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    prepare_maintenance(path, language="python", repeats=1)

    def test_semantically_wrong_candidate_can_pass_public_examples_but_fail_hidden(self):
        task = prepare_maintenance(MANIFEST, language="python", repeats=1)[0]
        probes = task["context"]["publicProbes"]
        source = "def decide(state):\n"
        for probe in probes:
            source += f'    if state == {probe["input"]!r}:\n        return {probe["expected"]!r}\n'
        source += '    return {"decision": {"status": "rejected", "reason": "expired"}}\n'
        response = {"caseId": task["caseId"], "attempt": 1, "action": "code", "source": source}
        self.assertEqual(public_feedback(task, response), [])
        report = score_maintenance(MANIFEST, [response], language="python", repeats=1)
        self.assertFalse(report["cases"][0]["finalSuccess"])
