import unittest

from gwtlang.checker import check_program
from gwtlang.runtime import parse_program


def check_messages(source: str) -> list[str]:
    return [diagnostic.message for diagnostic in check_program(parse_program(source))]


class CheckerTests(unittest.TestCase):
    def test_reports_unknown_behavior_call(self):
        messages = check_messages(
            """
            GIVEN count is 1
            WHEN missing count
            """
        )

        self.assertIn("no behavior matches: missing count", messages)

    def test_reports_behavior_shape_mismatch(self):
        messages = check_messages(
            """
            WHEN touch count
              add 1 to count

            GIVEN count is 1
            WHEN touch count by 1
            """
        )

        self.assertIn("no behavior matches: touch count by 1", messages)

    def test_reports_duplicate_behavior_signature_in_same_file(self):
        messages = check_messages(
            """
            WHEN touch count
              add 1 to count

            WHEN touch amount
              add amount to count
            """
        )

        self.assertTrue(any(message.startswith("duplicate behavior signature: touch _") for message in messages))

    def test_reports_let_overwriting_parameter(self):
        messages = check_messages(
            """
            WHEN withdraw amount from account
              LET amount be amount + 1
              subtract amount from account.balance
            """
        )

        self.assertIn("LET cannot overwrite an existing name: amount", messages)

    def test_reports_return_outside_behavior(self):
        messages = check_messages(
            """
            WHEN RETURN 1
            """
        )

        self.assertIn("RETURN is only allowed inside behavior", messages)

    def test_reports_bad_builtin_shape(self):
        messages = check_messages(
            """
            GIVEN count is 1
            WHEN set count 2
            """
        )

        self.assertIn("expected 'set path to value'", messages)

    def test_reports_let_behavior_call_without_return_value(self):
        messages = check_messages(
            """
            WHEN touch count
              add 1 to count

            WHEN apply touch
              LET result be touch count
            """
        )

        self.assertIn("behavior does not return a value: touch count", messages)

    def test_reports_zero_argument_let_behavior_call_without_return_value(self):
        messages = check_messages(
            """
            WHEN touch
              print "touch"

            WHEN apply touch
              LET result be touch
            """
        )

        self.assertIn("behavior does not return a value: touch", messages)

    def test_accepts_reusable_request_style_program(self):
        source = """
        DTO Cart
          items: list
          subtotal: number
          total: number

        WHEN subtotal cart
          set cart.subtotal to 0
          FOR item in cart.items
            add item to cart.subtotal
          RETURN cart.subtotal

        WHEN checkout cart
          LET subtotal be subtotal cart
          set cart.total to subtotal
        """

        self.assertEqual(check_messages(source), [])


if __name__ == "__main__":
    unittest.main()
