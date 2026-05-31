from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

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
                status = main([str(program_path), "--input", str(request_path), "--json"])

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout.getvalue())["cart"]["total"], 92)


if __name__ == "__main__":
    unittest.main()
