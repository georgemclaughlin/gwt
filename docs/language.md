# GWT Language Draft

GWT is an executable behavior language. A program describes public named
requests, reusable behavior, execution examples, and expected results.

See [spec/v0.2.md](spec/v0.2.md) for the current versioned specification,
[spec/v0.1.md](spec/v0.1.md) for the previous boundary model, and
[grammar.md](grammar.md) for the EBNF grammar. See
[design-principles.md](design-principles.md) for non-normative language-shape
guidance inspired by OpenSpec, GitHub Spec Kit, Cucumber, SpecFlow/Reqnroll,
and BDD examples. See [spec-is-code.md](spec-is-code.md) for the product thesis
behind making behavior specs executable instead of agent-interpreted handoff
documents. See [host-language-clients.md](host-language-clients.md) for the
serve-first cross-language integration model plus embedded Python and process
alternatives, and [http-service-design.md](http-service-design.md) for OpenAPI,
served-request behavior, and trust boundaries. Review
[execution-cases.md](execution-cases.md) for captured runs, named case corpora,
old/new comparison, and the local workbench; those are tooling artifacts rather
than additional language syntax. For the relationship between the core
language, program-specific domain DSLs, semantic models, and LLM authoring, see
[dsl-and-llms.md](dsl-and-llms.md) and [agent-authoring.md](agent-authoring.md).

## Program Shape

```gwt
PROGRAM name

USE "./module.gwt"

TYPE AccountStatus is "open" | "closed"

RECORD Account
  balance: number
  status: AccountStatus

REQUEST review account
  GIVEN account is Account
  WHEN review account
  OUTPUT account is Account
  THEN account.status != "blocked"

BACKGROUND
GIVEN state.path is value
AND other.path is value

GIVEN record is RecordName
  field: value
  nested:
    field: value

GIVEN rows are RowRecord
  | field | count |
  | "a"   | 1     |

WHEN behavior <parameter> from <target>
  GIVEN parameter is RecordName
  THEN returns number
  LET name be expression
  REQUIRE condition
  AND condition
  IF condition
    statement
  ELSE
    statement
  FOR name in expression WHERE condition
    statement
  RETURN expression
  PASS
  statement

WHEN concrete event from target
AND another concrete event
REQUEST review account

THEN state.path is value
AND other.path is value

THEN record is
  field: value

SCENARIO name
GIVEN state.path is value
REQUEST review account
THEN state.path is value

EXAMPLES
  | name | value |
  | a    | 1     |
```

`PROGRAM` is optional metadata. A file can contain one implicit scenario, or
multiple explicit `SCENARIO` blocks. Execution order for each scenario is:

1. Register named `REQUEST` blocks and block-form `WHEN` behavior definitions.
2. Run `BACKGROUND` and scenario `GIVEN` setup.
3. Run scenario single-line `REQUEST` and `WHEN` statements in source order.
4. Evaluate `BACKGROUND` and scenario `THEN` assertions.

When a scenario invokes a named request, the request validates its caller input,
runs request-local setup, executes its `WHEN` calls, validates `OUTPUT`, and
evaluates request-local `THEN` assertions before returning to the scenario.

`AND` repeats the previous top-level keyword. Inside a behavior block, `AND`
repeats the previous body keyword, which is most useful for chained `REQUIRE`
guards.

## Scenarios And Background

`SCENARIO` starts an independent run with fresh state.

```gwt
SCENARIO successful withdrawal
GIVEN account.balance is 100
WHEN withdraw 30 from account
THEN account.balance == 70
```

`BACKGROUND` contains shared setup that runs before each scenario.

```gwt
BACKGROUND
GIVEN account.status is "open"
AND fee is 3
```

Backgrounds are intentionally limited to setup and execution statements; they
cannot define block-form `WHEN` behavior.

Program-level block-form `WHEN` behavior can appear before scenarios and is
available to every scenario in the file.

## RECORD Contracts

`RECORD` declares the expected shape of input/state records:

