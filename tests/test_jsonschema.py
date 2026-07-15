from contextlib import redirect_stdout
import io
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from gwtlang import GwtClient, generate_json_schema_file, generate_json_schema_text
from gwtlang.__main__ import main
from gwtlang.jsonschema import JSON_SCHEMA_DRAFT_2020_12
from gwtlang.openapi import DECIMAL_STRING_PATTERN
from gwtlang.version import PACKAGE_VERSION


class JsonSchemaGenerationTests(unittest.TestCase):
    def test_optional_fields_are_nullable_and_not_required(self):
        result = generate_json_schema_text(
            """
            TYPE MaybeAmount is optional<decimal>

            RECORD Limits
              amount_min: decimal
              amount_max: optional<decimal>
              amount_override: MaybeAmount

            REQUEST assess limits
              GIVEN limits is Limits
              AND metadata.trace_id is optional<text>
              WHEN print limits.amount_min
              OUTPUT limits is Limits
            """
        )

        limits = result.as_payload()["$defs"]["Limits"]
        self.assertEqual(limits["required"], ["amount_min"])
        self.assertEqual(
            limits["properties"]["amount_override"],
            {"$ref": "#/$defs/MaybeAmount"},
        )
        request = result.as_payload()["$defs"]["AssessLimitsRequest"]
        self.assertEqual(request["required"], ["limits"])
        self.assertEqual(request["properties"]["metadata"]["required"], [])
        self.assertEqual(
            limits["properties"]["amount_max"],
            {
                "anyOf": [
                    {
                        "anyOf": [
                            {
                                "type": "string",
                                "format": "decimal",
                                "pattern": DECIMAL_STRING_PATTERN,
                            },
                            {"type": "integer"},
                        ],
                        "x-gwt-json-input": "decimal string or integer",
                        "x-gwt-json-output": "decimal string",
                    },
                    {"type": "null"},
                ]
            },
        )

    def test_generates_schema_catalog_from_contracts(self):
        result = generate_json_schema_text(
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
        defs = payload["$defs"]

        self.assertEqual(payload["$schema"], JSON_SCHEMA_DRAFT_2020_12)
        self.assertEqual(payload["title"], "checkout api")
        self.assertEqual(payload["x-gwt"]["file"], "checkout.gwt")
        self.assertEqual(payload["x-gwt"]["program"], "checkout api")
        self.assertEqual(payload["x-gwt"]["packageVersion"], PACKAGE_VERSION)
        self.assertEqual(
            payload["x-gwt"]["requests"]["checkout cart"],
            {
                "input": {"$ref": "#/$defs/CheckoutCartRequest"},
                "output": {"$ref": "#/$defs/CheckoutCartOutput"},
            },
        )

        self.assertEqual(defs["CartStatus"]["enum"], ["new", "priced"])
        self.assertEqual(
            defs["Cart"]["properties"]["subtotal"]["anyOf"],
            [
                {
                    "type": "string",
                    "format": "decimal",
                    "pattern": DECIMAL_STRING_PATTERN,
                },
                {"type": "integer"},
            ],
        )
        self.assertEqual(defs["Cart"]["properties"]["status"], {"$ref": "#/$defs/CartStatus"})
        self.assertEqual(defs["Cart"]["properties"]["items"]["items"], {"$ref": "#/$defs/CartItem"})
        self.assertEqual(defs["Cart"]["properties"]["customer"]["required"], ["id"])
        self.assertEqual(defs["CheckoutCartRequest"]["required"], ["cart", "metadata"])
        self.assertEqual(
            defs["CheckoutCartRequest"]["properties"]["metadata"]["properties"]["trace_id"],
            {"type": "string"},
        )
        self.assertEqual(
            defs["CheckoutCartOutput"]["properties"]["decision"],
            {"$ref": "#/$defs/Decision"},
        )
        self.assertEqual(
            defs["CheckoutCartOutput"]["properties"]["cart"],
            {"$ref": "#/$defs/CartOutputValue"},
        )
        self.assertEqual(
            defs["CartOutputValue"]["properties"]["subtotal"],
            {
                "type": "string",
                "format": "decimal",
                "pattern": DECIMAL_STRING_PATTERN,
                "x-gwt-json-output": "decimal string",
            },
        )
        self.assertNotIn("discriminator", defs["Decision"])
        self.assertEqual(
            defs["Decision"]["oneOf"][0]["properties"]["kind"],
            {"type": "string", "enum": ["approved"]},
        )
        self.assertNotIn("GwtErrorResponse", defs)
        self.assertNotIn("#/components/schemas", json.dumps(payload))

    def test_imported_contracts_are_available_in_schema_catalog(self):
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

            payload = generate_json_schema_file(
                rules,
                import_roots=[root],
                allow_absolute_imports=False,
            ).as_payload()

        defs = payload["$defs"]
        self.assertEqual(defs["Vendor"]["properties"]["name"], {"type": "string"})
        self.assertEqual(defs["DecisionStatus"]["enum"], ["approved", "needs_review"])
        self.assertEqual(
            defs["ReviewVendorOutput"]["properties"]["decision"],
            {"$ref": "#/$defs/Decision"},
        )

    def test_decimal_literal_union_schema_preserves_runtime_decimal_shapes(self):
        result = generate_json_schema_text(
            """
            TYPE Rate is 1.0 | 2.0

            RECORD Price
              rate: Rate

            REQUEST price order
              GIVEN price is Price

              WHEN price order

              OUTPUT price is Price

            WHEN price order
              PASS
            """
        )

        rate = result.as_payload()["$defs"]["Rate"]

        self.assertEqual(
            rate["anyOf"],
            [
                {
                    "type": "string",
                    "format": "decimal",
                    "pattern": DECIMAL_STRING_PATTERN,
                },
                {"type": "integer", "enum": [1, 2]},
            ],
        )
        self.assertEqual(
            result.as_payload()["$defs"]["RateOutputValue"],
            {
                "type": "string",
                "format": "decimal",
                "pattern": DECIMAL_STRING_PATTERN,
                "title": "Rate output",
                "x-gwt-json-output": "decimal string",
                "x-gwt-literal-values": ["1.0", "2.0"],
                "x-gwt-type": "typeAlias",
            },
        )

    def test_decimal_schema_validates_standard_json_schema_shapes(self):
        if importlib.util.find_spec("jsonschema") is None:
            self.skipTest("jsonschema package is not installed")
        from jsonschema import Draft202012Validator

        result = generate_json_schema_text(
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
        ).as_payload()
        input_schema = {
            "$schema": result["$schema"],
            "$defs": result["$defs"],
            "$ref": result["x-gwt"]["requests"]["price order"]["input"]["$ref"],
        }
        output_schema = {
            "$schema": result["$schema"],
            "$defs": result["$defs"],
            "$ref": result["x-gwt"]["requests"]["price order"]["output"]["$ref"],
        }

        Draft202012Validator(input_schema).validate({"price": {"amount": "1.00", "rate": "1"}})
        Draft202012Validator(input_schema).validate({"price": {"amount": "1.00", "rate": "+01.00"}})
        Draft202012Validator(input_schema).validate({"price": {"amount": " 1e0 ", "rate": "1e0"}})
        Draft202012Validator(input_schema).validate({"price": {"amount": 1, "rate": 2}})
        with self.assertRaises(Exception):
            Draft202012Validator(input_schema).validate({"price": {"amount": "abc", "rate": "1"}})
        Draft202012Validator(output_schema).validate({"price": {"amount": "1.00", "rate": "1E+0"}})
        with self.assertRaises(Exception):
            Draft202012Validator(output_schema).validate({"price": {"amount": 1, "rate": "1.00"}})

    def test_gwt_client_json_schema_uses_public_api(self):
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

            payload = GwtClient(program).json_schema().as_payload()

        self.assertEqual(
            payload["x-gwt"]["requests"]["ping"]["output"],
            {"$ref": "#/$defs/PingOutput"},
        )
        self.assertEqual(payload["$defs"]["PingOutput"]["properties"]["ok"], {"type": "boolean"})

    def test_cli_prints_json_schema_json(self):
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
                status = main(["schema", str(program)])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["$schema"], JSON_SCHEMA_DRAFT_2020_12)
        self.assertEqual(payload["$defs"]["PingOutput"]["properties"]["ok"], {"type": "boolean"})

    def test_cli_writes_json_schema_json_to_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "ping.gwt"
            output = root / "schema.json"
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
                status = main(["schema", str(program), "--output", str(output)])

            payload = json.loads(output.read_text())

        self.assertEqual(status, 0)
        self.assertIn(f"Wrote {output}", stdout.getvalue())
        self.assertEqual(payload["x-gwt"]["requests"]["ping"]["input"], {"$ref": "#/$defs/PingRequest"})
