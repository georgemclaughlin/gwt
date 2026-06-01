from pathlib import Path
import tempfile
import unittest

from gwtlang import GwtError, run_request, run_source


class RuntimeTests(unittest.TestCase):
    def test_runs_action_with_path_alias(self):
        result = run_source(
            """
            GIVEN account.balance is 100
            AND account.status is "open"

            WHEN withdraw amount from account
              REQUIRE account.status is "open"
              subtract amount from account.balance

            WHEN withdraw 25 from account

            THEN account.balance is 75
            AND account.status is "open"
            """
        )

        self.assertEqual(result.state["account"]["balance"], 75)

    def test_require_blocks_action(self):
        with self.assertRaisesRegex(GwtError, "requirement failed"):
            run_source(
                """
                GIVEN account.balance is 10

                WHEN withdraw amount from account
                  REQUIRE account.balance is at least amount
                  subtract amount from account.balance

                WHEN withdraw 25 from account
                """
            )

    def test_string_values_compare_without_quotes_in_state(self):
        result = run_source(
            '''
            GIVEN account.status is "open"

            WHEN set account.status to "closed"

            THEN account.status is "closed"
            '''
        )

        self.assertEqual(result.state["account"]["status"], "closed")

    def test_failed_assertion_reports_error(self):
        with self.assertRaisesRegex(GwtError, "assertion failed"):
            run_source(
                """
                GIVEN count is 0
                WHEN add 1 to count
                THEN count is 2
                """
            )

    def test_print_captures_output(self):
        result = run_source(
            """
            GIVEN count is 3
            WHEN print count
            THEN count is 3
            """
        )

        self.assertEqual(result.output, ["3"])

    def test_rejects_reserved_behavior_name(self):
        with self.assertRaisesRegex(GwtError, "behavior name is reserved: count"):
            run_source(
                """
                WHEN count items
                  RETURN 0
                """
            )

    def test_arithmetic_expressions_in_statements(self):
        result = run_source(
            """
            GIVEN account.balance is 100
            AND fee is 3

            WHEN withdraw amount from account
              subtract amount + fee * 2 from account.balance

            WHEN withdraw 30 from account

            THEN account.balance == 64
            """
        )

        self.assertEqual(result.state["account"]["balance"], 64)

    def test_symbolic_require_conditions(self):
        result = run_source(
            """
            GIVEN account.balance is 100
            AND fee is 3

            WHEN withdraw amount from account
              REQUIRE account.balance >= amount + fee
              subtract amount + fee from account.balance

            WHEN withdraw 30 from account

            THEN account.balance == 67
            """
        )

        self.assertEqual(result.state["account"]["balance"], 67)

    def test_boolean_expressions(self):
        result = run_source(
            '''
            GIVEN account.balance is 100
            AND account.status is "open"

            WHEN withdraw amount from account
              REQUIRE account.status == "open" and account.balance >= amount
              subtract amount from account.balance

            WHEN withdraw 25 from account

            THEN account.balance == 75
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 75)

    def test_and_continues_when_and_require(self):
        result = run_source(
            '''
            GIVEN account.balance is 100
            AND account.status is "open"

            WHEN withdraw amount from account
              REQUIRE account.status == "open"
              AND account.balance >= amount
              subtract amount from account.balance

            WHEN withdraw 25 from account
            AND withdraw 5 from account

            THEN account.balance == 70
            AND account.status == "open"
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 70)

    def test_explicit_signature_parameters_leave_unmarked_words_literal(self):
        result = run_source(
            '''
            GIVEN count is 0

            WHEN record literal <amount> in count
              add amount to count

            WHEN record literal 2 in count

            THEN count == 2
            '''
        )

        self.assertEqual(result.state["count"], 2)

    def test_runs_independent_scenarios_with_background(self):
        result = run_source(
            '''
            PROGRAM bank

            WHEN withdraw amount from account
              REQUIRE account.status == "open"
              AND account.balance >= amount + fee
              subtract amount + fee from account.balance

            BACKGROUND
            GIVEN account.status is "open"
            AND fee is 3

            SCENARIO successful withdrawal
            GIVEN account.balance is 100
            WHEN withdraw 30 from account
            THEN account.balance == 67

            SCENARIO smaller withdrawal
            GIVEN account.balance is 50
            WHEN withdraw 10 from account
            THEN account.balance == 37
            '''
        )

        self.assertEqual([scenario.name for scenario in result.scenarios], [
            "successful withdrawal",
            "smaller withdrawal",
        ])
        self.assertEqual(result.scenarios[0].state["account"]["balance"], 67)
        self.assertEqual(result.scenarios[1].state["account"]["balance"], 37)

    def test_state_property_requires_single_scenario(self):
        result = run_source(
            """
            SCENARIO one
            GIVEN count is 1
            THEN count == 1

            SCENARIO two
            GIVEN count is 2
            THEN count == 2
            """
        )

        with self.assertRaisesRegex(GwtError, "exactly one scenario"):
            _ = result.state

    def test_given_and_then_record_blocks(self):
        result = run_source(
            '''
            WHEN withdraw amount from account
              REQUIRE account.status == "open"
              AND account.balance >= amount
              subtract amount from account.balance

            GIVEN account is
              balance: 100
              status: "open"

            WHEN withdraw 30 from account

            THEN account is
              balance: 70
              status: "open"
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 70)
        self.assertEqual(result.state["account"]["status"], "open")

    def test_nested_record_blocks_expand_to_paths(self):
        result = run_source(
            '''
            GIVEN account is
              balance: 100
              owner:
                name: "Ada"
                active: true

            THEN account is
              balance: 100
              owner:
                name: "Ada"
                active: true
            '''
        )

        self.assertEqual(result.state["account"]["owner"]["name"], "Ada")
        self.assertTrue(result.state["account"]["owner"]["active"])

    def test_record_block_requires_values(self):
        with self.assertRaisesRegex(GwtError, "record block requires values"):
            run_source(
                """
                GIVEN account is
                  owner:
                """
            )

    def test_let_binds_local_values_inside_behavior(self):
        result = run_source(
            '''
            GIVEN account.balance is 100
            AND fee is 3

            WHEN withdraw amount from account
              LET total be amount + fee
              REQUIRE account.balance >= total
              subtract total from account.balance

            WHEN withdraw 30 from account

            THEN account.balance == 67
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 67)

    def test_let_can_reference_earlier_let(self):
        result = run_source(
            '''
            GIVEN account.balance is 100

            WHEN withdraw amount from account
              LET fee be 3
              LET total be amount + fee
              subtract total from account.balance

            WHEN withdraw 30 from account

            THEN account.balance == 67
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 67)

    def test_let_can_be_passed_to_nested_behavior(self):
        result = run_source(
            '''
            GIVEN account.balance is 100

            WHEN debit amount from account
              subtract amount from account.balance

            WHEN withdraw amount from account
              LET fee be 3
              LET total be amount + fee
              debit total from account

            WHEN withdraw 30 from account

            THEN account.balance == 67
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 67)

    def test_let_is_only_allowed_inside_behavior(self):
        with self.assertRaisesRegex(GwtError, "LET is only allowed inside behavior"):
            run_source(
                """
                WHEN LET total be 3
                """
            )

    def test_let_cannot_overwrite_existing_names(self):
        with self.assertRaisesRegex(GwtError, "cannot overwrite"):
            run_source(
                """
                GIVEN account.balance is 100

                WHEN withdraw amount from account
                  LET amount be amount + 1
                  subtract amount from account.balance

                WHEN withdraw 30 from account
                """
            )

    def test_if_runs_then_branch(self):
        result = run_source(
            '''
            GIVEN account.balance is 20
            AND account.status is "open"

            WHEN withdraw amount from account
              IF account.balance < amount
                set account.status to "declined"
              ELSE
                subtract amount from account.balance

            WHEN withdraw 30 from account

            THEN account.balance == 20
            AND account.status == "declined"
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 20)
        self.assertEqual(result.state["account"]["status"], "declined")

    def test_if_runs_else_branch(self):
        result = run_source(
            '''
            GIVEN account.balance is 100
            AND account.status is "open"

            WHEN withdraw amount from account
              IF account.balance < amount
                set account.status to "declined"
              ELSE
                subtract amount from account.balance

            WHEN withdraw 30 from account

            THEN account.balance == 70
            AND account.status == "open"
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 70)

    def test_if_without_else_can_skip_body(self):
        result = run_source(
            '''
            GIVEN count is 0

            WHEN maybe increment count
              IF count > 0
                add 1 to count

            WHEN maybe increment count

            THEN count == 0
            '''
        )

        self.assertEqual(result.state["count"], 0)

    def test_nested_if_blocks(self):
        result = run_source(
            '''
            GIVEN account.balance is 20
            AND account.status is "open"
            AND account.last_transaction is "none"
            AND fee is 3

            WHEN withdraw amount from account
              LET total be amount + fee
              IF account.status != "open"
                set account.last_transaction to "declined"
              ELSE
                IF account.balance < total
                  set account.last_transaction to "declined"
                ELSE
                  subtract total from account.balance
                  set account.last_transaction to "approved"

            WHEN withdraw 30 from account

            THEN account.balance == 20
            AND account.last_transaction == "declined"
            '''
        )

        self.assertEqual(result.state["account"]["last_transaction"], "declined")

    def test_if_requires_body(self):
        with self.assertRaisesRegex(GwtError, "IF requires a body"):
            run_source(
                """
                GIVEN count is 0

                WHEN maybe increment count
                  IF count == 0

                WHEN maybe increment count
                """
            )

    def test_else_requires_body(self):
        with self.assertRaisesRegex(GwtError, "ELSE requires a body"):
            run_source(
                """
                GIVEN count is 0

                WHEN maybe increment count
                  IF count == 0
                    add 1 to count
                  ELSE

                WHEN maybe increment count
                """
            )

    def test_behavior_return_value_can_be_bound_by_let(self):
        result = run_source(
            '''
            GIVEN account.balance is 100

            WHEN calculate fee for amount
              RETURN amount * 0.1

            WHEN withdraw amount from account
              LET fee be calculate fee for amount
              LET total be amount + fee
              subtract total from account.balance

            WHEN withdraw 30 from account

            THEN account.balance == 67
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 67)

    def test_return_stops_behavior_body(self):
        result = run_source(
            '''
            GIVEN count is 0

            WHEN choose amount
              RETURN 5
              set count to 99

            WHEN apply choice
              LET amount be choose amount
              add amount to count

            WHEN apply choice

            THEN count == 5
            '''
        )

        self.assertEqual(result.state["count"], 5)

    def test_return_propagates_out_of_if_branch(self):
        result = run_source(
            '''
            GIVEN account.balance is 100

            WHEN calculate charge for amount
              IF amount > 10
                RETURN amount + 3
              RETURN amount

            WHEN withdraw amount from account
              LET charge be calculate charge for amount
              subtract charge from account.balance

            WHEN withdraw 30 from account

            THEN account.balance == 67
            '''
        )

        self.assertEqual(result.state["account"]["balance"], 67)

    def test_return_is_only_allowed_inside_behavior(self):
        with self.assertRaisesRegex(GwtError, "RETURN is only allowed inside behavior"):
            run_source(
                """
                WHEN RETURN 1
                """
            )

    def test_return_requires_value(self):
        with self.assertRaisesRegex(GwtError, "RETURN requires a value"):
            run_source(
                """
                WHEN choose amount
                  RETURN

                WHEN choose amount
                """
            )

    def test_let_requires_behavior_to_return_value(self):
        with self.assertRaisesRegex(GwtError, "did not return a value"):
            run_source(
                """
                GIVEN count is 0

                WHEN touch count
                  add 1 to count

                WHEN apply touch
                  LET result be touch count

                WHEN apply touch
                """
            )

    def test_examples_table_expands_scenario_runs(self):
        result = run_source(
            '''
            WHEN withdraw amount from account
              REQUIRE account.balance >= amount
              subtract amount from account.balance

            SCENARIO withdrawal examples
            GIVEN account.balance is <start>
            WHEN withdraw <amount> from account
            THEN account.balance == <end>

            EXAMPLES
              | start | amount | end |
              | 100   | 30     | 70  |
              | 50    | 10     | 40  |
            '''
        )

        self.assertEqual([scenario.name for scenario in result.scenarios], [
            "withdrawal examples example 1",
            "withdrawal examples example 2",
        ])
        self.assertEqual(result.scenarios[0].state["account"]["balance"], 70)
        self.assertEqual(result.scenarios[1].state["account"]["balance"], 40)

    def test_examples_table_values_are_source_text(self):
        result = run_source(
            '''
            SCENARIO account statuses
            GIVEN account.status is <status>
            THEN account.status == <status>

            EXAMPLES
              | status |
              | "open" |
              | "held" |
            '''
        )

        self.assertEqual(result.scenarios[0].state["account"]["status"], "open")
        self.assertEqual(result.scenarios[1].state["account"]["status"], "held")

    def test_examples_missing_placeholder_value_reports_error(self):
        with self.assertRaisesRegex(GwtError, "no value for <amount>"):
            run_source(
                """
                SCENARIO missing placeholder
                GIVEN account.balance is <start>
                WHEN print <amount>
                THEN account.balance == <start>

                EXAMPLES
                  | start |
                  | 100   |
                """
            )

    def test_examples_table_requires_data_row(self):
        with self.assertRaisesRegex(GwtError, "at least one data row"):
            run_source(
                """
                SCENARIO missing rows
                GIVEN count is <count>
                THEN count == <count>

                EXAMPLES
                  | count |
                """
            )

    def test_examples_table_rejects_wrong_cell_count(self):
        with self.assertRaisesRegex(GwtError, "wrong number of cells"):
            run_source(
                """
                SCENARIO bad row
                GIVEN count is <count>
                THEN count == <count>

                EXAMPLES
                  | count | expected |
                  | 1     |
                """
            )

    def test_use_imports_behavior_definitions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = Path(temp_dir) / "banking.gwt"
            module_path.write_text(
                '''
                WHEN withdraw amount from account
                  subtract amount from account.balance
                '''
            )

            result = run_source(
                '''
                USE "./banking.gwt"

                GIVEN account.balance is 100
                WHEN withdraw 30 from account
                THEN account.balance == 70
                ''',
                filename=str(Path(temp_dir) / "main.gwt"),
            )

        self.assertEqual(result.state["account"]["balance"], 70)

    def test_use_imports_returning_behavior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = Path(temp_dir) / "fees.gwt"
            module_path.write_text(
                '''
                WHEN calculate fee for amount
                  RETURN 3
                '''
            )

            result = run_source(
                '''
                USE "./fees.gwt"

                GIVEN account.balance is 100

                WHEN withdraw amount from account
                  LET fee be calculate fee for amount
                  subtract amount + fee from account.balance

                WHEN withdraw 30 from account

                THEN account.balance == 67
                ''',
                filename=str(Path(temp_dir) / "main.gwt"),
            )

        self.assertEqual(result.state["account"]["balance"], 67)

    def test_local_behavior_is_tried_before_imported_behavior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = Path(temp_dir) / "banking.gwt"
            module_path.write_text(
                '''
                WHEN withdraw amount from account
                  subtract 1 from account.balance
                '''
            )

            result = run_source(
                '''
                USE "./banking.gwt"

                WHEN withdraw amount from account
                  subtract amount from account.balance

                GIVEN account.balance is 100
                WHEN withdraw 30 from account
                THEN account.balance == 70
                ''',
                filename=str(Path(temp_dir) / "main.gwt"),
            )

        self.assertEqual(result.state["account"]["balance"], 70)

    def test_use_reports_missing_file(self):
        with self.assertRaisesRegex(GwtError, "USE file not found"):
            run_source(
                'USE "./missing.gwt"\n',
                filename="/tmp/main.gwt",
            )

    def test_list_literals_and_for_loop(self):
        result = run_source(
            '''
            GIVEN cart.items is [10, 20, 30]
            AND cart.total is 0

            WHEN total cart
              FOR item in cart.items
                add item to cart.total

            WHEN total cart

            THEN cart.total == 60
            '''
        )

        self.assertEqual(result.state["cart"]["items"], [10, 20, 30])
        self.assertEqual(result.state["cart"]["total"], 60)

    def test_given_table_creates_list_of_records(self):
        result = run_source(
            '''
            GIVEN order.items are
              | sku      | quantity |
              | "widget" | 2        |
              | "gadget" | 3        |

            GIVEN fulfillment.requested_units is 0

            WHEN count_items
              FOR item in order.items
                add item.quantity to fulfillment.requested_units

            WHEN count_items

            THEN fulfillment.requested_units == 5
            '''
        )

        self.assertEqual(
            result.state["order"]["items"],
            [{"sku": "widget", "quantity": 2}, {"sku": "gadget", "quantity": 3}],
        )
        self.assertEqual(result.state["fulfillment"]["requested_units"], 5)

    def test_given_typed_table_validates_dto_rows(self):
        result = run_source(
            '''
            DTO OrderItem
              sku: text
              quantity: number

            DTO Order
              items: list<OrderItem>

            GIVEN order is Order
              items: []

            GIVEN order.items are OrderItem
              | sku      | quantity |
              | "widget" | 2        |

            WHEN count_items
              FOR item in order.items
                set last_sku to item.sku

            WHEN count_items

            THEN last_sku == "widget"
            '''
        )

        self.assertEqual(result.state["order"]["items"], [{"sku": "widget", "quantity": 2}])

    def test_given_typed_table_rejects_missing_dto_field(self):
        with self.assertRaisesRegex(GwtError, "DTO OrderItem missing field: order.items\\[1\\].quantity"):
            run_source(
                '''
                DTO OrderItem
                  sku: text
                  quantity: number

                GIVEN order.items are OrderItem
                  | sku      |
                  | "widget" |
                '''
            )

    def test_given_typed_table_rejects_wrong_dto_field_type(self):
        with self.assertRaisesRegex(GwtError, "expected order.items\\[1\\].quantity to be number, got text"):
            run_source(
                '''
                DTO OrderItem
                  sku: text
                  quantity: number

                GIVEN order.items are OrderItem
                  | sku      | quantity |
                  | "widget" | "two"    |
                '''
            )

    def test_given_table_supports_examples_placeholders(self):
        result = run_source(
            '''
            SCENARIO table examples
            GIVEN order.items are
              | sku      | quantity |
              | "widget" | <widget> |
              | "gadget" | <gadget> |

            GIVEN total is 0

            WHEN count_items
              FOR item in order.items
                add item.quantity to total

            WHEN count_items

            THEN total == <total>

            EXAMPLES
              | widget | gadget | total |
              | 2      | 3      | 5     |
              | 1      | 4      | 5     |
            '''
        )

        self.assertEqual([scenario.state["total"] for scenario in result.scenarios], [5, 5])

    def test_for_loop_can_return_from_behavior(self):
        result = run_source(
            '''
            GIVEN numbers is [3, 8, 13, 21]

            WHEN first large in numbers
              FOR number in numbers
                IF number > 10
                  RETURN number
              RETURN 0

            WHEN choose number
              LET found be first large in numbers
              set result to found

            WHEN choose number

            THEN result == 13
            '''
        )

        self.assertEqual(result.state["result"], 13)

    def test_collection_helpers_and_for_where(self):
        result = run_source(
            '''
            DTO LineItem
              name: text
              quantity: number

            GIVEN invoice.items are LineItem
              | name       | quantity |
              | "keyboard" | 2        |
              | "mouse"    | 1        |

            GIVEN invoice.quantities is [2, 1]
            AND invoice.names is []
            AND invoice.count is 0
            AND invoice.total_quantity is 0

            WHEN summarize invoice
              count invoice.items into invoice.count
              sum invoice.quantities into invoice.total_quantity
              FOR item in invoice.items WHERE item.quantity > 1
                append item.name to invoice.names
              find item in invoice.items WHERE item.name == "mouse" into invoice.found

            WHEN summarize invoice

            THEN invoice.count == 2
            AND invoice.total_quantity == 3
            AND invoice.names == ["keyboard"]
            AND invoice.found.quantity == 1
            '''
        )

        self.assertEqual(result.state["invoice"]["count"], 2)
        self.assertEqual(result.state["invoice"]["names"], ["keyboard"])
        self.assertEqual(result.state["invoice"]["found"]["name"], "mouse")

    def test_find_requires_match(self):
        with self.assertRaisesRegex(GwtError, "find found no matching item"):
            run_source(
                '''
                GIVEN numbers is [1, 2]

                WHEN choose number
                  find number in numbers where number > 10 into found

                WHEN choose number
                '''
            )

    def test_for_requires_list(self):
        with self.assertRaisesRegex(GwtError, "FOR requires a list"):
            run_source(
                """
                GIVEN count is 1

                WHEN loop count
                  FOR item in count
                    print item

                WHEN loop count
                """
            )

    def test_for_requires_body(self):
        with self.assertRaisesRegex(GwtError, "FOR requires a body"):
            run_source(
                """
                GIVEN items is [1]

                WHEN loop items
                  FOR item in items

                WHEN loop items
                """
            )

    def test_run_request_uses_program_behaviors_with_gwt_input_steps(self):
        program = '''
        WHEN checkout cart
          set cart.total to cart.subtotal + cart.shipping
          set order.status to "priced"
        '''
        request = '''
        GIVEN cart.subtotal is 84
        AND cart.shipping is 8
        AND order.status is "new"

        WHEN checkout cart

        THEN cart.total == 92
        AND order.status == "priced"
        '''

        result = run_request(program, request)

        self.assertEqual(result.state["cart"]["total"], 92)
        self.assertEqual(result.state["order"]["status"], "priced")

    def test_run_request_keeps_request_scenarios_and_examples(self):
        program = '''
        WHEN withdraw amount from account
          subtract amount from account.balance
        '''
        request = '''
        SCENARIO request examples
        GIVEN account.balance is <start>
        WHEN withdraw <amount> from account
        THEN account.balance == <end>

        EXAMPLES
          | start | amount | end |
          | 100   | 30     | 70  |
          | 50    | 10     | 40  |
        '''

        result = run_request(program, request)

        self.assertEqual(len(result.scenarios), 2)
        self.assertEqual(result.scenarios[0].state["account"]["balance"], 70)
        self.assertEqual(result.scenarios[1].state["account"]["balance"], 40)

    def test_run_request_can_use_request_local_behavior(self):
        program = '''
        WHEN calculate fee for amount
          RETURN 3
        '''
        request = '''
        WHEN withdraw amount from account
          LET fee be calculate fee for amount
          subtract amount + fee from account.balance

        GIVEN account.balance is 100
        WHEN withdraw 30 from account
        THEN account.balance == 67
        '''

        result = run_request(program, request)

        self.assertEqual(result.state["account"]["balance"], 67)

    def test_dto_validates_typed_given_record(self):
        result = run_source(
            '''
            DTO Account
              balance: number
              status: text
              owner:
                name: text

            GIVEN account is Account
              balance: 100
              status: "open"
              owner:
                name: "Ada"

            THEN account.balance == 100
            AND account.owner.name == "Ada"
            '''
        )

        self.assertEqual(result.state["account"]["status"], "open")

    def test_dto_rejects_missing_field(self):
        with self.assertRaisesRegex(GwtError, "missing field: account.status"):
            run_source(
                '''
                DTO Account
                  balance: number
                  status: text

                GIVEN account is Account
                  balance: 100
                '''
            )

    def test_dto_rejects_unknown_field(self):
        with self.assertRaisesRegex(GwtError, "unknown field: account.extra"):
            run_source(
                '''
                DTO Account
                  balance: number

                GIVEN account is Account
                  balance: 100
                  extra: true
                '''
            )

    def test_dto_rejects_wrong_type(self):
        with self.assertRaisesRegex(GwtError, "expected account.balance to be number, got text"):
            run_source(
                '''
                DTO Account
                  balance: number

                GIVEN account is Account
                  balance: "100"
                '''
            )

    def test_request_can_use_program_dto(self):
        program = '''
        DTO Cart
          subtotal: number
          total: number

        WHEN price cart
          set cart.total to cart.subtotal
        '''
        request = '''
        GIVEN cart is Cart
          subtotal: 42
          total: 0

        WHEN price cart

        THEN cart.total == 42
        '''

        result = run_request(program, request)

        self.assertEqual(result.state["cart"]["total"], 42)

    def test_request_contract_requires_declared_input_state(self):
        with self.assertRaisesRegex(GwtError, "REQUEST contract failed for cart: unknown path: cart"):
            run_source(
                '''
                DTO Cart
                  total: number

                REQUEST cart is Cart
                '''
            )

    def test_output_contract_rejects_invalid_final_state(self):
        with self.assertRaisesRegex(GwtError, "expected cart.total to be number, got text"):
            run_source(
                '''
                DTO Cart
                  total: number

                REQUEST cart is Cart
                OUTPUT cart is Cart

                GIVEN cart is Cart
                  total: 0

                WHEN set cart.total to "bad"
                '''
            )

    def test_set_enforces_declared_field_type_at_mutation(self):
        with self.assertRaisesRegex(GwtError, "expected cart.total to be number, got text"):
            run_source(
                '''
                DTO Cart
                  total: number

                REQUEST cart is Cart

                GIVEN cart is Cart
                  total: 0

                WHEN set cart.total to "bad"
                '''
            )

    def test_add_enforces_declared_field_type_at_mutation(self):
        with self.assertRaisesRegex(GwtError, "cannot add text to number"):
            run_source(
                '''
                DTO Cart
                  total: number

                REQUEST cart is Cart

                GIVEN cart is Cart
                  total: 0

                WHEN add "bad" to cart.total
                '''
            )

    def test_behavior_contract_enforces_pathref_mutation_type(self):
        with self.assertRaisesRegex(GwtError, "expected cart.total to be number, got text"):
            run_source(
                '''
                DTO Cart
                  total: number

                WHEN break cart
                  GIVEN cart is Cart
                  set cart.total to "bad"

                GIVEN cart.total is 0

                WHEN break cart
                '''
            )

    def test_typed_table_assignment_enforces_later_list_mutation(self):
        with self.assertRaisesRegex(GwtError, "expected invoice.items to be list<LineItem>, got text"):
            run_source(
                '''
                DTO LineItem
                  name: text
                  quantity: number

                GIVEN invoice.items are LineItem
                  | name       | quantity |
                  | "keyboard" | 2        |

                WHEN set invoice.items to "bad"
                '''
            )

    def test_behavior_contracts_are_metadata_not_runtime_steps(self):
        result = run_source(
            '''
            DTO Cart
              items: list
              total: number

            WHEN cart total for cart
              GIVEN cart is Cart
              THEN returns number
              RETURN cart.total

            WHEN mark cart
              GIVEN cart is Cart
              LET total be cart total for cart
              set cart.total to total + 1

            GIVEN cart is Cart
              items: [10, 20]
              total: 30

            WHEN mark cart

            THEN cart.total == 31
            '''
        )

        self.assertEqual(result.state["cart"]["total"], 31)

    def test_use_imports_dto_definitions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = Path(temp_dir) / "types.gwt"
            module_path.write_text(
                '''
                DTO Account
                  balance: number
                '''
            )

            result = run_source(
                '''
                USE "./types.gwt"

                GIVEN account is Account
                  balance: 100

                THEN account.balance == 100
                ''',
                filename=str(Path(temp_dir) / "main.gwt"),
            )

        self.assertEqual(result.state["account"]["balance"], 100)


if __name__ == "__main__":
    unittest.main()
