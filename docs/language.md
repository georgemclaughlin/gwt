# GWT Language Draft

GWT is an executable behavior language. A program describes initial state,
named behavior, execution, and expected results.

See [spec/v0.1.md](spec/v0.1.md) for the versioned v0.1 specification and
[grammar.md](grammar.md) for the EBNF grammar.

## Program Shape

```gwt
PROGRAM name

USE "./module.gwt"

DTO Account
  balance: number
  status: text

REQUEST request.path is Account
OUTPUT result.path is Account

BACKGROUND
GIVEN state.path is value
AND other.path is value

GIVEN record is DtoName
  field: value
  nested:
    field: value

GIVEN rows are RowDto
  | field | count |
  | "a"   | 1     |

WHEN behavior <parameter> from <target>
  GIVEN parameter is DtoName
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
  statement

WHEN concrete event from target
AND another concrete event

THEN state.path is value
AND other.path is value

THEN record is
  field: value

SCENARIO name
GIVEN state.path is value
WHEN concrete event from target
THEN state.path is value

EXAMPLES
  | name | value |
  | a    | 1     |
```

`PROGRAM` is optional metadata. A file can contain one implicit scenario, or
multiple explicit `SCENARIO` blocks. Execution order for each scenario is:

1. Register all block-form `WHEN` behavior definitions.
2. Run `BACKGROUND` `GIVEN` and `WHEN` statements.
3. Run the scenario's `GIVEN` and single-line `WHEN` statements.
4. Evaluate `BACKGROUND` and scenario `THEN` assertions.

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

## DTO Contracts

`DTO` declares the expected shape of input/state records:

```gwt
DTO CartItem
  sku: text
  price: number

DTO Cart
  items: list<CartItem>
  subtotal: number
  shipping: number
  discount: number
  total: number
```

`GIVEN name is DtoName` creates a record and validates it against the contract:

```gwt
GIVEN cart is Cart
  items: [20, 35, 45]
  subtotal: 0
  shipping: 0
  discount: 0
  total: 0
```

DTO validation requires all declared fields, rejects unknown fields, and checks
primitive value types. Supported DTO field types are `number`, `text`,
`boolean`, `list`, `any`, declared DTO names, and typed collections such as
`list<CartItem>`. Nested fields are declared with nested blocks:

```gwt
DTO Account
  balance: number
  owner:
    name: text
```

DTOs are contracts only; they do not define behavior or methods.

## Program Contracts

`REQUEST` declares state a host or request file must provide before execution.
`OUTPUT` declares state the program promises to return after execution:

```gwt
DTO CheckoutRequest
  subtotal: number
  shipping: number
  total: number

REQUEST cart is CheckoutRequest
OUTPUT cart is CheckoutRequest
```

Contracts use the same type syntax as DTO fields and behavior contracts,
including `list<DtoName>`. `REQUEST` contracts are validated after all `GIVEN`
setup has run and before any `WHEN` execution. `OUTPUT` contracts are validated
after `WHEN` execution. When a program has one or more `OUTPUT` declarations,
JSON/API payloads use a stable envelope. The top-level `result` value contains
only declared output paths when `OUTPUT` contracts are present; `state` still
keeps the full final runtime state for debugging and tests.

Declared DTO, `REQUEST`, `OUTPUT`, typed table, and behavior parameter
contracts also protect later writes. A `set`, `add`, or `subtract` that would
change a known `number` field to `text`, or replace a `list<OrderItem>` with a
non-list value, fails at the mutation line.

## Behavior Contracts

Block-form `WHEN` behaviors can declare parameter and return contracts before
their executable body:

```gwt
WHEN cart total for cart
  GIVEN cart is Cart
  THEN returns number
  RETURN cart.total
```

Contract `GIVEN` lines describe behavior parameters, not global state. They are
metadata for `gwt check`, future editor tooling, and documentation. Contract
types can use DTO field types (`number`, `text`, `boolean`, `list`, `any`,
declared DTO names, or `list<DtoName>`).

`AND` can continue contract `GIVEN` lines:

```gwt
WHEN checkout cart for customer
  GIVEN cart is Cart
  AND customer is Customer
  set cart.total to 1
```

`THEN returns Type` declares the behavior's return type. If a behavior declares
a return type, `gwt check` verifies that the body has a `RETURN` statement and
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
python -m gwtlang run examples/checkout_app.gwt --input examples/requests/checkout_request.gwt --json
```

The program file provides reusable block-form `WHEN` behavior. The input file
provides the request as ordinary `GIVEN`, single-line `WHEN`, and optional
`THEN` steps. This makes GWT usable as a deterministic workflow runner while
keeping inputs in the same language shape.

Request files can use DTOs declared by the program file.

If the program declares `REQUEST` contracts, request files must provide those
paths through `GIVEN` setup before execution. If the program declares `OUTPUT`
contracts, the `result` field in CLI JSON and API payloads contains only the
declared output paths.

## Embedding API

Host applications can call GWT through the Python package instead of shelling
out to the CLI:

```python
from gwtlang import check_file, run_file

