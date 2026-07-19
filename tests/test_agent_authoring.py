from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from gwtlang.agent_evaluation import (
    main as evaluation_main,
    prepare_evaluation,
    read_jsonl,
    score_evaluation,
)
from gwtlang.formatter import format_text
from gwtlang.inspection import inspect_source
from gwtlang.runtime import run_source
from gwtlang.service import analyze_source


FIXTURE_ROOT = Path("tests/fixtures/agent_authoring")
MANIFEST = FIXTURE_ROOT / "manifest.json"
BASELINE_ROOT = Path("evaluations/agent-authoring/2026-07-18")


class AgentAuthoringCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text())

    def test_manifest_has_versioned_unique_cases(self):
        self.assertEqual(self.manifest["schemaVersion"], 1)
        cases = self.manifest["cases"]
        identifiers = [case["id"] for case in cases]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(
            {case["kind"] for case in cases},
            {"author", "repair", "clarify"},
        )
        self.assertEqual(len(cases), 15)
        self.assertEqual(len(self._cases("author")), 5)
        self.assertEqual(len(self._cases("repair")), 6)
        self.assertEqual(len(self._cases("clarify")), 4)

    def test_author_gold_artifacts_check_format_and_run(self):
        for case in self._cases("author"):
            with self.subTest(case=case["id"]):
                path = FIXTURE_ROOT / case["source"]
                source = path.read_text()
                analysis = analyze_source(source, str(path))

                self.assertIsNotNone(analysis.program)
                self.assertEqual(self._errors(analysis), [])
                self.assertEqual(format_text(source, filename=str(path)), source)
                result = run_source(source, filename=str(path))
                self.assertGreaterEqual(
                    len(result.scenarios),
                    case["minimumScenarioCount"],
                )

    def test_author_starters_define_the_public_probe_vocabulary(self):
        for case in self._cases("author"):
            with self.subTest(case=case["id"]):
                starter_path = FIXTURE_ROOT / case["starterSource"]
                payload = inspect_source(
                    starter_path.read_text(),
                    filename=str(starter_path),
                ).as_payload()
                requests = {
                    request["name"]: request
                    for request in payload["requests"]
                }
                for probe in case["probes"]:
                    self.assertIn(probe["request"], requests)
                    request = requests[probe["request"]]
                    input_paths = {binding["path"] for binding in request["inputs"]}
                    output_paths = {binding["path"] for binding in request["outputs"]}
                    self.assertTrue(set(probe["input"]).issubset(input_paths))
                    self.assertTrue(set(probe["expectedResult"]).issubset(output_paths))

    def test_repair_cases_expose_expected_subcodes_and_validate_after_repair(self):
        for case in self._cases("repair"):
            with self.subTest(case=case["id"]):
                broken_path = FIXTURE_ROOT / case["brokenSource"]
                broken = analyze_source(broken_path.read_text(), str(broken_path))
                subcodes = {
                    diagnostic.subcode
                    for diagnostic in self._errors(broken)
                    if diagnostic.subcode is not None
                }
                self.assertTrue(
                    set(case["requiredDiagnosticSubcodes"]).issubset(subcodes),
                    (case["id"], subcodes),
                )

                repaired_path = FIXTURE_ROOT / case["repairedSource"]
                repaired_source = repaired_path.read_text()
                repaired = analyze_source(repaired_source, str(repaired_path))
                self.assertIsNotNone(repaired.program)
                self.assertEqual(self._errors(repaired), [])
                self.assertEqual(
                    format_text(repaired_source, filename=str(repaired_path)),
                    repaired_source,
                )
                run_source(repaired_source, filename=str(repaired_path))

    def test_clarification_cases_do_not_smuggle_in_gold_code(self):
        for case in self._cases("clarify"):
            with self.subTest(case=case["id"]):
                self.assertNotIn("source", case)
                self.assertNotIn("repairedSource", case)
                self.assertGreaterEqual(len(case["requiredClarifications"]), 1)

    def test_prepared_context_variants_do_not_expose_gold_or_hidden_probes(self):
        for variant in ("source-only", "inspect", "guide", "agent-context"):
            with self.subTest(variant=variant):
                prepared = prepare_evaluation(MANIFEST, variant=variant)
                serialized = json.dumps(prepared)

                self.assertEqual(len(prepared), len(self.manifest["cases"]))
                self.assertNotIn("expectedResult", serialized)
                self.assertNotIn('"probes"', serialized)
                author = next(
                    record
                    for record in prepared
                    if record["caseId"] == "author-explicit-return-window"
                )
                self.assertNotIn("SCENARIO", author["context"]["source"])
                if variant in {"source-only", "agent-context"}:
                    self.assertNotIn("inspection", author["context"])
                else:
                    self.assertIn("inspection", author["context"])
                if variant == "guide":
                    self.assertIn("Generate And Repair", author["context"]["guide"])
                    self.assertIn("PROGRAM hello", author["context"]["guide"])
                    self.assertIn("PROGRAM language tour", author["context"]["guide"])
                    self.assertNotIn("REQUEST review return", author["context"]["guide"])
                if variant == "agent-context":
                    generated = author["context"]["agentContext"]
                    self.assertIn("GWT domain-language context", generated)
                    self.assertIn("## Domain vocabulary", generated)
                    self.assertIn("## GWT syntax examples", generated)
                    self.assertIn("- `review return`", generated)
                    self.assertNotIn("SCENARIO return inside window", generated)

    def test_gold_responses_score_full_semantic_and_clarification_success(self):
        attempts = []
        for case in self.manifest["cases"]:
            if case["kind"] == "author":
                attempts.append(
                    {
                        "caseId": case["id"],
                        "attempt": 1,
                        "action": "code",
                        "source": (FIXTURE_ROOT / case["source"]).read_text(),
                    }
                )
            elif case["kind"] == "repair":
                attempts.append(
                    {
                        "caseId": case["id"],
                        "attempt": 1,
                        "action": "code",
                        "source": (FIXTURE_ROOT / case["repairedSource"]).read_text(),
                    }
                )
            else:
                attempts.append(
                    {
                        "caseId": case["id"],
                        "attempt": 1,
                        "action": "clarify",
                        "clarifications": case["requiredClarifications"],
                    }
                )

        result = score_evaluation(MANIFEST, attempts)

        self.assertEqual(result["attemptedCaseCount"], len(self.manifest["cases"]))
        self.assertEqual(result["metrics"]["firstPassParseRate"], 1.0)
        self.assertEqual(result["metrics"]["firstPassCheckRate"], 1.0)
        self.assertEqual(result["metrics"]["finalValidationRate"], 1.0)
        self.assertEqual(result["metrics"]["scenarioSemanticSuccessRate"], 1.0)
        self.assertEqual(result["metrics"]["correctClarificationRate"], 1.0)
        self.assertEqual(result["metrics"]["repairAttemptedCaseCount"], 0)
        self.assertIsNone(result["metrics"]["repairRecoveryRate"])
        self.assertEqual(result["metrics"]["medianRepairIterations"], 0.0)

    def test_scoring_records_a_failed_first_attempt_and_successful_repair(self):
        case = next(
            case
            for case in self.manifest["cases"]
            if case["id"] == "repair-domain-behavior-typo"
        )
        attempts = [
            {
                "caseId": case["id"],
                "attempt": 1,
                "action": "code",
                "source": (FIXTURE_ROOT / case["brokenSource"]).read_text(),
            },
            {
                "caseId": case["id"],
                "attempt": 2,
                "action": "code",
                "source": (FIXTURE_ROOT / case["repairedSource"]).read_text(),
            },
        ]

        result = score_evaluation(MANIFEST, attempts)
        detail = next(item for item in result["cases"] if item["caseId"] == case["id"])

        self.assertFalse(detail["attempts"][0]["checkOk"])
        self.assertIn("call.no-match", detail["attempts"][0]["diagnosticSubcodes"])
        self.assertTrue(detail["attempts"][1]["validationOk"])
        self.assertTrue(detail["finalSemanticOk"])
        self.assertEqual(result["metrics"]["repairAttemptedCaseCount"], 1)
        self.assertEqual(result["metrics"]["repairRecoveryRate"], 1.0)

    def test_scoring_rejects_non_contiguous_attempt_numbers(self):
        with self.assertRaisesRegex(ValueError, "contiguous from 1"):
            score_evaluation(
                MANIFEST,
                [
                    {
                        "caseId": "clarify-undefined-risk-policy",
                        "attempt": 2,
                        "action": "clarify",
                        "clarifications": ["What defines high risk?"],
                    }
                ],
            )

    def test_prepare_and_score_cli_round_trip_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tasks = root / "tasks.jsonl"
            responses = root / "responses.jsonl"
            report = root / "report.json"

            self.assertEqual(
                evaluation_main(
                    [
                        "prepare",
                        str(MANIFEST),
                        "--variant",
                        "source-only",
                        "--output",
                        str(tasks),
                    ]
                ),
                0,
            )
            prepared = read_jsonl(tasks)
            self.assertEqual(len(prepared), len(self.manifest["cases"]))
            responses.write_text(
                json.dumps(
                    {
                        "caseId": "clarify-undefined-risk-policy",
                        "attempt": 1,
                        "action": "clarify",
                        "clarifications": self._cases("clarify")[0]["requiredClarifications"],
                    }
                )
                + "\n"
            )
            self.assertEqual(
                evaluation_main(
                    ["score", str(MANIFEST), str(responses), "--output", str(report)]
                ),
                0,
            )
            self.assertEqual(json.loads(report.read_text())["attemptedCaseCount"], 1)

    def test_checked_in_live_baseline_reports_are_reproducible(self):
        for model in ("luna", "sol"):
            for variant in ("source-only", "inspect", "guide"):
                with self.subTest(model=model, variant=variant):
                    responses = read_jsonl(
                        BASELINE_ROOT / f"{model}.{variant}.responses.jsonl"
                    )
                    expected = json.loads(
                        (BASELINE_ROOT / f"{model}.{variant}.report.json").read_text()
                    )

                    self.assertEqual(score_evaluation(MANIFEST, responses), expected)

    def _cases(self, kind: str):
        return [case for case in self.manifest["cases"] if case["kind"] == kind]

    @staticmethod
    def _errors(analysis):
        return [
            diagnostic
            for diagnostic in analysis.diagnostics
            if diagnostic.severity == "error"
        ]


if __name__ == "__main__":
    unittest.main()
