# Host Integration

GWT should be easy to call from ordinary application code. A host application
should not need to be written in GWT; it should be able to treat GWT as the
portable executable module for deterministic domain behavior.

For guidance on choosing between served decisions, host-side executable specs,
and embedded Python decisions, see [Adoption Modes](adoption-modes.md).

The recommended cross-language boundary is:

```text
host application -> JSON HTTP request -> gwt serve -> GWT named request -> declared output
```

The host language owns I/O, persistence, networking, UI, scheduling, and other
non-deterministic work. GWT owns the deterministic rules, workflows, contracts,
state transitions, and executable examples.

## Recommended Boundary: `gwt serve`

Use `gwt serve` when a non-Python application needs to execute GWT behavior:

```sh
gwt validate rules.gwt --import-root rules --no-absolute-imports
gwt openapi rules.gwt --output openapi.json
gwt serve rules.gwt \
  --engine asgi \
  --host 127.0.0.1 \
  --port 8080 \
  --execution-budget 100000 \
  --max-call-depth 100
```

This keeps one evaluator and lets hosts use ordinary HTTP clients, generated
OpenAPI clients, gateways, and deployment controls. It is preferable to
building and maintaining a GWT-specific runtime wrapper for each ecosystem.
The service remains experimental; TLS, auth, authorization, and rate limiting
belong in host-owned infrastructure around it. Install `gwtlang[serve]` for
the ASGI engine shown here. The default built-in engine exposes the same
application contract without optional dependencies and is intended for local
development/reference use.

## Embedded And Process Alternatives

A GWT client library is a host-language package that makes a `.gwt` program feel
natural to call from that ecosystem.

For example, a Python caller can use `GwtClient` as the reference client
facade:

```python
from gwtlang import GwtClient

client = GwtClient("rules.gwt")
check = client.check()
if not check.ok:
    raise RuntimeError(check.as_payload())

execution = client.run_json(
    {"vendor": vendor},
    request="review vendor",
)

result = execution.as_payload()["result"]["decision"]
```

For long-running Python hosts, run the production-shaped check in local
development and CI:

```sh
python -m gwtlang validate rules.gwt \
  --import-root rules \
  --no-absolute-imports
```

`gwt validate` checks imports, static diagnostics, canonical formatting, and
embedded scenarios when the file has scenario content, before the host
application boots. Use `gwt inspect rules.gwt --json` when a CI job, editor, or
agent needs a stable manifest of records, named requests, behaviors, scenarios,
imports, and the program hash.

Then use the checked compile-once API during application startup as a final
safety gate:

```python
from gwtlang import compile_file

rules = compile_file(
    "rules.gwt",
    import_roots=["rules"],
    allow_absolute_imports=False,
)

execution = rules.run_json(
    {"vendor": vendor},
    request="review vendor",
)
```

The compiled program reuses the parsed and checked rule program while creating a
fresh runtime state for each execution. `import_roots` and
`allow_absolute_imports=False` should match the CLI `--import-root` and
`--no-absolute-imports` options used in CI.

## Python Host Observation Adapter

Some applications need GWT to check behavior around code that should remain in
the host project: parser output, formatter results, HTTP responses, SQL
analysis, async framework events, or other ecosystem-specific objects. Keep
that work in Python and inject a normalized observation record before GWT runs:

```python
from gwtlang import GwtHostAdapter, HostObservation


def observe_format(context):
    case = context.get("case")
    formatted = run_real_formatter(case["source"])
    return {
        "status": "ok",
        "formatted": formatted,
        "error": "",
    }


rules = GwtHostAdapter.from_file(
    "format_rules.gwt",
    request="review case",
    observations=[
        HostObservation("observation", observe_format),
    ],
    import_roots=["rules"],
    allow_absolute_imports=False,
)

execution = rules.run_json({
    "case": {"source": source, "expected": expected},
    "decision": {"status": "new", "reason": ""},
})
decision = execution.as_payload()["result"]["decision"]
```

The observation is computed from the host state, inserted at the named GWT
state path, and then validated by `REQUEST` contracts like any other input. The
adapter accepts JSON-compatible values and dataclass instances. It is
intentionally not a general callback system inside the GWT runtime: host code
owns I/O and framework behavior, while GWT owns deterministic contracts,
decisions, and assertions over normalized state.

Host-language clients should offer the same shape across ecosystems:

