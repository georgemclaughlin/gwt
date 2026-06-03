# GWT

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

## Spec Is Code

BMAD, GitHub Spec Kit, and OpenSpec are useful signs of the same shift: humans
and agents need durable specs instead of one-off prompts. GWT pushes on a
different boundary. It treats executable behavior as the source of truth.

Markdown specs can reduce ambiguity, but they still require interpretation.
GWT removes the semantic handoff for deterministic domain behavior:

- `GIVEN` setup is runtime state, not prose about state.
- `WHEN` behavior is executable logic, not a step name backed by separate code.
- `THEN` assertions are regression checks, not suggestions.
- `REQUEST` and `OUTPUT` contracts are host-facing runtime boundaries.

GWT does not remove all product ambiguity. It forces behavior ambiguity to be
resolved before the spec becomes executable.

## Host Language Clients

GWT is intended to plug into ordinary application stacks through explicit JSON
boundaries. A host application can own UI, persistence, network calls, and
deployment while GWT owns deterministic domain behavior.

The current Python package is the reference client API. Other host-language
clients can wrap the same runtime contract:

```text
host app -> JSON request object -> GWT entry behavior -> typed result envelope
```

The CLI also supports a portable runner protocol for early clients in .NET,
Java, TypeScript, Go, Ruby, or any language that can spawn a process:

```sh
printf '%s' "$REQUEST_JSON" | gwt run rules.gwt \
  --json-input - \
  --entry "review vendor into decision" \
  --json
```

GWT can also generate TypeScript declaration files from `RECORD`, `REQUEST`, and
`OUTPUT` contracts:

```sh
gwt types examples/vendor_onboarding/rules.gwt --language typescript \
  --output vendor-onboarding.d.ts
```

See [`docs/host-language-clients.md`](docs/host-language-clients.md) for the
client-library model and boundary rules. The first CLI-backed Node/TypeScript
client lives in [`clients/typescript`](clients/typescript), with a typed host
example in
[`clients/typescript/examples/vendor-onboarding.ts`](clients/typescript/examples/vendor-onboarding.ts).

## Quick Start

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
  --entry "review vendor into decision" \
  --json
```

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
| [`docs/spec-is-code.md`](docs/spec-is-code.md) | Short thesis note on executable specs versus agent-interpreted planning artifacts |
| [`docs/host-language-clients.md`](docs/host-language-clients.md) | Integration model for Python, .NET, Java, TypeScript, and other host-language clients |
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

Program contracts define the host-facing interface:

```gwt
REQUEST report is ExpenseReport
AND decision is ExpenseDecision

OUTPUT decision is ExpenseDecision
```

`REQUEST` contracts are validated after setup and before execution. `OUTPUT`
contracts are validated after execution. When outputs are declared, JSON/API
payloads put only those paths under `result`; the full final state stays under
`state`.

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

The fuller version lives in
[`examples/v01_language_tour`](examples/v01_language_tour).

Run it as embedded regression coverage:

```sh
python -m gwtlang test examples/v01_language_tour/rules.gwt
```

Run it like an app would, with a separate request file:

```sh
python -m gwtlang run examples/v01_language_tour/rules.gwt --input examples/v01_language_tour/request.gwt --json
```

Production callers can also provide JSON state and an explicit entry behavior:

```sh
python -m gwtlang run examples/order_fulfillment/rules.gwt \
  --json-input examples/order_fulfillment/request.json \
  --entry "fulfill order from inventory into fulfillment" \
  --json
```

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
gwt run examples/order_fulfillment/rules.gwt --json-input examples/order_fulfillment/request.json --entry "fulfill order from inventory into fulfillment" --json
gwt types examples/vendor_onboarding/rules.gwt --language typescript --output vendor-onboarding.d.ts
gwt test examples/checkout_scenarios.gwt
gwt check examples/checkout_app.gwt
gwt format examples/bank.gwt --check
gwt lsp
gwt debug-lines examples/checkout_scenarios.gwt --json
```

