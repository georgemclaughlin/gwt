from pathlib import Path
import unittest

from gwtlang.runtime import run_request, run_source
from gwtlang.service import analyze_file


class ExampleProgramTests(unittest.TestCase):
    def test_loan_underwriting_example_runs_scenarios_and_request(self):
        program = Path("examples/loan_underwriting/rules.gwt")
        request = Path("examples/loan_underwriting/request.gwt")
        request_with_assertions = Path("examples/loan_underwriting/request_with_assertions.gwt")

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

        asserted_request_result = run_request(
            program.read_text(),
            request_with_assertions.read_text(),
            filename=str(program),
            request_filename=str(request_with_assertions),
        )
        self.assertEqual(asserted_request_result.state["decision"]["status"], "approved")


if __name__ == "__main__":
    unittest.main()
