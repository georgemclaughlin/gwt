import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

from gwtlang import GwtError, check_file, is_formatted, run_file, run_json_file
from gwtlang.runtime import run_json_request, run_request, run_source
from gwtlang.service import analyze_file


PUBLIC_EXAMPLES_WITH_EMBEDDED_SCENARIOS = [
    Path("examples/language_tour/rules.gwt"),
    Path("examples/order_fulfillment/rules.gwt"),
    Path("examples/loan_underwriting/rules.gwt"),
    Path("examples/inventory_allocation_spike/rules.gwt"),
    Path("examples/minilang_spec/rules.gwt"),
    Path("examples/minilang2_vm/rules.gwt"),
    Path("examples/input_normalization/rules.gwt"),
    Path("examples/vendor_onboarding/rules.gwt"),
    Path("examples/exact_pricing/rules.gwt"),
]


def example_gwt_files():
    return sorted(Path("examples").rglob("*.gwt"))


def example_program_files():
    request_files = {request for _, request in example_gwt_request_pairs()}
    return [program for program in example_gwt_files() if program not in request_files]


def example_gwt_request_pairs():
    pairs = []
    for request in sorted(Path("examples").glob("*/request*.gwt")):
        program = request.parent / "rules.gwt"
        if program.exists():
            pairs.append((program, request))
    return pairs


def first_request_name(program):
    match = re.search(r"(?m)^REQUEST\s+(.+)$", program.read_text())
    if not match:
        raise AssertionError(f"{program} has a JSON request file but no REQUEST declaration")
    return match.group(1).strip()


