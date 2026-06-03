from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gwtlang.__main__ import format_error, main
from gwtlang.errors import GwtError


class CliDiagnosticsTests(unittest.TestCase):
    def test_formats_line_error_with_source_context(self):
        source = 'GIVEN account.balance is 100\nTHEN account.balance == total\n'

        message = format_error(GwtError("line 2: unknown name: total"), source, "example.gwt")

        self.assertIn("gwt: example.gwt:2: unknown name: total", message)
        self.assertIn("THEN account.balance == total", message)
        self.assertIn("                       ^^^^^", message)

    def test_formats_parser_error_with_filename(self):
        source = "AND count is 1\n"

        message = format_error(
            GwtError("example.gwt:1: AND has no previous GIVEN, WHEN, or THEN"),
            source,
            "example.gwt",
        )

        self.assertIn("gwt: example.gwt:1: AND has no previous", message)
        self.assertIn("AND count is 1", message)

    def test_cli_runs_program_with_gwt_input_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "checkout.gwt"
            request_path = Path(temp_dir) / "request.gwt"
            program_path.write_text(
                '''
                WHEN checkout cart
                  set cart.total to cart.subtotal + cart.shipping
                '''
            )
            request_path.write_text(
                '''
                GIVEN cart.subtotal is 84
                AND cart.shipping is 8

                WHEN checkout cart

                THEN cart.total == 92
                '''
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["run", str(program_path), "--input", str(request_path), "--json"])

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout.getvalue())["result"]["cart"]["total"], 92)

    def test_cli_runs_program_with_json_input_file_and_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "checkout.gwt"
            request_path = Path(temp_dir) / "request.json"
            program_path.write_text(
                """
                RECORD Cart
                  subtotal: number
                  shipping: number
                  total: number

                REQUEST cart is Cart
                OUTPUT cart is Cart

                WHEN checkout <cart>
                  GIVEN cart is Cart
                  set cart.total to cart.subtotal + cart.shipping
                  set audit.status to "priced"
                """
            )
            request_path.write_text(
                json.dumps({"cart": {"subtotal": 84, "shipping": 8, "total": 0}})
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(
                    [
                        "run",
                        str(program_path),
                        "--json-input",
                        str(request_path),
                        "--entry",
                        "checkout cart",
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["request_file"], str(request_path))
        self.assertEqual(payload["result"]["cart"]["total"], 92)
        self.assertEqual(payload["state"]["audit"]["status"], "priced")

    def test_cli_runs_program_with_json_input_from_stdin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "checkout.gwt"
            program_path.write_text(
                """
                RECORD Cart
                  subtotal: number
                  shipping: number
                  total: number

                REQUEST cart is Cart
                OUTPUT cart is Cart

                WHEN checkout <cart>
                  GIVEN cart is Cart
                  set cart.total to cart.subtotal + cart.shipping
                """
            )

            stdin = io.StringIO(json.dumps({"cart": {"subtotal": 84, "shipping": 8, "total": 0}}))
            stdout = io.StringIO()
            with patch("sys.stdin", stdin), redirect_stdout(stdout):
                status = main(
                    [
                        "run",
                        str(program_path),
                        "--json-input",
                        "-",
                        "--entry",
                        "checkout cart",
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["request_file"], "-")
        self.assertEqual(payload["result"]["cart"]["total"], 92)

    def test_cli_json_input_from_stdin_must_be_valid_json_object(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "checkout.gwt"
            program_path.write_text("WHEN checkout <cart>\n  print cart\n")

            stderr = io.StringIO()
            with patch("sys.stdin", io.StringIO("[1, 2]")), redirect_stderr(stderr):
                status = main(
                    [
                        "run",
                        str(program_path),
                        "--json-input",
                        "-",
                        "--entry",
                        "checkout cart",
                    ]
                )

        self.assertEqual(status, 1)
        self.assertIn("stdin JSON input must be an object", stderr.getvalue())

    def test_cli_reports_invalid_json_from_stdin(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "checkout.gwt"
            program_path.write_text("WHEN checkout <cart>\n  print cart\n")

            stderr = io.StringIO()
            with patch("sys.stdin", io.StringIO("{")), redirect_stderr(stderr):
                status = main(
                    [
                        "run",
                        str(program_path),
                        "--json-input",
                        "-",
                        "--entry",
                        "checkout cart",
                    ]
                )

        self.assertEqual(status, 1)
        self.assertIn("stdin JSON input is invalid at line 1, column 2", stderr.getvalue())

    def test_cli_json_input_requires_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "checkout.gwt"
            request_path = Path(temp_dir) / "request.json"
            program_path.write_text("WHEN checkout <cart>\n  print cart\n")
            request_path.write_text("{}")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(["run", str(program_path), "--json-input", str(request_path)])

        self.assertEqual(status, 2)
        self.assertIn("--entry is required", stderr.getvalue())

    def test_cli_entry_requires_json_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "checkout.gwt"
            program_path.write_text("WHEN checkout <cart>\n  print cart\n")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(["run", str(program_path), "--entry", "checkout cart"])

        self.assertEqual(status, 2)
        self.assertIn("--entry requires --json-input", stderr.getvalue())

    def test_legacy_cli_invocation_still_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "counter.gwt"
            program_path.write_text(
                """
                GIVEN count is 1
                THEN count == 1
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main([str(program_path)])

        self.assertEqual(status, 0)
        self.assertIn("PASS Main", stdout.getvalue())

    def test_test_command_prints_scenario_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "scenarios.gwt"
            program_path.write_text(
                """
                SCENARIO one
                GIVEN count is 1
                THEN count == 1

                SCENARIO two
                GIVEN count is 2
                THEN count == 2
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["test", str(program_path)])

        self.assertEqual(status, 0)
        self.assertIn("PASS one", stdout.getvalue())
        self.assertIn("PASS two", stdout.getvalue())

    def test_check_command_reports_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            program_path.write_text(
                """
                WHEN touch <count>
                  add 1 to count

                GIVEN count is 1
                WHEN touch count
                THEN count == 2
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["check", str(program_path)])

        self.assertEqual(status, 0)
        self.assertIn("OK", stdout.getvalue())
        self.assertIn("0 records", stdout.getvalue())
        self.assertIn("1 behaviors", stdout.getvalue())
        self.assertIn("1 scenarios", stdout.getvalue())

    def test_check_command_json_reports_counts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            program_path.write_text(
                """
                WHEN touch <count>
                  add 1 to count
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["check", str(program_path), "--json"])

        self.assertEqual(status, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["dtos"], 0)
        self.assertEqual(payload["behaviors"], 1)
        self.assertEqual(payload["scenarios"], 1)
        self.assertEqual(payload["diagnostics"], [])
        self.assertTrue(any(symbol["kind"] == "behavior" for symbol in payload["symbols"]))

    def test_check_command_reports_static_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            program_path.write_text(
                """
                GIVEN count is 1
                WHEN missing count
                """
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(["check", str(program_path)])

        self.assertEqual(status, 1)
        self.assertIn("GWT001", stderr.getvalue())
        self.assertIn("no behavior matches: missing count", stderr.getvalue())
        self.assertIn("WHEN missing count", stderr.getvalue())

    def test_check_command_json_reports_static_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            program_path.write_text(
                """
                GIVEN count is 1
                WHEN missing count
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["check", str(program_path), "--json"])

        self.assertEqual(status, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["diagnostics"][0]["message"], "no behavior matches: missing count")
        self.assertEqual(payload["diagnostics"][0]["code"], "GWT001")
        self.assertIn("range", payload["diagnostics"][0])

    def test_check_command_rejects_imports_outside_import_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            outside = Path(temp_dir) / "outside.gwt"
            program_path = root / "workflow.gwt"
            outside.write_text(
                """
                RECORD Account
                  balance: number
                """
            )
            program_path.write_text('USE "../outside.gwt"\n')

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(["check", str(program_path), "--import-root", str(root)])

        self.assertEqual(status, 1)
        self.assertIn("GWT900", stderr.getvalue())
        self.assertIn("USE import is outside allowed roots", stderr.getvalue())

    def test_check_command_json_rejects_absolute_imports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            module_path = root / "types.gwt"
            program_path = root / "workflow.gwt"
            module_path.write_text(
                """
                RECORD Account
                  balance: number
                """
            )
            program_path.write_text(f'USE "{module_path}"\n')

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(
                    [
                        "check",
                        str(program_path),
                        "--import-root",
                        str(root),
                        "--no-absolute-imports",
                        "--json",
                    ]
                )

        self.assertEqual(status, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["diagnostics"][0]["code"], "GWT900")
        self.assertIn(
            "USE absolute import is not allowed",
            payload["diagnostics"][0]["message"],
        )

    def test_test_command_rejects_imports_outside_import_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            outside = Path(temp_dir) / "outside.gwt"
            program_path = root / "workflow.gwt"
            outside.write_text(
                """
                WHEN touch count
                  add 1 to count
                """
            )
            program_path.write_text(
                """
                USE "../outside.gwt"

                GIVEN count is 1
                WHEN touch count
                """
            )

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(["test", str(program_path), "--import-root", str(root)])

        self.assertEqual(status, 1)
        self.assertIn("USE import is outside allowed roots", stderr.getvalue())

    def test_run_command_rejects_absolute_imports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            module_path = root / "steps.gwt"
            program_path = root / "workflow.gwt"
            request_path = root / "request.json"
            module_path.write_text(
                """
                WHEN touch count
                  add 1 to count
                """
            )
            program_path.write_text(
                f"""
                USE "{module_path}"

                REQUEST count is number
                OUTPUT count is number
                """
            )
            request_path.write_text('{"count": 1}\n')

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(
                    [
                        "run",
                        str(program_path),
                        "--json-input",
                        str(request_path),
                        "--entry",
                        "touch count",
                        "--import-root",
                        str(root),
                        "--no-absolute-imports",
                    ]
                )

        self.assertEqual(status, 1)
        self.assertIn("USE absolute import is not allowed", stderr.getvalue())

    def test_types_command_prints_typescript_declarations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            program_path.write_text(
                """
                RECORD Cart
                  subtotal: number
                  status: "new" | "priced"

                REQUEST cart is Cart
                OUTPUT cart is Cart
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["types", str(program_path)])

        self.assertEqual(status, 0)
        output = stdout.getvalue()
        self.assertIn("export interface Cart", output)
        self.assertIn('status: "new" | "priced";', output)
        self.assertIn("export interface GwtRequest", output)
        self.assertIn("cart: Cart;", output)

    def test_types_command_writes_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            output_path = Path(temp_dir) / "workflow.d.ts"
            program_path.write_text(
                """
                RECORD Cart
                  subtotal: number

                REQUEST cart is Cart
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["types", str(program_path), "--output", str(output_path)])

            self.assertEqual(status, 0)
            self.assertIn("Wrote", stdout.getvalue())
            self.assertIn("export interface Cart", output_path.read_text())

    def test_types_command_reports_checker_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            program_path.write_text("REQUEST cart is Missing\n")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(["types", str(program_path)])

        self.assertEqual(status, 1)
        self.assertIn("unknown REQUEST contract type: Missing", stderr.getvalue())

    def test_debug_lines_command_reports_executable_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            program_path.write_text(
                """
                WHEN touch count
                  add 1 to count

                GIVEN count is 1
                WHEN touch count
                THEN count == 2
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["debug-lines", str(program_path), "--json"])

        self.assertEqual(status, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual([line["line"] for line in payload["lines"]], [3, 5, 6, 7])

    def test_format_command_updates_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            program_path.write_text(
                """
                GIVEN  count is 1
                THEN count == 1
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["format", str(program_path)])

            self.assertEqual(status, 0)
            self.assertIn("Formatted", stdout.getvalue())
            self.assertEqual(program_path.read_text(), "GIVEN count is 1\nTHEN count == 1\n")

    def test_format_command_check_reports_unformatted_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "workflow.gwt"
            program_path.write_text("GIVEN  count is 1\nTHEN count == 1\n")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(["format", str(program_path), "--check"])

            self.assertEqual(status, 1)
            self.assertIn("needs formatting", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
