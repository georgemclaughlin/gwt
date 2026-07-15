from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gwtlang import GwtError, format_text
from gwtlang.execution_case import capture_execution_case
from gwtlang.payloads import ExecutionCasePayload
from gwtlang.program_identity import load_program_snapshot
from gwtlang.scenario_generation import ScenarioGenerationResult, generate_scenario
from gwtlang.runtime import ImportPolicy


PROGRAM = '''
TYPE ReviewStatus is "approved" | "review"

RECORD LineItem
  sku: text
  quantity: integer
  cost: decimal

RECORD Order
  customer:
    name: text
    vip: boolean
  items: list<LineItem>
  tags: list<text>
  notes: list<text>
  amount: decimal
  count: integer
  ratio: number
  mode: ReviewStatus

RECORD Decision
  status: ReviewStatus
  total: decimal
  labels: list<text>
  empty: list<integer>

REQUEST inspect order
  GIVEN order is Order
  WHEN inspect order
  OUTPUT decision is Decision
  THEN decision.status == "approved"

WHEN inspect <order>
  GIVEN order is Order
  set decision.status to order.mode
  set decision.total to order.amount
  set decision.labels to order.tags
  set decision.empty to []
'''


INPUT = {
    "order": {
        "customer": {"name": "Ada", "vip": True},
        "items": [
            {"sku": "widget", "quantity": 2, "cost": "4.50"},
            {"sku": "cable", "quantity": 1, "cost": "3.30"},
        ],
        "tags": ["priority", "new"],
        "notes": [],
        "amount": "12.30",
        "count": 2,
        "ratio": 1.25,
        "mode": "approved",
    }
}


