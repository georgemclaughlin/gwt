from contextlib import contextmanager, redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
from threading import Thread
from typing import Any
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from gwtlang.__main__ import main
from gwtlang.http_server import GwtHttpService, HttpTraceConfig, create_http_server


class HttpServerTests(unittest.TestCase):
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


@contextmanager
def running_service(path: str | Path, *, trace_config: HttpTraceConfig | None = None):
    service = GwtHttpService.from_file(path, trace_config=trace_config)
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


class OtlpSink(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), OtlpSinkHandler)
        self.payloads: list[dict[str, Any]] = []

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"


class OtlpSinkHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        server = cast_otlp_sink(self.server)
        server.payloads.append(json.loads(body.decode("utf-8")))
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


def request_raw(url: str, data: bytes | None, *, method: str) -> tuple[int, object]:
    status, payload, _headers = request_raw_with_headers(url, data, method=method)
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
