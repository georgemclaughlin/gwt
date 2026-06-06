from pathlib import Path
import unittest

from gwtlang import GwtError, generate_typescript_file, generate_typescript_text


class TypeGenerationTests(unittest.TestCase):
    def test_vendor_onboarding_typescript_example_fixture_is_current(self):
        generated = generate_typescript_file("examples/vendor_onboarding/rules.gwt")
        fixture = Path("clients/typescript/examples/vendor-onboarding.generated.d.ts")

        self.assertEqual(fixture.read_text(), generated.source)

    def test_typescript_generation_emits_named_request_types(self):
        result = generate_typescript_text(
            """
            RECORD Vendor
              name: text

            RECORD Decision
              status: text

            REQUEST review vendor
              GIVEN vendor is Vendor

              GIVEN decision is Decision
                status: "new"

              WHEN review vendor into decision

              OUTPUT decision is Decision

            WHEN review <vendor> into <decision>
              GIVEN vendor is Vendor
              AND decision is Decision
              PASS

            WHEN reset <decision>
              GIVEN decision is Decision
              PASS

            WHEN ignore <other>
              PASS
            """
        )

        self.assertIn(
            'export type GwtRequestName = "review vendor";',
            result.source,
        )
        self.assertIn('"review vendor": ReviewVendorRequest;', result.source)
        self.assertIn('"review vendor": ReviewVendorOutput;', result.source)
        self.assertNotIn("reset decision", result.source)
        self.assertNotIn("ignore other", result.source)

    def test_typescript_generation_emits_exact_numeric_types_and_request_name(self):
        result = generate_typescript_text(
            """
            RECORD Price
              quantity: integer
              amount: decimal

            REQUEST price order
              GIVEN price is Price

              WHEN price order price

              OUTPUT price is Price

            WHEN price order <price>
              GIVEN price is Price
              PASS
            """
        )

        self.assertIn("quantity: number;", result.source)
        self.assertIn("amount: string;", result.source)
        self.assertIn('export type GwtRequestName = "price order";', result.source)

    def test_typescript_generation_avoids_record_and_reserved_request_type_collisions(self):
        result = generate_typescript_text(
            """
            RECORD CartRequest
              total: number

            RECORD Cart
              total: number

            REQUEST cart
              GIVEN cart is Cart
              WHEN print cart.total
              OUTPUT cart is Cart

            REQUEST gwt
              GIVEN cart is Cart
              WHEN print cart.total
              OUTPUT cart is Cart
            """
        )

        self.assertIn("export interface CartRequest {", result.source)
        self.assertIn("export interface CartRequest2 {", result.source)
        self.assertIn("export interface GwtRequest2 {", result.source)
        self.assertIn('"cart": CartRequest2;', result.source)
        self.assertIn('"gwt": GwtRequest2;', result.source)

    def test_typescript_generation_rejects_overlapping_contract_paths(self):
        with self.assertRaisesRegex(GwtError, "REQUEST contract path x\\.y overlaps x"):
            generate_typescript_text(
                """
                REQUEST bad request
                  GIVEN x is text
                  AND x.y is number

                  WHEN print "bad"
                """
            )

    def test_typescript_generation_rejects_overlapping_record_field_paths(self):
        with self.assertRaisesRegex(GwtError, "record Foo field path x\\.y overlaps x"):
            generate_typescript_text(
                """
                RECORD Foo
                  x: text
                    y: number
                """
            )


if __name__ == "__main__":
    unittest.main()