```gwt
RECORD CartItem
  sku: text
  price: number

RECORD Cart
  items: list<CartItem>
  subtotal: number
  shipping: number
  discount: number
  total: number
```

`GIVEN name is RecordName` creates a record and validates it against the contract:

```gwt
GIVEN cart is Cart
  items: [20, 35, 45]
  subtotal: 0
  shipping: 0
  discount: 0
  total: 0
```

Record validation requires all declared fields, rejects unknown fields, and checks
primitive value types. Supported record field types are `number`, `integer`,
`decimal`, `text`, `boolean`, `list`, `any`, declared record names, declared
type aliases, typed collections such as `list<CartItem>` or
`list<DecisionStatus>`, and literal unions such as
`"new" | "approved" | "denied"`. Typed collections can also use inline literal
unions such as `list<"ready" | "manual_review">`.

An `optional<Type>` field may be omitted or supplied as JSON `null`; a present
value must satisfy `Type`. Missing and explicit null normalize to the same
absent value. Other record fields remain required.

`integer` is an exact whole number. `decimal` is a finite exact base-10 decimal value.
`number` is the legacy broad numeric type. `integer` can be assigned to
`decimal` or `number`; `decimal` can be assigned to `number`. At JSON
boundaries, `decimal` accepts finite exact decimal strings such as `"12.30"`
and integer JSON numbers such as `12`, but rejects JSON floats such as `12.30`
and non-finite strings such as `"NaN"` or `"Infinity"`. API and CLI payloads
serialize `decimal` values as strings.
Nested fields are declared with nested blocks:

```gwt
RECORD Account
  balance: number
  owner:
    name: text
```

Within a `RECORD`, field paths must not overlap. Declare either a scalar field
or a nested object field, not both:

```gwt
RECORD Account
  owner: text
    name: text # invalid: owner.name overlaps owner
```

Records are contracts only; they do not define behavior or methods. `RECORD`
is the only source spelling for record contracts.

## TYPE Aliases

`TYPE` gives a reusable name to an existing type expression:

```gwt
TYPE DecisionStatus is "new" | "approved" | "needs_review"
TYPE DecisionHistory is list<DecisionStatus>
TYPE ReviewReasons is list<"ready" | "manual_review">

RECORD Decision
  status: DecisionStatus
  history: DecisionHistory
  reasons: ReviewReasons
```

Aliases are contracts only. They do not define values, records, methods, or
runtime namespaces. They are useful for naming domain states that appear in
multiple records, request contracts, behavior contracts, or generated host
types.

Records can also describe values that are one of several named kinds:

```gwt
RECORD Statement is one of
  let_number:
    name: text
    value: number
  print_text:
    text: text
```

A one-of value contains an automatic `kind` field plus only the fields for its
active kind. Setup adds one concrete kind to a list:

```gwt
GIVEN program.statements is []

GIVEN program.statements contains a Statement of kind let_number
  name: "x"
  value: 2
```

This produces `{ "kind": "let_number", "name": "x", "value": 2 }`. Validation
rejects fields that do not belong to the active kind. In GWT setup, `kind` is
added automatically. In JSON input, include the same `kind` field shown in the
stored record.

## Named Requests

`REQUEST <natural phrase>` declares a public callable request. Its body owns the
input contract, request-local setup, execution plan, response shape, and
optional postconditions:

```gwt
RECORD CheckoutRequest
  subtotal: number
  shipping: number
  total: number

REQUEST checkout cart
  GIVEN cart is CheckoutRequest
  WHEN checkout cart
  OUTPUT cart is CheckoutRequest
```

Inside a named request:

- `GIVEN path is Type` without a body declares caller-provided input.
- `GIVEN path is Type` with a body creates request-local setup and validates it.
- other `GIVEN` forms create request-local setup.
- `WHEN command` calls reusable behavior or a built-in statement.
- `OUTPUT path is Type` declares the response shape and returned paths.
- `THEN condition` declares a postcondition.

`OUTPUT` and `THEN` are intentionally separate. `OUTPUT` answers what the caller
receives; `THEN` asserts what must be true after execution.

