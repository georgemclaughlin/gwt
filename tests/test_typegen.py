from pathlib import Path
import unittest

from gwtlang import (
    GwtError,
    generate_python_file,
    generate_python_text,
    generate_typescript_file,
    generate_typescript_text,
)


class TypeGenerationTests(unittest.TestCase):
    def test_vendor_onboarding_typescript_example_fixture_is_current(self):
        generated = generate_typescript_file("examples/vendor_onboarding/rules.gwt")
        fixture = Path("clients/typescript/examples/vendor-onboarding.generated.d.ts")

        self.assertEqual(fixture.read_text(), generated.source)

    def test_exact_pricing_python_example_fixture_is_current(self):
        generated = generate_python_file("examples/exact_pricing/rules.gwt")
        fixture = Path("examples/exact_pricing/rules_types.py")

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

    def test_python_generation_emits_exact_numeric_types_request_constant_and_client(self):
        result = generate_python_text(
            """
            PROGRAM exact_pricing

            RECORD Price
              mode: "reserve" | "quote"
              quantity: integer
              amount: decimal
              total: decimal

            REQUEST price order
              GIVEN price is Price

              WHEN price order price

              OUTPUT price is Price

            WHEN price order <price>
              GIVEN price is Price
              PASS
            """
        )

        self.assertIn("class Price(TypedDict):", result.source)
        self.assertIn("mode: Literal['reserve', 'quote']", result.source)
        self.assertIn("quantity: int", result.source)
        self.assertIn("amount: str", result.source)
        self.assertIn("PRICE_ORDER_REQUEST: GwtRequestName = 'price order'", result.source)
        self.assertIn("class ExactPricingClient:", result.source)
        self.assertIn("def run_price_order(self, request: PriceOrderRequest) -> ExecutionResult:", result.source)
        self.assertIn("def price_order(self, request: PriceOrderRequest) -> PriceOrderOutput:", result.source)

    def test_python_generation_maps_nested_records_variants_and_request_maps(self):
        result = generate_python_text(
            """
            RECORD Vendor
              name: text
              scores: list<number>
              owner:
                email: text

            RECORD Review is one of
              approved:
                reason: text
              denied:
                code: integer

            REQUEST review vendor
              GIVEN vendor is Vendor
              AND metadata.trace_id is text

              WHEN print metadata.trace_id

              OUTPUT review is Review
            """,
            filename="rules.gwt",
        )

        self.assertIn("class VendorOwner(TypedDict):", result.source)
        self.assertIn("scores: list[int | float]", result.source)
        self.assertIn("owner: VendorOwner", result.source)
        self.assertIn("class ReviewApproved(TypedDict):", result.source)
        self.assertIn("kind: Literal['approved']", result.source)
        self.assertIn("Review: TypeAlias = ReviewApproved | ReviewDenied", result.source)
        self.assertIn("class ReviewVendorRequestMetadata(TypedDict):", result.source)
        self.assertIn("metadata: ReviewVendorRequestMetadata", result.source)
        self.assertIn("'review vendor': ReviewVendorRequest", result.source)

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
