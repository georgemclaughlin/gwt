from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from gwtlang import GwtClient, generate_openapi_file, generate_openapi_text
from gwtlang.__main__ import main
from gwtlang.version import PACKAGE_VERSION


class OpenApiGenerationTests(unittest.TestCase):
    def test_generates_paths_and_schemas_from_named_requests(self):
        result = generate_openapi_text(
            """
            PROGRAM checkout api

            TYPE CartStatus is "new" | "priced"

            RECORD CartItem
              sku: text
              quantity: integer

            RECORD Cart
              subtotal: decimal
              status: CartStatus
              items: list<CartItem>
              customer:
                id: text

            RECORD Decision is one of
              approved:
                reason: text
              declined:
                code: integer

            REQUEST checkout cart
              GIVEN cart is Cart
              AND metadata.trace_id is text

              WHEN checkout cart

              OUTPUT cart is Cart
              AND decision is Decision

            WHEN checkout <cart>
              GIVEN cart is Cart
              PASS
            """,
            filename="checkout.gwt",
        )

        payload = result.as_payload()
        operation = payload["paths"]["/requests/checkout-cart"]["post"]
        schemas = payload["components"]["schemas"]

        self.assertEqual(payload["openapi"], "3.1.0")
        self.assertEqual(payload["info"]["title"], "checkout api")
        self.assertEqual(payload["info"]["version"], PACKAGE_VERSION)
        self.assertEqual(operation["operationId"], "checkoutCart")
        self.assertEqual(operation["x-gwt-request-name"], "checkout cart")
        self.assertEqual(
            operation["requestBody"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/CheckoutCartRequest"},
        )
        self.assertEqual(
            operation["responses"]["200"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/CheckoutCartOutput"},
        )
        self.assertEqual(
            operation["responses"]["400"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/GwtErrorResponse"},
        )
        self.assertEqual(
            operation["responses"]["500"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/GwtErrorResponse"},
        )

        self.assertEqual(schemas["CartStatus"]["enum"], ["new", "priced"])
        self.assertEqual(
            schemas["Cart"]["properties"]["subtotal"]["anyOf"],
            [{"type": "string", "format": "decimal"}, {"type": "integer"}],
        )
        self.assertEqual(schemas["Cart"]["properties"]["items"]["items"], {"$ref": "#/components/schemas/CartItem"})
        self.assertEqual(schemas["Cart"]["properties"]["customer"]["required"], ["id"])
        self.assertEqual(schemas["CheckoutCartRequest"]["required"], ["cart", "metadata"])
        self.assertEqual(
            schemas["CheckoutCartRequest"]["properties"]["metadata"]["properties"]["trace_id"],
            {"type": "string"},
        )
        self.assertEqual(
            schemas["CheckoutCartOutput"]["properties"]["decision"],
            {"$ref": "#/components/schemas/Decision"},
        )
        self.assertEqual(schemas["Decision"]["discriminator"], {"propertyName": "kind"})
        self.assertEqual(
            schemas["Decision"]["oneOf"][0]["properties"]["kind"],
            {"type": "string", "enum": ["approved"]},
        )
        self.assertEqual(
            schemas["GwtErrorResponse"],
            {
                "title": "GwtErrorResponse",
                "type": "object",
                "properties": {
                    "ok": {
                        "type": "boolean",
                        "description": "Always false for service error responses.",
                    },
                    "error": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                        },
                        "required": ["code", "message"],
                        "additionalProperties": False,
                    },
                },
                "required": ["ok", "error"],
                "additionalProperties": False,
            },
        )

    def test_decimal_literal_unions_do_not_reject_valid_decimal_input_shapes(self):
        result = generate_openapi_text(
            """
            TYPE Rate is 1.0 | 2.0

            RECORD Price
              amount: decimal
              rate: Rate

            REQUEST price order
              GIVEN price is Price

              WHEN price order

              OUTPUT price is Price

            WHEN price order
              PASS
            """
        )

        price = result.as_payload()["components"]["schemas"]["Price"]

        self.assertEqual(
            price["properties"]["amount"]["anyOf"],
            [{"type": "string", "format": "decimal"}, {"type": "integer"}],
        )
        self.assertEqual(
            result.as_payload()["components"]["schemas"]["Rate"],
            {
                "anyOf": [
                    {"type": "string", "format": "decimal"},
                    {"type": "integer", "enum": [1, 2]},
                ],
                "title": "Rate",
                "x-gwt-json-input": "decimal string or matching integer",
                "x-gwt-json-output": "decimal string",
                "x-gwt-literal-values": ["1.0", "2.0"],
                "x-gwt-type": "typeAlias",
            },
        )

    def test_generates_unique_paths_and_component_names_for_slug_collisions(self):
        result = generate_openapi_text(
            """
            REQUEST review vendor
              WHEN noop

            REQUEST review-vendor
              WHEN noop

            WHEN noop
              PASS
            """
        )

        payload = result.as_payload()
        schemas = payload["components"]["schemas"]

        self.assertIn("/requests/review-vendor", payload["paths"])
        self.assertIn("/requests/review-vendor-2", payload["paths"])
        self.assertIn("ReviewVendorRequest", schemas)
        self.assertIn("ReviewVendorRequest2", schemas)

    def test_imported_contracts_are_available_in_openapi(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            contracts = root / "contracts.gwt"
            rules = root / "rules.gwt"
            contracts.write_text(
                """
                TYPE DecisionStatus is "approved" | "needs_review"

                RECORD Vendor
                  name: text

                RECORD Decision
                  status: DecisionStatus
                """
            )
            rules.write_text(
                """
                USE "./contracts.gwt"

                REQUEST review vendor
                  GIVEN vendor is Vendor

                  WHEN review vendor

                  OUTPUT decision is Decision

                WHEN review vendor
                  set decision.status to "approved"
                """
            )

            payload = generate_openapi_file(
                rules,
                import_roots=[root],
                allow_absolute_imports=False,
            ).as_payload()

        schemas = payload["components"]["schemas"]
        self.assertEqual(schemas["Vendor"]["properties"]["name"], {"type": "string"})
        self.assertEqual(schemas["DecisionStatus"]["enum"], ["approved", "needs_review"])
        self.assertEqual(
            schemas["ReviewVendorOutput"]["properties"]["decision"],
            {"$ref": "#/components/schemas/Decision"},
        )

    def test_empty_request_and_output_contracts_are_empty_objects(self):
        result = generate_openapi_text(
            """
            REQUEST ping
              WHEN ping

            WHEN ping
              PASS
            """
        )

        schemas = result.as_payload()["components"]["schemas"]

        self.assertEqual(
            schemas["PingRequest"],
            {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        )
        self.assertEqual(
            schemas["PingOutput"],
            {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        )

    def test_gwt_client_openapi_uses_public_api(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "ping.gwt"
            program.write_text(
                """
                REQUEST ping
                  WHEN ping

                  OUTPUT ok is boolean

                WHEN ping
                  set ok to true
                """
            )

            payload = GwtClient(program).openapi().as_payload()

        self.assertEqual(payload["paths"]["/requests/ping"]["post"]["operationId"], "ping")
        self.assertEqual(
            payload["components"]["schemas"]["PingOutput"]["properties"]["ok"],
            {"type": "boolean"},
        )

    def test_cli_prints_openapi_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "ping.gwt"
            program.write_text(
                """
                REQUEST ping
                  WHEN ping

                  OUTPUT ok is boolean

                WHEN ping
                  set ok to true
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["openapi", str(program)])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["paths"]["/requests/ping"]["post"]["operationId"], "ping")
        self.assertEqual(
            payload["components"]["schemas"]["PingOutput"]["properties"]["ok"],
            {"type": "boolean"},
        )

    def test_cli_writes_openapi_json_to_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "ping.gwt"
            output = root / "openapi.json"
            program.write_text(
                """
                REQUEST ping
                  WHEN ping

                  OUTPUT ok is boolean

                WHEN ping
                  set ok to true
                """
            )

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(["openapi", str(program), "--output", str(output)])

            payload = json.loads(output.read_text())

        self.assertEqual(status, 0)
        self.assertIn(f"Wrote {output}", stdout.getvalue())
        self.assertEqual(payload["paths"]["/requests/ping"]["post"]["operationId"], "ping")

    def test_deployable_api_example_generates_expected_contract(self):
        payload = generate_openapi_file("examples/deployable_api/rules.gwt").as_payload()

        self.assertEqual(payload["info"]["title"], "support ticket api")
        self.assertIn("/requests/triage-ticket", payload["paths"])
        self.assertEqual(
            payload["components"]["schemas"]["TriageTicketRequest"]["properties"]["ticket"],
            {"$ref": "#/components/schemas/TicketRequest"},
        )
        self.assertEqual(
            payload["components"]["schemas"]["TriageTicketOutput"]["properties"]["decision"],
            {"$ref": "#/components/schemas/TicketDecision"},
        )