Contracts use the same type syntax as record fields and behavior contracts,
including type aliases, `list<Type>`, and literal unions. Request inputs validate before
the request `WHEN` calls. `OUTPUT` validates after request `WHEN` execution.

Within a request's inputs or within its outputs, contract paths must not
overlap. Declare either a whole record path or explicit leaf paths, not both:

```gwt
REQUEST checkout cart
  GIVEN cart is Cart
  AND cart.total is number # invalid: cart.total overlaps cart
  WHEN checkout cart
```

Request and output contracts are checked separately, so a `REQUEST` path may
overlap an `OUTPUT` path.

GWT v0.2 does not have a source-level `null` literal. JSON input can contain
`null` where a contract is `optional<Type>` or `any`; other typed contracts
reject it. An optional contract also accepts an omitted field or contract path.
Missing and JSON null intentionally collapse to the same absent value.

Use `optional<Type>` when absence is the only fact behavior needs. Use `any`
for raw untyped input, or normalize into status fields or one-of records when
missing, unknown, and not-applicable have different domain meanings.

Declared record, request input, `OUTPUT`, typed table, and behavior parameter
contracts also protect later writes. A `set`, `add`, or `subtract` that would
change a known numeric field to `text`, or replace a `list<OrderItem>` with a
non-list value, fails at the mutation line.

## Behavior Contracts

Block-form `WHEN` behaviors can declare parameter and return contracts before
their executable body:

```gwt
WHEN cart total for <cart>
  GIVEN cart is Cart
  THEN returns number
  RETURN cart.total
```

Contract `GIVEN` lines describe behavior parameters, not global state. They are
metadata for `gwt check`, future editor tooling, and documentation. Contract
types can use record field types (`number`, `text`, `boolean`, `list`, `any`,
declared record names, type aliases, `list<Type>`, or literal unions).

`AND` can continue contract `GIVEN` lines:

```gwt
WHEN checkout <cart> for <customer>
  GIVEN cart is Cart
  AND customer is Customer
  set cart.total to 1
```

`THEN returns Type` declares the behavior's return type. If a behavior declares
a return type, `gwt check` verifies that the body contains a `RETURN` statement and
that statically known return values match the declared type.

## Imports

`USE` imports behavior definitions from another GWT file:

```gwt
USE "./banking_module.gwt"
```

Relative paths are resolved from the importing file. Imported scenarios are not
run; imports are for reusable behavior. If a local behavior has the same
signature as an imported behavior, the later local definition is tried first.

## Request Mode

The CLI can run a behavior file with a separate GWT-shaped request file:

```sh
python -m gwtlang run examples/checkout/rules.gwt --input examples/checkout/request.gwt --json
```

The program file provides records, named requests, and reusable block-form
`WHEN` behavior. The input file provides ordinary `GIVEN` setup, single-line
`REQUEST` calls, and optional `THEN` steps. This makes GWT usable as a
deterministic workflow runner while keeping inputs in the same language shape.
Request files cannot declare `PROGRAM`, define behavior or named requests, or
use direct single-line `WHEN` calls. Use ordinary program scenarios for
low-level behavior checks.

Request files can use records declared by the program file.

If a named request declares caller-provided `GIVEN path is Type` inputs, request
files must provide those paths through setup before invoking that request. The
`result` field in CLI JSON and API payloads contains only the invoked request's
declared `OUTPUT` paths.

For production-style embedding, callers can provide initial state as JSON and
name the public request to execute:

```sh
python -m gwtlang run examples/order_fulfillment/rules.gwt \
  --json-input examples/order_fulfillment/request.json \
  --request "fulfill order" \
  --json
```

Use `--json-input -` to read the JSON object from stdin. This gives other host
languages a simple client protocol before they have native SDKs:

```sh
printf '%s' "$REQUEST_JSON" | python -m gwtlang run rules.gwt \
  --json-input - \
  --request "review vendor" \
  --json
```

The JSON file must contain an object whose keys are GWT state paths. Nested
JSON objects are ordinary record values:

