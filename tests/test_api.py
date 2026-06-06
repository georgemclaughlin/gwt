from pathlib import Path
from decimal import Decimal
import tempfile
import unittest

from gwtlang import (
    GwtError,
    GwtClient,
    check_file,
    check_text,
    compile_file,
    compile_text,
    generate_python_text,
    generate_typescript_text,
    inspect_file,
    run_file,
    run_json_file,
    run_json_text,
    run_text,
    validate_file,
)


class PublicApiTests(unittest.TestCase):
    def test_compile_file_checks_once_and_reuses_program(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            program.write_text(
                """
                RECORD Cart
                  subtotal: number
                  shipping: number
                  total: number

                REQUEST checkout cart
                  GIVEN cart is Cart

                  WHEN checkout cart

                  OUTPUT cart is Cart

                WHEN checkout <cart>
                  GIVEN cart is Cart
                  set cart.total to cart.subtotal + cart.shipping
                """
            )

            compiled = compile_file(program)
            program.write_text("this is no longer valid GWT")
            first = compiled.run_json(
                {"cart": {"subtotal": 84, "shipping": 8, "total": 0}},
                request="checkout cart",
            )
            second = compiled.run_json(
                {"cart": {"subtotal": 10, "shipping": 5, "total": 0}},
                request="checkout cart",
            )

        self.assertTrue(compiled.ok)
        self.assertEqual(len(compiled.source_hash), 64)
        self.assertEqual(first.as_payload()["result"]["cart"]["total"], 92)
        self.assertEqual(second.as_payload()["result"]["cart"]["total"], 15)

    def test_gwt_client_compile_returns_reusable_program(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "counter.gwt"
            program.write_text(
                """
                REQUEST increment count
                  GIVEN count is number

                  WHEN increment count

                  OUTPUT count is number

                WHEN increment count
                  add 1 to count
                """
            )

            compiled = GwtClient(program).compile()
            result = compiled.run_json({"count": 2}, request="increment count")

        self.assertEqual(result.as_payload()["result"]["count"], 3)

    def test_decimal_contract_accepts_exact_json_strings_and_serializes_payloads(self):
        compiled = compile_text(
            """
            RECORD Price
              amount: decimal
              quantity: integer
              total: decimal

            REQUEST price order
              GIVEN price is Price

              WHEN price order price

              OUTPUT price is Price

            WHEN price order <price>
              GIVEN price is Price
              set price.total to price.amount * price.quantity
            """
        )

        result = compiled.run_json(
            {"price": {"amount": "12.30", "quantity": 2, "total": "0.00"}},
            request="price order",
        )

        self.assertEqual(result.state["price"]["amount"], Decimal("12.30"))
        self.assertEqual(result.state["price"]["quantity"], 2)
        self.assertEqual(result.state["price"]["total"], Decimal("24.60"))
        self.assertEqual(result.as_payload()["result"]["price"]["total"], "24.60")

    def test_decimal_contract_rejects_json_float(self):
        compiled = compile_text(
            """
            RECORD Price
              amount: decimal

            REQUEST accept price
              GIVEN price is Price

              WHEN accept price

              OUTPUT price is Price

            WHEN accept price
              PASS
            """
        )

        with self.assertRaisesRegex(GwtError, "expected price.amount to be decimal, got number"):
            compiled.run_json({"price": {"amount": 12.3}}, request="accept price")

    def test_decimal_contract_rejects_non_finite_strings(self):
        compiled = compile_text(
            """
            RECORD Price
              amount: decimal

            REQUEST accept price
              GIVEN price is Price

              WHEN accept price

            WHEN accept price
              PASS
            """
        )

        for amount in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(amount=amount):
                with self.assertRaisesRegex(GwtError, "expected price.amount to be decimal"):
                    compiled.run_json({"price": {"amount": amount}}, request="accept price")

    def test_number_output_serializes_decimal_literal_as_json_number(self):
        compiled = compile_text(
            """
            REQUEST choose amount
              WHEN choose

              OUTPUT amount is number

            WHEN choose
              set amount to 1.5
            """
        )

        result = compiled.run_json({}, request="choose amount")

        self.assertEqual(result.state["amount"], 1.5)
        self.assertEqual(result.as_payload()["result"]["amount"], 1.5)

    def test_number_value_branch_matches_json_float(self):
        result = run_json_text(
            """
            REQUEST classify mode
              GIVEN mode is number

              WHEN classify mode

              OUTPUT status is text

            WHEN classify <mode>
              GIVEN mode is number
              DEPENDING ON mode
                WHEN the value is 1.5
                  set status to "matched"
                ELSE
                  set status to "other"
            """,
            {"mode": 1.5},
            request="classify mode",
        )

        self.assertEqual(result.as_payload()["result"]["status"], "matched")

    def test_compiled_program_runs_named_request(self):
        compiled = compile_text(
            """
            RECORD Cart
              subtotal: integer
              total: integer

            REQUEST price cart
              GIVEN cart is Cart

              WHEN price cart

              OUTPUT cart is Cart

            WHEN price <cart>
              GIVEN cart is Cart
              set cart.total to cart.subtotal
            """
        )

        result = compiled.run_json({"cart": {"subtotal": 84, "total": 0}}, request="price cart")

        self.assertEqual(result.as_payload()["result"]["cart"]["total"], 84)
        with self.assertRaisesRegex(GwtError, "unknown request: missing"):
            compiled.run_json({"cart": {"subtotal": 84, "total": 0}}, request="missing")

    def test_run_json_file_accepts_request_name(self):
        result = run_json_file(
            "examples/exact_pricing/rules.gwt",
            {
                "cart": {
                    "mode": "reserve",
                    "quantity": 2,
                    "unit_price": "12.30",
                    "total": "0.00",
                    "status": "pending",
                }
            },
            request="price cart",
        )

        self.assertEqual(result.as_payload()["result"]["cart"]["total"], "24.60")

    def test_trusted_json_skips_only_boundary_contracts(self):
        compiled = compile_text(
            """
            REQUEST accept amount
              GIVEN amount is integer

              WHEN accept amount

              OUTPUT amount is integer

            WHEN accept amount
              print "accepted"
            """
        )

        with self.assertRaisesRegex(GwtError, "REQUEST contract failed"):
            compiled.run_json({"amount": "bad"}, request="accept amount")

        result = compiled.run_trusted_json({"amount": "bad"}, request="accept amount")

        self.assertEqual(result.as_payload()["result"]["amount"], "bad")

    def test_compile_text_rejects_checker_errors(self):
        with self.assertRaisesRegex(GwtError, "GWT001 no behavior matches: missing count"):
            compile_text(
                """
                GIVEN count is 1
                WHEN missing count
                """,
                filename="bad.gwt",
            )

    def test_compile_file_allows_imports_inside_import_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            module = root / "types.gwt"
            program = root / "main.gwt"
            module.write_text(
                """
                RECORD Account
                  balance: number
                """
            )
            program.write_text(
                """
                USE "./types.gwt"

                REQUEST credit account
                  GIVEN account is Account

                  WHEN credit account

                  OUTPUT account is Account

                WHEN credit account
                  add 5 to account.balance
                """
            )

            compiled = compile_file(
                program,
                import_roots=[root],
                allow_absolute_imports=False,
            )
            result = compiled.run_json(
                {"account": {"balance": 10}},
                request="credit account",
            )

        self.assertEqual(result.as_payload()["result"]["account"]["balance"], 15)

    def test_compile_file_rejects_imports_outside_import_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            outside = Path(temp_dir) / "outside.gwt"
            program = root / "main.gwt"
            outside.write_text(
                """
                RECORD Account
                  balance: number
                """
            )
            program.write_text('USE "../outside.gwt"\n')

            with self.assertRaisesRegex(GwtError, "USE import is outside allowed roots"):
                compile_file(program, import_roots=[root])

    def test_compile_file_can_reject_absolute_imports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            module = root / "types.gwt"
            program = root / "main.gwt"
            module.write_text(
                """
                RECORD Account
                  balance: number
                """
            )
            program.write_text(f'USE "{module}"\n')

            with self.assertRaisesRegex(GwtError, "USE absolute import is not allowed"):
                compile_file(program, import_roots=[root], allow_absolute_imports=False)

    def test_check_file_reports_import_policy_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            outside = Path(temp_dir) / "outside.gwt"
            program = root / "main.gwt"
            outside.write_text(
                """
                RECORD Account
                  balance: number
                """
            )
            program.write_text('USE "../outside.gwt"\n')

            result = check_file(program, import_roots=[root])

        self.assertFalse(result.ok)
        self.assertEqual(result.diagnostics[0].code, "GWT900")
        self.assertIn(
            "USE import is outside allowed roots",
            result.diagnostics[0].message,
        )

    def test_run_json_file_enforces_import_policy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            outside = Path(temp_dir) / "outside.gwt"
            program = root / "main.gwt"
            outside.write_text(
                """
                WHEN touch count
                  add 1 to count
                """
            )
            program.write_text(
                """
                USE "../outside.gwt"

                REQUEST touch count
                  GIVEN count is number

                  WHEN touch count

                  OUTPUT count is number
                """
            )

            with self.assertRaisesRegex(
                GwtError,
                "USE import is outside allowed roots",
            ):
                run_json_file(
                    program,
                    {"count": 1},
                    request="touch count",
                    import_roots=[root],
                )

    def test_gwt_client_checks_and_runs_json_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            program.write_text(
                """
                RECORD Cart
                  subtotal: number
                  shipping: number
                  total: number

                REQUEST checkout cart
                  GIVEN cart is Cart

                  WHEN checkout cart

                  OUTPUT cart is Cart

                WHEN checkout <cart>
                  GIVEN cart is Cart
                  set cart.total to cart.subtotal + cart.shipping
                """
            )

            client = GwtClient(program)
            check = client.check()
            result = client.run_json(
                {"cart": {"subtotal": 84, "shipping": 8, "total": 0}},
                request="checkout cart",
            )

        self.assertTrue(check.ok)
        self.assertEqual(result.as_payload()["result"]["cart"]["total"], 92)

    def test_gwt_client_generates_typescript_types(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            program.write_text(
                """
                RECORD Cart
                  subtotal: number
                  status: "new" | "priced"

                REQUEST price cart
                  GIVEN cart is Cart

                  WHEN print "priced"

                  OUTPUT cart is Cart
                """
            )

            result = GwtClient(program).typescript_types()

        self.assertIn("export interface Cart", result.source)
        self.assertIn('status: "new" | "priced";', result.source)
        self.assertIn("export interface PriceCartRequest", result.source)
        self.assertEqual(result.language, "typescript")

    def test_gwt_client_generates_python_types(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "pricing.gwt"
            program.write_text(
                """
                PROGRAM pricing

                RECORD Cart
                  subtotal: number
                  total: decimal

                REQUEST price cart
                  GIVEN cart is Cart

                  WHEN print "priced"

                  OUTPUT cart is Cart
                """
            )

            result = GwtClient(program).python_types()

        self.assertIn("class Cart(TypedDict):", result.source)
        self.assertIn("subtotal: int | float", result.source)
        self.assertIn("total: str", result.source)
        self.assertIn("class PricingClient:", result.source)
        self.assertIn("def price_cart(self, request: PriceCartRequest) -> PriceCartOutput:", result.source)
        self.assertEqual(result.language, "python")

    def test_inspect_file_reports_named_requests(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            program.write_text(
                "RECORD Cart\n"
                "  subtotal: number\n"
                "  total: number\n"
                "\n"
                "REQUEST checkout cart\n"
                "  GIVEN cart is Cart\n"
                "\n"
                "  WHEN checkout cart\n"
                "\n"
                "  OUTPUT cart is Cart\n"
                "\n"
                "WHEN checkout <cart>\n"
                "  GIVEN cart is Cart\n"
                "  set cart.total to cart.subtotal\n"
            )

            result = inspect_file(program)
            payload = result.as_payload()

        self.assertTrue(result.ok)
        self.assertEqual(payload["schemaVersion"], 2)
        self.assertEqual(payload["requests"][0]["name"], "checkout cart")
        self.assertEqual(payload["counts"]["requests"], 1)

    def test_inspect_file_reports_request_contracts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "workflow.gwt"
            program.write_text(
                """
                REQUEST classify review
                  GIVEN status is text

                  WHEN classify status

                  OUTPUT status is text

                WHEN classify <status>
                  GIVEN status is text
                  print status
                """
            )

            payload = inspect_file(program).as_payload()

        request = payload["requests"][0]
        self.assertEqual(request["name"], "classify review")
        self.assertEqual(request["inputs"][0]["path"], "status")
        self.assertEqual(request["outputs"][0]["path"], "status")

    def test_inspect_file_accepts_public_import_policy_options(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            module = root / "types.gwt"
            program = root / "checkout.gwt"
            module.write_text(
                "RECORD Cart\n"
                "  subtotal: number\n"
            )
            program.write_text(
                'USE "./types.gwt"\n'
                "\n"
                "REQUEST price cart\n"
                "  GIVEN cart is Cart\n"
                "\n"
                "  WHEN print \"priced\"\n"
            )

            result = inspect_file(
                program,
                import_roots=[root],
                allow_absolute_imports=False,
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.as_payload()["records"][0]["name"], "Cart")

    def test_validate_file_runs_format_and_scenarios(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "counter.gwt"
            program.write_text(
                "WHEN touch <count>\n"
                "  add 1 to count\n"
                "\n"
                "GIVEN count is 1\n"
                "WHEN touch count\n"
                "THEN count == 2\n"
            )

            result = validate_file(program)
            payload = result.as_payload()

        self.assertTrue(result.ok)
        self.assertTrue(payload["phases"]["check"]["ok"])
        self.assertTrue(payload["phases"]["format"]["ok"])
        self.assertEqual(payload["phases"]["test"]["scenario_count"], 1)

    def test_validate_file_accepts_public_import_policy_options(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "rules"
            root.mkdir()
            module = root / "steps.gwt"
            program = root / "counter.gwt"
            module.write_text(
                "WHEN touch <count>\n"
                "  add 1 to count\n"
            )
            program.write_text(
                'USE "./steps.gwt"\n'
                "\n"
                "GIVEN count is 1\n"
                "WHEN touch count\n"
                "THEN count == 2\n"
            )

            result = validate_file(
                program,
                import_roots=[root],
                allow_absolute_imports=False,
            )

        self.assertTrue(result.ok)

    def test_gwt_client_inspects_and_validates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "counter.gwt"
            program.write_text(
                "GIVEN count is 1\n"
                "THEN count == 1\n"
            )

            client = GwtClient(program)
            inspected = client.inspect()
            validated = client.validate()

        self.assertTrue(inspected.ok)
        self.assertTrue(validated.ok)

    def test_gwt_client_runs_gwt_request_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            request = Path(temp_dir) / "request.gwt"
            program.write_text(
                """
                RECORD Cart
                  subtotal: number
                  shipping: number
                  total: number

                REQUEST checkout cart
                  GIVEN cart is Cart

                  WHEN checkout cart

                  OUTPUT cart is Cart

                WHEN checkout <cart>
                  GIVEN cart is Cart
                  set cart.total to cart.subtotal + cart.shipping
                """
            )
            request.write_text(
                """
                GIVEN cart is Cart
                  subtotal: 84
                  shipping: 8
                  total: 0

                REQUEST checkout cart
                """
            )

            result = GwtClient(program).run(request_file=request)

        self.assertEqual(result.as_payload()["result"]["cart"]["total"], 92)

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

    def test_generate_typescript_text_maps_records_variants_and_contracts(self):
        result = generate_typescript_text(
            """
            RECORD Vendor
              name: text
              risk: "low" | "high"
              scores: list<number>
              owner:
                email: text

            RECORD Review is one of
              approved:
                reason: text
              denied:
                code: number

            REQUEST review vendor
              GIVEN vendor is Vendor
              AND metadata.trace_id is text

              WHEN print metadata.trace_id

              OUTPUT review is Review
            """,
            filename="rules.gwt",
        )

        self.assertIn("export interface Vendor", result.source)
        self.assertIn("scores: number[];", result.source)
        self.assertIn("owner: {\n    email: string;\n  };", result.source)
        self.assertIn("export type Review =", result.source)
        self.assertIn('kind: "approved";', result.source)
        self.assertIn("export interface ReviewVendorRequest", result.source)
        self.assertIn("metadata: {\n    trace_id: string;\n  };", result.source)
        self.assertIn("export interface ReviewVendorOutput", result.source)
        self.assertIn("review: Review;", result.source)

    def test_generate_typescript_text_rejects_unknown_contract_type(self):
        with self.assertRaisesRegex(GwtError, "unknown REQUEST contract type: Missing"):
            generate_typescript_text(
                """
                REQUEST bad request
                  GIVEN cart is Missing

                  WHEN print "bad"
                """
            )

    def test_generate_python_text_rejects_unknown_contract_type(self):
        with self.assertRaisesRegex(GwtError, "unknown REQUEST contract type: Missing"):
            generate_python_text(
                """
                REQUEST bad request
                  GIVEN cart is Missing

                  WHEN print "bad"
                """
            )

    def test_run_file_with_request_file_returns_execution_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            request = Path(temp_dir) / "request.gwt"
            program.write_text(
                """
                RECORD Cart
                  subtotal: number
                  shipping: number
                  total: number

                REQUEST checkout cart
                  GIVEN cart is Cart

                  WHEN checkout cart

                  OUTPUT cart is Cart

                WHEN checkout <cart>
                  GIVEN cart is Cart
                  set cart.total to cart.subtotal + cart.shipping
                """
            )
            request.write_text(
                """
                GIVEN cart is Cart
                  subtotal: 84
                  shipping: 8
                  total: 0

                REQUEST checkout cart
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

            REQUEST checkout cart
              GIVEN cart is Cart

              WHEN set cart.total to cart.subtotal + cart.shipping
              WHEN set audit.status to "priced"

              OUTPUT cart is Cart
            """,
            request_source="""
            GIVEN cart is Cart
              subtotal: 84
              shipping: 8
              total: 0

            REQUEST checkout cart
            """,
        )

        self.assertEqual(result.state["audit"]["status"], "priced")
        payload = result.as_payload()
        self.assertEqual(payload["result"], {"cart": {"subtotal": 84, "shipping": 8, "total": 92}})
        self.assertEqual(payload["state"]["audit"]["status"], "priced")

    def test_run_json_text_runs_named_request_with_request_contracts(self):
        result = run_json_text(
            """
            RECORD Cart
              subtotal: number
              shipping: number
              total: number

            REQUEST checkout cart
              GIVEN cart is Cart

              WHEN set cart.total to cart.subtotal + cart.shipping
              WHEN set audit.status to "priced"

              OUTPUT cart is Cart
            """,
            {"cart": {"subtotal": 84, "shipping": 8, "total": 0}},
            request="checkout cart",
        )

        self.assertEqual(result.state["cart"]["total"], 92)
        self.assertEqual(result.state["audit"]["status"], "priced")
        self.assertEqual(
            result.as_payload()["result"],
            {"cart": {"subtotal": 84, "shipping": 8, "total": 92}},
        )

    def test_run_json_text_request_without_outputs_returns_empty_result(self):
        result = run_json_text(
            """
            REQUEST touch count
              GIVEN count is number

              WHEN add 1 to count
            """,
            {"count": 1},
            request="touch count",
        )

        self.assertEqual(result.state["count"], 2)
        self.assertEqual(result.as_payload()["result"], {})

    def test_run_json_text_validates_missing_request_contract(self):
        with self.assertRaisesRegex(GwtError, "REQUEST contract failed for cart: unknown path: cart"):
            run_json_text(
                """
                RECORD Cart
                  subtotal: number

                REQUEST checkout cart
                  GIVEN cart is Cart

                  WHEN print cart.subtotal
                """,
                {},
                request="checkout cart",
            )

    def test_run_json_text_reports_null_for_typed_contract_mismatch(self):
        program = """
        RECORD Profile
          name: text
          score: number

        REQUEST accept profile
          GIVEN profile is Profile

          WHEN accept profile

        WHEN accept profile
          print "accepted"
        """

        cases = [
            ("name", {"name": None, "score": 1}, "expected profile.name to be text, got null"),
            ("score", {"name": "Ada", "score": None}, "expected profile.score to be number, got null"),
        ]
        for field, profile, message in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(GwtError, message):
                    run_json_text(program, {"profile": profile}, request="accept profile")

    def test_run_json_text_allows_null_for_any_contract(self):
        result = run_json_text(
            """
            REQUEST accept raw
              GIVEN raw is any

              WHEN accept raw

              OUTPUT raw is any

            WHEN accept raw
              print "accepted"
            """,
            {"raw": None},
            request="accept raw",
        )

        self.assertIsNone(result.state["raw"])
        self.assertIsNone(result.as_payload()["result"]["raw"])

    def test_run_json_file_sets_json_file_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            payload = Path(temp_dir) / "request.json"
            program.write_text(
                """
                REQUEST checkout cart
                  GIVEN cart is any

                  WHEN set cart.total to cart.subtotal + cart.shipping

                  OUTPUT cart is any
                """
            )

            result = run_json_file(
                program,
                {"cart": {"subtotal": 84, "shipping": 8, "total": 0}},
                request="checkout cart",
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
