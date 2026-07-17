# Deployable API Example

This example shows how a named GWT `REQUEST` can be projected into an OpenAPI
contract and served as a typed HTTP endpoint.

The rules file defines one public request:

```gwt
REQUEST triage ticket
  GIVEN ticket is TicketRequest
  WHEN triage ticket into decision
  OUTPUT decision is TicketDecision
```

Run the executable scenario:

```sh
python -m gwtlang test examples/deployable_api/rules.gwt
```

Generate OpenAPI:

```sh
python -m gwtlang openapi examples/deployable_api/rules.gwt --json
```

Generate standalone JSON Schema:

```sh
python -m gwtlang schema examples/deployable_api/rules.gwt --json
```

Or write the document to a file for Swagger UI, Redoc, Postman, OpenAPI
Generator, or contract-test tooling:

```sh
python -m gwtlang openapi examples/deployable_api/rules.gwt \
  --output /tmp/gwt-openapi.json
python -m json.tool /tmp/gwt-openapi.json >/dev/null
```

Serve the same request boundary over HTTP:

```sh
python -m gwtlang serve examples/deployable_api/rules.gwt \
  --engine asgi \
  --port 8080 \
  --execution-budget 100000 \
  --max-call-depth 100
```

Install the optional transport first with
`python -m pip install -e '.[serve]'`. The dependency-free built-in engine is
fine for local work; this deployable example uses the ASGI engine. The shown
runtime values are bounded defaults. `GET /ready` also reports the active body,
execution-work, call-depth, and concurrency limits, current admission/in-flight
state, and complete program-closure digest.

Then call it with ordinary JSON:

```sh
curl -i -X POST http://127.0.0.1:8080/requests/triage-ticket \
  -H 'Content-Type: application/json' \
  -d '{
    "ticket": {
      "customer_id": "C-100",
      "subject": "checkout unavailable",
      "severity": "medium",
      "account_value": 5000,
      "has_outage": true
    }
  }'
```

The generated API surface is:

```text
POST /requests/triage-ticket
  request body:  TriageTicketRequest
  response body: TriageTicketOutput
  GWT request:   triage ticket
```

The OpenAPI response body is the declared `OUTPUT` object. It is intentionally
not the `gwt run --json` execution envelope, which remains the CLI/debug payload
with final state and print output.

## Self-Hosted Docker Demo

The example includes a self-hosted Docker Compose path that runs `gwt serve`,
an OpenTelemetry Collector, Jaeger, and Prometheus together. From the
repository root:

```sh
docker compose -f examples/deployable_api/docker-compose.yml up --build
```

The service listens on <http://127.0.0.1:8080>. Check the operational and
contract surfaces:

```sh
curl http://127.0.0.1:8080/live
curl http://127.0.0.1:8080/ready
curl http://127.0.0.1:8080/openapi.json
python -m gwtlang schema examples/deployable_api/rules.gwt --json \
  >/tmp/gwt-deployable-api.schema.json
```

Then call the deployed GWT request:

```sh
curl -X POST http://127.0.0.1:8080/requests/triage-ticket \
  -H 'Content-Type: application/json' \
  -d '{
    "ticket": {
      "customer_id": "C-100",
      "subject": "checkout unavailable",
      "severity": "medium",
      "account_value": 5000,
      "has_outage": true
    }
  }'
```

The Compose service sets `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`,
so `gwt serve` exports request traces and request metrics over OTLP/HTTP. The
OpenTelemetry Collector sends traces to Jaeger and exposes metrics to
Prometheus. Published demo ports are bound to `127.0.0.1` by default, and
served traces redact values by default. `gwt serve` queues those OTLP exports
in a bounded background queue, reports queue/drop state through readiness, and
uses a bounded flush on graceful shutdown.

Open Jaeger at <http://127.0.0.1:16686> and select `gwt-serve` to inspect the
trace. Open Prometheus at <http://127.0.0.1:9090> and query metrics such as:

```text
gwt_request_count_total
gwt_request_duration_ms_count
gwt_request_failure_count_total
gwt_contract_failure_count_total
```

The response headers include `x-gwt-trace-id` when trace export is enabled.
Use that trace ID with the playback helper if you want a linear GWT event list:

```sh
python examples/deployable_api/otel_trace_playback.py <trace_id>
```

If a local port is already in use, override the published ports while keeping
the in-container service wiring unchanged:

```sh
GWT_HTTP_PORT=18080 PROMETHEUS_PORT=19090 JAEGER_UI_PORT=16687 \
  docker compose -f examples/deployable_api/docker-compose.yml up --build
```

For local diagnostics that need full request, state, and output values in
Jaeger, opt in explicitly:

```sh
GWT_SERVE_ARGS=--trace-values \
  docker compose -f examples/deployable_api/docker-compose.yml up --build
```

## OpenAPI Generator Client Demo

The generated OpenAPI contract can drive standard client generators. This demo
does not commit generated code; it writes OpenAPI and the generated TypeScript
fetch client to a temporary directory, starts `gwt serve`, and calls the
generated `DefaultApi.triageTicket(...)` method:

```sh
node examples/deployable_api/openapi_generator_client_demo.mjs
```

It requires Node 20 or newer, npm, and the Java runtime used by OpenAPI
Generator CLI.

The generated TypeScript client provides `TriageTicketRequest` and
`TriageTicketOutput` types from the OpenAPI schemas. Set
`GWT_KEEP_OPENAPI_DEMO=1` to keep the generated files for inspection.

The demo uses:

```sh
npx --yes @openapitools/openapi-generator-cli@2.38.0 generate \
  -i /tmp/gwt-openapi.json \
  -g typescript-fetch \
  -o /tmp/gwt-openapi-client
```

See [`../../docs/http-service-design.md`](../../docs/http-service-design.md)
for the HTTP service direction.

## JSON Schema Validated Client Demo

The standalone JSON Schema contract can validate request and response bodies for
non-OpenAPI clients. With `gwt serve` or the Docker Compose stack running:

```sh
python -m pip install jsonschema
python examples/deployable_api/json_schema_client_demo.py
```

The demo generates JSON Schema from `rules.gwt`, validates the request body,
calls `POST /requests/triage-ticket`, validates the response body, and prints
the declared `OUTPUT` object. It uses the optional `jsonschema` Python package.

## OpenTelemetry Client Trace Demo

With the main Docker Compose stack running, the demo client can add a client
span and send both successful and intentionally invalid requests through the
served GWT API:

Then run the demo client:

```sh
python examples/deployable_api/otel_client_demo.py
```

The client prints a `trace_id` for each case. To read a trace as a linear GWT
audit story, pass one of those IDs to the playback helper:

```sh
python examples/deployable_api/otel_trace_playback.py <trace_id>
```

Open Jaeger at <http://127.0.0.1:16686>, select `gwt-demo-client` or
`gwt-serve`, and run a search. The trace should show the client request, the
served GWT request, the `WHEN triage <ticket> into <decision>` behavior,
executed statements, contract checks, branch conditions, checked assertions,
redacted state changes, and a `gwt.request.completed` event with the declared
output fields.
The playback helper sorts GWT events by `gwt.event.sequence` so you can scan
the execution without manually merging Jaeger span event tables. The client
sends one successful outage case and one intentionally invalid request, so the
viewer also shows a rejected request contract trace.

Only use `GWT_SERVE_ARGS=--trace-values` for local diagnostic runs or
environments with appropriate log-style redaction and retention controls.