```json
{
  "order": {
    "order_id": "A200",
    "payment_status": "paid",
    "fraud_score": 12,
    "expedited": true,
    "items": [
      { "sku": "widget", "quantity": 1 },
      { "sku": "gadget", "quantity": 2 }
    ]
  }
}
```

The runtime loads program `BACKGROUND` setup first, then JSON state, then
validates the named request inputs, runs request-local setup and `WHEN` calls,
validates `OUTPUT`, and returns the same stable execution envelope used by
`.gwt` request files. `EXPORT` and raw behavior-call execution are not part of
the v0.2 public interface.

JSON `null` values are accepted where the receiving contract is `any` or
`optional<Type>`. An optional path may also be omitted; both representations
become the same absent runtime value. They do not match other typed records or
primitive fields. Prefer explicit domain state when different kinds of absence
affect behavior.

## Embedding API

Host applications can call GWT through the Python package instead of shelling
out to the CLI:

```python
from gwtlang import GwtClient

client = GwtClient("rules.gwt")
check = client.check()
if check.ok:
    execution = client.run_json(
        request_state,
        request="review report",
    )
    state = execution.state
```

For production-style embedding, use the CLI as the local and CI feedback path:

```sh
python -m gwtlang check rules.gwt \
  --import-root rules \
  --no-absolute-imports
```

That command parses imports with the same confinement policy the host should use
in production, so broken rules fail before the app boots. Application startup
should still compile and check the program once as a final safety gate:

```python
from gwtlang import compile_file

rules = compile_file(
    "rules.gwt",
    import_roots=["rules"],
    allow_absolute_imports=False,
)

execution = rules.run_json(
    request_state,
    request="review report",
)
```

The compiled program keeps the parsed and checked program in memory and creates
a fresh runtime for each execution. `import_roots` confines `USE` imports to
known directories, matching `--import-root`, and
`allow_absolute_imports=False` matches `--no-absolute-imports`.
The same import-confinement flags are available on `gwt test` and `gwt run`.

For already-prevalidated internal loops, `GwtClient.run_trusted_json()` and
compiled-program `run_trusted_json()` skip only named-request input and output boundary
validation. Behavior contracts, runtime type checks, assertions, and ordinary
runtime errors still apply.

`GwtClient` is a small facade over the lower-level `check_file`, `run_file`,
`run_json_file`, and `compile_file` functions. `check_file` returns a
structured result with `ok`, `diagnostics`, and `as_payload()`. `run_file`,
`run_json_file`, and compiled-program `run_json` return an execution result
with `state`, `output`, `scenarios`, and `as_payload()`. `state` is the full
final runtime state. `as_payload()` always returns an envelope with `ok`,
`file`, `request_file`, `scenario_count`, `scenarios`, `state`, `result`, and
`output`. The top-level `state`, `result`, and `output` values are populated
for single-scenario runs; multi-scenario details are always available under
`scenarios`.

## Generated Host Types

The same `TYPE`, `RECORD`, and named request boundaries can generate
host-language types. For TypeScript:

```sh
python -m gwtlang types rules.gwt --language typescript --output rules.d.ts
```

The generated declaration file includes type aliases, record interfaces,
one-of record unions, per-request input/output interfaces, `GwtRequestName`,
`GwtRequests`, `GwtOutputs`, `GwtRequest`, and `GwtOutput`. Generated
TypeScript maps
`integer` and `number` to `number`, and maps `decimal` to `string` at the JSON
boundary. These declarations are integration helpers for host code; the `.gwt`
source remains the normative contract.
For `optional<Type>`, generated record and request properties use
`property?: Type | null`.
Generated TypeScript uses nested object shape for dotted contract paths. Raw
CLI JSON input may still provide state through dotted path keys such as
`"cart.total"`, or through nested objects that produce the same state.

TypeScript callers can pair generated types with the CLI-backed client:

```ts
import { GwtClient } from "@gwtlang/client";
import type { GwtOutput, GwtRequest, GwtRequestName } from "./rules.js";

const input: GwtRequest = { vendor };
const request: GwtRequestName = "review vendor";
const client = new GwtClient("rules.gwt");
const execution = await client.runJson<GwtRequest, GwtOutput>(input, {
  request,
});

execution.result.decision.status;
```

