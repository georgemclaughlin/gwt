from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from gwtlang import (
    OtlpHttpExporter,
    OtlpSpan,
    SPAN_KIND_CLIENT,
    make_traceparent,
    new_span_id,
    new_trace_id,
    now_unix_nano,
    otlp_trace_endpoint,
)


SUCCESS_BODY = {
    "ticket": {
        "customer_id": "C-100",
        "subject": "checkout unavailable",
        "severity": "medium",
        "account_value": 5000,
        "has_outage": True,
    }
}

INVALID_BODY = {
    "ticket": {
        "customer_id": "C-404",
    }
}


def main() -> int:
    base_url = os.environ.get("GWT_DEMO_BASE_URL", "http://127.0.0.1:8080")
    otlp_base = os.environ.get("GWT_DEMO_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    endpoint = otlp_trace_endpoint(otlp_base)
    url = f"{base_url.rstrip('/')}/requests/triage-ticket"
    cases = [
        ("outage escalates", SUCCESS_BODY, True),
        ("invalid request contract", INVALID_BODY, False),
    ]
    results = [
        run_case(label, body, expect_success, url=url, endpoint=endpoint)
        for label, body, expect_success in cases
    ]
    return 0 if all(results) else 1


def run_case(
    label: str,
    request_body: dict[str, object],
    expect_success: bool,
    *,
    url: str,
    endpoint: str,
) -> bool:
    trace_id = new_trace_id()
    client_span_id = new_span_id()
    traceparent = make_traceparent(trace_id, client_span_id)

    start = now_unix_nano()
    status = 0
    response_payload: object
    error: str | None = None
    try:
        request = Request(
            url,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "traceparent": traceparent,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            status = response.status
            response_payload = json.loads(response.read().decode("utf-8"))
            response_traceparent = response.headers.get("traceparent")
    except HTTPError as exc:
        status = exc.code
        response_payload = json.loads(exc.read().decode("utf-8"))
        response_traceparent = exc.headers.get("traceparent")
        error = f"HTTP {status}"
    except URLError as exc:
        print(f"demo client could not reach {url}: {exc}", file=sys.stderr)
        return 1
    end = now_unix_nano()

    parsed = urlparse(url)
    span = OtlpSpan(
        trace_id=trace_id,
        span_id=client_span_id,
        parent_span_id=None,
        name="demo client POST /requests/triage-ticket",
        kind=SPAN_KIND_CLIENT,
        start_time_unix_nano=start,
        end_time_unix_nano=end,
        attributes={
            "service.name": "gwt-demo-client",
            "gwt.demo.case": label,
            "server.address": parsed.hostname or "127.0.0.1",
            "url.path": parsed.path,
            "http.request.method": "POST",
            "http.response.status_code": status,
        },
    )
    span.finish(error=error)
    try:
        OtlpHttpExporter(endpoint).export([span])
    except Exception as exc:
        print(f"demo client could not export client span to {endpoint}: {exc}", file=sys.stderr)

    print(f"\ncase: {label}")
    print(json.dumps(response_payload, indent=2, sort_keys=True))
    print(f"trace_id: {trace_id}")
    if response_traceparent is not None:
        print(f"server_traceparent: {response_traceparent}")
    success = 200 <= status < 300
    return success if expect_success else not success


if __name__ == "__main__":
    raise SystemExit(main())