class ScenarioGenerationTests(unittest.TestCase):
    def test_generates_canonical_verified_scenario_from_typed_request_and_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "rules.gwt"
            program_path.write_text(PROGRAM)
            case = capture_execution_case(
                program_path,
                deepcopy(INPUT),
                request="inspect order",
            ).as_payload()

            generated = generate_scenario(case, program_path)
            repeated = generate_scenario(case, program_path)

        self.assertIsInstance(generated, ScenarioGenerationResult)
        self.assertEqual(generated.source, repeated.source)
        self.assertEqual(generated.scenario_name, "captured inspect order")
        self.assertEqual(generated.request_name, "inspect order")
        self.assertEqual(
            format_text(generated.source, filename="<generated-scenario>"),
            generated.source,
        )
        self.assertIn("GIVEN order is Order", generated.source)
        self.assertIn("  customer:\n    name: \"Ada\"\n    vip: true", generated.source)
        self.assertIn("  items: []", generated.source)
        self.assertIn("  tags: [\"priority\", \"new\"]", generated.source)
        self.assertIn("  notes: []", generated.source)
        self.assertIn("  amount: 12.30", generated.source)
        self.assertNotIn('amount: "12.30"', generated.source)
        self.assertIn("GIVEN order.items are LineItem", generated.source)
        self.assertIn("| sku", generated.source)
        self.assertIn('THEN decision.status == "approved"', generated.source)
        self.assertIn("AND decision.total == 12.30", generated.source)
        self.assertIn('AND decision.labels == ["priority", "new"]', generated.source)
        self.assertIn("AND decision.empty == []", generated.source)

    def test_uses_explicit_scenario_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "rules.gwt"
            program_path.write_text(PROGRAM)
            case = capture_execution_case(
                program_path,
                deepcopy(INPUT),
                request="inspect order",
            ).as_payload()

            generated = generate_scenario(
                case,
                program_path,
                scenario_name="regression for Ada",
            )

        self.assertTrue(generated.source.startswith("SCENARIO regression for Ada\n"))

    def test_generates_absence_assertions_and_omits_absent_optional_inputs(self):
        source = '''RECORD Limits
  amount_min: decimal
  amount_max: optional<decimal>

REQUEST inspect limits
  GIVEN limits is Limits
  WHEN inspect limits

  OUTPUT observed_maximum is optional<decimal>

WHEN inspect <limits>
  GIVEN limits is Limits
  PASS
'''
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "rules.gwt"
            program_path.write_text(source)
            case = capture_execution_case(
                program_path,
                {"limits": {"amount_min": "10.00"}},
                request="inspect limits",
            ).as_payload()

            generated = generate_scenario(case, program_path)

        self.assertIn("  amount_min: 10.00", generated.source)
        self.assertNotIn("amount_max:", generated.source)
        self.assertIn("THEN observed_maximum is absent", generated.source)

    def test_refuses_redacted_case(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path, case = self._captured_case(temp_dir)
            redacted = deepcopy(case)
            redacted["redaction"]["valuesIncluded"] = False

            with self.assertRaisesRegex(GwtError, "redacted or unavailable values"):
                generate_scenario(redacted, program_path)

    def test_refuses_null_input_with_exact_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path, case = self._captured_case(temp_dir)
            invalid = deepcopy(case)
            order = invalid["request"]["input"]["order"]
            assert isinstance(order, dict)
            customer = order["customer"]
            assert isinstance(customer, dict)
            customer["name"] = None

            with self.assertRaisesRegex(
                GwtError,
                r"null data at request\.input\.order\.customer\.name",
            ):
                generate_scenario(invalid, program_path)

    def test_refuses_missing_declared_input_field(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path, case = self._captured_case(temp_dir)
            invalid = deepcopy(case)
            order = invalid["request"]["input"]["order"]
            assert isinstance(order, dict)
            del order["mode"]

            with self.assertRaisesRegex(
                GwtError,
                "missing declared record field: order.mode",
            ):
                generate_scenario(invalid, program_path)

    def test_refuses_missing_declared_output_leaf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path, case = self._captured_case(temp_dir)
            invalid = deepcopy(case)
            decision = invalid["result"]["decision"]
            assert isinstance(decision, dict)
            del decision["total"]

            with self.assertRaisesRegex(
                GwtError,
                "missing declared output leaf: decision.total",
            ):
                generate_scenario(invalid, program_path)

    def test_refuses_program_identity_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path, case = self._captured_case(temp_dir)
            program_path.write_text(PROGRAM + "\n# changed after capture\n")

            with self.assertRaisesRegex(
                GwtError,
                "supplied program does not match the execution case",
            ):
                generate_scenario(case, program_path)

    def test_honors_import_policy_during_identity_parse_and_replay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rules = root / "rules"
            rules.mkdir()
            dependency = root / "behavior.gwt"
            program_path = rules / "rules.gwt"
            dependency.write_text(
                '''WHEN copy <request>
  set result.value to request.value
'''
            )
            program_path.write_text(
                '''USE "../behavior.gwt"

RECORD Value
  value: number

REQUEST copy value
  GIVEN request is Value
  WHEN copy request
  OUTPUT result is Value
'''
            )
            allowed = ImportPolicy((root,), allow_absolute=False)
            case = capture_execution_case(
                program_path,
                {"request": {"value": 4}},
                request="copy value",
                import_policy=allowed,
            ).as_payload()

            generated = generate_scenario(
                case,
                program_path,
                import_policy=allowed,
            )
            with self.assertRaisesRegex(GwtError, "outside allowed roots"):
                generate_scenario(
                    case,
                    program_path,
                    import_policy=ImportPolicy((rules,), allow_absolute=False),
                )

        self.assertIn("THEN result.value == 4", generated.source)

    def test_refuses_case_result_that_replay_does_not_reproduce(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path, case = self._captured_case(temp_dir)
            divergent = deepcopy(case)
            decision = divergent["result"]["decision"]
            assert isinstance(decision, dict)
            decision["status"] = "review"

            with self.assertRaisesRegex(
                GwtError,
                "failed replay verification",
            ):
                generate_scenario(divergent, program_path)

    def test_generation_replays_the_same_sources_used_for_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path, case = self._captured_case(temp_dir)
            snapshot = load_program_snapshot(program_path)
            program_path.write_text("PROGRAM changed after identity\n")

            with patch(
                "gwtlang.scenario_generation.load_program_snapshot",
                return_value=snapshot,
            ):
                generated = generate_scenario(case, program_path)

        self.assertIn("SCENARIO captured inspect order", generated.source)

    def test_refuses_empty_and_nonempty_object_valued_any_outputs(self):
        program = '''PROGRAM untyped output

REQUEST echo value
  GIVEN request is text
  WHEN preserve request
  OUTPUT value is any

WHEN preserve <request>
  set value to request
'''
        for value in ({}, {"nested": 1}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp_dir:
                program_path = Path(temp_dir) / "rules.gwt"
                program_path.write_text(program)
                case = capture_execution_case(
                    program_path,
                    {"request": "seed"},
                    request="echo value",
                ).as_payload()
                case["result"]["value"] = value

                with self.assertRaisesRegex(
                    GwtError,
                    "object-valued any output value cannot be asserted exactly",
                ):
                    generate_scenario(case, program_path)

    def _captured_case(
        self,
        temp_dir: str,
    ) -> tuple[Path, ExecutionCasePayload]:
        program_path = Path(temp_dir) / "rules.gwt"
        program_path.write_text(PROGRAM)
        case = capture_execution_case(
            program_path,
            deepcopy(INPUT),
            request="inspect order",
        ).as_payload()
        return program_path, case


if __name__ == "__main__":
    unittest.main()
