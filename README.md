# GWT

[![CI](https://github.com/georgemclaughlin/gwt/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/georgemclaughlin/gwt/actions/workflows/ci.yml)

GWT is a small experimental programming language built around executable
`GIVEN / WHEN / THEN` programs. It is for deterministic workflows, rules,
examples, and typed request/response programs where the spec is also the
runtime artifact.

GWT is not a policy decision point like OPA, not a SQL-like query language, and
not a general-purpose replacement for Python, JavaScript, or Go. The goal is
narrower: make behavior contracts readable enough for stakeholders and precise
enough to execute, test, check, format, and debug.

GWT is also a response to a common failure mode in spec-driven development:
the spec becomes a better prompt, but the durable behavior still lives in code
somewhere else. In GWT, natural language can propose intent, but executable
GWT defines normative behavior. A `.gwt` file is not a handoff document that an
agent interprets into hidden implementation code; it is the behavior program
itself.

OpenSpec's persistent-spec idea was an original inspiration, though GWT does
not use or depend on OpenSpec. The language is also shaped by Cucumber,
SpecFlow/Reqnroll, and BDD examples. New features should stay
behavior-oriented and should not drift toward broad query syntax or invisible
policy evaluation.

## Flagship Demo

Start with [`examples/vendor_onboarding`](examples/vendor_onboarding). It is the
clearest end-to-end GWT path: one executable rules file, embedded scenarios, a
named JSON request, generated Python and TypeScript host types, and host app
calls that consume a typed decision. CI keeps this path current by validating
the module, running the host apps, diffing generated host type fixtures, running
strict Pyright checks, checking the TypeScript client, and checking the VS Code
extension.

```sh
python -m gwtlang validate examples/vendor_onboarding/rules.gwt \
  --import-root examples/vendor_onboarding \
  --no-absolute-imports

python -m gwtlang run examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor" \
  --json

python examples/vendor_onboarding/host_app.py
```

Expected decision:

```txt
typed decision: needs_review (manual_review_required)
```

For incremental adoption, run
[`examples/vendor_onboarding/shadow_mode.py`](examples/vendor_onboarding/shadow_mode.py)
to compare a legacy Python decision function against the GWT request before
promoting GWT as the source of truth.

## Spec Is Code

BMAD, GitHub Spec Kit, and OpenSpec are useful signs of the same shift: humans
and agents need durable specs instead of one-off prompts. GWT pushes on a
different boundary. It treats executable behavior as the source of truth.

Markdown specs can reduce ambiguity, but they still require interpretation.
GWT removes the semantic handoff for deterministic domain behavior:

- `GIVEN` setup is runtime state, not prose about state.
- `WHEN` behavior is executable logic, not a step name backed by separate code.
- `THEN` assertions are regression checks, not suggestions.
- named `REQUEST` blocks are host-facing callable units.
- `OUTPUT` declares response shape; `THEN` declares assertions.

GWT does not remove all product ambiguity. It forces behavior ambiguity to be
resolved before the spec becomes executable.

## Host Language Clients

GWT is intended to plug into ordinary application stacks through explicit JSON
boundaries. A host application can own UI, persistence, network calls, and
deployment while GWT owns deterministic domain behavior.

The current Python package is the reference client API. Other host-language
clients can wrap the same runtime contract:

```text
host app -> JSON request object -> GWT named request -> typed result envelope
```

Programs expose stable request names for host code:

```gwt
REQUEST review vendor
  GIVEN vendor is VendorRequest
  WHEN review vendor into decision
  OUTPUT decision is VendorDecision
```

The CLI also supports a portable runner protocol for early clients in .NET,
Java, TypeScript, Go, Ruby, or any language that can spawn a process:

```sh
printf '%s' "$REQUEST_JSON" | gwt run rules.gwt \
  --json-input - \
  --request "review vendor" \
  --json
```

GWT can also generate TypeScript declaration files and standalone JSON Schema
documents from `TYPE`, `RECORD`, `REQUEST`, and `OUTPUT` contracts:

```sh
gwt types examples/vendor_onboarding/rules.gwt --language typescript \
  --output vendor-onboarding.d.ts
gwt schema examples/deployable_api/rules.gwt --json
```

For hosts that consume standard HTTP contracts, GWT can project the same named
request boundary into OpenAPI and serve those requests experimentally over
HTTP:

```sh
gwt openapi examples/deployable_api/rules.gwt --json
gwt serve examples/deployable_api/rules.gwt --port 8080
```

See [`docs/host-language-clients.md`](docs/host-language-clients.md) for the
client-library model and boundary rules, and
[`docs/http-service-design.md`](docs/http-service-design.md) for the OpenAPI
and HTTP service direction. Separate JSON Schemas for CLI/API payloads live in
[`docs/schemas`](docs/schemas). The first CLI-backed Node/TypeScript client
lives in [`clients/typescript`](clients/typescript), with a typed host example
in [`clients/typescript/examples/vendor-onboarding.ts`](clients/typescript/examples/vendor-onboarding.ts).

## Quick Start

For the realistic integration path, start with the
[vendor onboarding flagship demo](examples/vendor_onboarding). For a
concept-by-concept introduction, use the
[Getting Started walkthrough](docs/getting-started.html), which builds from a
single `GIVEN / WHEN / THEN` program up through records, scenarios, named
requests, and JSON input.

Run the hello world example:

```sh
python -m gwtlang run examples/hello.gwt --json
```

Run a practical workflow example as executable scenario coverage:

```sh
python -m gwtlang test examples/vendor_onboarding/rules.gwt
```

Run the same workflow with a JSON request, as a host application would:

```sh
python -m gwtlang run examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor" \
  --json
```

Explain why that JSON request produced its decision:

```sh
python -m gwtlang explain examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor"
```

Capture the same run as a versioned, machine-readable Execution Case:

```sh
python -m gwtlang capture examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor" \
  --output vendor-review.execution-case.json
```

Render that case as a self-contained local behavior-review page, including a
replay-verified scenario preview:

```sh
python -m gwtlang workbench vendor-review.execution-case.json \
  --program examples/vendor_onboarding/rules.gwt \
  --name "captured vendor review" \
  --output vendor-review.html
```

Add paired `--old` and `--new` programs to make old/new behavior comparison the
primary workbench view. Cases and HTML include full values, so review them
before sharing or committing them. See
[`docs/execution-cases.md`](docs/execution-cases.md) for artifact guidance and
the [`v0.4 external pilot runbook`](docs/external-pilot-v0.4.md) for the
two-workflow evaluation process.

Install a local `gwt` command while developing:

```sh
python -m pip install -e .
gwt run examples/hello.gwt --json
```

## Project Site

A simple fundamentals site lives at [`docs/index.html`](docs/index.html). It
is designed to publish through GitHub Pages from the `main` branch and `/docs`
directory.

## What To Review First

For a quick public review, start with:

| Artifact | Why |
| --- | --- |
| [`examples/vendor_onboarding`](examples/vendor_onboarding) | Practical workflow demo with typed state, review decisions, risk scoring, JSON input, and embedded scenarios |
| [`examples/behavior_review`](examples/behavior_review) | Focused local capture, explanation, scenario, comparison, and workbench review loop |
| [`examples/incident_triage`](examples/incident_triage) | v0.3 pilot artifact for deterministic incident escalation, JSON execution, generated Python host types, and a typed host call |
| [`docs/spec-is-code.md`](docs/spec-is-code.md) | Short thesis note on executable specs versus agent-interpreted planning artifacts |
| [`docs/adoption-modes.md`](docs/adoption-modes.md) | Practical paths for host-side executable specs and embedded decision runners |
| [`docs/roadmap-v0.4.md`](docs/roadmap-v0.4.md) | Active roadmap for trustworthy execution evidence, factual explanations, generated scenarios, impact comparison, and a local behavior-review workbench |
| [`docs/external-pilot-v0.4.md`](docs/external-pilot-v0.4.md) | Full capture-to-workbench runbook, privacy gate, and evidence template for two unrelated external workflows |
| [`docs/release-v0.4-checklist.md`](docs/release-v0.4-checklist.md) | Publication gate with name, license, external-pilot, artifact-trust, packaging, and manual-release controls |
| [`docs/release-notes-v0.4.md`](docs/release-notes-v0.4.md) | Draft candidate notes covering behavior-review tooling, compatibility, trust boundaries, and unresolved blockers |
| [`docs/project-identity-v0.4.md`](docs/project-identity-v0.4.md) | Rename decision memo, CauSpec working candidate, collision evidence, and compatibility-first migration matrix |
| [`docs/roadmap-v0.3.md`](docs/roadmap-v0.3.md) | Preceding stabilization roadmap for the v0.3 language/tooling milestone |
| [`docs/release-v0.3-checklist.md`](docs/release-v0.3-checklist.md) | Concrete v0.3 release-candidate gate, pilot evidence, deferred design pressure, and versioning checklist |
| [`docs/release-notes-v0.3.md`](docs/release-notes-v0.3.md) | Prepared v0.3 package release notes covering stabilization scope, pilots, and version surfaces |
| [`docs/pilot-evaluation.md`](docs/pilot-evaluation.md) | Template for testing GWT against real workflows before adding syntax |
| [`docs/host-language-clients.md`](docs/host-language-clients.md) | Integration model for Python, .NET, Java, TypeScript, and other host-language clients |
| [`docs/program-interface-boundary.md`](docs/program-interface-boundary.md) | Clarifying note on public entries, helper behaviors, scenarios, request files, and CLI JSON execution |
| [`examples/minilang2_vm`](examples/minilang2_vm) | Larger pressure test covering tokens, AST records, bytecode, closures, modules, stack traces, debugger state, and REPL-like execution |
| [`docs/design-principles.md`](docs/design-principles.md) | Guardrails for keeping GWT behavior-oriented instead of becoming OPA, SQL, or a general-purpose language |

## Hello World

```gwt
PROGRAM hello

GIVEN greeting is "hello world"

WHEN print greeting

THEN greeting == "hello world"
```

`GIVEN` creates state, `WHEN` does something, and `THEN` checks the result.

## Type Aliases

Use `TYPE` to name reusable domain states and collection item types:

```gwt
TYPE DecisionStatus is "new" | "approved" | "needs_review"
TYPE DecisionHistory is list<DecisionStatus>

RECORD Decision
  status: DecisionStatus
  history: DecisionHistory
```

Aliases are type contracts only; they do not create runtime values.

## Reusable Behavior

Block-form `WHEN` defines behavior. Single-line `WHEN` executes behavior or a
built-in statement.

```gwt
PROGRAM bank

GIVEN account.balance is 100
AND account.status is "open"

WHEN withdraw <amount> from <account>
  REQUIRE account.status is "open"
  AND account.balance is at least amount
  subtract amount from account.balance

WHEN withdraw 30 from account

THEN account.balance == 70
AND account.status is "open"
```

Explicit signature parameters use `<name>`. Inside the behavior body, use the
bare name, such as `amount` or `account`.

## Records And Contracts

Records group related state:

```gwt
GIVEN account is
  balance: 100
  status: "open"

THEN account is
  balance: 70
  status: "open"
```

`RECORD` declares expected state shape:

```gwt
RECORD Account
  balance: number
  status: "open" | "closed"

GIVEN account is Account
  balance: 100
  status: "open"
```

Named requests define the host-facing interface. Use `integer` for exact whole
numbers, `decimal` for finite exact base-10 values, and `number` for legacy
broad numeric values. Decimal JSON input may use strings such as `"12.30"` or
JSON integers; decimal values serialize as strings in JSON/API payloads.

```gwt
RECORD LineItem
  quantity: integer
  unit_price: decimal
```

Request input and output contracts live inside the named request:

```gwt
REQUEST review expense report
  GIVEN report is ExpenseReport

  GIVEN decision is ExpenseDecision
    submitted_total: 0
    status: "new"

  WHEN review report into decision

  OUTPUT decision is ExpenseDecision
```

Caller-provided `GIVEN` inputs validate before request execution. Request-local
`GIVEN` setup creates internal state. `OUTPUT` validates after execution. JSON/API
payloads put only declared output paths under `result`; the full final state
stays under `state`.

## Collections And Tables

Typed tables create lists of records:

```gwt
GIVEN report.lines are ExpenseLine
  | description    | amount | category    | reimbursable |
  | "airport taxi" | 42     | "transport" | true         |
  | "monitor"      | 225    | "equipment" | true         |
```

Collection helpers cover common list work:

```gwt
WHEN review <report> into <decision>
  GIVEN report is ExpenseReport
  AND decision is ExpenseDecision
  count report.lines into decision.line_count
  sum line.amount in report.lines into decision.submitted_total
  FOR line in report.lines WHERE line.reimbursable == true
    append line.description to decision.approved_descriptions
  exists line in report.lines WHERE line.amount > report.policy_limit into decision.has_violation
  find optional line in report.lines WHERE line.amount > report.policy_limit into policy_violation
  FIND line in report.lines WHERE line.amount > report.policy_limit
    set decision.status to "needs_review"
  ELSE
    set decision.status to "approved"
```

Conditions can also check containment, such as
`response.body contains "error"` for text, `tags contains "api"` for lists, and
`not tags contains "xml"` or `tags does not contain "xml"` for a negative
check.

The fuller version lives in
[`examples/language_tour`](examples/language_tour).

Run it as embedded regression coverage:

```sh
python -m gwtlang test examples/language_tour/rules.gwt
```

Run it like an app would, with a separate request file:

```sh
python -m gwtlang run examples/language_tour/rules.gwt --input examples/language_tour/request.gwt --json
```

Production callers can also provide JSON state and an explicit request name:

```sh
python -m gwtlang run examples/order_fulfillment/rules.gwt \
  --json-input examples/order_fulfillment/request.json \
  --request "fulfill order" \
  --json
```

Python hosts that need to run project-specific code first can use
`GwtHostAdapter` to inject normalized observation records before GWT validates
and executes the request. This keeps parsing, HTTP, SQL, formatting, and async
framework behavior in Python while GWT owns the executable decision spec. See
[`docs/host-language-clients.md`](docs/host-language-clients.md) for an example.

The JSON result uses a stable envelope. For this request, `result` contains the
declared `OUTPUT` paths:

```json
{
  "ok": true,
  "scenario_count": 1,
  "result": {
    "fulfillment": {
      "status": "partial",
      "reason": "partial_inventory",
      "reserved_units": 3,
      "backordered_units": 1
    },
    "inventory": {
      "widget_available": 4,
      "gadget_available": 0,
      "cable_available": 4
    }
  }
}
```

## Scenarios And Examples

Multiple `SCENARIO` blocks run independently. `EXAMPLES` turns one scenario
into multiple runs:

```gwt
SCENARIO withdrawal examples
GIVEN account.balance is <start>
WHEN withdraw <amount> from account
THEN account.balance == <end>

EXAMPLES
  | start | amount | end |
  | 100   | 30     | 70  |
  | 50    | 10     | 40  |
```

Run scenario files with:

```sh
python -m gwtlang test examples/scenarios.gwt
python -m gwtlang test examples/examples_table.gwt
```

For public examples, scenarios are part of the artifact, not optional
afterthoughts. A substantial example should include embedded `SCENARIO` blocks
with top-level `THEN` assertions. JSON requests show host-facing execution, but
they do not replace executable examples.

## Tooling

The CLI currently supports:

```sh
gwt run examples/bank.gwt
gwt run examples/order_fulfillment/rules.gwt --json-input examples/order_fulfillment/request.json --request "fulfill order" --json
gwt capture examples/vendor_onboarding/rules.gwt --json-input examples/vendor_onboarding/request.json --request "review vendor" --output vendor-review.execution-case.json
gwt scenario-from-run vendor-review.execution-case.json --program examples/vendor_onboarding/rules.gwt --output vendor-review-scenario.gwt
gwt compare --old rules-v1.gwt --new rules-v2.gwt case-1.json case-2.json --json
gwt workbench case-1.json case-2.json --old rules-v1.gwt --new rules-v2.gwt --output review.html
gwt explain examples/vendor_onboarding/rules.gwt --json-input examples/vendor_onboarding/request.json --request "review vendor"
gwt explain examples/vendor_onboarding/rules.gwt --json-input examples/vendor_onboarding/request.json --request "review vendor" --json
gwt types examples/vendor_onboarding/rules.gwt --language typescript --output vendor-onboarding.d.ts
gwt schema examples/deployable_api/rules.gwt --json
gwt openapi examples/deployable_api/rules.gwt --json
gwt serve examples/deployable_api/rules.gwt --port 8080
gwt test examples/checkout/scenarios.gwt
gwt check examples/checkout/rules.gwt
gwt inspect examples/vendor_onboarding/rules.gwt --json
gwt validate examples/vendor_onboarding/rules.gwt --import-root examples/vendor_onboarding --no-absolute-imports
gwt version --json
gwt format examples/bank.gwt --check
gwt lsp
gwt debug-lines examples/checkout/scenarios.gwt --json
```

`gwt check` parses a program and runs semantic checks without executing
scenarios. It reports problems such as unmatched behavior calls, duplicate
behavior signatures, invalid built-in statement shapes, type mismatches, and
`LET`/`RETURN` misuse. It also warns about deprecated implicit behavior
parameters. JSON output includes diagnostic codes, source ranges, and symbols
for editor tooling.

`gwt inspect file.gwt --json` emits a versioned machine-readable manifest for
tools, agents, and CI. It includes the program hash, direct imports, records,
named requests, behaviors, scenarios, and diagnostics. This is intentionally an
inspection surface, not a separate graph or alternate source format.

`gwt explain file.gwt --json-input request.json --request "<request name>"`
runs a named JSON request with trace values enabled. Its default output is a
domain-neutral, source-faithful summary of the input, declared result, all
recorded selected branches and evaluated operands, and changed values. It does
not privilege a field named `status`, call a selected branch the cause of an
output, or invent domain reasons that the program did not execute.

`gwt capture file.gwt --json-input request.json --request "<request name>"`
is the explicit Execution Case v1 capture path. It writes canonical pretty JSON
to stdout, or atomically replaces `--output case.json` when an output path is
provided. Pass `--json-input -` to read the input object from stdin. The
artifact records the dependency-closure program identity and hash,
language/package/payload versions, request input and declared result, execution
outcome, the exact execution budget and call-depth limit, ordered semantic
evidence with logical source references, ordered state changes, capture policy, and value
availability metadata. The schema is
[`docs/schemas/execution-case.schema.json`](docs/schemas/execution-case.schema.json).
The identity, replay, integrity-digest threat model, and sensitivity guidance
are documented in [`docs/execution-cases.md`](docs/execution-cases.md).

`gwt explain ... --json` remains a compatibility and convenience path that
emits the same Execution Case payload. Use `capture` when the artifact itself is
the intended output, and `explain` without `--json` for the factual text view.

By default, a GWT error is raised and full values are captured. Add
`--record-failures` to return a normalized failed Execution Case, and
`--omit-values` to execute without storing input, result, state-change,
operand, physical program/input-file, or full error-detail values. The two
flags compose. Use `--execution-budget N|none` and `--max-call-depth N|none`
to select the recorded semantic limits. See the Execution Case documentation
for the precise redacted, unavailable, absent, and present-value states.

`gwt scenario-from-run case.json --program rules.gwt` converts a full-value,
completed Execution Case into a canonical embedded `SCENARIO`. Generation only
succeeds when the supplied program's dependency-closure identity matches the
case, and the generated scenario passes formatting, checking, execution, and
exact result replay. Use `--name` to set the scenario name and `--output` for an
atomic file replacement.

`gwt compare --old rules-v1.gwt --new rules-v2.gwt case.json ...` replays one
or more Execution Cases against both program versions. The text view summarizes
classifications and output changes; `--json` emits the versioned comparison
payload. A case whose recorded hash does not match `--old` is reported as a
`baseline_mismatch` and is not attributed to the candidate program.
Omitted-value cases are reported as `unavailable` and are not run. Full-value
failed cases are baseline-verified and can report unchanged, path-changed,
failure-changed, resolved-failure, or incompatible candidate behavior.
Comparison JSON includes evaluated predicates and last-change source evidence
for declared-output differences, so mixed-corpus totals reconcile without
false change attribution.

`gwt workbench case.json ... --output review.html` writes a self-contained local
HTML dossier over the same validated artifacts. Paired `--old` and `--new`
programs add comparison; `--program` adds a replay-verified scenario preview
for the first case. Use `--review-notice` for a prominent scope/provenance note
and `--old-label` / `--new-label` to identify the compared sources beside their
hashes and evidence. Output changes are shown first; path-only cases remain in
a collapsed queue until requested. The renderer does not evaluate policy or
contact a service.

`gwt validate file.gwt` is the standard local/CI gate. It checks the program,
verifies canonical formatting, and runs embedded scenarios when the file has
scenario content, without waiting for a host application to boot. Use
`--skip-format` or `--skip-test` only while rolling the workflow into an
existing project.

`gwt format file.gwt` rewrites valid source to the canonical current layout.
`gwt format file.gwt --check` is intended for CI.

`gwt version --json` reports the installed package version, current language
spec version, and stable payload schema version.

`gwt types file.gwt --language typescript` generates host TypeScript
declarations from `TYPE`, `RECORD`, `REQUEST`, and `OUTPUT` contracts. Use
`--language python` to generate Python `TypeAlias`, `TypedDict` request/output
shapes plus a program-specific client wrapper. The generated types are
integration helpers; the `.gwt` file remains the source of truth.

`gwt schema file.gwt` generates a JSON Schema Draft 2020-12 catalog from
`TYPE`, `RECORD`, named `REQUEST`, and `OUTPUT` contracts. GWT type definitions
and request input/output object schemas are emitted under `$defs`, and `x-gwt`
metadata maps each request name to its input and output schema references.
Decimal schemas include both `format: decimal` and a regex `pattern`, because
many standard validators treat custom formats as annotation-only.

`gwt openapi file.gwt` generates an OpenAPI 3.1 document from named `REQUEST`
contracts. Caller-provided `GIVEN` bindings become request body schemas, and
declared `OUTPUT` bindings become response body schemas.

`gwt serve file.gwt` starts an experimental HTTP service for named `REQUEST`
contracts. `GET /openapi.json` returns the same OpenAPI document, `GET /requests`
lists callable requests, and `POST /requests/<request-slug>` runs the request
and returns only the declared `OUTPUT` object. Request posts require
`Content-Type: application/json` and are limited to 1 MiB by default; use
`--max-body-bytes` to change the local service limit. Use `--otlp-endpoint` or
`OTEL_EXPORTER_OTLP_ENDPOINT` to export experimental OpenTelemetry request
execution traces out-of-band. Use `--otlp-metrics-endpoint`,
`OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`, or the same base
`OTEL_EXPORTER_OTLP_ENDPOINT` to export request metrics. `gwt serve` queues
OTLP trace and metric exports in a background worker and uses a bounded flush
on graceful shutdown. Served traces redact state, output, and print values by
default; pass `--trace-values` for local diagnostic runs that need full values.

`gwt lsp` starts a minimal Language Server Protocol server over stdio. It
publishes diagnostics and supports document symbols, hover, go-to-definition for
behavior calls, and completions for known language symbols.

`gwt debug` powers the VS Code debug adapter. Line breakpoints pause before
matching executable GWT lines, and the Call Stack and Variables panels show
active behavior calls, frame locals, and current state while paused.

## Example Programs

| Example | What it shows |
| --- | --- |
| [`examples/hello.gwt`](examples/hello.gwt) | Smallest runnable program |
| [`examples/bank.gwt`](examples/bank.gwt) | Reusable behavior, guards, mutation |
| [`examples/expressions.gwt`](examples/expressions.gwt) | Boolean and arithmetic expressions |
| [`examples/records.gwt`](examples/records.gwt) | Record-shaped state |
| [`examples/let.gwt`](examples/let.gwt) | Local bindings |
| [`examples/control_flow.gwt`](examples/control_flow.gwt) | `IF` / `ELSE` |
| [`examples/decide.gwt`](examples/decide.gwt) | First-matching priority decisions with `DECIDE` |
| [`examples/return_values.gwt`](examples/return_values.gwt) | Returning values from behavior |
| [`examples/scenarios.gwt`](examples/scenarios.gwt) | Multiple named scenarios with shared background |
| [`examples/examples_table.gwt`](examples/examples_table.gwt) | Scenario examples tables |
| [`examples/counter.gwt`](examples/counter.gwt) | Small mutable counter |
| [`examples/collections.gwt`](examples/collections.gwt) | List iteration |
| [`examples/record_contracts.gwt`](examples/record_contracts.gwt) | Record validation |
| [`examples/typed_contracts.gwt`](examples/typed_contracts.gwt) | Behavior parameter and return contracts |
| [`examples/typed_tables.gwt`](examples/typed_tables.gwt) | Typed tables and collection helpers |
| [`examples/use_import`](examples/use_import) | Paired `USE` import example with an importer and imported module |
| [`examples/checkout`](examples/checkout) | Checkout workflow split into rules, scenarios, and request-mode input |
| [`examples/deployable_api`](examples/deployable_api) | Small named-request API example used for OpenAPI generation |
| [`examples/exact_pricing`](examples/exact_pricing) | Exact decimals, integer counts, scalar branching, named request, and Python host example |
| [`examples/language_tour`](examples/language_tour) | A compact tour of the current language |
| [`examples/loan_underwriting`](examples/loan_underwriting) | Larger rules/workflow sample |
| [`examples/order_fulfillment`](examples/order_fulfillment) | Larger state-transition workflow |
| [`examples/inventory_allocation_spike`](examples/inventory_allocation_spike) | List-shaped inventory pressure test |
| [`examples/minilang_spec`](examples/minilang_spec) | Executable spec for a tiny interpreter pipeline |
| [`examples/input_normalization`](examples/input_normalization) | JSON boundary normalization and explicit missing/null behavior |
| [`examples/minilang2_vm`](examples/minilang2_vm) | Bytecode VM pressure test with modules, closures, stack traces, debugger state, and REPL-like execution |
| [`examples/vendor_onboarding`](examples/vendor_onboarding) | Practical typed workflow demo with embedded scenario assertions and JSON request execution |
| [`examples/release_readiness`](examples/release_readiness) | Pilot evidence example for deterministic release decisions, public request invariants, and generated Python host types |

## Python API

Host applications can call GWT through the Python package instead of shelling
out to the CLI:

```python
import json

from gwtlang import GwtClient

client = GwtClient("examples/order_fulfillment/rules.gwt")
check = client.check()
if not check.ok:
    raise SystemExit(check.as_payload())

request = json.loads(open("examples/order_fulfillment/request.json").read())
execution = client.run_json(
    request,
    request="fulfill order",
)
payload = execution.as_payload()
print(payload["result"]["fulfillment"]["status"])
```

For production-style embedding, first make the rule check part of the local and
CI feedback loop:

```sh
python -m gwtlang validate examples/order_fulfillment/rules.gwt \
  --import-root examples/order_fulfillment \
  --no-absolute-imports
```

`gwt validate` catches parse/check/import/format failures and runs embedded
scenario content before the application starts. Then compile and check the
program once during application startup as a final safety gate, optionally
confining `USE` imports to the same known rule roots:

```python
from gwtlang import compile_file

rules = compile_file(
    "examples/order_fulfillment/rules.gwt",
    import_roots=["examples/order_fulfillment"],
    allow_absolute_imports=False,
)

execution = rules.run_json(
    request,
    request="fulfill order",
)
```

The same `--import-root` and `--no-absolute-imports` flags are available on
`gwt check`, `gwt inspect`, `gwt validate`, `gwt test`, and `gwt run` for
executable-spec and runner workflows.

The lower-level `check_file`, `run_file`, `run_json_file`, `run_text`, and
`run_json_text` functions are also available for callers that do not want a
client object. `GwtClient.inspect()` exposes the same manifest as
`gwt inspect`, and `GwtClient.validate()` exposes the local/CI validation
workflow from Python. `GwtClient.compile()` is the equivalent compile-once API
for a client object. For already-prevalidated internal loops,
`run_trusted_json()` skips only named-request input and output boundary
validation. `GwtClient.typescript_types()` and `generate_typescript_file()`
generate TypeScript declarations from checked GWT contracts.
`GwtClient.python_types()` and `generate_python_file()` generate Python helper
modules with `TypeAlias` declarations, `TypedDict` records, request/output
aliases, request-name constants, and a request-specific client wrapper.

Runnable Python host examples live in
[`examples/vendor_onboarding/host_app.py`](examples/vendor_onboarding/host_app.py)
and [`examples/exact_pricing/host_app.py`](examples/exact_pricing/host_app.py).
The vendor onboarding host is the typed executable-spec module path: it
validates the GWT file, inspects the public request manifest, compiles once,
and calls `review vendor` through generated Python types in
[`examples/vendor_onboarding/rules_types.py`](examples/vendor_onboarding/rules_types.py).
The exact-pricing host additionally shows exact `decimal` handling, float input
rejection, and trusted prevalidated execution.

The Python package includes a `py.typed` marker and typed payload aliases for
the public host boundary. The Pyright gate in
[`pyrightconfig.json`](pyrightconfig.json) runs in strict mode for the full
`gwtlang` package plus selected Python host and deployable API examples:

```sh
npx --yes pyright@1.1.410 --project pyrightconfig.json
```

GWT validates named request inputs and outputs at runtime, so Pydantic is not a
required dependency for ordinary host integration. Add host-side Pydantic models
only when an application needs its own pre-GWT request validation layer.

`.gwt` request files remain useful for examples and assertion-heavy tests:

```python
from gwtlang import run_file

execution = run_file(
    "examples/order_fulfillment/rules.gwt",
    request_file="examples/order_fulfillment/request_with_assertions.gwt",
)
```

## TypeScript Client

The CLI-backed TypeScript client lives in [`clients/typescript`](clients/typescript).
It uses the same JSON runner protocol as the Python API. Before a public npm
release, use the repository example or a local `file:` dependency.

```ts
import { createGwtProgram } from "@gwtlang/client";
import type { GwtOutputs, GwtRequests } from "./rules.js";

const rules = createGwtProgram<GwtRequests, GwtOutputs, "review vendor">({
  file: "examples/vendor_onboarding/rules.gwt",
  request: "review vendor",
});
const check = await rules.checkOnce();
if (!check.ok) {
  throw new Error(JSON.stringify(check.diagnostics));
}

const execution = await rules.runJson({ vendor });

console.log(execution.result.decision.status);
```

Generate `rules.d.ts` from the GWT source:

```sh
gwt types examples/vendor_onboarding/rules.gwt --language typescript --output rules.d.ts
```

With NodeNext-style ESM, import generated declarations through the runtime-style
`./rules.js` specifier. A complete typed host example lives at
[`clients/typescript/examples/vendor-onboarding.ts`](clients/typescript/examples/vendor-onboarding.ts).

The same analysis layer is available from Python:

```python
from gwtlang import analyze_source

analysis = analyze_source(source, "example.gwt")
print(analysis.diagnostics)
print(analysis.symbols)
```

## VS Code

VS Code support lives in [`vscode-gwt`](vscode-gwt). For local development:

```sh
cd gwt
python -m pip install -e .

cd vscode-gwt
npm install
```

Open the repository root in VS Code, choose **Run GWT VS Code Extension** in the
Run and Debug panel, then press `F5`. In the Extension Development Host window,
open a `.gwt` file such as `examples/language_tour/rules.gwt`.

The extension contributes Command Palette actions for the active `.gwt` file:

- `GWT: Validate Current File`
- `GWT: Test Current File`
- `GWT: Run Current File`
- `GWT: Format Current File`
- `GWT: Debug Current File`

The command output is streamed to the `GWT` output channel. During repository
development the extension runs `python -m gwtlang` with the repo on
`PYTHONPATH`; installed extensions fall back to the `gwt` command.

## Specs And Tests

The current versioned language spec is [`docs/spec/v0.2.md`](docs/spec/v0.2.md).
The longer language guide is [`docs/language.md`](docs/language.md), and the
EBNF grammar is [`docs/grammar.md`](docs/grammar.md). Design intent and
language-shape guardrails live in
[`docs/design-principles.md`](docs/design-principles.md). The current
variant/match design pressure from MiniLang is captured in
[`docs/variant-match-design.md`](docs/variant-match-design.md). Current
behavior-review product work is tracked in
[`docs/roadmap-v0.4.md`](docs/roadmap-v0.4.md). The preceding v0.3 stabilization
roadmap is [`docs/roadmap-v0.3.md`](docs/roadmap-v0.3.md), and its concrete
release-candidate gate is
[`docs/release-v0.3-checklist.md`](docs/release-v0.3-checklist.md),
release notes are in [`docs/release-notes-v0.3.md`](docs/release-notes-v0.3.md),
and real-workflow evaluation should use
[`docs/pilot-evaluation.md`](docs/pilot-evaluation.md).

Run tests:

```sh
python -m unittest discover
```

The GitHub Actions workflow in [`.github/workflows/ci.yml`](.github/workflows/ci.yml)
runs the standard validation gate, v0.2 conformance tests as part of the Python
suite, strict Pyright checking for the full Python package plus host examples,
generated TypeScript and Python vendor host fixture checks, Python and
TypeScript client tests, VS Code extension checks, and whitespace verification
with `git diff --check`.
