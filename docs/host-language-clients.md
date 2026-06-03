# Host Language Clients

GWT should be easy to call from ordinary application code. A host application
should not need to be written in GWT; it should be able to treat GWT as the
portable executable module for deterministic domain behavior.

The intended boundary is:

```text
host application -> GWT request object -> GWT behavior -> typed GWT result
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
    {"vendor": vendor, "decision": decision},
    entry="review vendor into decision",
)

result = execution.as_payload()["result"]["decision"]
```

For long-running Python hosts, use the checked compile-once API during
application startup:

```python
from gwtlang import compile_file

rules = compile_file(
    "rules.gwt",
    import_roots=["rules"],
    allow_absolute_imports=False,
)

execution = rules.run_json(
    {"vendor": vendor, "decision": decision},
    entry="review vendor into decision",
)
```

The compiled program reuses the parsed and checked rule program while creating a
fresh runtime state for each execution. `import_roots` and
`allow_absolute_imports=False` let production hosts confine `USE` imports to
known rule directories.

Host-language clients should offer the same shape across ecosystems:

```csharp
var result = await Gwt.RunFileAsync(
    "rules.gwt",
    new { vendor, decision },
    entry: "review vendor into decision");

var reviewed = result.Result["decision"];
```

```java
GwtResult result = Gwt.runFile(
    "rules.gwt",
    Map.of("vendor", vendor, "decision", decision),
    "review vendor into decision");

VendorDecision reviewed = result.resultAs("decision", VendorDecision.class);
```

```ts
import { runFile } from "@gwtlang/client";

const result = await runFile("rules.gwt", {
  input: { vendor, decision },
  entry: "review vendor into decision",
});

const reviewed = result.result.decision;
```

The exact host-language API can vary, but each client should preserve the same
conceptual contract:

- check a `.gwt` program before running it
- send a JSON-compatible request object
- name the entry behavior explicitly
- return the stable GWT execution envelope
- expose diagnostics and runtime failures without hiding GWT source locations

## Runner Protocol

Not every host language needs a native runtime immediately. The lowest common
protocol is process-based:

```sh
printf '%s' "$REQUEST_JSON" | gwt run rules.gwt \
  --json-input - \
  --entry "review vendor into decision" \
  --json
```

The client writes a JSON object to stdin and reads the stable execution envelope
from stdout. This is enough for early .NET, Java, Go, Ruby, and TypeScript
clients to exist as thin wrappers around the CLI.

The process contract is intentionally small:

- command: `gwt run <rules.gwt> --json-input - --entry "<behavior call>" --json`
- stdin: one JSON object containing initial GWT state
- stdout on success: the stable execution envelope with `ok: true`
- stderr on failure: GWT diagnostics or runtime errors with source locations
- exit code `0`: execution succeeded
- exit code `1`: parse, check, contract, runtime, or JSON input failure
- exit code `2`: command-line usage error, such as missing `--entry`

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

- document the runner protocol: stdin JSON, explicit `--entry`, stdout envelope,
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
  input: { vendor, decision },
  entry: "review vendor into decision",
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
JSON request, check the rules file, run the entry behavior, and consume a typed
`GwtOutput` result.

### 3. Generated Host Types

Add type generation after the client contract is stable. Start with TypeScript:

- `RECORD` declarations become interfaces or type aliases
- literal unions become string literal unions
- `REQUEST` declarations become the input type
- `OUTPUT` declarations become the result type

Python `TypedDict` or dataclass generation can follow. .NET and Java clients can
start as CLI-backed wrappers before they need generated classes.

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
- `REQUEST` declarations map to the required input object.
- `OUTPUT` declarations map to the result object.
- Literal unions map to enums or string literal unions when the host supports
  them.

For TypeScript, GWT emits declarations for records, one-of records, `GwtRequest`,
and `GwtOutput`:

```sh
gwt types examples/vendor_onboarding/rules.gwt --language typescript \
  --output examples/vendor_onboarding/rules.d.ts
```

The generator checks the source before emitting types, so unknown record or
contract types fail with the same source-located diagnostics as `gwt check`.
The generated declarations can be passed to `@gwtlang/client` as generics:

```ts
const execution = await client.runJson<GwtRequest, GwtOutput>(request, {
  entry: "review vendor into decision",
});
```

Generated TypeScript uses nested object shape for dotted contract paths. Lower
level CLI JSON may still provide state through dotted path keys such as
`"cart.total"`, or through nested objects that produce the same state.

Generated types should be treated as host integration helpers, not as the source
of truth. The `.gwt` contracts remain normative.

## Boundary Rules

Client libraries should reinforce GWT's core promise:

- Do not reimplement GWT rules in the host language.
- Do not hide checker/runtime diagnostics behind generic client errors.
- Do not make entry behavior implicit when more than one workflow exists.
- Do not let host callbacks introduce non-determinism into ordinary GWT
  behavior.
- Do keep JSON/API boundaries explicit and testable.

This keeps GWT pluggable without turning it into a general host-language
scripting extension.
