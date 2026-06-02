# GWT

GWT is a small experimental programming language built around executable
`GIVEN / WHEN / THEN` programs. It is meant for deterministic workflows,
rules, examples, and request/response style programs that should read close to
their behavior specification. OpenSpec's persistent-spec idea was an original
inspiration, though GWT does not use or depend on OpenSpec: GWT takes the
spec-driven collaboration point and makes the spec itself executable, rather
than treating the spec as a prompt or handoff document for separate code. The
language is also shaped by Cucumber,
SpecFlow/Reqnroll, and BDD examples; new features should stay behavior-oriented
and should not drift toward SQL-like query syntax.

## Quick Start

Run the hello world example:

```sh
python -m gwtlang run examples/hello.gwt --json
```

Install a local `gwt` command while developing:

```sh
python -m pip install -e .
gwt run examples/hello.gwt --json
```

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

The JSON result is a stable envelope:

```json
{
  "ok": true,
  "scenario_count": 1,
  "result": {
    "decision": {
      "line_count": 4,
      "submitted_total": 297,
      "approved_total": 60,
      "has_violation": true,
      "status": "needs_review"
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

## Tooling

The CLI currently supports:

```sh
gwt run examples/bank.gwt
gwt run examples/order_fulfillment/rules.gwt --json-input examples/order_fulfillment/request.json --entry "fulfill order from inventory into fulfillment" --json
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

## Python API

Host applications can call GWT through the Python package instead of shelling
out to the CLI:

```python
import json

from gwtlang import check_file, run_json_file

check = check_file("examples/order_fulfillment/rules.gwt")
if not check.ok:
    raise SystemExit(check.as_payload())

request = json.loads(open("examples/order_fulfillment/request.json").read())
execution = run_json_file(
    "examples/order_fulfillment/rules.gwt",
    request,
    entry="fulfill order from inventory into fulfillment",
)
print(execution.state["fulfillment"]["status"])
print(execution.as_payload()["result"])
```

`.gwt` request files remain useful for examples and assertion-heavy tests:

```python
from gwtlang import run_file

execution = run_file(
    "examples/order_fulfillment/rules.gwt",
    request_file="examples/order_fulfillment/request_with_assertions.gwt",
)
```

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
cd /home/g/code/gwt
python -m pip install -e .

cd vscode-gwt
npm install
```

Open `/home/g/code/gwt` in VS Code, choose **Run GWT VS Code Extension** in the
Run and Debug panel, then press `F5`. In the Extension Development Host window,
open a `.gwt` file such as `/home/g/code/gwt/examples/v01_language_tour/rules.gwt`.

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
