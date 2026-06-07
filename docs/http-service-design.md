# HTTP Service And OpenAPI

Status: proposed direction, with OpenAPI generation as the first implemented
slice.

GWT named `REQUEST` blocks already define a public request/response boundary.
The HTTP service direction is to project that boundary into standard API
contracts before adding deployment behavior:

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

The OpenAPI slice is useful before `gwt serve` exists because many host tools
can consume the generated document directly.

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

## Future HTTP Runner

A later `gwt serve` command can use the same OpenAPI generator and compiled
program API:

```text
POST /requests/review-vendor
  JSON body -> REQUEST review vendor -> declared OUTPUT JSON
```

The server layer should compile and check the GWT program once at startup, then
run named requests against fresh runtime state for each HTTP call. It should not
reimplement durable domain rules in host code.

## Proposed Experimental Service

The first service slice should be explicitly experimental and should live behind
optional dependencies so the base `gwtlang` package remains a small runtime and
tooling package:

```toml
[project.optional-dependencies]
server = ["fastapi", "uvicorn"]
```

Proposed command:

```sh
python -m gwtlang serve rules.gwt \
  --host 127.0.0.1 \
  --port 8080
```

Startup behavior:

- parse, import, and check the `.gwt` program once
- fail startup if parser/checker diagnostics include errors
- keep the compiled program in memory
- generate OpenAPI from the same compiled program model
- expose only named `REQUEST` blocks, not helper `WHEN` behaviors

Initial routes:

```text
GET  /health
GET  /openapi.json
GET  /docs
POST /requests/<request-slug>
```

Request execution:

- HTTP JSON body is the caller-provided GWT state for that named request
- the service invokes the exact named `REQUEST` stored in
  `x-gwt-request-name`
- `REQUEST` input contracts validate before execution
- request-local `GIVEN` setup and `WHEN` calls run normally
- `OUTPUT` contracts validate after execution
- the HTTP `200` response body is the declared `OUTPUT` object

The service response should not be the CLI execution envelope by default. The
CLI envelope is useful for local runners, scenario state, print output, and
debugging. The service should start with the API contract that host clients
expect from OpenAPI: request body in, declared response body out.

Error posture:

- startup parse/check failures should fail the process with source-located
  diagnostics
- malformed JSON should return `400`
- missing or invalid `REQUEST` input should return `400`
- failed request `THEN` assertions or missing `OUTPUT` values should return
  `500` unless a later design proves a better contract-specific status shape
- returned error bodies should include GWT source locations when available, but
  should not expose unrelated host stack traces by default

Deferred service options:

- custom routes such as `POST /triage`
- custom operation IDs
- CORS configuration
- structured logging
- debug envelope mode
- reload/watch mode for local development
- Docker examples

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
