from pathlib import Path
import tempfile
import unittest

from gwtlang import (
    GwtError,
    GwtClient,
    check_file,
    check_text,
    compile_file,
    compile_text,
    generate_typescript_text,
    run_file,
    run_json_file,
    run_json_text,
    run_text,
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

                REQUEST cart is Cart
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
                entry="checkout cart",
            )
            second = compiled.run_json(
                {"cart": {"subtotal": 10, "shipping": 5, "total": 0}},
                entry="checkout cart",
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
                REQUEST count is number
                OUTPUT count is number

                WHEN increment count
                  add 1 to count
                """
            )

            compiled = GwtClient(program).compile()
            result = compiled.run_json({"count": 2}, entry="increment count")

        self.assertEqual(result.as_payload()["result"]["count"], 3)

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

                REQUEST account is Account
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
                entry="credit account",
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

                REQUEST count is number
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
                    entry="touch count",
                    import_roots=[root],
                )

    def test_gwt_client_checks_and_runs_json_entry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            program.write_text(
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
                """
            )

            client = GwtClient(program)
            check = client.check()
            result = client.run_json(
                {"cart": {"subtotal": 84, "shipping": 8, "total": 0}},
                entry="checkout cart",
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

                REQUEST cart is Cart
                OUTPUT cart is Cart
                """
            )

            result = GwtClient(program).typescript_types()

        self.assertIn("export interface Cart", result.source)
        self.assertIn('status: "new" | "priced";', result.source)
        self.assertIn("export interface GwtRequest", result.source)
        self.assertEqual(result.language, "typescript")

    def test_gwt_client_runs_gwt_request_file(self):
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

            REQUEST vendor is Vendor
            AND metadata.trace_id is text
            OUTPUT review is Review
            """,
            filename="rules.gwt",
        )

        self.assertIn("export interface Vendor", result.source)
        self.assertIn("scores: number[];", result.source)
        self.assertIn("owner: {\n    email: string;\n  };", result.source)
        self.assertIn("export type Review =", result.source)
        self.assertIn('kind: "approved";', result.source)
        self.assertIn("export interface GwtRequest", result.source)
        self.assertIn("metadata: {\n    trace_id: string;\n  };", result.source)
        self.assertIn("export interface GwtOutput", result.source)
        self.assertIn("review: Review;", result.source)

    def test_generate_typescript_text_rejects_unknown_contract_type(self):
        with self.assertRaisesRegex(GwtError, "unknown REQUEST contract type: Missing"):
            generate_typescript_text("REQUEST cart is Missing\n")

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

    def test_run_json_text_reports_null_for_typed_contract_mismatch(self):
        program = """
        RECORD Profile
          name: text
          score: number

        REQUEST profile is Profile

        WHEN accept <profile>
          GIVEN profile is Profile
          PASS
        """

        cases = [
            ("name", {"name": None, "score": 1}, "expected profile.name to be text, got null"),
            ("score", {"name": "Ada", "score": None}, "expected profile.score to be number, got null"),
        ]
        for field, profile, message in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(GwtError, message):
                    run_json_text(program, {"profile": profile}, entry="accept profile")

    def test_run_json_text_allows_null_for_any_contract(self):
        result = run_json_text(
            """
            REQUEST raw is any
            OUTPUT raw is any

            WHEN accept <raw>
              GIVEN raw is any
              PASS
            """,
            {"raw": None},
            entry="accept raw",
        )

        self.assertIsNone(result.state["raw"])
        self.assertIsNone(result.as_payload()["result"]["raw"])

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
