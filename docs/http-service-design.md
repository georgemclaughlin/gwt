# HTTP Service And OpenAPI

Status: OpenAPI generation and an experimental standard-library HTTP service
are implemented. Deployment policy and deeper service customization remain
deferred.

GWT named `REQUEST` blocks already define a public request/response boundary.
The implemented HTTP surface projects that boundary into standard API
contracts and a narrow local service without adding deployment policy to the
language:

```text
.gwt REQUEST contracts -> OpenAPI document -> generated host clients
```

This keeps the language surface stable while making GWT easier to consume from
ordinary application hosts.

## Implemented First Slice: OpenAPI

`gwt openapi` generates an OpenAPI 3.1 document from the current program:

```sh
python -m gwtlang openapi examples/deployable_api/rules.gwt --json
```

The generator uses existing language concepts:

- each named `REQUEST` becomes a `POST` operation
- caller-provided `GIVEN path is Type` bindings become the JSON request body
- declared `OUTPUT path is Type` bindings become the JSON response body
- `RECORD`, one-of records, `TYPE` aliases, literal unions, and typed lists
  become component schemas
- each operation includes `x-gwt-request-name` so tooling can recover the exact
  GWT request name

The generated endpoint response shape is the declared `OUTPUT` object. This is
intentionally different from the CLI execution envelope returned by
`gwt run --json`: the CLI envelope remains the stable runner/debug payload,
while OpenAPI describes the clean host-facing API shape.

## Interop Smoke Path

The OpenAPI slice remains useful on its own because many host tools can consume
the generated document directly.

Generate the contract:

```sh
python -m gwtlang openapi examples/deployable_api/rules.gwt \
  --output /tmp/gwt-openapi.json
```

Check that it is ordinary JSON:

```sh
python -m json.tool /tmp/gwt-openapi.json >/dev/null
```

Then load `/tmp/gwt-openapi.json` into an OpenAPI 3.1-aware tool:

- Swagger UI or Swagger Editor for interactive API documentation
- Redoc for rendered API reference pages
- Postman or Insomnia for request collections
- OpenAPI Generator for host-language clients and DTOs
- API gateway or contract-test tooling that accepts OpenAPI schemas

For `examples/deployable_api/rules.gwt`, the important generated surface is:

```text
POST /requests/triage-ticket
  request body:  TriageTicketRequest
  response body: TriageTicketOutput
  GWT request:   triage ticket
```

The request body schema contains the caller-provided `ticket` input. The
response body schema contains only the declared `decision` output. Runtime
debug information such as final full state and print output remains part of the
CLI execution envelope, not the OpenAPI endpoint response.

## Implemented Experimental HTTP Service

`gwt serve` uses the same OpenAPI generator and compiled program API:

```sh
python -m gwtlang serve examples/deployable_api/rules.gwt \
  --host 127.0.0.1 \
  --port 8080
```

Startup behavior:

- parse, import, and check the `.gwt` program once
- fail startup if parser/checker diagnostics include errors
- keep the compiled program in memory
- generate OpenAPI for the same source and import policy
- expose only named `REQUEST` blocks, not helper `WHEN` behaviors

Routes:

```text
GET  /health
GET  /openapi.json
GET  /requests
POST /requests/<request-slug>
```

Request execution:

- HTTP JSON body is the caller-provided GWT state for that named request
- `POST /requests/<request-slug>` requires `Content-Type: application/json`
  and rejects other media types with `415`
- request bodies are limited to 1 MiB by default and larger bodies are
  rejected with `413`; pass `--max-body-bytes` to change the local service
  limit
- request slugs are derived from the generated OpenAPI paths, including
  collision suffixes such as `/requests/review-vendor-2`
- the service invokes the exact named `REQUEST` stored in `x-gwt-request-name`
- request bodies are strict against the declared `REQUEST` input paths, so
  undeclared JSON fields are rejected with `400` before execution
- `REQUEST` input contracts validate before execution
- request-local `GIVEN` setup and `WHEN` calls run normally
- `OUTPUT` contracts validate after execution
- the HTTP `200` response body is the declared `OUTPUT` object

The service response should not be the CLI execution envelope by default. The
CLI envelope is useful for local runners, scenario state, print output, and
debugging. The service should start with the API contract that host clients
expect from OpenAPI: request body in, declared response body out.

## Opt-In Execution Case Evidence

`gwt serve` can persist the exact evaluator trace behind a served decision as a
versioned Execution Case:

```sh
python -m gwtlang serve examples/deployable_api/rules.gwt \
  --port 8080 \
  --capture-dir /tmp/gwt-cases
```

The service runs the named request once, then reuses that completed trace to
build the same artifact format as `gwt capture`. Successful writes add
`x-gwt-case-id` to the HTTP response; the ID is both the artifact integrity
digest and the content-addressed filename. OpenAPI advertises this optional
header on success and error responses. Capture also creates trace correlation
headers even when OTLP export is disabled.

The default is `values: "omit"` with failed GWT executions recorded. This is a
reviewable execution shape, not replay evidence. `--capture-values` preserves
the request, declared output, operands, state changes, and error detail so the
case can drive `gwt compare`, scenario generation, and the workbench. It should
therefore be enabled only where those values may be stored. Repeated
`--capture-request` flags constrain recording to named request contracts.

