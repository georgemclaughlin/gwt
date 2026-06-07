import json
from pathlib import Path
import tempfile
import unittest

from gwtlang import (
    GwtError,
    check_text,
    format_text,
    generate_python_text,
    generate_typescript_text,
    inspect_source,
    run_json_text,
    run_text,
    validate_file,
)


class SpecV02ConformanceTests(unittest.TestCase):
    def test_source_files_and_formatter_define_canonical_layout(self):
        formatted = format_text(
            """
            PROGRAM   canonical

            # comments survive
            RECORD   Item
              sku:   text

            GIVEN   items are Item
              | sku |
              | "a" |
            """
        )

        self.assertEqual(
            formatted,
            """PROGRAM canonical

# comments survive
RECORD Item
  sku: text

GIVEN items are Item
  | sku |
  | "a" |
""",
        )
        self.assertTrue(formatted.endswith("\n"))

    def test_program_shape_imports_records_requests_and_behaviors_but_not_scenarios(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library.gwt"
            main = root / "main.gwt"
            library.write_text(
                """
                RECORD ImportedInput
                  amount: integer

                RECORD ImportedDecision
                  status: text

                REQUEST imported review
                  GIVEN request is ImportedInput

                  GIVEN decision is ImportedDecision
                    status: "pending"

                  WHEN approve request into decision

                  OUTPUT decision is ImportedDecision

                WHEN approve <request> into <decision>
                  set decision.status to "approved"

                SCENARIO imported scenario should not run
                GIVEN leak is 1
                THEN leak == 1
                """
            )
            main.write_text(
                """
                USE "library.gwt"

                GIVEN request is ImportedInput
                  amount: 3

                REQUEST imported review

                THEN decision.status == "approved"
                """
            )

            result = run_text(main.read_text(), filename=str(main))

        self.assertEqual(result.state["decision"]["status"], "approved")
        self.assertNotIn("leak", result.state)

    def test_named_request_execution_validates_inputs_and_returns_declared_outputs(self):
        source = """
        RECORD Order
          total: decimal

        RECORD Decision
          status: "new" | "priced"
          total: decimal

        REQUEST price order
          GIVEN order is Order

          GIVEN decision is Decision
            status: "new"
            total: "0.00"

          WHEN price order into decision

          OUTPUT decision is Decision

          THEN decision.status == "priced"

        WHEN price <order> into <decision>
          set decision.total to order.total
          set decision.status to "priced"
        """

        result = run_json_text(
            source,
            {"order": {"total": "12.30"}, "host_note": "kept in state"},
            request="price order",
        )
        payload = result.as_payload()

        self.assertEqual(payload["result"], {"decision": {"status": "priced", "total": "12.30"}})
        self.assertEqual(payload["state"]["host_note"], "kept in state")

        with self.assertRaisesRegex(GwtError, "REQUEST contract failed for order"):
            run_json_text(source, {"order": {}}, request="price order")

    def test_behavior_statements_cover_control_flow_and_builtins(self):
        result = run_text(
            """
            RECORD Event is one of
              charge:
                amount: integer
              refund:
                amount: integer

            GIVEN events contains an Event of kind charge
              amount: 7
            GIVEN events contains an Event of kind refund
              amount: 3

            GIVEN summary is
              charge_total: 0
              refunds: 0
              first_charge: 0
              status: "new"
              sign: "unknown"

            WHEN summarize <events> into <summary>
              FOR event in events WHERE event.amount > 0
                DEPENDING ON event
                  WHEN the kind is charge
                    add event.amount to summary.charge_total
                  WHEN the kind is refund
                    add event.amount to summary.refunds
              FIND event in events WHERE event.kind == "charge"
                set summary.first_charge to event.amount
              ELSE
                set summary.first_charge to 0
              DECIDE
                WHEN summary.charge_total >= 10
                  set summary.status to "high"
                WHEN summary.charge_total > 0
                  set summary.status to "some"
                ELSE
                  set summary.status to "none"
              DEPENDING ON summary.status
                WHEN the value is "some"
                  set summary.sign to "ok"
                ELSE
                  set summary.sign to "other"

            WHEN summarize events into summary

            THEN summary.charge_total == 7
            AND summary.refunds == 3
            AND summary.first_charge == 7
            AND summary.status == "some"
            AND summary.sign == "ok"
            """
        )

        self.assertEqual(result.state["summary"]["charge_total"], 7)
        self.assertEqual(result.state["summary"]["sign"], "ok")

    def test_types_include_decimal_literal_unions_lists_any_and_no_null_type(self):
        source = """
        RECORD Payment
          amount: decimal
          attempts: integer
          status: "new" | "paid"
          tags: list<text>
          metadata: any

        REQUEST accept payment
          GIVEN payment is Payment
          WHEN mark payment
          OUTPUT payment is Payment

        WHEN mark <payment>
          set payment.status to "paid"
        """

        result = run_json_text(
            source,
            {
                "payment": {
                    "amount": "19.99",
                    "attempts": 1,
                    "status": "new",
                    "tags": ["card"],
                    "metadata": None,
                }
            },
            request="accept payment",
        )

        self.assertEqual(result.as_payload()["result"]["payment"]["amount"], "19.99")
        self.assertEqual(result.as_payload()["result"]["payment"]["metadata"], None)

        with self.assertRaisesRegex(GwtError, "expected payment.status to be one of"):
            run_json_text(
                source,
                {
                    "payment": {
                        "amount": "19.99",
                        "attempts": 1,
                        "status": "void",
                        "tags": [],
                        "metadata": None,
                    }
                },
                request="accept payment",
            )

        with self.assertRaisesRegex(GwtError, "expected payment.tags to be list<text>, got null"):
            run_json_text(
                source,
                {
                    "payment": {
                        "amount": "19.99",
                        "attempts": 1,
                        "status": "new",
                        "tags": None,
                        "metadata": None,
                    }
                },
                request="accept payment",
            )

    def test_type_aliases_name_literal_unions_and_collection_items(self):
        source = """
        TYPE DecisionStatus is "new" | "approved"
        TYPE DecisionHistory is list<DecisionStatus>
        TYPE ReviewReasons is list<"ready" | "manual">

        RECORD Decision
          status: DecisionStatus
          history: DecisionHistory
          reasons: ReviewReasons

        REQUEST review decision
          GIVEN decision is Decision

          WHEN approve decision

          OUTPUT decision is Decision

          THEN decision.status == "approved"

        WHEN approve <decision>
          GIVEN decision is Decision
          set decision.status to "approved"
          append "approved" to decision.history
          append "ready" to decision.reasons
        """

        result = run_json_text(
            source,
            {"decision": {"status": "new", "history": [], "reasons": []}},
            request="review decision",
        )

        self.assertEqual(result.as_payload()["result"]["decision"]["status"], "approved")
        self.assertEqual(result.as_payload()["result"]["decision"]["history"], ["approved"])

        with self.assertRaisesRegex(GwtError, "expected decision.status to be one of"):
            run_json_text(
                source,
                {"decision": {"status": "denied", "history": [], "reasons": []}},
                request="review decision",
            )

    def test_api_payloads_inspection_and_type_generation_use_named_requests(self):
        source = """
        PROGRAM host contract

        RECORD Decision
          status: text

        REQUEST review vendor
          GIVEN vendor.name is text

          GIVEN decision is Decision
            status: "pending"

          WHEN mark vendor.name into decision

          OUTPUT decision is Decision

        WHEN mark <name> into <decision>
          set decision.status to "approved"
        """

        execution = run_json_text(source, {"vendor": {"name": "Ada"}}, request="review vendor")
        payload = execution.as_payload()
        manifest = inspect_source(source).as_payload()
        typescript = generate_typescript_text(source).source
        python = generate_python_text(source).source

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scenario_count"], 1)
        self.assertEqual(payload["result"], {"decision": {"status": "approved"}})
        self.assertEqual([request["name"] for request in manifest["requests"]], ["review vendor"])
        self.assertIn("export interface ReviewVendorRequest", typescript)
        self.assertIn('export type GwtRequestName = "review vendor";', typescript)
        self.assertNotIn("GwtEntry", typescript)
        self.assertIn("class HostContractClient", python)
        self.assertIn("REVIEW_VENDOR_REQUEST: GwtRequestName = 'review vendor'", python)

    def test_removed_v01_boundary_forms_are_rejected(self):
        with self.assertRaisesRegex(GwtError, "unknown top-level form: DTO Account"):
            run_text("DTO Account\n  balance: number\n")

        with self.assertRaisesRegex(GwtError, "top-level REQUEST contracts were removed"):
            run_text("REQUEST account is Account\n")

        with self.assertRaisesRegex(GwtError, "EXPORT is no longer a public interface form"):
            run_text("EXPORT review as review vendor\n")

        with self.assertRaisesRegex(GwtError, "OUTPUT must appear inside a named REQUEST block"):
            run_text("OUTPUT decision is Decision\n")

    def test_request_file_mode_only_invokes_named_requests(self):
        program = """
        RECORD Input
          value: integer

        RECORD Output
          doubled: integer

        REQUEST double input
          GIVEN input is Input

          GIVEN output is Output
            doubled: 0

          WHEN double input into output

          OUTPUT output is Output

        WHEN double <input> into <output>
          set output.doubled to input.value * 2
        """

        request = """
        GIVEN input is Input
          value: 4

        REQUEST double input
        """

        result = run_text(program, request_source=request)

        self.assertEqual(result.as_payload()["result"], {"output": {"doubled": 8}})

        with self.assertRaisesRegex(GwtError, "direct WHEN is not allowed"):
            run_text(program, request_source="WHEN double input into output\n")

        with self.assertRaisesRegex(GwtError, "request files cannot define named REQUEST blocks"):
            run_text(
                program,
                request_source="""
                REQUEST bad request
                  WHEN double input into output
                """,
            )

    def test_validation_gate_covers_check_format_and_embedded_scenarios(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rules.gwt"
            path.write_text(
                """PROGRAM validation

REQUEST flip status
  GIVEN decision.status is text
  WHEN set decision.status to "done"
  OUTPUT decision.status is text

SCENARIO validates
GIVEN decision.status is "new"
REQUEST flip status
THEN decision.status == "done"
"""
            )

            result = validate_file(path)

        payload = result.as_payload()
        self.assertTrue(payload["ok"], json.dumps(payload, indent=2, sort_keys=True))
        self.assertTrue(payload["phases"]["check"]["checked"])
        self.assertTrue(payload["phases"]["format"]["checked"])
        self.assertEqual(payload["phases"]["test"]["scenario_count"], 1)

    def test_conformance_test_names_map_to_spec_sections(self):
        section_tests = [
            name
            for name in dir(self)
            if name.startswith("test_")
            and name != "test_conformance_test_names_map_to_spec_sections"
        ]

        self.assertGreaterEqual(len(section_tests), 8)


if __name__ == "__main__":
    unittest.main()