With NodeNext-style ESM, import the generated `rules.d.ts` declarations through
the runtime-style `./rules.js` specifier.

For a complete host example, see
[`clients/typescript/examples/vendor-onboarding.ts`](../clients/typescript/examples/vendor-onboarding.ts).

For Python:

```sh
python -m gwtlang types rules.gwt --language python --output rules_types.py
```

The generated Python module includes `TypeAlias` declarations, `TypedDict`
records, per-request request/output shapes, `GwtRequestName`, `GwtRequest`,
`GwtOutput`, request-name constants, and a program-specific client wrapper.
Generated Python maps `integer` to `int`, `number` to `int | float`, and
`decimal` to `str` at the JSON boundary.
For `optional<Type>`, generated record and request properties use
`NotRequired[Type | None]`.

```python
from rules_types import PricingClient, PriceCartRequest

rules = PricingClient.from_file("rules.gwt")
request: PriceCartRequest = {"cart": cart}
result = rules.price_cart(request)
```

## Static Checking

`gwt check file.gwt` parses a program and runs semantic checks without
executing scenarios. The checker is intentionally conservative: reusable
workflow files can still refer to request/state paths that are supplied later.

The current checker reports:

- unmatched behavior calls and signature/arity mismatches
- duplicate behavior signatures within the same source file
- reserved behavior names that conflict with built-ins or behavior-body keywords
- duplicate or invalid behavior parameters
- invalid built-in statement shapes
- `LET`, `RETURN`, and `PASS` outside behavior bodies
- `LET` names that overwrite parameters or earlier local names
- `LET` bindings to behavior calls that do not return a value
- invalid `DECIDE` branch conditions and branch body statements
- invalid expression syntax in statically checkable expressions
- missing `EXAMPLES` placeholders
- obvious `FOR` use over a scalar literal
- obvious `FIND` use over a scalar literal
- unknown behavior contract types
- unknown `REQUEST` / `OUTPUT` contract types
- typed table row shape/type mismatches
- statically obvious `set`, `add`, `subtract`, `append`, `count`, `sum`,
  `find`, `exists`, and `FIND` type mismatches on known record/contract fields
- statically known behavior argument and return type mismatches
- implicit behavior parameters as deprecation warnings

`gwt check --lint` and `gwt validate --lint` add opt-in lint warnings for
quality conventions that are useful during design review but too opinionated
for the default checker. Current lint warnings include public requests without
scenario evidence, bare `list` contracts where `list<Type>` would be clearer,
requests that declare `OUTPUT` without a request-level `THEN` invariant, and
behavior parameters without `GIVEN` contracts.

`gwt check --json` includes editor-oriented diagnostics with codes, severity,
source ranges, and a symbol list for records, type aliases, record fields,
named requests, behavior signatures, parameters, local names, and scenarios.

`gwt format file.gwt` rewrites a valid GWT file using the canonical current source
layout. Use `gwt format file.gwt --check` in CI to fail when a file needs
formatting, or `gwt format file.gwt --stdout` to print the formatted source
without writing.

The same language-service API is available to tools:

```python
from gwtlang import analyze_source

analysis = analyze_source(source, "example.gwt")
analysis.diagnostics
analysis.symbols
analysis.program
```

`gwt lsp` starts a minimal Language Server Protocol server over stdio. It
currently supports:

- publish diagnostics on document open/change
- document symbols
- hover for known records, fields, behaviors, parameters, and locals
- go-to-definition for behavior calls
- completions for known language symbols

`gwt debug file.gwt --breakpoint line` runs a GWT file using the debugger
protocol. The VS Code extension uses this mode to support line breakpoints,
continue, step over, source-level call stacks, and state/local variable
inspection.

`gwt debug-lines file.gwt --json` reports the executable source lines that can
accept debugger breakpoints. The VS Code extension uses this to verify
breakpoints and reject lines such as declarations and `EXAMPLES` rows.

