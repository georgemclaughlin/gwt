from dataclasses import dataclass
from decimal import Decimal
import unittest

from gwtlang import GwtError, GwtHostAdapter, HostObservation


FORMAT_RULES = """
RECORD FormatCase
  source: text
  expected: text

RECORD FormatObservation
  status: "ok" | "error"
  formatted: text
  error: text

RECORD FormatDecision
  status: "new" | "passed" | "failed"
  reason: text

REQUEST case is FormatCase
AND observation is FormatObservation
AND decision is FormatDecision

OUTPUT decision is FormatDecision

WHEN review <case> using <observation> into <decision>
  GIVEN case is FormatCase
  AND observation is FormatObservation
  AND decision is FormatDecision
  IF observation.status == "error"
    set decision.status to "failed"
    set decision.reason to observation.error
  ELSE
    IF observation.formatted == case.expected
      set decision.status to "passed"
      set decision.reason to "formatted_as_expected"
    ELSE
      set decision.status to "failed"
      set decision.reason to "formatted_output_mismatch"
"""


@dataclass(frozen=True)
class FormatCase:
    source: str
    expected: str


@dataclass(frozen=True)
class FormatObservation:
    status: str
    formatted: str
    error: str


@dataclass(frozen=True)
class Price:
    amount: Decimal
    total: Decimal


class HostAdapterTests(unittest.TestCase):
    def test_host_observation_is_injected_before_request_validation(self):
        def observe_format(context):
            source = context.get("case.source")
            return FormatObservation(
                status="ok",
                formatted=f"{source.strip()}\n",
                error="",
            )

        adapter = GwtHostAdapter.from_text(
            FORMAT_RULES,
            entry="review case using observation into decision",
            observations=[HostObservation("observation", observe_format)],
        )
        execution = adapter.run_json(
            {
                "case": FormatCase("print(1)  ", "print(1)\n"),
                "decision": {"status": "new", "reason": ""},
            }
        )

        payload = execution.as_payload()
        self.assertEqual(payload["result"]["decision"]["status"], "passed")
        self.assertEqual(payload["result"]["decision"]["reason"], "formatted_as_expected")
        self.assertEqual(payload["state"]["observation"]["formatted"], "print(1)\n")

    def test_host_adapter_converts_decimal_values_to_exact_json_strings(self):
        adapter = GwtHostAdapter.from_text(
            """
            RECORD Price
              amount: decimal
              total: decimal

            REQUEST price is Price
            OUTPUT price is Price

            WHEN double price
              set price.total to price.amount * 2
            """,
            entry="double price",
        )

        execution = adapter.run_json({"price": Price(Decimal("12.30"), Decimal("0.00"))})

        self.assertEqual(execution.as_payload()["result"]["price"]["total"], "24.60")

    def test_adapter_can_add_observations_fluently(self):
        adapter = GwtHostAdapter.from_text(
            FORMAT_RULES,
            entry="review case using observation into decision",
        ).with_observation(
            "observation",
            lambda context: {
                "status": "ok",
                "formatted": context.get("case.source"),
                "error": "",
            },
        )

        execution = adapter.run_json(
            {
                "case": {"source": "print(2)\n", "expected": "print(2)\n"},
                "decision": {"status": "new", "reason": ""},
            }
        )

        self.assertEqual(execution.as_payload()["result"]["decision"]["status"], "passed")

    def test_host_observation_failures_are_wrapped(self):
        def observe_format(_context):
            raise ValueError("formatter crashed")

        adapter = GwtHostAdapter.from_text(
            FORMAT_RULES,
            entry="review case using observation into decision",
            observations=[HostObservation("observation", observe_format)],
        )

        with self.assertRaisesRegex(
            GwtError,
            "host observation failed for observation: formatter crashed",
        ):
            adapter.run_json(
                {
                    "case": {"source": "x", "expected": "x"},
                    "decision": {"status": "new", "reason": ""},
                }
            )


if __name__ == "__main__":
    unittest.main()
