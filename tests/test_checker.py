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

    def test_warns_for_implicit_behavior_parameters(self):
        diagnostics = check_program(
            parse_program(
                """
                WHEN touch count
                  add 1 to count
                """
            )
        )

        self.assertTrue(any(diagnostic.code == "GWT018" and diagnostic.severity == "warning" for diagnostic in diagnostics))

    def test_accepts_explicit_signature_parameters(self):
        messages = check_messages(
            """
            WHEN record literal <amount> in count
              GIVEN amount is number
              add amount to count

            GIVEN count is 0
            WHEN record literal 2 in count
            """
        )

        self.assertEqual(messages, [])

    def test_explicit_signature_words_are_literals(self):
        messages = check_messages(
            """
            WHEN record literal <amount> in count
              GIVEN literal is text
              add amount to count
            """
        )

        self.assertIn("contract refers to unknown behavior parameter: literal", messages)

    def test_reports_duplicate_explicit_behavior_signature(self):
        messages = check_messages(
            """
            WHEN record literal <amount> in count
              add amount to count

            WHEN record literal <value> in count
              add value to count
            """
        )

        self.assertTrue(any(message.startswith("duplicate behavior signature: record literal _ in count") for message in messages))

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

    def test_reports_pass_misuse(self):
        outside_messages = check_messages(
            """
            WHEN PASS
            """
        )
        argument_messages = check_messages(
            """
            WHEN keep going
              PASS now

            WHEN keep going
            """
        )

        self.assertIn("PASS is only allowed inside behavior", outside_messages)
        self.assertIn("PASS does not take arguments", argument_messages)

    def test_reports_bad_builtin_shape(self):
        messages = check_messages(
            """
            GIVEN count is 1
            WHEN set count 2
            """
        )

        self.assertIn("expected 'set path to value'", messages)

    def test_reports_set_type_mismatch_for_known_dto_field(self):
        messages = check_messages(
            """
            RECORD Cart
              total: number

            GIVEN cart is Cart
              total: 0

            WHEN set cart.total to "bad"
            """
        )

        self.assertIn("set cart.total expected number, got text", messages)

    def test_reports_add_type_mismatch_for_known_dto_field(self):
        messages = check_messages(
            """
            RECORD Cart
              total: number

            REQUEST cart is Cart

            WHEN add "bad" to cart.total
            """
        )

        self.assertIn("add to cart.total expected number, got text", messages)

    def test_reports_subtract_type_mismatch_for_known_dto_field(self):
        messages = check_messages(
            """
            RECORD Cart
              status: text

            REQUEST cart is Cart

            WHEN subtract 1 from cart.status
            """
        )

        self.assertIn("subtract from cart.status expected number, got text", messages)

    def test_reports_set_type_mismatch_inside_behavior_contract(self):
        messages = check_messages(
            """
            RECORD Cart
              total: number

            WHEN break cart
              GIVEN cart is Cart
              set cart.total to "bad"
            """
        )

        self.assertIn("set cart.total expected number, got text", messages)

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
        RECORD Cart
          items: list
          subtotal: number
          total: number

        WHEN subtotal <cart>
          set cart.subtotal to 0
          FOR item in cart.items
            add item to cart.subtotal
          RETURN cart.subtotal

        WHEN checkout <cart>
          LET subtotal be subtotal cart
          set cart.total to subtotal
        """

        self.assertEqual(check_messages(source), [])

    def test_accepts_typed_behavior_contracts(self):
        messages = check_messages(
            """
            RECORD Cart
              items: list
              total: number

            WHEN cart total for <cart>
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
            RECORD Cart
              total: number

            RECORD Customer
              member: boolean

            WHEN checkout <cart> for <customer>
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

    def test_accepts_request_and_output_contracts(self):
        messages = check_messages(
            """
            RECORD Cart
              total: number

            REQUEST cart is Cart
            OUTPUT cart is Cart

            WHEN checkout <cart>
              GIVEN cart is Cart
              set cart.total to 1
            """
        )

        self.assertEqual(messages, [])

    def test_reports_unknown_request_output_contract_type(self):
        messages = check_messages(
            """
            REQUEST cart is MissingCart
            OUTPUT result is MissingResult
            """
        )

        self.assertIn("unknown REQUEST contract type: MissingCart", messages)
        self.assertIn("unknown OUTPUT contract type: MissingResult", messages)

    def test_reports_overlapping_request_contract_paths(self):
        messages = check_messages(
            """
            REQUEST x is text
            AND x.y is number
            """
        )

        self.assertIn("REQUEST contract path x.y overlaps x; declare x or x.y, not both", messages)

    def test_reports_overlapping_request_contract_paths_when_ancestor_comes_second(self):
        messages = check_messages(
            """
            REQUEST x.y is number
            AND x is text
            """
        )

        self.assertIn("REQUEST contract path x.y overlaps x; declare x or x.y, not both", messages)

    def test_reports_overlapping_output_contract_paths(self):
        messages = check_messages(
            """
            OUTPUT result is text
            AND result.value is number
            """
        )

        self.assertIn(
            "OUTPUT contract path result.value overlaps result; declare result or result.value, not both",
            messages,
        )

    def test_allows_contract_path_overlap_across_request_and_output(self):
        messages = check_messages(
            """
            RECORD Cart
              total: number

            REQUEST cart is Cart
            OUTPUT cart.total is number
            """
        )

        self.assertEqual(messages, [])

    def test_reports_unknown_dto_field_type(self):
        messages = check_messages(
            """
            RECORD Order
              items: list<MissingItem>
            """
        )

        self.assertIn("unknown record field type: list<MissingItem>", messages)

    def test_reports_overlapping_record_field_paths(self):
        messages = check_messages(
            """
            RECORD Foo
              x: text
                y: number
            """
        )

        self.assertIn("record Foo field path x.y overlaps x; declare x or x.y, not both", messages)

    def test_reports_overlapping_record_field_paths_when_ancestor_comes_second(self):
        messages = check_messages(
            """
            RECORD Foo
              x:
                y: number
              x: text
            """
        )

        self.assertIn("record Foo field path x.y overlaps x; declare x or x.y, not both", messages)

    def test_accepts_typed_dto_collection_and_table(self):
        messages = check_messages(
            """
            RECORD OrderItem
              sku: text
              quantity: number

            RECORD Order
              items: list<OrderItem>
              total: number

            WHEN count_order <order>
              GIVEN order is Order
              FOR item in order.items
                add item.quantity to order.total

            GIVEN order is Order
              items: []
              total: 0

            GIVEN order.items are OrderItem
              | sku      | quantity |
              | "widget" | 2        |

            WHEN count_order order
            """
        )

        self.assertEqual(messages, [])

    def test_reports_typed_table_row_mismatch(self):
        messages = check_messages(
            """
            RECORD OrderItem
              sku: text
              quantity: number

            GIVEN order.items are OrderItem
              | sku      | quantity |
              | "widget" | "two"    |
            """
        )

        self.assertIn("GIVEN table field 'quantity' expected number, got text", messages)

    def test_accepts_one_of_record_setup_and_depending_on(self):
        messages = check_messages(
            """
            RECORD Statement is one of
              let_number:
                name: text
                value: number
              print_text:
                text: text

            GIVEN program.statements contains a Statement of kind let_number
              name: "x"
              value: 2

            WHEN handle <statement>
              GIVEN statement is Statement
              DEPENDING ON statement
                WHEN the kind is let_number
                  set statement.value to 3
                WHEN the kind is print_text
                  print statement.text
            """
        )

        self.assertEqual(messages, [])

    def test_reports_one_of_record_setup_type_mismatch(self):
        messages = check_messages(
            """
            RECORD Statement is one of
              let_number:
                name: text
                value: number

            GIVEN program.statements contains a Statement of kind let_number
              name: "x"
              value: "bad"
            """
        )

        self.assertIn("GIVEN Statement field 'value' expected number, got text", messages)

    def test_reports_depending_on_branch_type_mismatch_and_missing_else(self):
        messages = check_messages(
            """
            RECORD Statement is one of
              let_number:
                name: text
                value: number
              print_text:
                text: text

            WHEN handle <statement>
              GIVEN statement is Statement
              DEPENDING ON statement
                WHEN the kind is let_number
                  set statement.value to "bad"
            """
        )

        self.assertIn("set statement.value expected number, got text", messages)
        self.assertIn("DEPENDING ON requires ELSE unless all kinds are covered; missing print_text", messages)

    def test_accepts_collection_helpers_and_for_where(self):
        messages = check_messages(
            """
            RECORD LineItem
              name: text
              quantity: number

            RECORD Invoice
              items: list<LineItem>
              total: number

            GIVEN invoice.items are LineItem
              | name       | quantity |
              | "keyboard" | 2        |

            GIVEN invoice.quantities is [2, 1]
            AND invoice.names is []
            AND invoice.count is 0
            AND invoice.total_quantity is 0

            WHEN summarize <invoice>
              count invoice.items into invoice.count
              sum invoice.quantities into invoice.total_quantity
              sum item.quantity in invoice.items into invoice.total_quantity
              FOR item in invoice.items WHERE item.quantity > 1
                append item.name to invoice.names
              FIND item in invoice.items WHERE item.name == "keyboard"
                append item.name to invoice.names
              ELSE
                append "missing" to invoice.names
              find item in invoice.items WHERE item.name == "keyboard" into invoice.found
              exists item in invoice.items WHERE item.name == "keyboard" into invoice.has_keyboard

            WHEN summarize invoice
            """
        )

        self.assertEqual(messages, [])

    def test_reports_collection_helper_type_mismatches(self):
        messages = check_messages(
            """
            RECORD Cart
              total: number
              status: text
              tags: list<text>

            REQUEST cart is Cart

            WHEN summarize cart
              GIVEN cart is Cart
              count cart.total into cart.status
              sum cart.status into cart.total
              sum cart.tags into cart.total
              append "bad" to cart.total
              FIND tag in cart.total WHERE tag == "sale"
                append tag to cart.tags
              ELSE
                append "missing" to cart.tags
            """
        )

        self.assertIn("count requires a list, got number", messages)
        self.assertIn("count into cart.status expected text, got number", messages)
        self.assertIn("sum requires a list, got text", messages)
        self.assertIn("sum requires a list of numbers, got list<text>", messages)
        self.assertIn("append to cart.total expected list, got number", messages)
        self.assertIn("FIND requires a list", messages)

    def test_reports_find_block_body_type_mismatch(self):
        messages = check_messages(
            """
            RECORD LineItem
              name: text
              quantity: number

            RECORD Invoice
              items: list<LineItem>

            REQUEST invoice is Invoice

            WHEN mark <invoice>
              GIVEN invoice is Invoice
              FIND item in invoice.items WHERE item.name == "keyboard"
                set item.quantity to "many"
              ELSE
                print "missing"
            """
        )

        self.assertIn("set item.quantity expected number, got text", messages)

    def test_reports_projected_sum_type_mismatch(self):
        messages = check_messages(
            """
            RECORD LineItem
              name: text
              quantity: number

            RECORD Invoice
              items: list<LineItem>
              total: number

            GIVEN invoice.items are LineItem
              | name       | quantity |
              | "keyboard" | 2        |

            GIVEN invoice.total is 0

            WHEN summarize <invoice>
              GIVEN invoice is Invoice
              sum item.name in invoice.items into invoice.total

            WHEN summarize invoice
            """
        )

        self.assertIn("sum projection expected number, got text", messages)

    def test_reports_literal_union_assignment_mismatch(self):
        messages = check_messages(
            '''
            RECORD Decision
              status: "new" | "approved"

            REQUEST decision is Decision

            WHEN break <decision>
              GIVEN decision is Decision
              set decision.status to "oops"
            '''
        )

        self.assertIn('set decision.status expected "new" | "approved", got text', messages)

    def test_reports_contract_for_unknown_parameter(self):
        messages = check_messages(
            """
            RECORD Cart
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
            RECORD Cart
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

    def test_accepts_contains_conditions(self):
        messages = check_messages(
            """
            GIVEN response.body is "HTTP/1.1 200 OK"
            AND tags is ["api", "json"]

            WHEN require api tag <tags>
              GIVEN tags is list<text>
              REQUIRE response.body contains "200"
              AND tags contains "api"

            WHEN require api tag tags

            THEN response.body contains "OK"
            AND not tags contains "xml"
            AND not response.body == "HTTP/1.1 500"
            AND response.body does not contain "500"
            """
        )

        self.assertEqual(messages, [])


if __name__ == "__main__":
    unittest.main()