check = check_file("rules.gwt")
if check.ok:
    execution = run_file("rules.gwt", request_file="request.gwt")
    state = execution.state
```

`check_file` returns a structured result with `ok`, `diagnostics`, and
`as_payload()`. `run_file` returns an execution result with `state`, `output`,
`scenarios`, and `as_payload()`. `state` is the full final runtime state.
`as_payload()` always returns an envelope with `ok`, `file`, `request_file`,
`scenario_count`, `scenarios`, `state`, `result`, and `output`. The top-level
`state`, `result`, and `output` values are populated for single-scenario runs;
multi-scenario details are always available under `scenarios`.

## Static Checking

`gwt check file.gwt` parses a program and runs semantic checks without
executing scenarios. The checker is intentionally conservative: reusable
workflow files can still refer to request/state paths that are supplied later.

The current checker reports:

- unmatched behavior calls and signature/arity mismatches
- duplicate behavior signatures within the same source file
- reserved behavior names that conflict with built-ins
- duplicate or invalid behavior parameters
- invalid built-in statement shapes
- `LET` and `RETURN` outside behavior bodies
- `LET` names that overwrite parameters or earlier local names
- `LET` bindings to behavior calls that do not return a value
- invalid expression syntax in statically checkable expressions
- missing `EXAMPLES` placeholders
- obvious `FOR` use over a scalar literal
- unknown behavior contract types
- unknown `REQUEST` / `OUTPUT` contract types
- typed table row shape/type mismatches
- statically obvious `set`, `add`, `subtract`, `append`, `count`, `sum`, and
  `find` type mismatches on known DTO/contract fields
- statically known behavior argument and return type mismatches

`gwt check --json` includes editor-oriented diagnostics with codes, severity,
source ranges, and a symbol list for DTOs, DTO fields, behavior signatures,
parameters, local names, program contracts, and scenarios.

`gwt format file.gwt` rewrites a valid GWT file using the canonical v0.1 source
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
- hover for known DTOs, fields, behaviors, parameters, and locals
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

- numbers: `10`, `3.14`
- strings: `"open"`
- booleans: `true`, `false`
- lists: `[10, 20, 30]`
- paths: `account.balance`, `count`

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

Typed tables validate every row against a DTO and give the checker a typed
collection:

```gwt
DTO OrderItem
  sku: text
  quantity: number

DTO Order
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
When a table names a DTO, each row must include all DTO fields, cannot include
unknown fields, and must match the DTO field types.
Scenario `EXAMPLES` placeholders can be used inside table cells.

## Statements

```gwt
set path to value
add value to path
subtract value from path
append value to path
count list into path
sum list into path
find name in list where condition into path
print value
```

Examples:

```gwt
set account.status to "closed"
add 5 to count
subtract amount from account.balance
subtract amount + fee from account.balance
append item.name to invoice.names
count invoice.items into invoice.count
sum invoice.quantities into invoice.total_quantity
find item in invoice.items where item.name == "mouse" into invoice.found
print account.balance
```

`value` can be an expression. If the target path has a known type from a DTO,
program contract, typed table, or behavior contract, mutations are checked
against that type immediately.

Collection helpers operate on lists. `append` adds one value to a list target,
`count` stores the list length, `sum` stores the total of a numeric list, and
`find` stores the first item matching its condition or fails if none matches.

## Local Bindings

Behavior blocks can bind local names:

```gwt
WHEN withdraw amount from account
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
WHEN withdraw amount from account
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

WHEN total cart
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

## Return Values

Behavior can return a value:

```gwt
WHEN calculate fee for amount
  RETURN amount * 0.1
```

Returned behavior calls can be bound with `LET`:

```gwt
WHEN withdraw amount from account
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
not account.locked
```

Supported operators:

- arithmetic: `+`, `-`, `*`, `/`
- comparison: `==`, `!=`, `>`, `<`, `>=`, `<=`
- boolean: `and`, `or`, `not`

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

Older implicit signatures are still accepted for compatibility: when a
signature has no `<name>` parameters, non-connector words after the behavior
name are treated as parameters, while connector words such as `from`, `into`,
`to`, `with`, `by`, and `for` are matched literally.

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

In version 1, `WHEN` has two forms.

Block-form `WHEN` defines behavior:

```gwt
WHEN withdraw amount from account
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