`gwt check` parses a program and runs semantic checks without executing
scenarios. It reports problems such as unmatched behavior calls, duplicate
behavior signatures, invalid built-in statement shapes, type mismatches, and
`LET`/`RETURN` misuse. It also warns about deprecated implicit behavior
parameters. JSON output includes diagnostic codes, source ranges, and symbols
for editor tooling.

`gwt format file.gwt` rewrites valid source to the canonical v0.1 layout.
`gwt format file.gwt --check` is intended for CI.

`gwt types file.gwt --language typescript` generates host TypeScript
declarations from `RECORD`, `REQUEST`, and `OUTPUT` contracts. The generated
types are integration helpers; the `.gwt` file remains the source of truth.

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
| [`examples/records.gwt`](examples/records.gwt) | Record-shaped state |
| [`examples/let.gwt`](examples/let.gwt) | Local bindings |
| [`examples/control_flow.gwt`](examples/control_flow.gwt) | `IF` / `ELSE` |
| [`examples/return_values.gwt`](examples/return_values.gwt) | Returning values from behavior |
| [`examples/examples_table.gwt`](examples/examples_table.gwt) | Scenario examples tables |
| [`examples/use_import.gwt`](examples/use_import.gwt) | `USE` imports |
| [`examples/collections.gwt`](examples/collections.gwt) | List iteration |
| [`examples/record_contracts.gwt`](examples/record_contracts.gwt) | Record validation |
| [`examples/typed_contracts.gwt`](examples/typed_contracts.gwt) | Behavior parameter and return contracts |
| [`examples/typed_tables.gwt`](examples/typed_tables.gwt) | Typed tables and collection helpers |
| [`examples/v01_language_tour`](examples/v01_language_tour) | A compact tour of v0.1 |
| [`examples/loan_underwriting`](examples/loan_underwriting) | Larger rules/workflow sample |
| [`examples/order_fulfillment`](examples/order_fulfillment) | Larger state-transition workflow |
| [`examples/inventory_allocation_spike`](examples/inventory_allocation_spike) | List-shaped inventory pressure test |
| [`examples/minilang_spec`](examples/minilang_spec) | Executable spec for a tiny interpreter pipeline |
| [`examples/input_normalization`](examples/input_normalization) | JSON boundary normalization and explicit missing/null behavior |
| [`examples/minilang2_vm`](examples/minilang2_vm) | Bytecode VM pressure test with modules, closures, stack traces, debugger state, and REPL-like execution |
| [`examples/vendor_onboarding`](examples/vendor_onboarding) | Practical typed workflow demo with embedded scenario assertions and JSON request execution |

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
    entry="fulfill order from inventory into fulfillment",
)
payload = execution.as_payload()
print(payload["result"]["fulfillment"]["status"])
```

The lower-level `check_file`, `run_file`, `run_json_file`, `run_text`, and
`run_json_text` functions are also available for callers that do not want a
client object. `GwtClient.typescript_types()` and
`generate_typescript_file()` generate TypeScript declarations from checked GWT
contracts.

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
import { GwtClient } from "@gwtlang/client";
import type { GwtOutput, GwtRequest } from "./rules.js";

const client = new GwtClient("examples/vendor_onboarding/rules.gwt");
const check = await client.check();
if (!check.ok) {
  throw new Error(JSON.stringify(check.diagnostics));
}

const execution = await client.runJson<GwtRequest, GwtOutput>(request, {
  entry: "review vendor into decision",
});

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
open a `.gwt` file such as `examples/v01_language_tour/rules.gwt`.

## Specs And Tests

The versioned language spec starts at [`docs/spec/v0.1.md`](docs/spec/v0.1.md).
The longer language guide is [`docs/language.md`](docs/language.md), and the
EBNF grammar is [`docs/grammar.md`](docs/grammar.md). Design intent and
language-shape guardrails live in
[`docs/design-principles.md`](docs/design-principles.md). The current
variant/match design pressure from MiniLang is captured in
[`docs/variant-match-design.md`](docs/variant-match-design.md).

Run tests:

```sh
python -m unittest discover
```