class ExampleProgramTests(unittest.TestCase):
    def test_all_example_gwt_files_are_formatted(self):
        for program in example_gwt_files():
            with self.subTest(program=str(program)):
                self.assertTrue(is_formatted(program.read_text(), filename=str(program)))

    def test_all_example_program_files_check(self):
        for program in example_program_files():
            with self.subTest(program=str(program)):
                result = check_file(program)
                self.assertTrue(result.ok, result.as_payload())

    def test_all_example_programs_run(self):
        for program in example_program_files():
            with self.subTest(program=str(program)):
                run_file(program)

    def test_all_example_gwt_request_files_run_with_their_program(self):
        for program, request in example_gwt_request_pairs():
            with self.subTest(program=str(program), request=str(request)):
                run_file(program, request_file=request)

    def test_all_example_json_request_files_run_with_their_program(self):
        for request in sorted(Path("examples").glob("*/request.json")):
            program = request.parent / "rules.gwt"
            if not program.exists():
                continue
            with self.subTest(program=str(program), request=str(request)):
                run_json_file(
                    program,
                    json.loads(request.read_text()),
                    request=first_request_name(program),
                    json_file=request,
                )

    def test_checkout_request_uses_named_request_output_boundary(self):
        result = run_file(
            Path("examples/checkout/rules.gwt"),
            request_file=Path("examples/checkout/request.gwt"),
        )
        payload = result.as_payload()

        self.assertEqual(payload["result"]["cart"]["total"], 90.0)
        self.assertEqual(payload["result"]["order"]["status"], "priced")
        self.assertNotIn("customer", payload["result"])
        self.assertIn("customer", payload["state"])

        json_result = run_json_file(
            Path("examples/checkout/rules.gwt"),
            json.loads(Path("examples/checkout/request.json").read_text()),
            request="checkout cart",
            json_file=Path("examples/checkout/request.json"),
        )
        json_payload = json_result.as_payload()

        self.assertEqual(json_payload["result"]["cart"]["total"], 90.0)
        self.assertEqual(json_payload["result"]["order"]["status"], "priced")
        self.assertNotIn("customer", json_payload["result"])
        self.assertIn("customer", json_payload["state"])

    def test_public_examples_include_embedded_scenarios_with_assertions(self):
        for program in PUBLIC_EXAMPLES_WITH_EMBEDDED_SCENARIOS:
            with self.subTest(program=str(program)):
                source = program.read_text()
                self.assertRegex(source, r"(?m)^SCENARIO ")
                self.assertRegex(source, r"(?m)^THEN ")

    def test_language_tour_example_runs_scenario_and_request(self):
        program = Path("examples/language_tour/rules.gwt")
        request = Path("examples/language_tour/request.gwt")

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

    def test_language_tour_approves_when_no_policy_violation_exists(self):
        program = Path("examples/language_tour/rules.gwt")
        request = """
        GIVEN report is ExpenseReport
          employee: "Ada"
          policy_limit: 100
          lines: []

        GIVEN report.lines are ExpenseLine
          | description    | amount | category    | reimbursable |
          | "airport taxi" | 42     | "transport" | true         |
          | "team lunch"   | 18     | "meals"     | true         |

        REQUEST review expense report
        """

        result = run_request(program.read_text(), request, filename=str(program), request_filename="no_violation.gwt")

        self.assertEqual(result.state["decision"]["status"], "approved")
        self.assertEqual(result.state["decision"]["reason"], "within_policy")
        self.assertFalse(result.state["decision"]["has_violation"])
        self.assertEqual(result.state["decision"]["violation_amount"], 0)

    def test_exact_pricing_python_host_example_runs(self):
        completed = subprocess.run(
            [sys.executable, "examples/exact_pricing/host_app.py"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn('"price cart"', completed.stdout)
        self.assertIn('"total": "24.60"', completed.stdout)
        self.assertIn("runtime total: 24.60 (Decimal)", completed.stdout)
        self.assertIn("float input rejected:", completed.stdout)
        self.assertIn('"total": "29.97"', completed.stdout)

    def test_vendor_onboarding_python_host_example_runs(self):
        completed = subprocess.run(
            [sys.executable, "examples/vendor_onboarding/host_app.py"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn('"review vendor"', completed.stdout)
        self.assertIn('"status": "needs_review"', completed.stdout)
        self.assertIn('"reason": "manual_review_required"', completed.stdout)
        self.assertIn("typed decision: needs_review (manual_review_required)", completed.stdout)

    def test_vendor_onboarding_shadow_mode_example_runs(self):
        completed = subprocess.run(
            [sys.executable, "examples/vendor_onboarding/shadow_mode.py"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("MATCH low risk vendor stays approved", completed.stdout)
        self.assertIn("MISMATCH expired insurance exposes legacy gap", completed.stdout)
        self.assertIn("risk_points legacy=9 gwt=10", completed.stdout)
        self.assertIn('"mismatches": 1', completed.stdout)
        self.assertIn('"promotion_ready": false', completed.stdout)

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

        REQUEST fulfill order
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
            request="fulfill order",
            filename=str(program),
            request_filename=str(request),
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
            request="run mini source",
            filename=str(program),
            request_filename=str(request),
        )
        self.assertEqual(request_result.scenarios[0].returned_state["runtime"]["status"], "passed")
        self.assertEqual(request_result.scenarios[0].returned_state["runtime"]["outputs"], ["large"])
        self.assertEqual(request_result.scenarios[0].returned_state["runtime"]["mapped_numbers"], [2, 4, 6, 8])

    def test_minilang2_vm_runs_scenarios_and_json_request(self):
        program = Path("examples/minilang2_vm/rules.gwt")
        request = Path("examples/minilang2_vm/request.json")
        request_name = "execute mini2 source"

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
            request=request_name,
            filename=str(program),
            request_filename=str(request),
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
            request="normalize contact profile",
            filename=str(program),
            request_filename=str(request),
        )
        profile = request_result.scenarios[0].returned_state["profile"]
        self.assertEqual(profile["status"], "normalized")
        self.assertEqual(profile["name"], "Grace")
        self.assertEqual(profile["middle_name_status"], "missing")
        self.assertEqual(profile["middle_name"], "")
        self.assertEqual(profile["errors"], [])

    def test_vendor_onboarding_runs_scenarios_and_json_request(self):
        program = Path("examples/vendor_onboarding/rules.gwt")
        request = Path("examples/vendor_onboarding/request.json")

        analysis = analyze_file(program)
        self.assertEqual(analysis.diagnostics, [])

        result = run_source(program.read_text(), filename=str(program))
        self.assertEqual(
            [scenario.state["decision"]["status"] for scenario in result.scenarios],
            ["approved", "needs_review", "rejected"],
        )
        self.assertEqual([scenario.state["decision"]["risk_points"] for scenario in result.scenarios], [0, 10, 17])
        self.assertEqual(
            result.scenarios[1].state["decision"]["missing_requirements"],
            ["insurance_expired", "security_questionnaire"],
        )

        request_result = run_json_request(
            program.read_text(),
            json.loads(request.read_text()),
            request="review vendor",
            filename=str(program),
            request_filename=str(request),
        )
        decision = request_result.scenarios[0].returned_state["decision"]
        self.assertEqual(decision["status"], "needs_review")
        self.assertEqual(decision["reason"], "manual_review_required")
        self.assertEqual(decision["risk_points"], 10)
        self.assertEqual(decision["tier"], "critical")
        self.assertEqual(decision["missing_requirements"], ["insurance_expired", "security_questionnaire"])

    def test_output_contract_failure_is_reported(self):
        with self.assertRaisesRegex(GwtError, "OUTPUT contract failed for decision"):
            run_source(
                '''
                RECORD Decision
                  status: "new" | "done"

                REQUEST bad output
                  WHEN print "bad"

                  OUTPUT decision is Decision

                SCENARIO bad output
                REQUEST bad output
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
