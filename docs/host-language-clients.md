# Host Language Clients

GWT should be easy to call from ordinary application code. A host application
should not need to be written in GWT; it should be able to treat GWT as the
portable executable module for deterministic domain behavior.

For guidance on choosing between host-side executable specs and embedded
application decisions, see [Adoption Modes](adoption-modes.md).

The intended boundary is:

```text
host application -> JSON request object -> GWT named request -> typed GWT result
```

The host language owns I/O, persistence, networking, UI, scheduling, and other
non-deterministic work. GWT owns the deterministic rules, workflows, contracts,
state transitions, and executable examples.

## Client Libraries

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

## Runtime Shapes

GWT can support several client implementation strategies without changing the
language:

| Shape | Use when | Tradeoff |
| --- | --- | --- |
| In-process SDK | The runtime exists in the host language | Best ergonomics, but requires a native runtime or binding |
| CLI-backed client | A host app can spawn `gwt` | Portable now, process overhead per call |
| Long-running runner | A host app wants lower overhead without embedding | Requires a local protocol and lifecycle management |
| HTTP/gRPC service | Multiple apps or languages share one deployed rules service | Operationally heavier, but language-neutral |

The first production-quality client should probably be Python, because it is
already the implementation language. The next most valuable clients are likely
TypeScript, .NET, and Java because they represent common application hosts.

## Near-Term Chunks

Client work should land in small compatibility-preserving chunks. The first
goal is a stable integration contract, not a large fleet of clients.

### 1. Reference Contract And Python Client

Harden the current Python API and the process runner as one reference contract:

- document the runner protocol: stdin JSON, explicit `--request`, stdout envelope,
  stderr diagnostics, and exit codes
- keep `GwtClient`, `check_file`, `run_json_file`, and `run_json_text` as the
  reference SDK shape
- make error payloads and source locations predictable enough for other clients
  to expose directly
- add examples that show a host app checking a program before executing it

This chunk is the foundation for every other client. The process bridge can be
used by any host language while native integrations mature.

### 2. TypeScript Client

Build the first non-Python client as a CLI-backed TypeScript package. It should
spawn `gwt`, send JSON through stdin, parse the execution envelope, and expose a
small API such as:

```ts
import { runFile } from "@gwtlang/client";

const result = await runFile("rules.gwt", {
  input: { vendor },
  request: "review vendor",
});
```

This proves the runner protocol from a real external ecosystem without needing
to port the runtime. The initial package lives in
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

### 3. Generated Host Types

Add type generation after the client contract is stable. Start with TypeScript:

- `RECORD` declarations become interfaces or type aliases
- literal unions become string literal unions
- named request inputs become the input type
- named request outputs become the result type

Python `TypedDict` generation follows the same request boundary and also emits a
program-specific client wrapper. .NET and Java clients can start as CLI-backed
wrappers before they need generated classes.

The initial command is:

```sh
gwt types rules.gwt --language typescript > rules.d.ts
```

`gwt serve` should wait until these chunks prove the client contract. A server
adds lifecycle, concurrency, deployment, and security decisions that are not
needed to validate the basic host-language client model.

## Generated Host Types

Client libraries become more useful when host types can be generated from GWT
contracts:

- `RECORD` declarations map to host DTOs/classes/interfaces.
- named request input bindings map to the required input object.
- named request output bindings map to the result object.
- Literal unions map to enums or string literal unions when the host supports
  them.

For TypeScript, GWT emits declarations for records, one-of records,
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

For Python, GWT emits `TypedDict` records, one-of record unions, per-request
request/output shapes, request-name constants, `GwtRequestName`, `GwtRequest`,
`GwtOutput`, and a program-specific client wrapper:

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
strict checking covers `gwtlang/api.py`, validation and inspection payload
builders, and the Python host examples before it expands into parser/runtime
internals.

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
