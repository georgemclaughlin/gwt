from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
import sys
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from gwtlang import generate_json_schema_file


RULES_FILE = "examples/deployable_api/rules.gwt"
REQUEST_NAME = "triage ticket"

REQUEST_BODY = {
    "ticket": {
        "customer_id": "C-100",
        "subject": "checkout unavailable",
        "severity": "medium",
        "account_value": 5000,
        "has_outage": True,
    }
}


class _JsonSchemaValidator(Protocol):
    def validate(self, instance: object) -> None:
        ...


class _JsonSchemaValidatorFactory(Protocol):
    def __call__(self, schema: Mapping[str, Any]) -> _JsonSchemaValidator:
        ...


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Call the deployable API with JSON Schema request/response validation.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("GWT_DEMO_BASE_URL", "http://127.0.0.1:8080"),
        help="GWT service base URL. Defaults to GWT_DEMO_BASE_URL or http://127.0.0.1:8080.",
    )
    args = parser.parse_args()

    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        print(
            "json_schema_client_demo.py requires the optional 'jsonschema' package",
            file=sys.stderr,
        )
        return 1

    validator = cast(_JsonSchemaValidatorFactory, Draft202012Validator)
    base_url = str(args.base_url)
    schema = generate_json_schema_file(RULES_FILE).as_payload()
    request_schema = _request_schema(schema, "input")
    output_schema = _request_schema(schema, "output")

    validator(request_schema).validate(REQUEST_BODY)
    try:
        response_payload = _post_json(
            f"{base_url.rstrip('/')}/requests/triage-ticket",
            REQUEST_BODY,
        )
    except DemoClientError as exc:
        print(f"JSON Schema client demo failed: {exc}", file=sys.stderr)
        return 1

    validator(output_schema).validate(response_payload)
    print(json.dumps(response_payload, indent=2, sort_keys=True))
    return 0


def _request_schema(document: dict[str, Any], side: str) -> dict[str, Any]:
    x_gwt = document.get("x-gwt")
    if not isinstance(x_gwt, dict):
        raise DemoClientError("generated schema does not include x-gwt")
    requests = cast(dict[str, object], x_gwt).get("requests")
    if not isinstance(requests, dict):
        raise DemoClientError("generated schema does not include x-gwt.requests")
    request = cast(dict[str, object], requests).get(REQUEST_NAME)
    if not isinstance(request, dict):
        raise DemoClientError(f"generated schema does not include request: {REQUEST_NAME}")
    side_schema = cast(dict[str, object], request).get(side)
    if not isinstance(side_schema, dict):
        raise DemoClientError(f"generated schema does not include {side} schema")
    ref = cast(dict[str, object], side_schema).get("$ref")
    if not isinstance(ref, str):
        raise DemoClientError(f"generated schema does not include {side} ref")
    return {
        "$schema": document["$schema"],
        "$ref": ref,
        "$defs": document["$defs"],
    }


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            body = exc.read().decode("utf-8")
        finally:
            exc.close()
        raise DemoClientError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise DemoClientError(f"could not reach {url}: {exc.reason}") from exc
    if not isinstance(decoded, dict):
        raise DemoClientError("response was not a JSON object")
    return cast(dict[str, Any], decoded)


class DemoClientError(Exception):
    pass


if __name__ == "__main__":
    raise SystemExit(main())
