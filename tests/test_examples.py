from pathlib import Path
import unittest

from gwtlang.runtime import run_request, run_source
from gwtlang.service import analyze_file


class ExampleProgramTests(unittest.TestCase):
    def test_loan_underwriting_example_runs_scenarios_and_request(self):
        program = Path("examples/loan_underwriting.gwt")
        request = Path("examples/requests/loan_request.gwt")

        analysis = analyze_file(program)
        self.assertEqual(analysis.diagnostics, [])

        result = run_source(program.read_text(), filename=str(program))
        self.assertEqual(
            [scenario.state["decision"]["status"] for scenario in result.scenarios],
            ["approved", "manual_review", "denied"],
        )
        self.assertEqual([scenario.state["decision"]["risk_points"] for scenario in result.scenarios], [0, 8, 32])

        request_result = run_request(
            program.read_text(),
            request.read_text(),
            filename=str(program),
            request_filename=str(request),
        )
        self.assertEqual(request_result.state["decision"]["status"], "approved")
        self.assertEqual(request_result.state["decision"]["risk_points"], 2)


if __name__ == "__main__":
    unittest.main()
