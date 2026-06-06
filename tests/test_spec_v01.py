import unittest

from gwtlang import GwtError, check_text, format_text, run_json_text, run_text


class SpecV01Tests(unittest.TestCase):
    def test_request_contract_validates_after_givens_before_whens(self):
        with self.assertRaisesRegex(GwtError, "record Account missing field: account.status"):
            run_json_text(
                """
                RECORD Account
                  balance: number
                  status: text

                REQUEST repair account
                  GIVEN account is Account

                  WHEN repair account

                WHEN repair <account>
                  set account.status to "open"
                """,
                {"account": {"balance": 100}},
                request="repair account",
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
            RECORD Cart
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

    def test_strings_can_contain_hash_and_is(self):
        result = run_text(
            '''
            GIVEN message is "this is # ok"
            THEN message == "this is # ok"
            '''
        )

        self.assertEqual(result.state["message"], "this is # ok")

    def test_formatter_keeps_hash_inside_string(self):
        formatted = format_text(
            '''
            GIVEN message is "a # b" # trailing
            THEN message == "a # b"
            '''
        )

        self.assertIn('GIVEN message is "a # b"  # trailing', formatted)

    def test_literal_union_contract_rejects_unknown_value(self):
        with self.assertRaisesRegex(GwtError, 'expected decision.status to be one of "new", "approved", got "oops"'):
            run_text(
                '''
                RECORD Decision
                  status: "new" | "approved"

                GIVEN decision is Decision
                  status: "oops"
                '''
            )


if __name__ == "__main__":
    unittest.main()
