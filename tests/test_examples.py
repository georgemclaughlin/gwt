import json
from pathlib import Path
import unittest

from gwtlang import GwtError
from gwtlang.runtime import run_json_request, run_request, run_source
from gwtlang.service import analyze_file


class ExampleProgramTests(unittest.TestCase):
    def test_v01_language_tour_example_runs_scenario_and_request(self):
        program = Path("examples/v01_language_tour/rules.gwt")
        request = Path("examples/v01_language_tour/request.gwt")

        analysis = analyze_file(program)
        self.assertEqual(analysis.diagnostics, [])

        result = run_source(program.read_text(), filename=str(program))
        self.assertEqual(result.state["decision"]["status"], "needs_review")
        self.assertEqual(result.state["decision"]["approved_total"], 60)

        request_result = run_request(
            program.read_text(),
            request.read_text(),
            filename=str(program),
            request_filename=str(request),
        )
        self.assertEqual(request_result.state["decision"]["line_count"], 4)
        self.assertEqual(request_result.state["decision"]["violation_description"], "monitor")

    def test_v01_language_tour_approves_when_no_policy_violation_exists(self):
        program = Path("examples/v01_language_tour/rules.gwt")
        request = """
        GIVEN report is ExpenseReport
          employee: "Ada"
          policy_limit: 100
          lines: []

        GIVEN report.lines are ExpenseLine
          | description    | amount | category    | reimbursable |
          | "airport taxi" | 42     | "transport" | true         |
          | "team lunch"   | 18     | "meals"     | true         |

        GIVEN decision is ExpenseDecision
          line_count: 0
          submitted_total: 0
          approved_total: 0
          approved_descriptions: []
          has_violation: false
          violation_description: "old"
          violation_amount: 999
          status: "new"
          reason: "new"

        WHEN review report into decision
        """

        result = run_request(program.read_text(), request, filename=str(program), request_filename="no_violation.gwt")

        self.assertEqual(result.state["decision"]["status"], "approved")
        self.assertEqual(result.state["decision"]["reason"], "within_policy")
        self.assertFalse(result.state["decision"]["has_violation"])
        self.assertEqual(result.state["decision"]["violation_amount"], 0)

    def test_loan_underwriting_example_runs_scenarios_and_request(self):
        program = Path("examples/loan_underwriting/rules.gwt")
        request = Path("examples/loan_underwriting/request.gwt")
        request_with_assertions = Path("examples/loan_underwriting/request_with_assertions.gwt")

        analysis = analyze_file(program)
        self.assertEqual(analysis.diagnostics, [])

        result = run_source(program.read_text(), filename=str(program))
        self.assertEqual(
            [scenario.state["decision"]["status"] for scenario in result.scenarios],
            ["approved", "manual_review", "denied"],
        )
        self.assertEqual([scenario.state["decision"]["risk_points"] for scenario in result.scenarios], [0, 8, 32])

        request_result = run_request(
            program.read_text(),
            request.read_text(),
            filename=str(program),
            request_filename=str(request),
        )
        self.assertEqual(request_result.state["decision"]["status"], "approved")
        self.assertEqual(request_result.state["decision"]["risk_points"], 2)

        asserted_request_result = run_request(
            program.read_text(),
            request_with_assertions.read_text(),
            filename=str(program),
            request_filename=str(request_with_assertions),
        )
        self.assertEqual(asserted_request_result.state["decision"]["status"], "approved")

    def test_order_fulfillment_example_runs_scenarios_and_request(self):
        program = Path("examples/order_fulfillment/rules.gwt")
        request = Path("examples/order_fulfillment/request.gwt")
        request_with_assertions = Path("examples/order_fulfillment/request_with_assertions.gwt")

        analysis = analyze_file(program)
        self.assertEqual(analysis.diagnostics, [])

        result = run_source(program.read_text(), filename=str(program))
        self.assertEqual(
            [scenario.state["fulfillment"]["status"] for scenario in result.scenarios],
            ["ready", "partial", "held", "backordered", "held"],
        )
        self.assertEqual(
            [scenario.state["fulfillment"]["reserved_units"] for scenario in result.scenarios],
            [5, 5, 0, 0, 0],
        )

        request_result = run_request(
            program.read_text(),
            request.read_text(),
            filename=str(program),
            request_filename=str(request),
        )
        self.assertEqual(request_result.state["fulfillment"]["status"], "partial")
        self.assertEqual(request_result.state["fulfillment"]["reserved_units"], 3)
        self.assertEqual(request_result.state["fulfillment"]["shipping_fee"], 19.5)

        asserted_request_result = run_request(
            program.read_text(),
            request_with_assertions.read_text(),
            filename=str(program),
            request_filename=str(request_with_assertions),
        )
        self.assertEqual(asserted_request_result.state["fulfillment"]["status"], "partial")

    def test_order_fulfillment_holds_unknown_sku_instead_of_ignoring_it(self):
        program = Path("examples/order_fulfillment/rules.gwt")
        request = """
        GIVEN order is OrderRequest
          order_id: "BAD-SKU"
          payment_status: "paid"
          fraud_score: 10
          expedited: false
          items: []

        GIVEN order.items are OrderItem
          | sku       | quantity |
          | "mystery" | 1        |

        GIVEN inventory is InventoryState
          widget_available: 5
          gadget_available: 5
          cable_available: 5
          widget_reserved: 0
          gadget_reserved: 0
          cable_reserved: 0

        GIVEN fulfillment is FulfillmentState
          requested_units: 0
          reserved_units: 0
          backordered_units: 0
          widget_reserved: 0
          gadget_reserved: 0
          cable_reserved: 0
          widget_backordered: 0
          gadget_backordered: 0
          cable_backordered: 0
          unknown_sku_count: 0
          package_count: 0
          shipping_fee: 0
          status: "new"
          reason: "new"

        WHEN fulfill order from inventory into fulfillment
        """

        result = run_request(program.read_text(), request, filename=str(program), request_filename="unknown_sku.gwt")

        self.assertEqual(result.state["fulfillment"]["status"], "held")
        self.assertEqual(result.state["fulfillment"]["reason"], "unknown_sku")
        self.assertEqual(result.state["fulfillment"]["unknown_sku_count"], 1)

    def test_inventory_allocation_spike_runs_scenarios_and_json_request(self):
        program = Path("examples/inventory_allocation_spike/rules.gwt")
        request = Path("examples/inventory_allocation_spike/request.json")

        analysis = analyze_file(program)
        self.assertEqual(analysis.diagnostics, [])

        result = run_source(program.read_text(), filename=str(program))
        self.assertEqual(
            [scenario.state["fulfillment"]["status"] for scenario in result.scenarios],
            ["partial", "partial", "held"],
        )
        self.assertEqual(result.scenarios[1].state["widget_inventory"]["reserved"], 3)

        request_result = run_json_request(
            program.read_text(),
            json.loads(request.read_text()),
            entry="fulfill order from inventory into fulfillment",
            filename=str(program),
            entry_filename=str(request),
        )
        self.assertEqual(request_result.state["fulfillment"]["status"], "partial")
        self.assertEqual(request_result.state["inventory"]["items"][1]["available"], 0)
        self.assertEqual(request_result.scenarios[0].returned_state["inventory"]["items"][1]["reserved"], 1)
        self.assertNotIn("selected_inventory_item", request_result.state)
        self.assertNotIn("inventory_match_found", request_result.state)

    def test_minilang_spec_runs_scenarios_and_json_request(self):
        program = Path("examples/minilang_spec/rules.gwt")
        request = Path("examples/minilang_spec/request.json")

        analysis = analyze_file(program)
        self.assertEqual(analysis.diagnostics, [])

        result = run_source(program.read_text(), filename=str(program))
        self.assertEqual([scenario.state["runtime"]["status"] for scenario in result.scenarios], ["passed", "failed"])
        self.assertEqual(result.scenarios[0].state["runtime"]["outputs"], ["large"])
        self.assertEqual(result.scenarios[0].state["runtime"]["mapped_numbers"], [2, 4, 6, 8])
        self.assertEqual(
            result.scenarios[1].state["front_end"]["errors"],
            ["missing_print_map_double", "unexpected_statement_count"],
        )

        request_result = run_json_request(
            program.read_text(),
            json.loads(request.read_text()),
            entry="run source through front_end into runtime",
            filename=str(program),
            entry_filename=str(request),
        )
        self.assertEqual(request_result.scenarios[0].returned_state["runtime"]["status"], "passed")
        self.assertEqual(request_result.scenarios[0].returned_state["runtime"]["outputs"], ["large"])
        self.assertEqual(request_result.scenarios[0].returned_state["runtime"]["mapped_numbers"], [2, 4, 6, 8])

    def test_minilang2_vm_runs_scenarios_and_json_request(self):
        program = Path("examples/minilang2_vm/rules.gwt")
        request = Path("examples/minilang2_vm/request.json")
        entry = "execute program source through front_end with resolver and bytecode on vm under debugger using repl"

        analysis = analyze_file(program)
        self.assertEqual(analysis.diagnostics, [])

        result = run_source(program.read_text(), filename=str(program))
        self.assertEqual([scenario.state["vm"]["status"] for scenario in result.scenarios], ["passed", "failed"])
        self.assertEqual(result.scenarios[0].state["vm"]["outputs"], [11, 12, 3.162277660168379])
        self.assertEqual(result.scenarios[0].state["repl"]["outputs"], [13, 10])
        self.assertEqual(result.scenarios[0].state["debugger"]["snapshots"][0]["label"], "after_loop")
        self.assertEqual(result.scenarios[0].state["debugger"]["snapshots"][0]["captured_n"], 10)
        self.assertEqual(result.scenarios[1].state["vm"]["errors"], ["undefined_global_missing"])
        self.assertEqual(result.scenarios[1].state["vm"]["stack_trace"][0]["function_name"], "script")
        self.assertEqual(result.scenarios[1].state["vm"]["stack_trace"][1]["function_name"], "vm.execute")

        request_result = run_json_request(
            program.read_text(),
            json.loads(request.read_text()),
            entry=entry,
            filename=str(program),
            entry_filename=str(request),
        )
        returned = request_result.scenarios[0].returned_state
        self.assertEqual(returned["vm"]["status"], "passed")
        self.assertEqual(returned["vm"]["outputs"], [11, 12, 3.162277660168379])
        self.assertEqual(returned["vm"]["closures"][0]["call_count"], 3)
        self.assertEqual(returned["repl"]["outputs"], [13, 10])

    def test_input_normalization_runs_scenario_and_json_request(self):
        program = Path("examples/input_normalization/rules.gwt")
        request = Path("examples/input_normalization/request.json")

        analysis = analyze_file(program)
        self.assertEqual(analysis.diagnostics, [])

        result = run_source(program.read_text(), filename=str(program))
        self.assertEqual(result.state["profile"]["status"], "normalized")
        self.assertEqual(result.state["profile"]["middle_name_status"], "provided")
        self.assertEqual(result.state["profile"]["middle_name"], "Lovelace")

        request_result = run_json_request(
            program.read_text(),
            json.loads(request.read_text()),
            entry="normalize raw into profile",
            filename=str(program),
            entry_filename=str(request),
        )
        profile = request_result.scenarios[0].returned_state["profile"]
        self.assertEqual(profile["status"], "normalized")
        self.assertEqual(profile["name"], "Grace")
        self.assertEqual(profile["middle_name_status"], "missing")
        self.assertEqual(profile["middle_name"], "")
        self.assertEqual(profile["errors"], [])

    def test_output_contract_failure_is_reported(self):
        with self.assertRaisesRegex(GwtError, "OUTPUT contract failed for decision"):
            run_source(
                '''
                RECORD Decision
                  status: "new" | "done"

                OUTPUT decision is Decision

                GIVEN count is 1
                '''
            )

    def test_bad_request_contract_failure_is_reported(self):
        program = Path("examples/order_fulfillment/rules.gwt")
        request = Path("examples/order_fulfillment/request.gwt").read_text().replace(
            'payment_status: "paid"',
            'payment_status: "pending"',
        )

        with self.assertRaisesRegex(GwtError, "expected order.payment_status to be one of"):
            run_request(program.read_text(), request, filename=str(program), request_filename="bad_request.gwt")


if __name__ == "__main__":
    unittest.main()