## Examples Tables

`EXAMPLES` turns one scenario into multiple scenario runs by replacing
`<placeholders>` in that scenario's `GIVEN`, single-line `WHEN`, and `THEN`
statements.

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

Each table value is inserted as source text. Quote string values in the table
when they should be strings:

```gwt
  | status |
  | "open" |
```

## Values

Supported values:

- integer literals: `10`
- decimal literals: `3.14`
- strings: `"open"`
- booleans: `true`, `false`
- lists: `[10, 20, 30]`
- paths: `account.balance`, `count`

There is no `null` source literal in GWT source. Optional values come from
typed boundaries and are inspected with `is present` or `is absent`. Model
missing, unknown, or not-applicable as explicit domain cases when those states
have different meanings.

## State

State is a nested object map. Paths use dot notation:

```gwt
GIVEN account.balance is 100
AND account.status is "open"
```

This creates:

```json
{
  "account": {
    "balance": 100,
    "status": "open"
  }
}
```

Record blocks are shorthand for dotted paths:

```gwt
GIVEN account is
  balance: 100
  status: "open"
  owner:
    name: "Ada"
```

This is equivalent to:

```gwt
GIVEN account.balance is 100
AND account.status is "open"
AND account.owner.name is "Ada"
```

`THEN` supports the same record block shape for grouped assertions:

```gwt
THEN account is
  balance: 70
  status: "open"
```

Record blocks support object fields, nested object fields, and expression
values such as list literals.

## Data Tables

`GIVEN path are` creates a list of records from a pipe table:

```gwt
GIVEN order.items are
  | sku      | quantity |
  | "widget" | 2        |
  | "gadget" | 1        |
```

Typed tables validate every row against a record and give the checker a typed
collection:

```gwt
RECORD OrderItem
  sku: text
  quantity: number

RECORD Order
  items: list<OrderItem>

GIVEN order.items are OrderItem
  | sku      | quantity |
  | "widget" | 2        |
  | "gadget" | 1        |
```

This creates:

```json
{
  "order": {
    "items": [
      { "sku": "widget", "quantity": 2 },
      { "sku": "gadget", "quantity": 1 }
    ]
  }
}
```

Table headers become record field names. Cell values use the normal GWT value
and expression syntax, so quote strings and leave numbers/booleans unquoted.
When a table names a record, each row must include all record fields, cannot include
unknown fields, and must match the record field types.
Scenario `EXAMPLES` placeholders can be used inside table cells.

## Statements

```gwt
set path to value
add value to path
subtract value from path
append value to path
count list into path
sum list into path
sum item.amount in list into path
find name in list where condition into path
find optional name in list where condition into path
exists name in list where condition into path
print value
```

Behavior branches can use `PASS` when the branch is intentionally successful
and does not need to mutate state:

```gwt
FIND token in tokens WHERE token.lexeme == "let"
  PASS
ELSE
  append "missing_let" to errors
```

Examples:

```gwt
set account.status to "closed"
add 5 to count
subtract amount from account.balance
subtract amount + fee from account.balance
append item.name to invoice.names
count invoice.items into invoice.count
sum item.quantity in invoice.items into invoice.total_quantity
find item in invoice.items where item.name == "mouse" into invoice.found
find optional item in invoice.items where item.name == "trackpad" into invoice.found
exists item in invoice.items where item.name == "keyboard" into invoice.has_keyboard
print account.balance
```

`value` can be an expression. If the target path contains a known type from a record,
program contract, typed table, or behavior contract, mutations are checked
against that type immediately.

Collection helpers operate on lists. `append` adds one value to a list target,
`count` stores the list length, `sum` stores the total of a numeric list, and
projected `sum` totals a numeric field from each item. `find` stores the first
item matching its condition or fails if none matches. `find optional` leaves
the target unchanged when no item matches. `exists` stores whether any item
matches.

For workflows that need to immediately act on one matched record, use the
uppercase `FIND` behavior block:

```gwt
FIND item in inventory.items WHERE item.sku == order_item.sku
  reserve_known_item order_item using item into fulfillment
ELSE
  add 1 to fulfillment.unknown_sku_count
```

`FIND` binds the first matching item as a local name for its body. The `ELSE`
body is required so the missing case is explicit. If the matched item is a
record from a list, mutations such as `subtract quantity from item.available`
update that record in the original list.

## Local Bindings

Behavior blocks can bind local names:

```gwt
WHEN withdraw <amount> from <account>
  LET total be amount + fee
  REQUIRE account.balance >= total
  subtract total from account.balance
```

`LET` values exist only for the current behavior call. They can reference
parameters, state, and earlier `LET` values. They cannot overwrite parameters
or state paths.

## Control Flow

Behavior blocks can branch with `IF` and optional `ELSE`:

```gwt
WHEN withdraw <amount> from <account>
  LET total be amount + fee
  IF account.balance < total
    set account.last_transaction to "declined"
  ELSE
    subtract total from account.balance
    set account.last_transaction to "approved"
```

`IF` conditions use the same comparison language as `REQUIRE` and `THEN`.
Nested `IF` blocks are allowed. Branches share the current behavior call's
local bindings and state.

Behavior blocks can also iterate over lists:

```gwt
GIVEN cart.items are
  | sku      | price |
  | "widget" | 10    |
  | "gadget" | 20    |

GIVEN cart.total is 0

WHEN total <cart>
  FOR item in cart.items
    add item.price to cart.total
```

`FOR` can filter iterations with `WHERE`:

```gwt
FOR item in invoice.items WHERE item.quantity > 1
  append item.name to invoice.names
```

`FOR` loop variables are local to each iteration. Returning from inside a loop
exits the current behavior. When a loop item is a record, its fields can be
read with dot paths such as `item.price`.

`FIND` uses the same list and condition shape as `FOR ... WHERE`, but executes
only the first matching item and requires an `ELSE` block:

```gwt
FIND line in invoice.items WHERE line.sku == requested_sku
  set line.status to "reserved"
ELSE
  set invoice.status to "missing_item"
```

The matched name exists only in the match body, not in the `ELSE` body.

Behavior blocks can express ordered priority rules with `DECIDE`:

```gwt
DECIDE
  WHEN decision.has_severe_signal
    block risk with severe_signal into decision
  WHEN decision.risk_score >= 60
    route risk to review with high_score into decision
  ELSE
    approve risk with low_risk into decision
```

`DECIDE` evaluates branch conditions from top to bottom and executes exactly the
first true branch. If no branch matches, it executes `ELSE`. The `ELSE` block is
required so the default outcome is explicit; use an `ELSE` block containing
`PASS` when no default mutation is needed. Branch conditions use the same
condition syntax as `IF`, `REQUIRE`, and `THEN`.

Behavior blocks can branch on one-of record kinds with `DEPENDING ON`:

```gwt
DEPENDING ON statement
  WHEN the kind is let_number
    add statement.value to result.total
  WHEN the kind is print_text
    append statement.text to result.output
  ELSE
    append "unknown_statement" to result.errors
```

`ELSE` is required unless every declared kind is covered. Inside
`DEPENDING ON statement`, `WHEN the kind is let_number` means `statement.kind`
is `let_number`. GWT can then check ordinary paths such as `statement.value`
and `statement.text` for the active kind.

`DEPENDING ON` can also branch on scalar literal values:

```gwt
DEPENDING ON mode
  WHEN the value is "reserve"
    set decision.status to "reserved"
  WHEN the value is "quote"
    set decision.status to "quoted"
  ELSE
    set decision.status to "manual_review"
```

Value branches are literal-only and type-aware. `"1"` does not match `1`, and
integer `1` does not match decimal `1.0`. A block cannot mix
`WHEN the kind is` and `WHEN the value is` branches. `ELSE` is required unless
the expression has a finite literal-union type and every value is covered.
For broad `number` expressions, decimal-looking branch literals match host
number values by numeric value; use `decimal` when exact decimal matching is
required.

