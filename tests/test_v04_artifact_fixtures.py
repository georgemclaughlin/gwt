from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import unittest

from gwtlang.comparison import compare_execution_cases
from gwtlang.execution_case import load_execution_case


FIXTURE_ROOT = Path("tests/fixtures/v0.4")
CASE_NAMES = (
    "library-completed.execution-case.json",
    "library-available.execution-case.json",
    "library-omitted.execution-case.json",
    "shipping-contract-failure.execution-case.json",
    "shipping-runtime-failure.execution-case.json",
)


class V04ArtifactFixtureTests(unittest.TestCase):
    def test_execution_case_fixtures_cover_profiles_outcomes_and_domains(self):
        cases = {
            name: load_execution_case(FIXTURE_ROOT / name).as_payload()
            for name in CASE_NAMES
        }

        self.assertEqual(
            {
                (payload["execution"]["outcome"], payload["redaction"]["mode"])
                for payload in cases.values()
            },
            {
                ("completed", "none"),
                ("completed", "omit-values"),
                ("failed", "none"),
            },
        )
        failure_messages = {
            payload["execution"]["error"]["message"]
            for payload in cases.values()
            if payload["execution"]["outcome"] == "failed"
        }
        self.assertTrue(
            any(message.startswith("REQUEST contract failed") for message in failure_messages)
        )
        self.assertTrue(any("requirement failed" in message for message in failure_messages))
        self.assertEqual(
            {
                payload["program"]["name"]
                for payload in cases.values()
            },
            {"library hold routing baseline", "shipping quote fixture"},
        )

        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator

            schema = json.loads(
                Path("docs/schemas/execution-case.schema.json").read_text()
            )
            validator = Draft202012Validator(schema)
            for name, payload in cases.items():
                with self.subTest(name=name):
                    validator.validate(payload)

            incomplete_contract = deepcopy(
                cases["library-completed.execution-case.json"]
            )
            contract = next(
                item
                for item in incomplete_contract["evidence"]
                if item["kind"] == "contract"
            )
            del contract["label"]
            self.assertFalse(validator.is_valid(incomplete_contract))

            contradictory_omission = deepcopy(
                cases["library-omitted.execution-case.json"]
            )
            condition = next(
                item
                for item in contradictory_omission["evidence"]
                if item["kind"] == "condition"
            )
            condition["operands"] = {"availability": "available", "values": []}
            self.assertFalse(validator.is_valid(contradictory_omission))

            invalid_failure_policy = deepcopy(
                cases["shipping-runtime-failure.execution-case.json"]
            )
            invalid_failure_policy["execution"]["capturePolicy"]["onError"] = "raise"
            self.assertFalse(validator.is_valid(invalid_failure_policy))

    def test_comparison_fixture_reconciles_and_reproduces_exactly(self):
        fixture_path = FIXTURE_ROOT / "library-change.comparison.json"
        expected = json.loads(fixture_path.read_text())
        completed = load_execution_case(
            FIXTURE_ROOT / "library-completed.execution-case.json"
        )
        available = load_execution_case(
            FIXTURE_ROOT / "library-available.execution-case.json"
        )

        actual = compare_execution_cases(
            "examples/behavior_review/baseline.gwt",
            "examples/behavior_review/candidate.gwt",
            [completed, available],
        ).as_payload()

        self.assertEqual(actual, expected)
        self.assertEqual(
            [case["classification"] for case in expected["cases"]],
            ["output_changed", "unchanged"],
        )
        self.assertEqual(
            expected["totals"]["cases"],
            sum(
                count
                for name, count in expected["totals"].items()
                if name != "cases"
            ),
        )
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator

            schema = json.loads(
                Path("docs/schemas/comparison.schema.json").read_text()
            )
            validator = Draft202012Validator(schema)
            validator.validate(expected)
            invalid_presence = deepcopy(expected)
            old_value = invalid_presence["cases"][0]["outputDifferences"][0]["old"]
            old_value["present"] = False
            self.assertFalse(validator.is_valid(invalid_presence))


if __name__ == "__main__":
    unittest.main()
