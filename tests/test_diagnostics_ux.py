from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from gwtlang.__main__ import main


class DiagnosticUxTests(unittest.TestCase):
    def test_unknown_json_request_points_at_request_selector_and_lists_available_requests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "rules.gwt"
            request = root / "request.json"
            program.write_text('REQUEST review vendor\n  WHEN print "ok"\n')
            request.write_text("{}")

            status, _stdout, stderr = run_cli(
                [
                    "run",
                    str(program),
                    "--json-input",
                    str(request),
                    "--request",
                    "missing request",
                ]
            )

        self.assertEqual(status, 1)
        self.assertIn("gwt: <request>:1: unknown request: missing request", stderr)
        self.assertIn("available requests: review vendor", stderr)
        self.assertIn("  missing request", stderr)

    def test_missing_request_input_points_at_request_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "rules.gwt"
            request = root / "request.json"
            program.write_text(
                "RECORD Cart\n"
                "  total: number\n"
                "\n"
                "REQUEST price cart\n"
                "  GIVEN cart is Cart\n"
                "  WHEN print \"ok\"\n"
            )
            request.write_text("{}")

            status, _stdout, stderr = run_cli(
                [
                    "run",
                    str(program),
                    "--json-input",
                    str(request),
                    "--request",
                    "price cart",
                ]
            )

        self.assertEqual(status, 1)
        self.assertIn(
            "REQUEST contract failed for cart: missing required input; expected Cart",
            stderr,
        )
        self.assertIn("GIVEN cart is Cart", stderr)

    def test_missing_output_points_at_output_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "rules.gwt"
            request = root / "request.json"
            program.write_text(
                "RECORD Cart\n"
                "  total: number\n"
                "\n"
                "REQUEST price cart\n"
                "  WHEN print \"ok\"\n"
                "  OUTPUT cart is Cart\n"
            )
            request.write_text("{}")

            status, _stdout, stderr = run_cli(
                [
                    "run",
                    str(program),
                    "--json-input",
                    str(request),
                    "--request",
                    "price cart",
                ]
            )

        self.assertEqual(status, 1)
        self.assertIn(
            "OUTPUT contract failed for cart: missing required output; expected Cart",
            stderr,
        )
        self.assertIn("OUTPUT cart is Cart", stderr)

    def test_unknown_record_field_reports_expanded_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                "RECORD Cart\n"
                "  total: number\n"
                "\n"
                "GIVEN cart is Cart\n"
                "  subtotal: 1\n"
                "  total: 1\n"
            )

            status, _stdout, stderr = run_cli(["validate", str(program), "--skip-format"])

        self.assertEqual(status, 1)
        self.assertIn("GWT800 record Cart unknown field: cart.subtotal", stderr)
        self.assertIn("GIVEN cart is Cart", stderr)

    def test_literal_union_mismatch_reports_allowed_values_and_actual_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                "RECORD Decision\n"
                "  status: \"approved\" | \"denied\"\n"
                "\n"
                "GIVEN decision is Decision\n"
                "  status: \"maybe\"\n"
            )

            status, _stdout, stderr = run_cli(["validate", str(program), "--skip-format"])

        self.assertEqual(status, 1)
        self.assertIn(
            'expected decision.status to be one of "approved", "denied", got "maybe"',
            stderr,
        )
        self.assertIn("GIVEN decision is Decision", stderr)

    def test_find_block_missing_else_reports_required_else(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                "WHEN classify <items>\n"
                "  FIND item in items WHERE item == \"ok\"\n"
                "    PASS\n"
            )

            status, _stdout, stderr = run_cli(["check", str(program)])

        self.assertEqual(status, 1)
        self.assertIn("GWT900 FIND requires an ELSE block", stderr)
        self.assertIn('FIND item in items WHERE item == "ok"', stderr)

    def test_typoed_behavior_call_suggests_similar_signature(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                "WHEN review <vendor>\n"
                "  PASS\n"
                "\n"
                "GIVEN vendor is \"Acme\"\n"
                "WHEN revieu vendor\n"
            )

            status, _stdout, stderr = run_cli(["check", str(program)])

        self.assertEqual(status, 1)
        self.assertIn("GWT001 no behavior matches: revieu vendor", stderr)
        self.assertIn("did you mean review <vendor>?", stderr)

    def test_json_diagnostic_exposes_structured_repair_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                "WHEN review <vendor>\n"
                "  PASS\n"
                "\n"
                'GIVEN vendor is "Acme"\n'
                "WHEN revieu vendor\n"
            )

            status, stdout, _stderr = run_cli(["check", str(program), "--json"])

        payload = json.loads(stdout)
        diagnostic = payload["diagnostics"][0]
        self.assertEqual(status, 1)
        self.assertEqual(diagnostic["subcode"], "call.no-match")
        self.assertEqual(diagnostic["expected"], "review <vendor>")
        self.assertIn("declare a matching behavior", diagnostic["help"])

    def test_json_type_mismatch_separates_expected_and_actual_types(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                "WHEN review <count>\n"
                "  GIVEN count is integer\n"
                "  PASS\n"
                "\n"
                'GIVEN count is "many"\n'
                "WHEN review count\n"
            )

            status, stdout, _stderr = run_cli(["check", str(program), "--json"])

        diagnostic = json.loads(stdout)["diagnostics"][0]
        self.assertEqual(status, 1)
        self.assertEqual(diagnostic["code"], "GWT016")
        self.assertEqual(diagnostic["subcode"], "type.mismatch")
        self.assertEqual(diagnostic["expected"], "integer")
        self.assertEqual(diagnostic["actual"], "text")
        self.assertIn("types agree", diagnostic["help"])

    def test_invalid_indentation_reports_spacing_guidance(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text("WHEN touch count\n add 1 to count\n")

            status, _stdout, stderr = run_cli(["check", str(program)])

        self.assertEqual(status, 1)
        self.assertIn("invalid indentation: use two spaces per level", stderr)
        self.assertNotIn("unknown top-level form", stderr)

    def test_json_null_mismatch_reports_path_expected_type_and_null_actual(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "rules.gwt"
            request = root / "request.json"
            program.write_text(
                "RECORD Cart\n"
                "  total: number\n"
                "\n"
                "REQUEST price cart\n"
                "  GIVEN cart is Cart\n"
                "  WHEN print \"ok\"\n"
            )
            request.write_text(json.dumps({"cart": {"total": None}}))

            status, _stdout, stderr = run_cli(
                [
                    "run",
                    str(program),
                    "--json-input",
                    str(request),
                    "--request",
                    "price cart",
                ]
            )

        self.assertEqual(status, 1)
        self.assertIn("expected cart.total to be number, got null", stderr)
        self.assertIn("GIVEN cart is Cart", stderr)

    def test_decimal_float_mismatch_reports_decimal_boundary_rule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "rules.gwt"
            request = root / "request.json"
            program.write_text(
                "RECORD Cart\n"
                "  total: decimal\n"
                "\n"
                "REQUEST price cart\n"
                "  GIVEN cart is Cart\n"
                "  WHEN print \"ok\"\n"
            )
            request.write_text(json.dumps({"cart": {"total": 12.3}}))

            status, _stdout, stderr = run_cli(
                [
                    "run",
                    str(program),
                    "--json-input",
                    str(request),
                    "--request",
                    "price cart",
                ]
            )

        self.assertEqual(status, 1)
        self.assertIn("expected cart.total to be decimal, got number", stderr)
        self.assertIn("GIVEN cart is Cart", stderr)


def run_cli(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = main(args)
    return status, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
