import json
import unittest
from unittest.mock import patch

from gwtlang.runtime import GwtError, Runtime, parse_program
from gwtlang.tracing import (
    GwtTraceRecorder,
    OtlpMetric,
    otlp_metrics_endpoint,
    otlp_metrics_payload,
    otlp_trace_endpoint,
    otlp_traces_payload,
)


class TracingTests(unittest.TestCase):
    def test_runtime_trace_records_request_behavior_contracts_conditions_and_state(self):
        program = parse_program(
            """
            RECORD Cart
              subtotal: number
              shipping: number
              total: number

            REQUEST checkout cart
              GIVEN cart is Cart
              WHEN checkout cart
              OUTPUT cart is Cart
              THEN cart.total == 92

            WHEN checkout <cart>
              GIVEN cart is Cart
              set cart.total to cart.subtotal + cart.shipping
            """,
            filename="checkout.gwt",
        )
        recorder = GwtTraceRecorder(
            program_file="checkout.gwt",
            program_name="checkout",
            program_hash="sha256:" + ("a" * 64),
            request_name="checkout cart",
        )

        Runtime(program, tracer=recorder).run_json(
            {"cart": {"subtotal": 84, "shipping": 8, "total": 0}},
            "checkout cart",
        )
        recorder.finish()

        span_names = [span.name for span in recorder.spans]
        event_names = [
            event.name
            for span in recorder.spans
            for event in span.events
        ]
        events = [
            event
            for span in recorder.spans
            for event in span.events
        ]
        state_events = [
            event
            for event in events
            if event.name == "gwt.state.changed"
        ]

        self.assertIn("GWT REQUEST checkout cart", span_names)
        self.assertIn("GWT WHEN checkout <cart>", span_names)
        self.assertIn("gwt.statement.executed", event_names)
        self.assertIn("gwt.contract.checked", event_names)
        self.assertIn("gwt.behavior.entered", event_names)
        self.assertIn("gwt.behavior.exited", event_names)
        self.assertIn("gwt.input.applied", event_names)
        self.assertIn("gwt.assertion.checked", event_names)
        self.assertIn("gwt.request.completed", event_names)
        self.assertTrue(
            any(
                event.attributes["gwt.state.path"] == "cart.total"
                and event.attributes["gwt.state.operation"] == "replace"
                and event.attributes["gwt.state.old"] == 0
                and event.attributes["gwt.state.new"] == 92
                for event in state_events
            )
        )
        self.assertTrue(
            all(
                isinstance(event.attributes.get("gwt.event.summary"), str)
                and event.attributes["gwt.event.summary"]
                for event in events
            )
        )
        self.assertTrue(
            any(
                event.name == "gwt.request.completed"
                and "cart.total=92" in event.attributes["gwt.event.summary"]
                for event in events
            )
        )

        behavior_events = [
            event for event in events
            if event.name in {"gwt.behavior.entered", "gwt.behavior.exited"}
        ]
        self.assertEqual(
            [event.attributes["gwt.behavior.phase"] for event in behavior_events],
            ["enter", "exit"],
        )
        self.assertEqual(
            behavior_events[0].attributes["gwt.behavior.call_id"],
            behavior_events[1].attributes["gwt.behavior.call_id"],
        )
        self.assertEqual(behavior_events[0].attributes["gwt.behavior.depth"], 0)
        assertion_event = next(
            event for event in events
            if event.name == "gwt.assertion.checked"
        )
        self.assertEqual(
            json.loads(assertion_event.attributes["gwt.expression.operands"]),
            [
                {
                    "name": "cart.total",
                    "valueType": "integer",
                    "value": 92,
                }
            ],
        )

        payload = otlp_traces_payload(recorder.spans)
        spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(spans[0]["traceId"], recorder.trace_id)
        self.assertTrue(
            any(
                attribute["key"] == "gwt.state.patch"
                for span in spans
                for event in span["events"]
                for attribute in event["attributes"]
            )
        )
        self.assertTrue(
            any(
                attribute["key"] == "gwt.output.cart.total"
                and attribute["value"]["intValue"] == "92"
                for span in spans
                for event in span["events"]
                for attribute in event["attributes"]
            )
        )
        self.assertTrue(
            any(
                attribute["key"] == "gwt.request.summary"
                and "cart.total=92" in attribute["value"]["stringValue"]
                for span in spans
                for event in span["events"]
                for attribute in event["attributes"]
            )
        )

    def test_trace_records_branch_outcome_without_duplicate_condition_statement(self):
        program = parse_program(
            """
            RECORD Ticket
              has_outage: boolean

            REQUEST route ticket
              GIVEN ticket is Ticket
              GIVEN decision.queue is "standard"
              WHEN route ticket
              OUTPUT decision is any

            WHEN route <ticket>
              IF ticket.has_outage
                set decision.queue to "incident"
            """,
            filename="ticket.gwt",
        )
        recorder = GwtTraceRecorder(
            program_file="ticket.gwt",
            program_name="ticket",
            program_hash="sha256:" + ("b" * 64),
            request_name="route ticket",
        )

        Runtime(program, tracer=recorder).run_json(
            {"ticket": {"has_outage": False}},
            "route ticket",
        )
        recorder.finish()

        events = [
            event
            for span in recorder.spans
            for event in span.events
        ]
        self.assertTrue(
            any(
                event.name == "gwt.branch.skipped"
                and event.attributes["gwt.branch.label"] == "THEN"
                and event.attributes["gwt.branch.condition"] == "ticket.has_outage"
                and event.attributes["gwt.branch.selected"] is False
                and event.attributes["gwt.branch.start_line"]
                == event.attributes["gwt.branch.end_line"]
                for event in events
            )
        )
        self.assertFalse(
            any(
                event.name == "gwt.statement.executed"
                and event.attributes.get("gwt.statement.text") == "ticket.has_outage"
                for event in events
            )
        )

    def test_trace_false_if_reports_the_else_body_range(self):
        program = parse_program(
            """GIVEN status is "new"

WHEN choose status
  IF false
    set status to "unreachable"
  ELSE
    set status to "selected"

WHEN choose status
""",
            filename="branch.gwt",
        )
        recorder = GwtTraceRecorder(
            program_file="branch.gwt",
            program_name="branch",
            program_hash="sha256:" + ("c" * 64),
            request_name="choose status",
        )

        Runtime(program, tracer=recorder).run()
        recorder.finish()

        branch_events = [
            event
            for span in recorder.spans
            for event in span.events
            if event.name in {"gwt.branch.skipped", "gwt.branch.selected"}
        ]
        self.assertEqual(len(branch_events), 2)
        self.assertEqual(
            branch_events[0].attributes["gwt.branch.summary"],
            "IF THEN false skipped line 5",
        )
        self.assertEqual(
            branch_events[1].attributes["gwt.branch.summary"],
            "IF ELSE selected line 7",
        )

    def test_trace_records_decide_and_depending_else_selections(self):
        program = parse_program(
            '''GIVEN mode is "cancel"
GIVEN decision.first is "new"
GIVEN decision.second is "new"

WHEN choose <mode>
  DECIDE
    WHEN false
      set decision.first to "unreachable"
    ELSE
      set decision.first to "fallback"
  DEPENDING ON mode
    WHEN the value is "reserve"
      set decision.second to "reserved"
    ELSE
      set decision.second to "fallback"

WHEN choose mode
''',
            filename="alternate-branches.gwt",
        )
        recorder = GwtTraceRecorder(
            program_file="alternate-branches.gwt",
            program_name="alternate branches",
            program_hash="sha256:" + ("d" * 64),
            request_name="choose mode",
        )

        Runtime(program, tracer=recorder).run()
        recorder.finish()

        selected = [
            event.attributes
            for span in recorder.spans
            for event in span.events
            if event.name == "gwt.branch.selected"
        ]
        self.assertEqual(
            [
                (
                    item["gwt.branch.kind"],
                    item["gwt.branch.label"],
                    item["gwt.branch.condition"],
                )
                for item in selected
            ],
            [
                ("DECIDE", "ELSE", "ELSE"),
                ("DEPENDING", "ELSE", "ELSE"),
            ],
        )

    def test_path_reference_mutation_is_a_replayable_state_change_when_root_is_shadowed(self):
        program = parse_program(
            """GIVEN customer.status is "new"

WHEN update <target> using <customer>
  set target.status to customer

WHEN update customer using closed
""",
            filename="path-ref.gwt",
        )
        recorder = GwtTraceRecorder(
            program_file="path-ref.gwt",
            program_name="path-ref",
            program_hash="sha256:" + ("d" * 64),
            request_name="update customer",
        )

        result = Runtime(program, tracer=recorder).run()
        recorder.finish()

        self.assertEqual(result.state["customer"]["status"], "closed")
        state_events = [
            event
            for span in recorder.spans
            for event in span.events
            if event.name == "gwt.state.changed"
            and event.attributes.get("gwt.state.path") == "customer.status"
            and event.attributes.get("gwt.state.new") == "closed"
        ]
        self.assertEqual(len(state_events), 1)
        self.assertEqual(state_events[0].attributes["gwt.state.operation"], "replace")
        self.assertEqual(
            state_events[0].attributes["gwt.state.patch"],
            '[{"op":"replace","path":"/customer/status","value":"closed"}]',
        )

    def test_trace_does_not_record_state_change_when_mutation_fails(self):
        program = parse_program(
            """
            REQUEST close account
              GIVEN account is number
              WHEN close account

            WHEN close account
              set account.status to "closed"
            """,
            filename="account.gwt",
        )
        recorder = GwtTraceRecorder(
            program_file="account.gwt",
            program_name="account",
            program_hash="sha256:" + ("c" * 64),
            request_name="close account",
        )
        runtime = Runtime(program, tracer=recorder)

        with self.assertRaisesRegex(GwtError, "cannot create nested path under scalar: account"):
            runtime.run_json({"account": 1}, "close account")
        recorder.finish(error="cannot create nested path under scalar: account")

        self.assertEqual(runtime.state, {"account": 1})
        state_events = [
            event
            for span in recorder.spans
            for event in span.events
            if event.name == "gwt.state.changed"
        ]
        self.assertFalse(
            any(event.attributes["gwt.state.path"] == "account.status" for event in state_events)
        )

    def test_redacted_trace_does_not_export_observed_operand_values(self):
        program = parse_program(
            """
            RECORD Credential
              value: text
              expected: text
              matched: boolean

            REQUEST verify credential
              GIVEN credential is Credential
              WHEN verify credential
              OUTPUT credential is Credential

            WHEN verify <credential>
              IF credential.value == credential.expected
                set credential.matched to true
            """,
            filename="credential.gwt",
        )
        recorder = GwtTraceRecorder(
            program_file="credential.gwt",
            program_name="credential",
            program_hash="sha256:" + ("e" * 64),
            request_name="verify credential",
            include_values=False,
        )
        secret = "do-not-export-this-secret"

        Runtime(program, tracer=recorder).run_json(
            {
                "credential": {
                    "value": secret,
                    "expected": secret,
                    "matched": False,
                }
            },
            "verify credential",
        )
        recorder.finish()

        condition_event = next(
            event
            for span in recorder.spans
            for event in span.events
            if event.name == "gwt.condition.evaluated"
        )
        self.assertEqual(
            condition_event.attributes["gwt.expression.operands.availability"],
            "redacted",
        )
        self.assertNotIn("gwt.expression.operands", condition_event.attributes)
        self.assertNotIn(secret, json.dumps(otlp_traces_payload(recorder.spans)))

    def test_trace_marks_unrepresentable_operands_unavailable(self):
        recorder = GwtTraceRecorder(
            program_file="unsupported.gwt",
            program_name="unsupported",
            program_hash="sha256:" + ("f" * 64),
            request_name="unsupported",
        )

        recorder.record_condition(
            text="unsupported",
            result=True,
            operands=[("unsupported", object())],
        )

        event = recorder.spans[0].events[0]
        self.assertEqual(
            event.attributes["gwt.expression.operands.availability"],
            "unavailable",
        )
        self.assertEqual(
            event.attributes["gwt.expression.operands.unavailable_reason"],
            "unsupported-runtime-value",
        )
        self.assertNotIn("gwt.expression.operands", event.attributes)

    def test_trace_endpoint_uses_standard_environment_fallback(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"}, clear=True):
            self.assertEqual(otlp_trace_endpoint(), "http://localhost:4318/v1/traces")

        with patch.dict(
            "os.environ",
            {"OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://localhost:4318/custom"},
            clear=True,
        ):
            self.assertEqual(otlp_trace_endpoint(), "http://localhost:4318/custom")

    def test_metrics_endpoint_uses_standard_environment_fallback(self):
        with patch.dict("os.environ", {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"}, clear=True):
            self.assertEqual(otlp_metrics_endpoint(), "http://localhost:4318/v1/metrics")

        with patch.dict(
            "os.environ",
            {"OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://localhost:4318/custom"},
            clear=True,
        ):
            self.assertEqual(otlp_metrics_endpoint(), "http://localhost:4318/custom")

    def test_otlp_metrics_payload_records_sum_and_histogram_points(self):
        payload = otlp_metrics_payload(
            [
                OtlpMetric(
                    name="gwt.request.count",
                    description="GWT HTTP request executions.",
                    unit="{request}",
                    kind="sum",
                    value=1,
                    attributes={"gwt.request.name": "checkout cart"},
                    start_time_unix_nano=100,
                    time_unix_nano=200,
                ),
                OtlpMetric(
                    name="gwt.request.duration_ms",
                    description="GWT HTTP request execution duration.",
                    unit="ms",
                    kind="histogram",
                    value=12.5,
                    attributes={"gwt.request.name": "checkout cart"},
                    start_time_unix_nano=100,
                    time_unix_nano=200,
                ),
            ],
            service_name="gwt-serve",
        )

        metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
        self.assertEqual(metrics[0]["name"], "gwt.request.count")
        self.assertEqual(metrics[0]["sum"]["aggregationTemporality"], 1)
        self.assertEqual(metrics[0]["sum"]["dataPoints"][0]["asInt"], "1")
        self.assertEqual(metrics[1]["name"], "gwt.request.duration_ms")
        self.assertEqual(metrics[1]["histogram"]["aggregationTemporality"], 1)
        self.assertEqual(metrics[1]["histogram"]["dataPoints"][0]["count"], "1")
        self.assertEqual(metrics[1]["histogram"]["dataPoints"][0]["sum"], 12.5)


if __name__ == "__main__":
    unittest.main()
