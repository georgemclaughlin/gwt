import unittest

from gwtlang import GwtError, check_text, format_text, run_text


class SpecV01Tests(unittest.TestCase):
    def test_request_contract_validates_after_givens_before_whens(self):
        with self.assertRaisesRegex(GwtError, "DTO Account missing field: account.status"):
            run_text(
                """
                DTO Account
                  balance: number
                  status: text

                REQUEST account is Account

                WHEN repair <account>
                  set account.status to "open"

                GIVEN account.balance is 100
                WHEN repair account
                """
            )

    def test_builtin_behavior_names_are_reserved(self):
        with self.assertRaisesRegex(GwtError, "behavior name is reserved: sum"):
            run_text(
                """
                WHEN sum values into total
                  RETURN 0
                """
            )

    def test_sum_typed_collection_mismatch_is_static(self):
        result = check_text(
            """
            DTO Cart
              tags: list<text>
              total: number

            WHEN summarize <cart>
              GIVEN cart is Cart
              sum cart.tags into cart.total
            """
        )

        self.assertFalse(result.ok)
        self.assertIn(
            "sum requires a list of numbers, got list<text>",
            [diagnostic.message for diagnostic in result.diagnostics],
        )

    def test_formatter_normalizes_builtin_statement_spacing(self):
        formatted = format_text(
            """
            GIVEN count is 1

            WHEN set  count to 2
            """
        )

        self.assertEqual(formatted, "GIVEN count is 1\n\nWHEN set count to 2\n")

    def test_program_resets_and_continuation(self):
        result = check_text(
            """
            GIVEN count is 1
            PROGRAM sample
            AND total is 2
            """
        )

        self.assertFalse(result.ok)
        self.assertIn("AND has no previous", result.diagnostics[0].message)


if __name__ == "__main__":
    unittest.main()
