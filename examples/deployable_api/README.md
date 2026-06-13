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

Or write the document to a file for Swagger UI, Redoc, Postman, OpenAPI
Generator, or contract-test tooling:

```sh
python -m gwtlang openapi examples/deployable_api/rules.gwt \
  --output /tmp/gwt-openapi.json
python -m json.tool /tmp/gwt-openapi.json >/dev/null
```

Serve the same request boundary over HTTP:

```sh
python -m gwtlang serve examples/deployable_api/rules.gwt --port 8080
```

Then call it with ordinary JSON:

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

## OpenTelemetry Trace Demo

The experimental HTTP service can export request execution traces over
OTLP/HTTP. The demo stack uses Jaeger v2 all-in-one as the local OTLP ingester
and trace viewer.

Start the observability stack:

```sh
docker compose -f examples/deployable_api/observability/docker-compose.yml up
```

In another terminal, start the GWT service with OTLP export enabled:

```sh
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
  python -m gwtlang serve examples/deployable_api/rules.gwt --port 8080
```

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
state changes, and a `gwt.request.completed` event with the declared output.
The playback helper prints the same GWT events sorted by `gwt.event.sequence`
so you can scan the execution without manually merging Jaeger span event
tables. The client sends one successful outage case and one intentionally
invalid request, so the viewer also shows a rejected request contract trace.

The trace can include request and state values. Treat it as diagnostic/audit
data and route it through the same redaction and retention controls as
application logs before using it outside local development.
