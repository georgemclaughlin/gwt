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

    def test_accepts_typed_behavior_contracts(self):
        messages = check_messages(
            """
            DTO Cart
              items: list
              total: number

            WHEN cart total for cart
              GIVEN cart is Cart
              THEN returns number
              RETURN cart.total

            GIVEN cart is Cart
              items: []
              total: 3

            WHEN cart total for cart
            """
        )

        self.assertEqual(messages, [])

    def test_and_continues_contract_given(self):
        messages = check_messages(
            """
            DTO Cart
              total: number

            DTO Customer
              member: boolean

            WHEN checkout cart for customer
              GIVEN cart is Cart
              AND customer is Customer
              set cart.total to 1

            GIVEN cart is Cart
              total: 0
            GIVEN customer is Customer
              member: true

            WHEN checkout cart for customer
            """
        )

        self.assertEqual(messages, [])

    def test_reports_unknown_contract_type(self):
        messages = check_messages(
            """
            WHEN total cart
              GIVEN cart is MissingCart
              RETURN 1
            """
        )

        self.assertIn("unknown contract type: MissingCart", messages)

    def test_reports_contract_for_unknown_parameter(self):
        messages = check_messages(
            """
            DTO Cart
              total: number

            WHEN total cart
              GIVEN customer is Cart
              RETURN 1
            """
        )

        self.assertIn("contract refers to unknown behavior parameter: customer", messages)

    def test_reports_behavior_argument_type_mismatch(self):
        messages = check_messages(
            """
            DTO Cart
              total: number

            WHEN checkout cart
              GIVEN cart is Cart
              set cart.total to 1

            GIVEN total is 3
            WHEN checkout total
            """
        )

        self.assertIn("behavior argument 'cart' expected Cart, got number", messages)

    def test_reports_return_type_mismatch(self):
        messages = check_messages(
            """
            WHEN total cart
              GIVEN cart is any
              THEN returns number
              RETURN "not a number"
            """
        )

        self.assertIn("RETURN expected number, got text", messages)

    def test_reports_missing_declared_return(self):
        messages = check_messages(
            """
            WHEN total cart
              GIVEN cart is any
              THEN returns number
              print cart
            """
        )

        self.assertIn("behavior declares number but does not return a value", messages)

    def test_reports_examples_placeholder_mismatches_in_given_tables(self):
        messages = check_messages(
            """
            SCENARIO table example
            GIVEN order.items are
              | sku      | quantity  |
              | "widget" | <missing> |

            THEN true

            EXAMPLES
              | other |
              | 1     |
            """
        )

        self.assertIn("EXAMPLES has no value for <missing>", messages)


if __name__ == "__main__":
    unittest.main()
