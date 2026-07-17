# HTTP Service And OpenAPI

Status: active serve-first integration hardening. OpenAPI generation, the
transport-neutral HTTP application, the built-in adapter, and the optional
ASGI adapter are implemented; the service remains experimental while the
operator and deployment contract is hardened.

GWT named `REQUEST` blocks already define a public request/response boundary.
The implemented HTTP surface projects that boundary into standard API
contracts and a narrow local service without adding deployment policy to the
language:

```text
.gwt REQUEST contracts -> gwt serve -> ordinary HTTP/OpenAPI clients
```

This keeps the language surface stable while making GWT easier to consume from
ordinary application hosts.

## Serve-First Integration Decision

`gwt serve` is the preferred cross-language application boundary. GWT should
execute its own semantics once behind named `REQUEST` contracts; host
applications should use their normal HTTP libraries and, when useful, standard
OpenAPI generators. Bespoke .NET, Java, Go, Ruby, or TypeScript runtimes are not
the current expansion path.

This does not make HTTP part of the language. `REQUEST`, `GIVEN`, `WHEN`,
`OUTPUT`, and `THEN` remain the normative behavior boundary. The server is a
standard projection, just as JSON Schema and OpenAPI are projections.

The hardening order is:

1. stable request, response, and error contracts;
2. explicit body, execution-work, and behavior-call limits;
3. predictable lifecycle, health, shutdown, and concurrency behavior;
4. operational tracing, metrics, and opt-in review evidence;
5. repeatable deployment behind host-owned TLS, auth, and rate limits.

The current implementation covers the first four items through one
transport-neutral HTTP application. The dependency-free built-in adapter is a
development/reference server; the optional ASGI adapter supplies a
production-oriented transport without duplicating GWT request semantics.
Neither transport claims to replace host-owned TLS, authentication,
authorization, or edge rate limiting.

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

For the optional ASGI transport:

```sh
python -m pip install 'gwtlang[serve]'
python -m gwtlang serve examples/deployable_api/rules.gwt \
  --engine asgi \
  --host 127.0.0.1 \
  --port 8080
```

Both transports adapt into the same `GwtHttpApplication`. Route dispatch,
JSON errors, body limits, admission, lifecycle state, response headers, and
program identity therefore have one implementation. The ASGI adapter executes
the synchronous evaluator outside the event-loop thread and implements ASGI
lifespan startup and shutdown. The built-in adapter uses HTTP/1.1 and a
configurable socket timeout, but remains deliberately dependency-free rather
than being presented as an internet-facing production server.

The supported protocol surface and its message/server test matrix are recorded
in [ASGI Application Contract](asgi-contract.md). GWT claims ASGI 3.0 HTTP
major version 2 and lifespan 2.0; it does not claim WebSocket support.

Startup behavior:

- parse, import, and check the `.gwt` program once
- fail startup if parser/checker diagnostics include errors
- keep the compiled program in memory
- generate OpenAPI for the same source and import policy
- expose only named `REQUEST` blocks, not helper `WHEN` behaviors

Routes:

```text
GET  /health
GET  /live
GET  /ready
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
- execution work and nested behavior calls are bounded by default; use
  `--execution-budget N|none` and `--max-call-depth N|none` to set the served
  runtime policy explicitly (disabling limits is not recommended for a service)
- `GET /live` remains `200` while the process can answer HTTP
- `GET /ready` returns `200` while new evaluations are accepted and `503`
  while draining; `GET /health` is a compatibility alias for readiness
- readiness reports body, execution, call-depth, and concurrent-evaluation
  limits plus admission state and the current in-flight count
- `--max-concurrent-requests` bounds executing GWT requests; excess work gets
  a JSON `503 GWT_HTTP_UNAVAILABLE` response with `Retry-After`
- SIGTERM/interrupt stops admission, waits up to `--shutdown-grace-seconds`
  for admitted requests, then closes service resources
- the built-in adapter applies `--request-timeout` to accepted sockets
- request slugs are derived from the generated OpenAPI paths, including
  collision suffixes such as `/requests/review-vendor-2`
- the service invokes the exact named `REQUEST` stored in `x-gwt-request-name`
- request bodies are strict against the declared `REQUEST` input paths, so
  undeclared JSON fields are rejected with `400` before execution
- `REQUEST` input contracts validate before execution
- request-local `GIVEN` setup and `WHEN` calls run normally
- `OUTPUT` contracts validate after execution
- the HTTP `200` response body is the declared `OUTPUT` object

## Operator Identity And Version Surface

The service snapshot already computes a portable SHA-256 identity over the
entry file and its complete `USE` closure. Serving exposes that existing
identity rather than hashing only the entry file:

- every JSON response includes `x-gwt-program-digest`
- readiness, liveness, and request discovery include `programDigest` and
  `programIdentityAlgorithm`
- readiness also includes package and language-spec versions
- served `/openapi.json` includes the digest and algorithm under `x-gwt`
- generated operations document the digest response header and the overload
  `503` response

This lets a deployment probe, host client, trace, and captured Execution Case
refer to the same concrete program closure. It is visibility, not hot reload:
changing source on disk does not change a running process because compilation
and snapshot loading happen once at startup.

## Transport And Capacity Boundary

`--engine builtin` is the default so `gwt serve` remains dependency-free and
easy to use locally. `--engine asgi` uses the optional Uvicorn dependency for a
mature HTTP connection and ASGI lifespan boundary. The GWT application-level
concurrency limit is shared by both transports and bounds evaluator work, not
all possible upstream connections or process memory.

For CPU capacity beyond one Python process, run multiple service processes
behind an ordinary supervisor or orchestrator and size them with workload
benchmarks. Keep TLS, authentication, authorization, coarse connection limits,
and external rate limiting in the gateway/deployment layer.

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
Served OTLP trace and metric exports use a bounded 1,024-item background queue
and are flushed with a bounded wait on graceful shutdown, so collector latency
does not sit on the HTTP response path or permit unbounded queue growth. When
the queue is full the service drops new export work, emits one warning, and
reports queue capacity, current depth, and the cumulative drop count through
the readiness payload.

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
- unsupported methods on known routes should return JSON `405` with `Allow`
- undeclared request body fields should return `400`
- missing or invalid `REQUEST` input should return `400`
- failed request `THEN` assertions or missing `OUTPUT` values should return
  `500` unless a later design proves a better contract-specific status shape
- returned error bodies use the `GwtErrorResponse` OpenAPI schema and include
  the GWT diagnostic message when available, but do not expose unrelated host
  stack traces by default
- unexpected host/runtime exceptions are logged server-side and become a
  sanitized `500` response with code `GWT_HTTP_UNEXPECTED_ERROR`
- JSON responses use `no-store` caching and `nosniff` content-type headers
- overload or draining should return JSON `503` with `Retry-After`

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