Use `DECIDE` for first-matching priority policies over arbitrary conditions.
Use `DEPENDING ON` when dispatching on one known value or one one-of record
kind.

## Return Values

Behavior can return a value:

```gwt
WHEN calculate fee for <amount>
  RETURN amount * 0.1
```

Returned behavior calls can be bound with `LET`:

```gwt
WHEN withdraw <amount> from <account>
  LET fee be calculate fee for amount
  LET total be amount + fee
  subtract total from account.balance
```

`RETURN` exits the current behavior immediately. Calling a returning behavior
with a single-line `WHEN` is allowed, but the returned value is discarded.

## Expressions

Expressions support:

```gwt
1 + 2 * 3
(amount + fee) / 2
account.balance >= amount + fee
account.status == "open" and account.balance >= amount
response.body contains "200"
not response.body contains "500"
not account.locked
limits.amount_max is present
limits.amount_max is absent
```

Supported operators:

- arithmetic: `+`, `-`, `*`, `/`
- comparison: `==`, `!=`, `>`, `<`, `>=`, `<=`, `contains`
- boolean: `and`, `or`, `not`
- presence: `is present`, `is absent`

`contains` checks substrings for text values and membership for lists.
`not` negates a whole comparison before combining with `and` or `or`, so
`not tags contains "xml"` means `not (tags contains "xml")`. In conditions,
`value does not contain item` is also accepted as a readable alias for
`not (value contains item)`.

Presence checks are intended for `optional<Type>` paths. The checker narrows a
directly guarded path inside the matching branch:

```gwt
IF limits.amount_max is present
  REQUIRE item_total <= limits.amount_max
ELSE
  PASS
```

The inner value cannot be used by operators until it is guarded. Narrowing is
branch-local; it does not currently propagate through compound conditions or
after a branch returns.

## Behavior

Behavior is defined with block-form `WHEN` and executed with single-line
`WHEN`.

```gwt
WHEN deposit <amount> into <account>
  add amount to account.balance

WHEN deposit 30 into account
```

The first word after `WHEN` is the behavior name. In the preferred explicit
form, parameters are written as `<name>` in the signature and are referenced by
bare `name` inside the behavior body. Any unmarked word is matched literally:

```gwt
WHEN add line <item> to <invoice>
  GIVEN item is LineItem
  AND invoice is Invoice
  add item.quantity to invoice.count

WHEN add line widget to invoice
```

Older implicit signatures are still executable for compatibility: when a
signature has no `<name>` parameters, non-connector words after the behavior
name are treated as parameters, while connector words such as `from`, `into`,
`to`, `with`, `by`, and `for` are matched literally. `gwt check` emits a
deprecation warning for implicit parameters, and new code should use explicit
`<name>` parameters.

## Requirements

`REQUIRE` stops a behavior if a condition is false.

```gwt
REQUIRE account.balance is at least amount
AND account.status is "open"
AND account.balance >= amount + fee
```

## Conditions And Assertions

Conditions and `THEN` assertions share the same comparison language:

```gwt
path is value
path is not value
path is greater than value
path is less than value
path is at least value
path is at most value
expression == expression
expression >= expression
expression contains expression
not expression contains expression
expression does not contain expression
expression and expression
```

English comparisons are converted to expression comparisons internally:

```gwt
account.balance is at least amount
```

means:

```gwt
account.balance >= amount
```

## The Role Of WHEN

In current GWT, `WHEN` has two forms.

Block-form `WHEN` defines behavior:

```gwt
WHEN withdraw <amount> from <account>
  REQUIRE account.balance >= amount
  subtract amount from account.balance
```

Single-line `WHEN` executes behavior or built-in statements:

```gwt
WHEN withdraw 30 from account
AND set account.status to "closed"
```

The important constraint is that `WHEN` always represents behavior crossing
from possibility into execution.

## Diagnostics

The CLI formats runtime and parser failures with source context:

```text
gwt: examples/bank.gwt:12: unknown name: total
  REQUIRE account.balance >= total
                            ^^^^^
```
