# ASGI Application Contract

GWT's optional ASGI adapter has an explicit, deliberately narrow protocol
contract:

- ASGI application interface version `3.0`
- ASGI HTTP sub-specification major version `2`
- ASGI lifespan sub-specification version `2.0`
- HTTP request/response and lifespan scopes only
- no WebSocket support

The normative references are the
[ASGI 3 specification](https://asgi.readthedocs.io/en/latest/specs/main.html),
[HTTP and WebSocket message specification](https://asgi.readthedocs.io/en/latest/specs/www.html),
and [lifespan specification](https://asgi.readthedocs.io/en/latest/specs/lifespan.html).

## What CI Proves

The repository checks the adapter at three layers:

1. Message-level tests supply complete ASGI scopes and events directly. They
   cover split request bodies, omitted optional request-event fields,
   disconnects, oversized multi-chunk bodies, response event ordering,
   lowercase byte response headers, invalid scope/event rejection, lifespan
   order, cleanup failure, and unsupported scopes.
2. A Uvicorn subprocess serves readiness and a real named GWT request through
   `gwt serve --engine asgi`.
3. A Hypercorn subprocess serves the same application fixture and request
   contract, catching assumptions specific to the bundled Uvicorn runner.

CI installs both the `serve` extra and Hypercorn, so these interoperability
tests do not silently skip in the authoritative workflow. Local runs skip an
external-server test only when that optional server is not installed.

These checks establish conformance for the supported messages and versions;
they are not a claim that GWT implements every protocol ASGI can carry.

## Operator Qualification

For a specific program and a full-value completed Case Corpus, run:

```sh
gwt qualify-serve rules.gwt --corpus corpus.json --engine asgi --json
```

The command starts `gwt serve --engine asgi` and treats served OpenAPI as the
route-discovery contract. It verifies readiness, dependency-closure identity
in payloads and headers, OpenAPI/request-list agreement, and exact declared
results for the complete corpus. It then starts the same ASGI application with
a controlled hold around the first real evaluator call. That hold proves the
one-slot overload response and active-request SIGTERM path deterministically;
it is harness instrumentation, not a public server option and not language
syntax.

The command exits nonzero when any check or corpus case fails. `--json` emits
the versioned `gwt.serve-qualification` report described by
[`schemas/serve-qualification.schema.json`](schemas/serve-qualification.schema.json).
No elapsed-time threshold is a pass condition, so this artifact qualifies the
supported boundary but does not benchmark capacity or latency. TLS, auth,
proxy behavior, and multi-process supervision still require deployment-level
checks.

The repository's next deployment layer is executable as well:

```sh
python examples/deployable_api/qualify_container.py rules.gwt \
  --program-root . --corpus corpus.json --json
```

That runner builds the checked Dockerfile and repeats the endpoint checks
through an ephemeral published port. It additionally requires Docker health to
reach `healthy`, an ordinary `docker stop` to exit cleanly, overload to remain
stable through port publication, and Docker-delivered SIGTERM to preserve an
already admitted response. The image starts Python/Uvicorn as PID 1 through an
`exec` handoff, verified from the PID 1 executable and argument vector. Once
the local inputs validate, `--json` remains a schema-valid report even when a
Docker boundary check fails. This establishes the single-container process
contract, not reverse-proxy, TLS, authentication, orchestration, or
multi-worker conformance.

## Runtime Shape

The adapter consumes the complete HTTP request body from one or more
`http.request` events, enforcing the configured byte limit while continuing to
drain an oversized body. It then runs the synchronous GWT evaluator in a worker
thread and emits exactly one `http.response.start` followed by one terminal
`http.response.body` event.

Unexpected scopes and invalid HTTP or lifespan events raise
`GwtAsgiProtocolError`. Extra keys on valid ASGI dictionaries remain allowed,
as required for forward-compatible protocol extensions.

The Uvicorn runner marks the shared HTTP application as draining in its signal
handler before delegating to Uvicorn's exit handling. Standard lifespan
shutdown still performs final cleanup and reports either
`lifespan.shutdown.complete` or `lifespan.shutdown.failed`. A subprocess test
holds an admitted GWT evaluation across SIGTERM and verifies that the request
finishes.

## Boundaries

- Request bodies are buffered up to GWT's configured limit; the evaluator does
  not expose a streaming language API.
- HTTP/2 socket support is a server/transport capability. The application
  accepts valid ASGI HTTP scopes whose `http_version` is `1.0`, `1.1`, or `2`.
- The CLI runner is single-process. Additional worker processes and their
  lifespan instances belong to the deployment supervisor.
- TLS, authentication, authorization, connection limits, and edge rate limits
  remain outside the ASGI application.
