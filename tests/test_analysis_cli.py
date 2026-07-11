from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from gwtlang import (
    COMPARISON_SCHEMA_VERSION,
    ScenarioGenerationResult,
    capture_execution_case,
    generate_scenario,
    load_execution_case,
)
from gwtlang.__main__ import main
from gwtlang.formatter import format_text


PROGRAM = '''
PROGRAM decisions

RECORD Input
  value: number

RECORD Decision
  status: text

REQUEST decide
  GIVEN request is Input
  WHEN classify request
  OUTPUT decision is Decision

WHEN classify <request>
  GIVEN request is Input
  DECIDE
    WHEN request.value >= 10
      set decision.status to "review"
    ELSE
      set decision.status to "approved"
'''


class AnalysisCliTests(unittest.TestCase):
    def test_scenario_from_run_prints_named_canonical_verified_scenario(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program_path, case_path = self._captured_case(root, value=12)
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                status = main(
                    [
                        "scenario-from-run",
                        str(case_path),
                        "--program",
                        str(program_path),
                        "--name",
                        "captured high value",
                    ]
                )

            source = stdout.getvalue()
            loaded = load_execution_case(case_path)
            api_result = generate_scenario(
                loaded.as_payload(),
                program_path,
                scenario_name="captured high value",
            )

        self.assertEqual(status, 0)
        self.assertIsInstance(api_result, ScenarioGenerationResult)
        self.assertEqual(source, api_result.source)
        self.assertEqual(format_text(source, filename="<test>"), source)
        self.assertTrue(source.startswith("SCENARIO captured high value\n"))
        self.assertIn("REQUEST decide\n", source)
        self.assertIn('THEN decision.status == "review"', source)

    def test_scenario_from_run_atomically_replaces_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program_path, case_path = self._captured_case(root, value=2)
            output_path = root / "captured.gwt"
            output_path.write_text("replace me")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                status = main(
                    [
                        "scenario-from-run",
                        str(case_path),
                        "--program",
                        str(program_path),
                        "--output",
                        str(output_path),
                    ]
                )

            source = output_path.read_text()
            temporary_files = list(root.glob(f".{output_path.name}.*.tmp"))

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), f"Wrote {output_path}\n")
        self.assertTrue(source.startswith("SCENARIO captured decide\n"))
        self.assertIn('THEN decision.status == "approved"', source)
        self.assertEqual(temporary_files, [])

    def test_scenario_from_run_reports_identity_mismatch_and_invalid_case(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program_path, case_path = self._captured_case(root, value=12)
            program_path.write_text(PROGRAM + "\n# changed after capture\n")
            mismatch_stderr = io.StringIO()

            with redirect_stderr(mismatch_stderr):
                mismatch_status = main(
                    [
                        "scenario-from-run",
                        str(case_path),
                        "--program",
                        str(program_path),
                    ]
                )

            invalid_path = root / "invalid.execution-case.json"
            invalid_path.write_text("{}\n")
            invalid_stderr = io.StringIO()
            with redirect_stderr(invalid_stderr):
                invalid_status = main(
                    [
                        "scenario-from-run",
                        str(invalid_path),
                        "--program",
                        str(program_path),
                    ]
                )

        self.assertEqual(mismatch_status, 1)
        self.assertIn("supplied program does not match", mismatch_stderr.getvalue())
        self.assertEqual(invalid_status, 1)
        self.assertIn("execution case", invalid_stderr.getvalue())

    def test_compare_prints_canonical_json_and_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_path, case_path = self._captured_case(root, value=12)
            new_path = root / "new.gwt"
            new_path.write_text(PROGRAM.replace('"review"', '"rejected"'))

            json_stdout = io.StringIO()
            with redirect_stdout(json_stdout):
                json_status = main(
                    [
                        "compare",
                        "--old",
                        str(old_path),
                        "--new",
                        str(new_path),
                        str(case_path),
                        "--json",
                    ]
                )

            text_stdout = io.StringIO()
            with redirect_stdout(text_stdout):
                text_status = main(
                    [
                        "compare",
                        "--old",
                        str(old_path),
                        "--new",
                        str(new_path),
                        str(case_path),
                    ]
                )

        rendered = json_stdout.getvalue()
        payload = json.loads(rendered)
        self.assertEqual(json_status, 0)
        self.assertEqual(rendered, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        self.assertEqual(payload["schemaVersion"], COMPARISON_SCHEMA_VERSION)
        self.assertEqual(payload["kind"], "gwt.comparison")
        self.assertEqual(payload["cases"][0]["classification"], "output_changed")
        self.assertEqual(text_status, 0)
        self.assertIn("1 cases compared", text_stdout.getvalue())
        self.assertIn("[output_changed] decide", text_stdout.getvalue())
        self.assertIn('/decision/status: "review" -> "rejected"', text_stdout.getvalue())

    def test_compare_reports_baseline_mismatch_without_failing_the_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_path, case_path = self._captured_case(root, value=12)
            new_path = root / "new.gwt"
            new_path.write_text(PROGRAM)
            old_path.write_text(PROGRAM + "\n# changed after capture\n")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                status = main(
                    [
                        "compare",
                        "--old",
                        str(old_path),
                        "--new",
                        str(new_path),
                        str(case_path),
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["totals"]["baselineMismatch"], 1)
        self.assertEqual(payload["cases"][0]["classification"], "baseline_mismatch")

    @staticmethod
    def _captured_case(root: Path, *, value: int) -> tuple[Path, Path]:
        program_path = root / "old.gwt"
        program_path.write_text(PROGRAM)
        execution_case = capture_execution_case(
            program_path,
            deepcopy({"request": {"value": value}}),
            request="decide",
        )
        case_path = root / "case.execution-case.json"
        execution_case.write(case_path)
        return program_path, case_path


if __name__ == "__main__":
    unittest.main()
