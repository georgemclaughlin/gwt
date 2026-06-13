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
                and event.attributes["gwt.branch.summary"] == "IF ticket.has_outage skipped line 13"
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