```csharp
var result = await Gwt.RunFileAsync(
    "rules.gwt",
    new { vendor },
    request: "review vendor");

var reviewed = result.Result["decision"];
```

```java
GwtResult result = Gwt.runFile(
    "rules.gwt",
    Map.of("vendor", vendor),
    "review vendor");

VendorDecision reviewed = result.resultAs("decision", VendorDecision.class);
```

```ts
import { runFile } from "@gwtlang/client";

const result = await runFile("rules.gwt", {
  input: { vendor },
  request: "review vendor",
});

const reviewed = result.result.decision;
```

The exact host-language API can vary, but each client should preserve the same
conceptual contract:

- check a `.gwt` program before running it
- expose the `inspect` manifest for tools that need records, named requests,
  and program hashes
- send a JSON-compatible request object
- name the public request explicitly
- return the stable GWT execution envelope
- expose diagnostics and runtime failures without hiding GWT source locations

## Runner Protocol

Not every host language needs a native runtime immediately. The lowest common
protocol is process-based:

```sh
printf '%s' "$REQUEST_JSON" | gwt run rules.gwt \
  --json-input - \
  --request "review vendor" \
  --json
```

The client writes a JSON object to stdin and reads the stable execution envelope
from stdout. This is enough for early .NET, Java, Go, Ruby, and TypeScript
clients to exist as thin wrappers around the CLI.

The process contract is intentionally small:

- command: `gwt run <rules.gwt> --json-input - --request "<request name>" --json`
- stdin: one JSON object containing initial GWT state
- stdout on success: the stable execution envelope with `ok: true`
- stderr on failure: GWT diagnostics or runtime errors with source locations
- exit code `0`: execution succeeded
- exit code `1`: parse, check, contract, runtime, or JSON input failure
- exit code `2`: command-line usage error, such as missing `--request`

Native clients can later replace the process call with an embedded runtime or a
service call while preserving the same public API.

JSON Schemas for the stable command payloads live in
[`docs/schemas`](schemas/). They cover diagnostics, execution envelopes,
`check --json`, `inspect --json`, and `validate --json`. Client libraries
should treat them as additive contracts: new optional fields may appear, while
incompatible shape changes should bump the payload `schemaVersion`.

## JSON Schema Projection

For hosts that need contract schemas without an HTTP API document, `gwt schema`
projects GWT type and request contracts into a JSON Schema Draft 2020-12
catalog:

```sh
python -m gwtlang schema rules.gwt --json
```

The generated document emits `TYPE`, `RECORD`, one-of records, named request
inputs, and named request outputs under `$defs`. The top-level `x-gwt.requests`
metadata maps each exact request name to its input and output schema references.
This gives validators, schema registries, generated forms, and non-HTTP
contract-test tooling a standard contract surface without adding GWT syntax or
requiring OpenAPI.

Decimal contracts use a JSON Schema `pattern` as well as `format: decimal`, so
standard validators can reject non-decimal strings even when they treat
`format` as annotation. Request schemas accept decimal strings and JSON
integers, matching GWT's host input normalization. Response schemas model the
serialized GWT wire shape, so decimal outputs are strings. Decimal literal
unions carry `x-gwt-literal-values`; standard schemas preserve the accepted
decimal wire shape, while the GWT runtime remains the final authority for exact
literal membership.

## OpenAPI Projection

For hosts that already consume HTTP API contracts, `gwt openapi` projects named
`REQUEST` blocks into an OpenAPI 3.1 document:

```sh
python -m gwtlang openapi rules.gwt --json
```

The generated document turns caller-provided `GIVEN` bindings into request
body schemas and declared `OUTPUT` bindings into response body schemas. This is
the contract served by `gwt serve`, and it improves
interoperability with generated clients, API gateways, Swagger UI, Postman,
and contract-test tooling without adding new GWT syntax.

See [HTTP Service And OpenAPI](http-service-design.md) for the active hardening
focus and deferred auth boundary.

## Runtime Shapes

GWT can support several client implementation strategies without changing the
language:

| Shape | Use when | Tradeoff |
| --- | --- | --- |
| HTTP service | A non-Python app or multiple apps execute GWT decisions | Recommended cross-language boundary; operationally heavier than embedding |
| In-process Python SDK | A Python host wants compile-once local execution | Lowest overhead, but couples the host to the Python runtime |
| CLI-backed client | A script, test, or local tool can spawn `gwt` | Portable, with process overhead per call |
| Long-running custom runner | A host cannot use HTTP but needs lower process overhead | Additional lifecycle and protocol surface to own |

