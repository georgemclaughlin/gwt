from pathlib import Path
import tempfile
import unittest

from gwtlang import (
    GwtError,
    check_file,
    check_text,
    run_file,
    run_json_file,
    run_json_text,
    run_text,
)


class PublicApiTests(unittest.TestCase):
    def test_check_file_returns_structured_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "bad.gwt"
            program.write_text(
                """
                GIVEN count is 1
                WHEN missing count
                """
            )

            result = check_file(program)

        self.assertFalse(result.ok)
        self.assertEqual(result.diagnostics[0].code, "GWT001")
        self.assertFalse(result.as_payload()["ok"])

    def test_check_text_returns_ok_result(self):
        result = check_text(
            """
            GIVEN count is 1
            THEN count == 1
            """
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.diagnostics, [])

    def test_run_file_with_request_file_returns_execution_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            request = Path(temp_dir) / "request.gwt"
            program.write_text(
                """
                WHEN checkout cart
                  set cart.total to cart.subtotal + cart.shipping
                """
            )
            request.write_text(
                """
                GIVEN cart.subtotal is 84
                AND cart.shipping is 8

                WHEN checkout cart
                """
            )

            result = run_file(program, request_file=request)

        self.assertEqual(result.state["cart"]["total"], 92)
        payload = result.as_payload()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scenario_count"], 1)
        self.assertEqual(payload["result"]["cart"]["total"], 92)

    def test_output_contract_filters_execution_payload(self):
        result = run_text(
            """
            RECORD Cart
              subtotal: number
              shipping: number
              total: number

            REQUEST cart is Cart
            OUTPUT cart is Cart

            WHEN checkout cart
              set cart.total to cart.subtotal + cart.shipping
              set audit.status to "priced"
            """,
            request_source="""
            GIVEN cart is Cart
              subtotal: 84
              shipping: 8
              total: 0

            WHEN checkout cart
            """,
        )

        self.assertEqual(result.state["audit"]["status"], "priced")
        payload = result.as_payload()
        self.assertEqual(payload["result"], {"cart": {"subtotal": 84, "shipping": 8, "total": 92}})
        self.assertEqual(payload["state"]["audit"]["status"], "priced")

    def test_run_json_text_runs_entry_with_request_contracts(self):
        result = run_json_text(
            """
            RECORD Cart
              subtotal: number
              shipping: number
              total: number

            REQUEST cart is Cart
            OUTPUT cart is Cart

            WHEN checkout <cart>
              GIVEN cart is Cart
              set cart.total to cart.subtotal + cart.shipping
              set audit.status to "priced"
            """,
            {"cart": {"subtotal": 84, "shipping": 8, "total": 0}},
            entry="checkout cart",
        )

        self.assertEqual(result.state["cart"]["total"], 92)
        self.assertEqual(result.state["audit"]["status"], "priced")
        self.assertEqual(
            result.as_payload()["result"],
            {"cart": {"subtotal": 84, "shipping": 8, "total": 92}},
        )

    def test_run_json_text_validates_missing_request_contract(self):
        with self.assertRaisesRegex(GwtError, "REQUEST contract failed for cart: unknown path: cart"):
            run_json_text(
                """
                RECORD Cart
                  subtotal: number

                REQUEST cart is Cart

                WHEN checkout <cart>
                  GIVEN cart is Cart
                  print cart.subtotal
                """,
                {},
                entry="checkout cart",
            )

    def test_run_json_file_sets_json_file_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            payload = Path(temp_dir) / "request.json"
            program.write_text(
                """
                WHEN checkout <cart>
                  set cart.total to cart.subtotal + cart.shipping
                """
            )

            result = run_json_file(
                program,
                {"cart": {"subtotal": 84, "shipping": 8, "total": 0}},
                entry="checkout cart",
                json_file=payload,
            )

        self.assertEqual(result.request_file, str(payload))
        self.assertEqual(result.state["cart"]["total"], 92)

    def test_run_text_returns_execution_result(self):
        result = run_text(
            """
            GIVEN count is 1
            WHEN add 2 to count
            THEN count == 3
            """
        )

        self.assertEqual(result.state["count"], 3)

    def test_execution_payload_shape_is_stable_for_multiple_scenarios(self):
        result = run_text(
            """
            SCENARIO one
            GIVEN count is 1

            SCENARIO two
            GIVEN count is 2
            """
        )

        payload = result.as_payload()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scenario_count"], 2)
        self.assertIsNone(payload["state"])
        self.assertIsNone(payload["result"])
        self.assertEqual([scenario["name"] for scenario in payload["scenarios"]], ["one", "two"])
        self.assertEqual(payload["scenarios"][1]["result"]["count"], 2)


if __name__ == "__main__":
    unittest.main()
