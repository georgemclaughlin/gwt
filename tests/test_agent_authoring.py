from __future__ import annotations

import json
from pathlib import Path
import unittest

from gwtlang.formatter import format_text
from gwtlang.runtime import run_source
from gwtlang.service import analyze_source


FIXTURE_ROOT = Path("tests/fixtures/agent_authoring")
MANIFEST = FIXTURE_ROOT / "manifest.json"


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
