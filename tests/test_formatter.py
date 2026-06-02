from pathlib import Path
import tempfile
import unittest

from gwtlang import format_file, format_text, is_formatted, run_text


class FormatterTests(unittest.TestCase):
    def test_format_text_normalizes_spacing_tables_and_comments(self):
        source = """

            PROGRAM   sample


            # leading comment
            GIVEN  order.items are
              | sku | quantity |
              | "keyboard" | 2 |
              | "mouse" | 10 |  # keeps comments

            WHEN total items
              FOR  item in order.items
                add  item.quantity to total
        """

        formatted = format_text(source)

        self.assertEqual(
            formatted,
            """PROGRAM sample

# leading comment
GIVEN order.items are
  | sku        | quantity |
  | "keyboard" | 2        |
  | "mouse"    | 10       |  # keeps comments

WHEN total items
  FOR item in order.items
    add item.quantity to total
""",
        )
        self.assertTrue(is_formatted(formatted))

    def test_format_text_keeps_runtime_behavior(self):
        source = """
            GIVEN  cart.items is [10, 20, 30]
            AND cart.total is 0

            WHEN total cart
              FOR item in cart.items
                add item to cart.total

            WHEN total cart
            THEN cart.total == 60
        """

        formatted = format_text(source)
        result = run_text(formatted)

        self.assertEqual(result.state["cart"]["total"], 60)

    def test_format_text_normalizes_find_block_keyword_spacing(self):
        formatted = format_text(
            """
            GIVEN order.items is []

            WHEN reserve order
              FIND  item in order.items WHERE item.sku == "widget"
                print item.sku
              ELSE
                print "missing"
            """
        )

        self.assertIn("  FIND item in order.items WHERE item.sku == \"widget\"\n", formatted)

    def test_format_text_normalizes_pass_keyword_spacing(self):
        formatted = format_text(
            """
            WHEN keep going
              PASS
            """
        )

        self.assertEqual(formatted, "WHEN keep going\n  PASS\n")

    def test_format_file_reports_changed_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "counter.gwt"
            path.write_text(
                """
                GIVEN  count is 1
                THEN count == 1
                """
            )

            result = format_file(path)

        self.assertTrue(result.changed)
        self.assertEqual(result.formatted, "GIVEN count is 1\nTHEN count == 1\n")

    def test_formatter_canonicalizes_legacy_dto_keyword(self):
        formatted = format_text(
            """
            DTO Account
              balance: number
            """
        )

        self.assertEqual(formatted, "RECORD Account\n  balance: number\n")

    def test_formatter_accepts_request_file_with_external_records(self):
        formatted = format_text(
            """
            GIVEN application is LoanApplication
              amount: 100

            WHEN submit application
            """
        )

        self.assertEqual(
            formatted,
            "GIVEN application is LoanApplication\n  amount: 100\n\nWHEN submit application\n",
        )


if __name__ == "__main__":
    unittest.main()
