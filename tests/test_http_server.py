from contextlib import contextmanager, redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import subprocess
import sys
import tempfile
from threading import Thread
import time
from typing import Any
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from gwtlang.__main__ import main
from gwtlang.comparison import compare_execution_cases
from gwtlang.execution_case import ExecutionCase
from gwtlang.http_server import (
    DEFAULT_MAX_REQUEST_BODY_BYTES,
    GwtHttpService,
    HttpExecutionCaseConfig,
    HttpMetricsConfig,
    HttpServiceError,
    HttpTraceConfig,
    HttpRouteResult,
    create_http_server,
)
from gwtlang.tracing import OtlpHttpExporter, OtlpMetricsExporter


class HttpServerTests(unittest.TestCase):
    def test_public_http_api_exports_embedded_service_symbols(self):
        from gwtlang import (
            DEFAULT_MAX_REQUEST_BODY_BYTES as exported_body_limit,
            GwtHttpService as ExportedGwtHttpService,
            HttpMetricsConfig as ExportedHttpMetricsConfig,
            HttpExecutionCaseConfig as ExportedHttpExecutionCaseConfig,
            HttpRouteResult as ExportedHttpRouteResult,
            HttpServiceError as ExportedHttpServiceError,
            HttpTraceConfig as ExportedHttpTraceConfig,
        )
        import gwtlang

        self.assertEqual(exported_body_limit, DEFAULT_MAX_REQUEST_BODY_BYTES)
        self.assertIs(ExportedGwtHttpService, GwtHttpService)
        self.assertIs(ExportedHttpExecutionCaseConfig, HttpExecutionCaseConfig)
        self.assertIs(ExportedHttpMetricsConfig, HttpMetricsConfig)
        self.assertIs(ExportedHttpRouteResult, HttpRouteResult)
        self.assertIs(ExportedHttpServiceError, HttpServiceError)
        self.assertIs(ExportedHttpTraceConfig, HttpTraceConfig)
        self.assertIn("DEFAULT_MAX_REQUEST_BODY_BYTES", gwtlang.__all__)
        self.assertIn("HttpMetricsConfig", gwtlang.__all__)
        self.assertIn("HttpExecutionCaseConfig", gwtlang.__all__)
        self.assertIn("HttpRouteResult", gwtlang.__all__)
        self.assertIn("HttpServiceError", gwtlang.__all__)

    def test_gwt_serve_openapi_contract_smoke(self):
        success_trace_id = "77777777777777777777777777777777"
        bad_request_trace_id = "88888888888888888888888888888888"
        too_large_trace_id = "99999999999999999999999999999999"
        unsupported_trace_id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        with running_otlp_sink() as otlp:
            with running_serve_process(
                "examples/deployable_api/rules.gwt",
                otlp_endpoint=f"{otlp.base_url}/v1/traces",
                max_body_bytes=4096,
            ) as base_url:
                openapi_status, openapi = request_json(f"{base_url}/openapi.json")
                route = route_for_request(openapi, "triage ticket")
                operation = openapi["paths"][route]["post"]

                success_status, success_payload, success_headers = request_json_with_headers(
                    f"{base_url}{route}",
                    triage_ticket_request(),
                    method="POST",
                    headers={
                        "traceparent": f"00-{success_trace_id}-1111111111111111-01",
                    },
                )
                bad_status, bad_payload, bad_headers = request_json_with_headers(
                    f"{base_url}{route}",
                    {**triage_ticket_request(), "unexpected": "not declared"},
                    method="POST",
                    headers={
                        "traceparent": f"00-{bad_request_trace_id}-2222222222222222-01",
                    },
                )
                too_large_status, too_large_payload, too_large_headers = request_raw_with_headers(
                    f"{base_url}{route}",
                    b" " * 4097,
                    method="POST",
                    headers={
                        "traceparent": f"00-{too_large_trace_id}-3333333333333333-01",
                    },
                )
                unsupported_status, unsupported_payload, unsupported_headers = request_raw_with_headers(
                    f"{base_url}{route}",
                    b"{}",
                    method="POST",
                    headers={
                        "Content-Type": "text/plain",
                        "traceparent": f"00-{unsupported_trace_id}-4444444444444444-01",
                    },
                )

            exported = otlp.payloads

        self.assertEqual(openapi_status, 200)
        self.assertEqual(operation["requestBody"]["content"]["application/json"]["schema"], {
            "$ref": "#/components/schemas/TriageTicketRequest"
        })
        for status in ("200", "400", "413", "415", "500"):
            self.assertIn(status, operation["responses"])

        self.assertEqual(success_status, 200)
        self.assertEqual(success_payload["decision"]["queue"], "incident")
        self.assertNotIn("ticket", success_payload)
        self.assert_trace_headers(success_headers, success_trace_id)

        self.assertEqual(bad_status, 400)
        self.assertEqual(bad_payload["error"]["code"], "GWT_HTTP_UNDECLARED_INPUT")
        self.assert_trace_headers(bad_headers, bad_request_trace_id)

        self.assertEqual(too_large_status, 413)
        self.assertEqual(too_large_payload["error"]["code"], "GWT_HTTP_BODY_TOO_LARGE")
        self.assert_trace_headers(too_large_headers, too_large_trace_id)

        self.assertEqual(unsupported_status, 415)
        self.assertEqual(unsupported_payload["error"]["code"], "GWT_HTTP_UNSUPPORTED_MEDIA_TYPE")
        self.assert_trace_headers(unsupported_headers, unsupported_trace_id)

        exported_trace_ids = {
            span["traceId"]
            for payload in exported
            for resource_span in payload["resourceSpans"]
            for scope_span in resource_span["scopeSpans"]
            for span in scope_span["spans"]
        }
        self.assertEqual(len(exported), 4)
        self.assertTrue(
            {
                success_trace_id,
                bad_request_trace_id,
                too_large_trace_id,
                unsupported_trace_id,
            }.issubset(exported_trace_ids)
        )

    def test_gwt_serve_runs_host_evaluated_commit_selection_request(self):
        rules = "examples/external_pilots/semantic_release_commit_analyzer/rules.gwt"
        request_input = {
            "evaluations": [
                {"id": "patch", "matched": True, "release": "patch"},
                {"id": "feature", "matched": True, "release": "minor"},
                {"id": "ignored", "matched": False, "release": "major"},
            ]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_dir = Path(temp_dir) / "cases"
            with running_serve_process(
                rules,
                capture_dir=capture_dir,
                capture_values=True,
                capture_request="select release from evaluated rules",
                fact_provenance=Path(
                    "examples/external_pilots/semantic_release_commit_analyzer/"
                    "evaluated-fact-provenance.json"
                ),
            ) as base_url:
                openapi_status, openapi = request_json(f"{base_url}/openapi.json")
                route = route_for_request(openapi, "select release from evaluated rules")
                status, payload, headers = request_json_with_headers(
                    f"{base_url}{route}",
                    request_input,
                    method="POST",
                )
            execution_case = ExecutionCase.load(
                next(capture_dir.glob("*.execution-case.json"))
            )

        self.assertEqual(openapi_status, 200)
        self.assertEqual(route, "/requests/select-release-from-evaluated-rules")
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["release"], "minor")
        self.assertEqual(payload["result"]["selected_rule_id"], "feature")
        self.assertEqual(execution_case.input, request_input)
        self.assertEqual(execution_case.result, payload)
        self.assertEqual(
            execution_case.as_payload()["integrity"]["digest"],
            headers["x-gwt-case-id"],
        )

    def test_serve_capture_defaults_to_shape_only_and_returns_case_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_dir = Path(temp_dir) / "cases"
            with running_serve_process(
                "examples/deployable_api/rules.gwt",
                capture_dir=capture_dir,
            ) as base_url:
                status, payload, headers = request_json_with_headers(
                    f"{base_url}/requests/triage-ticket",
                    triage_ticket_request(),
                    method="POST",
                )

            case_id = headers["x-gwt-case-id"]
            case_path = capture_dir / (
                f"{case_id.removeprefix('sha256:')}.execution-case.json"
            )
            execution_case = ExecutionCase.load(case_path)
            case_payload = execution_case.as_payload()

        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"]["queue"], "incident")
        self.assertRegex(case_id, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(case_payload["integrity"]["digest"], case_id)
        self.assertEqual(
            case_payload["execution"]["capturePolicy"],
            {"onError": "record", "values": "omit"},
        )
        self.assertEqual(case_payload["request"]["input"], {})
        self.assertEqual(case_payload["result"], {})
        self.assertEqual(
            case_payload["redaction"]["availability"]["requestInput"],
            "redacted",
        )
        self.assertIn("traceparent", headers)
        self.assertIn("x-gwt-trace-id", headers)

    def test_serve_full_capture_records_provenance_and_replays(self):
        program = Path("examples/deployable_api/rules.gwt")
        request_input = triage_ticket_request()
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_dir = Path(temp_dir) / "cases"
            provenance_path = Path(temp_dir) / "provenance.json"
            provenance_path.write_text(
                json.dumps(
                    {
                        "ticket.customer_id": {
                            "source": "support-api.ticket.customer_id",
                            "description": "Supplied by the local pilot adapter.",
                        }
                    }
                )
            )
            with running_serve_process(
                program,
                capture_dir=capture_dir,
                capture_values=True,
                capture_request="triage ticket",
                fact_provenance=provenance_path,
            ) as base_url:
                status, payload, headers = request_json_with_headers(
                    f"{base_url}/requests/triage-ticket",
                    request_input,
                    method="POST",
                )

            case_id = headers["x-gwt-case-id"]
            execution_case = ExecutionCase.load(
                capture_dir
                / f"{case_id.removeprefix('sha256:')}.execution-case.json"
            )
            comparison = compare_execution_cases(
                program,
                program,
                [execution_case],
            )

        self.assertEqual(status, 200)
        self.assertEqual(execution_case.input, request_input)
        self.assertEqual(execution_case.result, payload)
        self.assertEqual(
            execution_case.fact_provenance[0]["source"],
            "support-api.ticket.customer_id",
        )
        self.assertEqual(comparison.cases[0].classification, "unchanged")

    def test_serve_capture_records_runtime_failure_but_not_transport_rejection(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_dir = Path(temp_dir) / "cases"
            with running_serve_process(
                "examples/deployable_api/rules.gwt",
                capture_dir=capture_dir,
            ) as base_url:
                failure_status, failure_payload, failure_headers = (
                    request_json_with_headers(
                        f"{base_url}/requests/triage-ticket",
                        {},
                        method="POST",
                    )
                )
                invalid_status, _invalid_payload, invalid_headers = (
                    request_raw_with_headers(
                        f"{base_url}/requests/triage-ticket",
                        b"{",
                        method="POST",
                    )
                )

            case_paths = list(capture_dir.glob("*.execution-case.json"))
            execution_case = ExecutionCase.load(case_paths[0])

        self.assertEqual(failure_status, 400)
        self.assertEqual(failure_payload["error"]["code"], "GWT_REQUEST_FAILED")
        self.assertIn("x-gwt-case-id", failure_headers)
        self.assertEqual(invalid_status, 400)
        self.assertNotIn("x-gwt-case-id", invalid_headers)
        self.assertEqual(len(case_paths), 1)
        self.assertEqual(execution_case.outcome, "failed")
        self.assertEqual(
            execution_case.as_payload()["execution"]["error"]["message"],
            "GWT execution failed; error detail omitted by capture policy",
        )

    def test_serve_capture_validates_selected_request_and_trace_privacy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_dir = Path(temp_dir)
            with self.assertRaisesRegex(ValueError, "unknown capture request"):
                GwtHttpService.from_file(
                    "examples/deployable_api/rules.gwt",
                    capture_config=HttpExecutionCaseConfig(
                        capture_dir,
                        request_names=frozenset({"missing request"}),
                    ),
                )
            with self.assertRaisesRegex(ValueError, "redacted OTLP trace"):
                GwtHttpService.from_file(
                    "examples/deployable_api/rules.gwt",
                    trace_config=HttpTraceConfig("http://127.0.0.1:4318/v1/traces"),
                    capture_config=HttpExecutionCaseConfig(
                        capture_dir,
                        include_values=True,
                    ),
                )

    def test_serve_capture_write_failure_preserves_decision_response(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = GwtHttpService.from_file(
                "examples/deployable_api/rules.gwt",
                capture_config=HttpExecutionCaseConfig(Path(temp_dir)),
            )
            stderr = io.StringIO()
            with (
                patch(
                    "gwtlang.execution_case.ExecutionCase.write",
                    side_effect=OSError("disk unavailable"),
                ),
                redirect_stderr(stderr),
            ):
                result = service.run_route(
                    "/requests/triage-ticket",
                    triage_ticket_request(),
                )

        self.assertEqual(result.body["decision"]["queue"], "incident")
        self.assertIsNone(result.case_id)
        self.assertIn("execution case capture failed", stderr.getvalue())
        self.assertIn("disk unavailable", stderr.getvalue())

    def test_gwt_serve_preserves_absent_and_null_optional_decimal(self):
        rules = "examples/external_pilots/spree_item_total/rules.gwt"
        base_facts = {
            "item_total": "1000.00",
            "amount_min": "50.00",
            "minimum_mode": "gt",
            "maximum_mode": "lt",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            capture_dir = Path(temp_dir) / "cases"
            with running_serve_process(
                rules,
                capture_dir=capture_dir,
                capture_request="assess item total eligibility",
            ) as base_url:
                route = "/requests/assess-item-total-eligibility"
                absent_status, absent, absent_headers = request_json_with_headers(
                    f"{base_url}{route}",
                    {"facts": base_facts},
                    method="POST",
                )
                null_status, explicit_null, null_headers = request_json_with_headers(
                    f"{base_url}{route}",
                    {"facts": {**base_facts, "amount_max": None}},
                    method="POST",
                )
            case_paths = list(capture_dir.glob("*.execution-case.json"))

        self.assertEqual(absent_status, 200)
        self.assertEqual(null_status, 200)
        self.assertEqual(absent, explicit_null)
        self.assertEqual(absent["decision"]["eligible"], True)
        self.assertEqual(absent["decision"]["first_error"], "none")
        self.assertNotEqual(
            absent_headers["x-gwt-case-id"],
            null_headers["x-gwt-case-id"],
        )
        self.assertEqual(len(case_paths), 2)

    def test_json_schema_client_demo_validates_request_and_response(self):
        if importlib.util.find_spec("jsonschema") is None:
            self.skipTest("jsonschema package is not installed")

        with running_service("examples/deployable_api/rules.gwt") as base_url:
            result = subprocess.run(
                [
                    sys.executable,
                    "examples/deployable_api/json_schema_client_demo.py",
                ],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "GWT_DEMO_BASE_URL": base_url},
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["decision"]["status"], "escalated")
        self.assertEqual(payload["decision"]["queue"], "incident")

    def test_serves_health_request_manifest_and_openapi(self):
        with running_service("examples/deployable_api/rules.gwt") as base_url:
            health_status, health = request_json(f"{base_url}/health")
            requests_status, requests = request_json(f"{base_url}/requests")
            openapi_status, openapi = request_json(f"{base_url}/openapi.json")

        self.assertEqual(health_status, 200)
        self.assertEqual(health["ok"], True)
        self.assertEqual(health["program"], "support ticket api")
        self.assertEqual(health["requests"], 1)

        self.assertEqual(requests_status, 200)
        self.assertEqual(requests["requests"][0]["name"], "triage ticket")
        self.assertEqual(requests["requests"][0]["path"], "/requests/triage-ticket")
        self.assertEqual(requests["requests"][0]["inputs"], [{"path": "ticket", "type": "TicketRequest"}])
        self.assertEqual(requests["requests"][0]["outputs"], [{"path": "decision", "type": "TicketDecision"}])

        self.assertEqual(openapi_status, 200)
        self.assertIn("/requests/triage-ticket", openapi["paths"])
        self.assertEqual(
            openapi["paths"]["/requests/triage-ticket"]["post"]["x-gwt-request-name"],
            "triage ticket",
        )

    def test_post_request_returns_declared_output_body(self):
        with running_service("examples/deployable_api/rules.gwt") as base_url:
            status, payload = request_json(
                f"{base_url}/requests/triage-ticket",
                {
                    "ticket": {
                        "customer_id": "C-100",
                        "subject": "checkout unavailable",
                        "severity": "medium",
                        "account_value": 5000,
                        "has_outage": True,
                    }
                },
                method="POST",
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"]["status"], "escalated")
        self.assertEqual(payload["decision"]["queue"], "incident")
        self.assertNotIn("ok", payload)
        self.assertNotIn("state", payload)
        self.assertNotIn("ticket", payload)

    def test_post_request_exports_otlp_trace_and_returns_trace_headers(self):
        incoming_trace_id = "0af7651916cd43dd8448eb211c80319c"
        incoming_span_id = "b7ad6b7169203331"
        with running_otlp_sink() as otlp:
            with running_service(
                "examples/deployable_api/rules.gwt",
                trace_config=HttpTraceConfig(f"{otlp.base_url}/v1/traces"),
            ) as base_url:
                status, payload, headers = request_json_with_headers(
                    f"{base_url}/requests/triage-ticket",
                    {
                        "ticket": {
                            "customer_id": "C-100",
                            "subject": "checkout unavailable",
                            "severity": "medium",
                            "account_value": 5000,
                            "has_outage": True,
                        }
                    },
                    method="POST",
                    headers={
                        "traceparent": f"00-{incoming_trace_id}-{incoming_span_id}-01",
                    },
                )

            exported = otlp.payloads

        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"]["queue"], "incident")
        self.assertTrue(headers["traceparent"].startswith(f"00-{incoming_trace_id}-"))
        self.assertEqual(headers["x-gwt-trace-id"], incoming_trace_id)
        self.assertEqual(len(exported), 1)
        spans = exported[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(spans[0]["traceId"], incoming_trace_id)
        self.assertEqual(spans[0]["parentSpanId"], incoming_span_id)
        self.assertIn("POST /requests/triage-ticket", [span["name"] for span in spans])
        self.assertIn("GWT REQUEST triage ticket", [span["name"] for span in spans])
        root_attributes = attributes_by_key(spans[0]["attributes"])
        self.assertEqual(root_attributes["gwt.trace.values"]["stringValue"], "redacted")
        self.assertTrue(
            any(
                event["name"] == "gwt.state.changed"
                for span in spans
                for event in span["events"]
            )
        )
        self.assertTrue(
            any(
                event["name"] == "gwt.request.completed"
                for span in spans
                for event in span["events"]
            )
        )
        event_attribute_keys = {
            attribute["key"]
            for span in spans
            for event in span["events"]
            for attribute in event["attributes"]
        }
        self.assertIn("gwt.state.values.redacted", event_attribute_keys)
        self.assertIn("gwt.output.redacted", event_attribute_keys)
        self.assertNotIn("gwt.state.old", event_attribute_keys)
        self.assertNotIn("gwt.state.new", event_attribute_keys)
        self.assertNotIn("gwt.state.patch", event_attribute_keys)
        self.assertNotIn("gwt.output.decision.status", event_attribute_keys)

    def test_trace_values_opt_in_exports_output_and_state_values(self):
        with running_otlp_sink() as otlp:
            with running_service(
                "examples/deployable_api/rules.gwt",
                trace_config=HttpTraceConfig(
                    f"{otlp.base_url}/v1/traces",
                    include_values=True,
                ),
            ) as base_url:
                status, payload = request_json(
                    f"{base_url}/requests/triage-ticket",
                    {
                        "ticket": {
                            "customer_id": "C-100",
                            "subject": "checkout unavailable",
                            "severity": "medium",
                            "account_value": 5000,
                            "has_outage": True,
                        }
                    },
                    method="POST",
                )

            exported = otlp.payloads

        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"]["queue"], "incident")
        spans = exported[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
        root_attributes = attributes_by_key(spans[0]["attributes"])
        self.assertEqual(root_attributes["gwt.trace.values"]["stringValue"], "full")
        self.assertTrue(
            any(
                attribute["key"] == "gwt.state.new"
                and attribute["value"].get("stringValue") == "incident"
                for span in spans
                for event in span["events"]
                for attribute in event["attributes"]
            )
        )
        self.assertTrue(
            any(
                attribute["key"] == "gwt.output.decision.status"
                and attribute["value"].get("stringValue") == "escalated"
                for span in spans
                for event in span["events"]
                for attribute in event["attributes"]
            )
        )

    def test_post_request_exports_otlp_metrics(self):
        with running_otlp_sink() as otlp:
            with running_service(
                "examples/deployable_api/rules.gwt",
                metrics_config=HttpMetricsConfig(f"{otlp.base_url}/v1/metrics"),
            ) as base_url:
                status, payload = request_json(
                    f"{base_url}/requests/triage-ticket",
                    triage_ticket_request(),
                    method="POST",
                )

            exported = otlp.payloads_for_path("/v1/metrics")

        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"]["queue"], "incident")
        self.assertEqual(len(exported), 1)
        metrics = exported[0]["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
        metric_names = {metric["name"] for metric in metrics}
        self.assertIn("gwt.request.count", metric_names)
        self.assertIn("gwt.request.duration_ms", metric_names)
        request_count = next(metric for metric in metrics if metric["name"] == "gwt.request.count")
        data_point = request_count["sum"]["dataPoints"][0]
        attributes = attributes_by_key(data_point["attributes"])
        self.assertEqual(attributes["gwt.request.name"]["stringValue"], "triage ticket")
        self.assertEqual(attributes["http.route"]["stringValue"], "/requests/triage-ticket")
        self.assertEqual(attributes["http.response.status_code"]["intValue"], "200")
        self.assertEqual(data_point["asInt"], "1")

    def test_malformed_otlp_metrics_endpoint_does_not_break_response(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with running_service(
                "examples/deployable_api/rules.gwt",
                metrics_config=HttpMetricsConfig("://missing-scheme"),
            ) as base_url:
                status, payload = request_json(
                    f"{base_url}/requests/triage-ticket",
                    triage_ticket_request(),
                    method="POST",
                )

        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"]["queue"], "incident")
        self.assertIn("OTLP metric export failed", stderr.getvalue())

    def test_malformed_otlp_trace_endpoint_does_not_break_response(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with running_service(
                "examples/deployable_api/rules.gwt",
                trace_config=HttpTraceConfig("://missing-scheme"),
            ) as base_url:
                status, payload = request_json(
                    f"{base_url}/requests/triage-ticket",
                    triage_ticket_request(),
                    method="POST",
                )

        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"]["queue"], "incident")
        self.assertIn("OTLP trace export failed", stderr.getvalue())

    def test_background_otlp_exports_do_not_delay_response(self):
        completed_metric_calls: Queue[str] = Queue()
        completed_trace_calls: Queue[str] = Queue()
        metric_calls: Queue[str] = Queue()
        trace_calls: Queue[str] = Queue()

        def slow_metrics_export(
            exporter: OtlpMetricsExporter,
            metrics: list[dict[str, Any]],
            *,
            service_name: str,
        ) -> None:
            del exporter, metrics, service_name
            metric_calls.put("metrics")
            time.sleep(0.35)
            completed_metric_calls.put("metrics")

        def slow_trace_export(exporter: OtlpHttpExporter, spans: list[Any]) -> None:
            del exporter, spans
            trace_calls.put("trace")
            time.sleep(0.35)
            completed_trace_calls.put("trace")

        with (
            patch.object(OtlpMetricsExporter, "export", slow_metrics_export),
            patch.object(OtlpHttpExporter, "export", slow_trace_export),
            running_service(
                "examples/deployable_api/rules.gwt",
                trace_config=HttpTraceConfig("http://127.0.0.1:4318/v1/traces"),
                metrics_config=HttpMetricsConfig("http://127.0.0.1:4318/v1/metrics"),
                background_exports=True,
            ) as base_url,
        ):
            start = time.monotonic()
            status, payload = request_json(
                f"{base_url}/requests/triage-ticket",
                triage_ticket_request(),
                method="POST",
            )
            elapsed = time.monotonic() - start

        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"]["queue"], "incident")
        self.assertLess(elapsed, 0.25)
        self.assertEqual(metric_calls.get(timeout=1), "metrics")
        self.assertEqual(trace_calls.get(timeout=1), "trace")
        self.assertEqual(completed_metric_calls.get(timeout=1), "metrics")
        self.assertEqual(completed_trace_calls.get(timeout=1), "trace")

    def test_background_otlp_worker_continues_after_unexpected_export_error(self):
        trace_calls: Queue[str] = Queue()

        def flaky_trace_export(exporter: OtlpHttpExporter, spans: list[Any]) -> None:
            del exporter, spans
            trace_calls.put("trace")
            if trace_calls.qsize() == 1:
                raise RuntimeError("boom")

        stderr = io.StringIO()
        with (
            redirect_stderr(stderr),
            patch.object(OtlpHttpExporter, "export", flaky_trace_export),
            running_service(
                "examples/deployable_api/rules.gwt",
                trace_config=HttpTraceConfig("http://127.0.0.1:4318/v1/traces"),
                background_exports=True,
            ) as base_url,
        ):
            for _ in range(2):
                status, payload = request_json(
                    f"{base_url}/requests/triage-ticket",
                    triage_ticket_request(),
                    method="POST",
                )
                self.assertEqual(status, 200)
                self.assertEqual(payload["decision"]["queue"], "incident")

        self.assertEqual(trace_calls.get(timeout=1), "trace")
        self.assertEqual(trace_calls.get(timeout=1), "trace")
        self.assertIn("OTLP trace export failed: boom", stderr.getvalue())

    def test_failed_request_exports_otlp_failure_metrics(self):
        with running_otlp_sink() as otlp:
            with running_service(
                "examples/deployable_api/rules.gwt",
                metrics_config=HttpMetricsConfig(f"{otlp.base_url}/v1/metrics"),
            ) as base_url:
                status, payload = request_json(
                    f"{base_url}/requests/triage-ticket",
                    {"ticket": {"customer_id": "C-100"}},
                    method="POST",
                )

            exported = otlp.payloads_for_path("/v1/metrics")

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "GWT_REQUEST_FAILED")
        metrics = exported[0]["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]
        metric_names = {metric["name"] for metric in metrics}
        self.assertIn("gwt.request.failure.count", metric_names)
        self.assertIn("gwt.contract.failure.count", metric_names)
        failure_count = next(metric for metric in metrics if metric["name"] == "gwt.request.failure.count")
        attributes = attributes_by_key(failure_count["sum"]["dataPoints"][0]["attributes"])
        self.assertEqual(attributes["http.response.status_code"]["intValue"], "400")
        self.assertEqual(attributes["gwt.error.code"]["stringValue"], "GWT_REQUEST_FAILED")

    def test_redacted_trace_hides_contract_failure_values(self):
        secret = "customer-secret-123"
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                """
                TYPE Status is "approved" | "denied"

                REQUEST review
                  GIVEN status is Status
                  WHEN review

                WHEN review
                  PASS
                """
            )

            with running_otlp_sink() as otlp:
                with running_service(
                    program,
                    trace_config=HttpTraceConfig(f"{otlp.base_url}/v1/traces"),
                ) as base_url:
                    status, payload = request_json(
                        f"{base_url}/requests/review",
                        {"status": secret},
                        method="POST",
                    )

                exported = otlp.payloads

        self.assertEqual(status, 400)
        self.assertIn(secret, payload["error"]["message"])
        serialized_trace = json.dumps(exported, sort_keys=True)
        self.assertNotIn(secret, serialized_trace)
        self.assertIn("GWT error", serialized_trace)
        self.assertIn("GWT contract failed", serialized_trace)

    def test_redacted_trace_uses_declared_output_paths_not_runtime_object_keys(self):
        sensitive_key = "ssn-123-45-6789"
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                """
                REQUEST echo
                  GIVEN payload is any
                  WHEN echo

                  OUTPUT payload is any

                WHEN echo
                  PASS
                """
            )

            with running_otlp_sink() as otlp:
                with running_service(
                    program,
                    trace_config=HttpTraceConfig(f"{otlp.base_url}/v1/traces"),
                ) as base_url:
                    status, payload = request_json(
                        f"{base_url}/requests/echo",
                        {"payload": {sensitive_key: "present"}},
                        method="POST",
                    )

                exported = otlp.payloads

        self.assertEqual(status, 200)
        self.assertEqual(payload["payload"], {sensitive_key: "present"})
        serialized_trace = json.dumps(exported, sort_keys=True)
        self.assertNotIn(sensitive_key, serialized_trace)
        self.assertIn("payload [values redacted]", serialized_trace)

    def test_invalid_request_contract_returns_400(self):
        with running_service("examples/deployable_api/rules.gwt") as base_url:
            status, payload = request_json(
                f"{base_url}/requests/triage-ticket",
                {"ticket": {"customer_id": "C-100"}},
                method="POST",
            )

        self.assertEqual(status, 400)
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "GWT_REQUEST_FAILED")
        self.assertIn("REQUEST contract failed for ticket", payload["error"]["message"])

    def test_undeclared_request_input_returns_400(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                """
                REQUEST ping
                  GIVEN metadata.trace_id is text
                  WHEN ping

                  OUTPUT ok is boolean

                WHEN ping
                  set ok to true
                """
            )

            with running_service(program) as base_url:
                status, payload = request_json(
                    f"{base_url}/requests/ping",
                    {"metadata": {"trace_id": "T-100", "extra": "ignored before strict mode"}},
                    method="POST",
                )

        self.assertEqual(status, 400)
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "GWT_HTTP_UNDECLARED_INPUT")
        self.assertEqual(
            payload["error"]["message"],
            "request body contains undeclared input: metadata.extra",
        )

    def test_undeclared_request_input_exports_error_trace(self):
        incoming_trace_id = "33333333333333333333333333333333"
        incoming_span_id = "4444444444444444"
        with running_otlp_sink() as otlp:
            with running_service(
                "examples/deployable_api/rules.gwt",
                trace_config=HttpTraceConfig(f"{otlp.base_url}/v1/traces"),
            ) as base_url:
                status, payload, headers = request_json_with_headers(
                    f"{base_url}/requests/triage-ticket",
                    {
                        "ticket": {
                            "customer_id": "C-100",
                            "subject": "checkout unavailable",
                            "severity": "medium",
                            "account_value": 5000,
                            "has_outage": True,
                        },
                        "unexpected": "not declared",
                    },
                    method="POST",
                    headers={
                        "traceparent": f"00-{incoming_trace_id}-{incoming_span_id}-01",
                    },
                )

            exported = otlp.payloads

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "GWT_HTTP_UNDECLARED_INPUT")
        self.assertTrue(headers["traceparent"].startswith(f"00-{incoming_trace_id}-"))
        self.assertEqual(headers["x-gwt-trace-id"], incoming_trace_id)
        self.assertEqual(len(exported), 1)
        spans = exported[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(spans[0]["traceId"], incoming_trace_id)
        self.assertEqual(spans[0]["parentSpanId"], incoming_span_id)
        self.assertTrue(
            any(
                event["name"] == "exception"
                and any(
                    attribute["key"] == "exception.message"
                    and attribute["value"]["stringValue"] == "GWT error"
                    for attribute in event["attributes"]
                )
                and any(
                    attribute["key"] == "exception.message.redacted"
                    and attribute["value"]["boolValue"]
                    for attribute in event["attributes"]
                )
                for span in spans
                for event in span["events"]
            )
        )

    def test_empty_request_rejects_nonempty_body(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                """
                REQUEST ping
                  WHEN ping

                  OUTPUT ok is boolean

                WHEN ping
                  set ok to true
                """
            )

            with running_service(program) as base_url:
                status, payload = request_json(
                    f"{base_url}/requests/ping",
                    {"extra": "not declared"},
                    method="POST",
                )

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "GWT_HTTP_UNDECLARED_INPUT")
        self.assertEqual(payload["error"]["message"], "request body contains undeclared input: extra")

    def test_request_assertion_failure_returns_500(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                """
                REQUEST ping
                  WHEN ping

                  OUTPUT ok is boolean

                  THEN ok == true

                WHEN ping
                  set ok to false
                """
            )

            with running_service(program) as base_url:
                status, payload = request_json(f"{base_url}/requests/ping", {}, method="POST")

        self.assertEqual(status, 500)
        self.assertEqual(payload["ok"], False)
        self.assertIn("assertion failed: ok == true", payload["error"]["message"])

    def test_missing_output_returns_500(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                """
                REQUEST ping
                  WHEN ping

                  OUTPUT missing is text

                WHEN ping
                  PASS
                """
            )

            with running_service(program) as base_url:
                status, payload = request_json(f"{base_url}/requests/ping", {}, method="POST")

        self.assertEqual(status, 500)
        self.assertEqual(payload["ok"], False)
        self.assertIn("OUTPUT contract failed for missing", payload["error"]["message"])

    def test_uses_openapi_paths_for_slug_collisions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                """
                REQUEST review vendor
                  WHEN set label to "space"
                  OUTPUT label is text

                REQUEST review-vendor
                  WHEN set label to "dash"
                  OUTPUT label is text
                """
            )

            with running_service(program) as base_url:
                first_status, first = request_json(f"{base_url}/requests/review-vendor", {}, method="POST")
                second_status, second = request_json(f"{base_url}/requests/review-vendor-2", {}, method="POST")

        self.assertEqual(first_status, 200)
        self.assertEqual(first["label"], "space")
        self.assertEqual(second_status, 200)
        self.assertEqual(second["label"], "dash")

    def test_malformed_json_returns_400(self):
        with running_service("examples/deployable_api/rules.gwt") as base_url:
            status, payload = request_raw(
                f"{base_url}/requests/triage-ticket",
                b"{",
                method="POST",
            )

        self.assertEqual(status, 400)
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "GWT_HTTP_INVALID_JSON")

    def test_accepts_json_content_type_with_charset(self):
        with running_service("examples/deployable_api/rules.gwt") as base_url:
            status, payload, _headers = request_json_with_headers(
                f"{base_url}/requests/triage-ticket",
                {
                    "ticket": {
                        "customer_id": "C-100",
                        "subject": "checkout unavailable",
                        "severity": "medium",
                        "account_value": 5000,
                        "has_outage": True,
                    }
                },
                method="POST",
                headers={"Content-Type": "application/json; charset=utf-8"},
            )

        self.assertEqual(status, 200)
        self.assertEqual(payload["decision"]["queue"], "incident")

    def test_unsupported_content_type_returns_415(self):
        with running_service("examples/deployable_api/rules.gwt") as base_url:
            status, payload = request_raw(
                f"{base_url}/requests/triage-ticket",
                b"{}",
                method="POST",
                headers={"Content-Type": "text/plain"},
            )

        self.assertEqual(status, 415)
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "GWT_HTTP_UNSUPPORTED_MEDIA_TYPE")
        self.assertEqual(
            payload["error"]["message"],
            "request Content-Type must be application/json",
        )

    def test_run_route_uses_decoded_json_without_http_body_rules(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                """
                REQUEST ping
                  GIVEN metadata.trace_id is text
                  WHEN ping

                  OUTPUT ok is boolean

                WHEN ping
                  set ok to true
                """
            )
            service = GwtHttpService.from_file(program, max_request_body_bytes=0)

            result = service.run_route(
                "/requests/ping",
                {"metadata": {"trace_id": "T-100"}},
            )

        self.assertEqual(result.body, {"ok": True})

    def test_run_http_route_keeps_previous_positional_call_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                """
                REQUEST ping
                  WHEN ping

                  OUTPUT ok is boolean

                WHEN ping
                  set ok to true
                """
            )
            service = GwtHttpService.from_file(program)

            result = service.run_http_route(
                "/requests/ping",
                "2",
                io.BytesIO(b"{}"),
            )

        self.assertEqual(result.body, {"ok": True})

    def test_missing_content_type_returns_415(self):
        service = GwtHttpService.from_file("examples/deployable_api/rules.gwt")
        with self.assertRaisesRegex(HttpServiceError, "Content-Type") as error:
            service.run_http_route(
                "/requests/triage-ticket",
                "2",
                io.BytesIO(b"{}"),
                content_type=None,
            )

        self.assertEqual(error.exception.status, 415)
        self.assertEqual(error.exception.code, "GWT_HTTP_UNSUPPORTED_MEDIA_TYPE")

    def test_request_body_too_large_returns_413_and_trace_headers(self):
        incoming_trace_id = "55555555555555555555555555555555"
        incoming_span_id = "6666666666666666"
        with running_otlp_sink() as otlp:
            with running_service(
                "examples/deployable_api/rules.gwt",
                trace_config=HttpTraceConfig(f"{otlp.base_url}/v1/traces"),
                max_request_body_bytes=1,
            ) as base_url:
                status, payload, headers = request_raw_with_headers(
                    f"{base_url}/requests/triage-ticket",
                    b"{}",
                    method="POST",
                    headers={
                        "traceparent": f"00-{incoming_trace_id}-{incoming_span_id}-01",
                    },
                )

            exported = otlp.payloads

        self.assertEqual(status, 413)
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "GWT_HTTP_BODY_TOO_LARGE")
        self.assertEqual(payload["error"]["message"], "request body exceeds 1 byte limit")
        self.assertTrue(headers["traceparent"].startswith(f"00-{incoming_trace_id}-"))
        self.assertEqual(headers["x-gwt-trace-id"], incoming_trace_id)
        self.assertEqual(len(exported), 1)
        spans = exported[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(spans[0]["traceId"], incoming_trace_id)
        self.assertEqual(spans[0]["parentSpanId"], incoming_span_id)
        self.assertTrue(
            any(
                event["name"] == "exception"
                and any(
                    attribute["key"] == "exception.message"
                    and attribute["value"]["stringValue"] == "GWT error"
                    for attribute in event["attributes"]
                )
                and any(
                    attribute["key"] == "exception.message.redacted"
                    and attribute["value"]["boolValue"]
                    for attribute in event["attributes"]
                )
                for span in spans
                for event in span["events"]
            )
        )

    def test_malformed_json_exports_error_trace_and_returns_trace_headers(self):
        incoming_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
        incoming_span_id = "00f067aa0ba902b7"
        with running_otlp_sink() as otlp:
            with running_service(
                "examples/deployable_api/rules.gwt",
                trace_config=HttpTraceConfig(f"{otlp.base_url}/v1/traces"),
            ) as base_url:
                status, payload, headers = request_raw_with_headers(
                    f"{base_url}/requests/triage-ticket",
                    b"{",
                    method="POST",
                    headers={
                        "traceparent": f"00-{incoming_trace_id}-{incoming_span_id}-01",
                    },
                )

            exported = otlp.payloads

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "GWT_HTTP_INVALID_JSON")
        self.assertTrue(headers["traceparent"].startswith(f"00-{incoming_trace_id}-"))
        self.assertEqual(headers["x-gwt-trace-id"], incoming_trace_id)
        self.assertEqual(len(exported), 1)
        spans = exported[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(spans[0]["traceId"], incoming_trace_id)
        self.assertEqual(spans[0]["parentSpanId"], incoming_span_id)
        self.assertTrue(
            any(
                event["name"] == "exception"
                and any(
                    attribute["key"] == "exception.message"
                    and attribute["value"]["stringValue"] == "GWT error"
                    for attribute in event["attributes"]
                )
                and any(
                    attribute["key"] == "exception.message.redacted"
                    and attribute["value"]["boolValue"]
                    for attribute in event["attributes"]
                )
                for span in spans
                for event in span["events"]
            )
        )

    def test_bad_content_length_exports_error_trace(self):
        incoming_trace_id = "11111111111111111111111111111111"
        incoming_span_id = "2222222222222222"
        with running_otlp_sink() as otlp:
            service = GwtHttpService.from_file(
                "examples/deployable_api/rules.gwt",
                trace_config=HttpTraceConfig(f"{otlp.base_url}/v1/traces"),
            )
            with self.assertRaisesRegex(HttpServiceError, "invalid Content-Length header") as error:
                service.run_http_route(
                    "/requests/triage-ticket",
                    "not-a-number",
                    io.BytesIO(b"{}"),
                    content_type="application/json",
                    traceparent=f"00-{incoming_trace_id}-{incoming_span_id}-01",
                )
            exported = otlp.payloads

        self.assertTrue(error.exception.traceparent.startswith(f"00-{incoming_trace_id}-"))
        self.assertEqual(len(exported), 1)
        spans = exported[0]["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertEqual(spans[0]["traceId"], incoming_trace_id)
        self.assertEqual(spans[0]["parentSpanId"], incoming_span_id)
        self.assertTrue(
            any(
                event["name"] == "exception"
                and any(
                    attribute["key"] == "exception.message"
                    and attribute["value"]["stringValue"] == "GWT error"
                    for attribute in event["attributes"]
                )
                and any(
                    attribute["key"] == "exception.message.redacted"
                    and attribute["value"]["boolValue"]
                    for attribute in event["attributes"]
                )
                for span in spans
                for event in span["events"]
            )
        )

    def test_non_object_json_body_returns_400(self):
        with running_service("examples/deployable_api/rules.gwt") as base_url:
            status, payload = request_raw(
                f"{base_url}/requests/triage-ticket",
                b"[1, 2]",
                method="POST",
            )

        self.assertEqual(status, 400)
        self.assertEqual(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "GWT_HTTP_INVALID_JSON")
        self.assertEqual(payload["error"]["message"], "request body must be a JSON object")

    def test_unknown_route_returns_404(self):
        with running_service("examples/deployable_api/rules.gwt") as base_url:
            get_status, get_payload = request_json(f"{base_url}/missing")
            post_status, post_payload = request_json(
                f"{base_url}/requests/missing",
                {},
                method="POST",
            )

        self.assertEqual(get_status, 404)
        self.assertEqual(get_payload["ok"], False)
        self.assertEqual(get_payload["error"]["code"], "GWT_HTTP_ROUTE_NOT_FOUND")
        self.assertEqual(post_status, 404)
        self.assertEqual(post_payload["ok"], False)
        self.assertEqual(post_payload["error"]["code"], "GWT_HTTP_ROUTE_NOT_FOUND")

    def test_serve_command_reports_startup_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "bad.gwt"
            program.write_text("AND count is 1\n")

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(["serve", str(program), "--port", "0"])

        self.assertEqual(status, 1)
        self.assertIn("AND has no previous", stderr.getvalue())

    def test_serve_command_rejects_negative_body_limit(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            main(["serve", "examples/deployable_api/rules.gwt", "--max-body-bytes", "-1"])

        self.assertEqual(error.exception.code, 2)
        self.assertIn("expected a non-negative integer", stderr.getvalue())

    def test_serve_command_requires_capture_directory_for_capture_options(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            status = main(
                [
                    "serve",
                    "examples/deployable_api/rules.gwt",
                    "--capture-values",
                ]
            )

        self.assertEqual(status, 1)
        self.assertIn("require --capture-dir", stderr.getvalue())

    def assert_trace_headers(self, headers: dict[str, str], trace_id: str) -> None:
        self.assertTrue(headers["traceparent"].startswith(f"00-{trace_id}-"))
        self.assertEqual(headers["x-gwt-trace-id"], trace_id)


@contextmanager
def running_service(
    path: str | Path,
    *,
    trace_config: HttpTraceConfig | None = None,
    metrics_config: HttpMetricsConfig | None = None,
    capture_config: HttpExecutionCaseConfig | None = None,
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    background_exports: bool = False,
):
    service = GwtHttpService.from_file(
        path,
        trace_config=trace_config,
        metrics_config=metrics_config,
        capture_config=capture_config,
        max_request_body_bytes=max_request_body_bytes,
        background_exports=background_exports,
    )
    server = create_http_server(service, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@contextmanager
def running_serve_process(
    path: str | Path,
    *,
    otlp_endpoint: str | None = None,
    max_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    capture_dir: Path | None = None,
    capture_values: bool = False,
    capture_request: str | None = None,
    fact_provenance: Path | None = None,
):
    command = [
        sys.executable,
        "-m",
        "gwtlang",
        "serve",
        str(path),
        "--host",
        "127.0.0.1",
        "--port",
        "0",
        "--max-body-bytes",
        str(max_body_bytes),
    ]
    if otlp_endpoint is not None:
        command.extend(["--otlp-endpoint", otlp_endpoint])
    if capture_dir is not None:
        command.extend(["--capture-dir", str(capture_dir)])
    if capture_values:
        command.append("--capture-values")
    if capture_request is not None:
        command.extend(["--capture-request", capture_request])
    if fact_provenance is not None:
        command.extend(["--fact-provenance", str(fact_provenance)])

    process = subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    output = Queue()
    if process.stdout is None:
        raise AssertionError("expected gwt serve stdout pipe")
    Thread(target=_read_server_startup_line, args=(process.stdout, output), daemon=True).start()
    try:
        try:
            line = output.get(timeout=10)
        except Empty as exc:
            _stop_process(process)
            stderr = process.stderr.read() if process.stderr is not None else ""
            _close_process_pipes(process)
            raise AssertionError(f"gwt serve did not report startup URL\n{stderr}") from exc

        match = re.search(r" at (http://\S+)$", line.strip())
        if match is None:
            _stop_process(process)
            stderr = process.stderr.read() if process.stderr is not None else ""
            _close_process_pipes(process)
            raise AssertionError(f"unexpected gwt serve startup output: {line!r}\n{stderr}")
        yield match.group(1)
    finally:
        _stop_process(process)
        _close_process_pipes(process)


def _read_server_startup_line(stream: Any, output: Queue) -> None:
    output.put(stream.readline())


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _close_process_pipes(process: subprocess.Popen) -> None:
    for stream in (process.stdout, process.stderr):
        if stream is not None:
            stream.close()


class OtlpSink(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), OtlpSinkHandler)
        self.payloads: list[dict[str, Any]] = []
        self.requests: list[tuple[str, dict[str, Any]]] = []

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def payloads_for_path(self, path: str) -> list[dict[str, Any]]:
        return [payload for request_path, payload in self.requests if request_path == path]


class OtlpSinkHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        server = cast_otlp_sink(self.server)
        payload = json.loads(body.decode("utf-8"))
        server.payloads.append(payload)
        server.requests.append((self.path, payload))
        rendered = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(rendered)))
        self.end_headers()
        self.wfile.write(rendered)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def running_otlp_sink():
    server = OtlpSink()
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def cast_otlp_sink(server: object) -> OtlpSink:
    if not isinstance(server, OtlpSink):
        raise TypeError("expected OtlpSink")
    return server


def attributes_by_key(attributes: object) -> dict[str, dict[str, object]]:
    if not isinstance(attributes, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        key = attribute.get("key")
        value = attribute.get("value")
        if isinstance(key, str) and isinstance(value, dict):
            result[key] = value
    return result


def triage_ticket_request() -> dict[str, dict[str, object]]:
    return {
        "ticket": {
            "customer_id": "C-100",
            "subject": "checkout unavailable",
            "severity": "medium",
            "account_value": 5000,
            "has_outage": True,
        }
    }


def route_for_request(openapi: object, request_name: str) -> str:
    if not isinstance(openapi, dict):
        raise AssertionError("expected OpenAPI object")
    paths = openapi.get("paths")
    if not isinstance(paths, dict):
        raise AssertionError("expected OpenAPI paths object")
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        post = path_item.get("post")
        if isinstance(post, dict) and post.get("x-gwt-request-name") == request_name:
            return path
    raise AssertionError(f"missing OpenAPI route for request: {request_name}")


def request_json(url: str, payload: object | None = None, *, method: str = "GET") -> tuple[int, object]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    return request_raw(url, data, method=method)


def request_json_with_headers(
    url: str,
    payload: object | None = None,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
) -> tuple[int, object, dict[str, str]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    return request_raw_with_headers(url, data, method=method, headers=headers)


def request_raw(
    url: str,
    data: bytes | None,
    *,
    method: str,
    headers: dict[str, str] | None = None,
) -> tuple[int, object]:
    status, payload, _headers = request_raw_with_headers(url, data, method=method, headers=headers)
    return status, payload


def request_raw_with_headers(
    url: str,
    data: bytes | None,
    *,
    method: str,
    headers: dict[str, str] | None = None,
) -> tuple[int, object, dict[str, str]]:
    request_headers = {"Content-Type": "application/json"} if data is not None else {}
    request_headers.update(headers or {})
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return (
                response.status,
                json.loads(response.read().decode("utf-8")),
                dict(response.headers.items()),
            )
    except HTTPError as exc:
        try:
            return (
                exc.code,
                json.loads(exc.read().decode("utf-8")),
                dict(exc.headers.items()),
            )
        finally:
            exc.close()


if __name__ == "__main__":
    unittest.main()