The Python API remains the reference embedded client. The CLI-backed TypeScript
package in [`clients/typescript`](../clients/typescript) remains a useful
compatibility and testing surface, but new language-specific clients are not
the current focus. Standard HTTP/OpenAPI tooling should be tried first.

## Existing Client Compatibility Surfaces

Existing client work should receive small compatibility-preserving changes.
The goal is a stable integration contract, not a large fleet of clients. The
sections below document supported alternatives, not a plan to expand bespoke
clients ahead of the served boundary.

### 1. Reference Contract And Python Client

Keep hardening the current Python API and the process runner as one reference
contract:

- document the runner protocol: stdin JSON, explicit `--request`, stdout envelope,
  stderr diagnostics, and exit codes
- keep `GwtClient`, `check_file`, `run_json_file`, and `run_json_text` as the
  reference SDK shape
- make error payloads and source locations predictable enough for other clients
  to expose directly
- add examples that show a host app checking a program before executing it

These APIs remain the compatibility foundation for embedded Python and local
tooling. The process bridge remains available where running an HTTP service is
not appropriate.

### 2. TypeScript Client

The first non-Python client is a CLI-backed TypeScript package. It spawns
`gwt`, sends JSON through stdin, parses the execution envelope, and exposes a
small API such as:

```ts
import { runFile } from "@gwtlang/client";

const result = await runFile("rules.gwt", {
  input: { vendor },
  request: "review vendor",
});
```

This proves the runner protocol from a real external ecosystem without needing
to port the runtime. The package lives in
[`clients/typescript`](../clients/typescript) and uses zero runtime
dependencies: Node spawns the configured GWT command, writes stdin JSON, and
returns the parsed envelope.

The typed vendor onboarding example at
[`clients/typescript/examples/vendor-onboarding.ts`](../clients/typescript/examples/vendor-onboarding.ts)
shows the complete host flow: generate declarations from GWT contracts, read a
JSON request, check the rules file, run the named request, and consume a typed
`GwtOutput` result.

The paired Python host example at
[`examples/vendor_onboarding/host_app.py`](../examples/vendor_onboarding/host_app.py)
uses generated `TypedDict` contracts and the generated
`VendorOnboardingClient` wrapper for the same `REQUEST review vendor` boundary.
It validates the GWT file, inspects the public request manifest, compiles once,
and runs the named request as an executable spec module.

TypeScript test suites can use the same package as a small spec fixture:

```ts
import { beforeAll, expect, it } from "vitest";
import { createGwtSpec } from "@gwtlang/client";
import type { GwtOutput, GwtRequest, GwtRequestName } from "./rules.js";

const rules = createGwtSpec<
  GwtRequest,
  GwtOutput,
  Record<string, unknown>,
  GwtRequestName
>({
  file: "rules.gwt",
  request: "review vendor",
  importRoots: ["rules"],
  allowAbsoluteImports: false,
});

beforeAll(() => rules.checkOnce());

it("reviews a vendor request", async () => {
  const execution = await rules.runJson(request);

  expect(execution.result.decision.status).toBe("approved");
});

it("keeps embedded GWT scenarios passing", async () => {
  const execution = await rules.test();

  expect(execution.scenario_count).toBeGreaterThan(0);
});
```

`createGwtSpec` is intentionally test-framework agnostic. It caches the
`check()` result, supports the generated `GwtRequestName` type as a default
request, and passes import policy options through to `gwt check`, `gwt run`,
and `gwt test`.

Host application code can use `createGwtProgram` with generated `GwtRequests`
and `GwtOutputs` maps when it wants the request name, input object, and output
object to stay correlated:

```ts
import { createGwtProgram } from "@gwtlang/client";
import type { GwtOutputs, GwtRequests } from "./rules.js";

const rules = createGwtProgram<GwtRequests, GwtOutputs, "review vendor">({
  file: "rules.gwt",
  request: "review vendor",
  importRoots: ["rules"],
  allowAbsoluteImports: false,
});

const execution = await rules.runJson({ vendor });
const status = execution.result.decision.status;
```

`GwtClient.inspect()` and `GwtClient.validate()` expose the same JSON payloads
as `gwt inspect --json` and `gwt validate --json`, including non-OK diagnostic
payloads.

`GwtClient.agent_context()` builds the same provider-neutral domain-language
pack as `gwt agent-context`. Use its structured payload when a host application
or provider-specific skill needs program types, public requests, behavior
signatures, selected scenarios, and the validation workflow without copying
domain knowledge into agent configuration.

