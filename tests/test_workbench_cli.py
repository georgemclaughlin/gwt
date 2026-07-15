from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from gwtlang.__main__ import main
from gwtlang.execution_case import capture_execution_case


PROGRAM = '''PROGRAM workbench command

RECORD Input
  value: number

RECORD Decision
  status: text

REQUEST decide
  GIVEN request is Input
  WHEN decide request
  OUTPUT decision is Decision

WHEN decide <request>
  GIVEN request is Input
  DECIDE
    WHEN request.value >= 10
      set decision.status to "review"
    ELSE
      set decision.status to "approved"
'''


class WorkbenchCliTests(unittest.TestCase):
    def test_builds_local_dossier_with_real_comparison_and_verified_scenario(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = root / "old.gwt"
            new = root / "new.gwt"
            old.write_text(PROGRAM)
            new.write_text(PROGRAM.replace('"review"', '"rejected"'))
            case_path = root / "case.execution-case.json"
            capture_execution_case(
                old,
                {"request": {"value": 12}},
                request="decide",
            ).write(case_path)
            output = root / "review.html"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                status = main(
                    [
                        "workbench",
                        str(case_path),
                        "--old",
                        str(old),
                        "--new",
                        str(new),
                        "--program",
                        str(old),
                        "--name",
                        "captured regression",
                        "--review-notice",
                        "Pinned local comparison; no upstream contact.",
                        "--old-label",
                        "upstream snapshot @ abc123",
                        "--new-label",
                        "local GWT candidate",
                        "--output",
                        str(output),
                    ]
                )

            rendered = output.read_text()
            temporary_files = list(root.glob(f".{output.name}.*.tmp"))

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), f"Wrote {output}\n")
        self.assertTrue(rendered.startswith("<!doctype html>\n"))
        self.assertIn("Behavior comparison", rendered)
        self.assertIn("Output changed", rendered)
        self.assertIn("/decision/status", rendered)
        self.assertIn("Verified scenario preview", rendered)
        self.assertIn("SCENARIO captured regression", rendered)
        self.assertIn("Pinned local comparison; no upstream contact.", rendered)
        self.assertIn("Baseline · upstream snapshot @ abc123", rendered)
        self.assertIn("Candidate · local GWT candidate", rendered)
        self.assertIn("No policy was evaluated by this renderer.", rendered)
        self.assertEqual(temporary_files, [])

    def test_builds_case_only_dossier_without_running_a_program(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "rules.gwt"
            program.write_text(PROGRAM)
            case_path = root / "case.execution-case.json"
            capture_execution_case(
                program,
                {"request": {"value": 2}},
                request="decide",
            ).write(case_path)
            output = root / "review.html"

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(
                    [
                        "workbench",
                        str(case_path),
                        "--output",
                        str(output),
                    ]
                )
            rendered = output.read_text()

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), f"Wrote {output}\n")
        self.assertIn("Case overview", rendered)
        self.assertNotIn("Behavior comparison", rendered)
        self.assertNotIn("Verified scenario preview", rendered)

    def test_requires_paired_programs_and_program_for_scenario_name(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            pair_status = main(
                [
                    "workbench",
                    "case.json",
                    "--old",
                    "old.gwt",
                    "--output",
                    "review.html",
                ]
            )
        pair_error = stderr.getvalue()

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            name_status = main(
                [
                    "workbench",
                    "case.json",
                    "--name",
                    "regression",
                    "--output",
                    "review.html",
                ]
            )

        self.assertEqual(pair_status, 2)
        self.assertIn("--old and --new must be supplied together", pair_error)
        self.assertEqual(name_status, 2)
        self.assertIn("--name requires --program", stderr.getvalue())

    def test_rejects_multiple_cases_without_a_comparison(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            status = main(
                [
                    "workbench",
                    "first.execution-case.json",
                    "second.execution-case.json",
                    "--output",
                    "review.html",
                ]
            )

        self.assertEqual(status, 2)
        self.assertIn("multiple CASE files require --old and --new", stderr.getvalue())
        self.assertIn("first CASE as its primary case", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