`--fact-provenance` is static server-side configuration validated at startup;
it is not accepted from callers and cannot influence the decision. A sidecar
used for more than one selected request must contain only paths valid for each
of those contracts. Shape-only capture omits provenance descriptions while
recording that the field was redacted.

Transport failures occur before evaluator execution and are not cases. Runtime
and contract failures are cases. Artifact write errors remain out-of-band: the
server logs them, omits `x-gwt-case-id`, and preserves the original decision or
error response.

## Experimental OpenTelemetry Export

`gwt serve` can export request execution traces and metrics over OTLP/HTTP
without changing the HTTP response body:

```sh
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 \
  python -m gwtlang serve examples/deployable_api/rules.gwt --port 8080
```

The `--otlp-endpoint` flag can also set the base OTLP endpoint explicitly.
When a request includes a W3C `traceparent` header, GWT uses that trace ID and
parent span. Responses include `traceparent` and `x-gwt-trace-id` headers when
trace export is enabled. Served traces redact state, output, and print values by
default; pass `--trace-values` for local diagnostic runs that need full values.
Use `--otlp-metrics-endpoint` to send metrics to a separate collector endpoint;
otherwise `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` or the standard
`OTEL_EXPORTER_OTLP_ENDPOINT` base endpoint is used when present.
Served OTLP trace and metric exports are queued in a background worker and
flushed with a bounded wait on graceful shutdown, so collector latency does not
sit on the HTTP response path.

The exported trace is a diagnostic projection of GWT execution:

- root span: served HTTP request route
- child span: named GWT `REQUEST`
- child spans: matched `WHEN` behavior calls
- span events: executed statements, contract checks, evaluated conditions,
  checked assertions, `print` output, request completion summaries, runtime
  errors, and state-change paths

Every GWT span event includes `gwt.event.sequence` and `gwt.event.summary` so
generic trace tools can render a stable audit timeline without knowing every
GWT-specific event type. Redacted state-change events include the state path,
JSON pointer, and operation, but not old values, new values, or full patch
payloads. Redacted request completion events include output field paths but not
the declared output snapshot or scalar values. With `--trace-values`, state
changes also include JSON Patch-shaped payloads plus parsed `gwt.state.old`,
`gwt.state.new`, and scalar output fields such as `gwt.output.decision.status`.
This remains out-of-band: OpenAPI clients still receive only the declared
`OUTPUT` object.

Source locations and GWT source text remain visible in redacted traces so tools
can point back to the executable spec. Do not put secrets directly in `.gwt`
source if traces are exported to shared systems.

For known `POST /requests/<request-slug>` routes, unsupported content types,
oversized bodies, body parsing failures, and strict request-body rejections are
traced on the route span and return `traceparent` plus `x-gwt-trace-id`
response headers when trace export is enabled.

The emitted request metrics are:

- `gwt.request.count`
- `gwt.request.duration_ms`
- `gwt.request.failure.count`
- `gwt.contract.failure.count`
- `gwt.assertion.failure.count`

Metric attributes include the request name, HTTP route, method, response
status code, and error code when one is available. Metrics do not include GWT
state, request input, output values, source text, or error messages.

The deployable API example includes a small playback helper that reads a Jaeger
trace by ID and prints GWT events sorted by `gwt.event.sequence`:

```sh
python examples/deployable_api/otel_trace_playback.py <trace_id>
```

Jaeger remains the trace UI for now. A future GWT-specific debugger should be a
domain UI over source, state diffs, contract checks, and request/response data,
not a thin duplicate of Jaeger.

## Generated Client Smoke Path

Standard OpenAPI tooling should be the first typed HTTP client path. The
deployable API example includes a generated-client smoke script:

```sh
node examples/deployable_api/openapi_generator_client_demo.mjs
```

The script generates OpenAPI from `rules.gwt`, runs OpenAPI Generator's
`typescript-fetch` generator into a temporary directory, starts `gwt serve`, and
calls the generated `DefaultApi.triageTicket(...)` method. This proves the
service can be consumed without a custom GWT HTTP client wrapper.

Error posture:

- startup parse/check failures should fail the process with source-located
  diagnostics
- malformed JSON should return `400`
- undeclared request body fields should return `400`
- missing or invalid `REQUEST` input should return `400`
- failed request `THEN` assertions or missing `OUTPUT` values should return
  `500` unless a later design proves a better contract-specific status shape
- returned error bodies use the `GwtErrorResponse` OpenAPI schema and include
  the GWT diagnostic message when available, but do not expose unrelated host
  stack traces by default

Deferred service options:

- custom routes such as `POST /triage`
- custom operation IDs
- CORS configuration
- structured logging
- debug envelope mode
- persistent audit storage and redaction policy
- reload/watch mode for local development

Explicit non-goals for the first service slice:

- no auth, OAuth, scopes, or token validation
- no sidecar deployment config
- no custom route syntax in `.gwt`
- no persistence, host callbacks, or network side effects inside GWT behavior
- no generated host code that reimplements GWT rules

## Deferred: Auth And Deployment Policy

Authentication, authorization, routing policy, CORS, rate limits, TLS, logging,
and provider-specific OAuth/JWKS behavior belong at the HTTP/deployment
boundary until concrete examples prove which parts should become GWT source
syntax.

For now, do not add `AUTH`, scope declarations, or sidecar auth config as part
of the OpenAPI slice. The immediate interoperability value is the generated API
contract.