### 3. Generated Host Types

Keep generated host types aligned with the stable client contract. TypeScript
and Python generation currently follow these rules:

- `TYPE` declarations become type aliases
- `RECORD` declarations become interfaces
- literal unions become string literal unions
- named request inputs become the input type
- named request outputs become the result type

Python `TypedDict` generation follows the same request boundary and also emits a
program-specific client wrapper. Other ecosystems should prefer classes and
clients generated by standard OpenAPI tooling before GWT adds bespoke support.

The command shape is:

```sh
gwt types rules.gwt --language typescript > rules.d.ts
```

`gwt serve` is now the primary hardening focus because these chunks proved the
request and output contract. Lifecycle, concurrency, deployment, and security
remain explicit service-boundary concerns rather than new GWT syntax.

## Generated Host Types

Client libraries become more useful when host types can be generated from GWT
contracts:

- `RECORD` declarations map to host DTOs/classes/interfaces.
- `TYPE` declarations map to host type aliases.
- named request input bindings map to the required input object.
- named request output bindings map to the result object.
- Literal unions map to enums or string literal unions when the host supports
  them.

For TypeScript, GWT emits declarations for type aliases, records, one-of records,
`GwtRequestName`, `GwtRequests`, `GwtOutputs`, `GwtRequest`, and `GwtOutput`:

```sh
gwt types examples/vendor_onboarding/rules.gwt --language typescript \
  --output examples/vendor_onboarding/rules.d.ts
```

The generator checks the source before emitting types, so unknown record or
contract types fail with the same source-located diagnostics as `gwt check`.
The generated request/output maps can be passed to `@gwtlang/client` as
generics:

```ts
const rules = createGwtProgram<GwtRequests, GwtOutputs, "review vendor">({
  file: "rules.gwt",
  request: "review vendor",
});
const execution = await rules.runJson({ vendor });
```

`GwtRequestName` gives host code compile-time protection against request-name
typos. `createGwtProgram` uses the `GwtRequests` and `GwtOutputs` maps plus the
default request literal to keep each request name correlated with its input and
output shape. The same named request list powers `gwt inspect --json`, so host
types and tool manifests agree on which request strings are valid.

Generated TypeScript uses nested object shape for dotted contract paths. Lower
level CLI JSON may still provide state through dotted path keys such as
`"cart.total"`, or through nested objects that produce the same state.

For Python, GWT emits `TypeAlias` declarations, `TypedDict` records, one-of
record unions, per-request request/output shapes, request-name constants,
`GwtRequestName`, `GwtRequest`, `GwtOutput`, and a program-specific client
wrapper:

```sh
gwt types examples/exact_pricing/rules.gwt --language python \
  --output examples/exact_pricing/rules_types.py
```

Python callers can use the generated wrapper for request-specific methods while
keeping `GwtClient` or `gwt validate` for validation and inspection workflows:

```python
from rules_types import ExactPricingClient, PriceCartRequest

rules = ExactPricingClient.from_file("rules.gwt")
request: PriceCartRequest = {"cart": cart}
result = rules.price_cart(request)
```

Generated types should be treated as host integration helpers, not as the source
of truth. The `.gwt` contracts remain normative.

The Python package ships a `py.typed` marker and typed payload aliases for the
public host boundary. The repository's Pyright gate is intentionally scoped:
strict checking covers `gwtlang/api.py`, the host observation adapter,
generated host type support, the package re-export surface, the base error
type, analysis service payloads, completion items, checker/type-analysis logic,
expression parsing/evaluation, runtime/parser execution, LSP response helpers,
the CLI entrypoint, formatter helpers, debugger line payloads, validation and
inspection payload builders, and the Python host examples.

GWT performs runtime request/output contract validation itself. Pydantic can be
useful in a host application before values reach GWT, but it should remain an
application choice rather than a required GWT dependency unless a concrete host
workflow needs that second validation layer.

## Boundary Rules

Client libraries should reinforce GWT's core promise:

- Do not reimplement GWT rules in the host language.
- Do not hide checker/runtime diagnostics behind generic client errors.
- Do not make the request name implicit when more than one workflow exists.
- Do not let host callbacks introduce non-determinism into ordinary GWT
  behavior.
- Do keep JSON/API boundaries explicit and testable.

This keeps GWT pluggable without turning it into a general host-language
scripting extension.
