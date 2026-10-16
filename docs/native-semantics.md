# Native GWT semantics: working decisions

Status: experimental native language profile. The existing Python language
specification remains [v0.2](spec/v0.2.md). This document records deliberate
choices for the Rust foundation, implemented features, and unresolved needs.
The native engine runs complete source files within the documented profile;
it is not a v0.2 compatibility implementation. The
[support and transition contract](native-language-transition.md) distinguishes
deliberate omissions from future requirements and versioned-release work.

Start with [the native execution model](native-execution-model.md) for a connected
account of requests, state, decisions, failures, evidence, and host boundaries.
The [native grammar](native-grammar.md) describes accepted source forms and their
context restrictions. This document supplies detailed working rules and migration notes.

The governing objective is [the project goal](project-goal.md). Neither Python
behavior nor Rust defaults are normative by themselves. A retained behavior
needs a domain or human-understanding rationale; a changed behavior needs an
explicit rule, independent examples, and migration guidance.

## Audit of the current implementation

| Area | Current evidence | Native direction |
| --- | --- | --- |
| Expression representation | `gwtlang/expressions.py:evaluate_expression` reparses text on evaluation | Parse once, resolve paths and types, execute the checked tree |
| Conditions | `gwtlang/expressions.py:_truthy` delegates to Python `bool` | Require boolean expressions; reject implicit truthiness |
| Numeric operations | `_coerce_mixed_float_decimal` converts mixed operands to float; decimal arithmetic inherits Python's active decimal context | Keep exact arithmetic independent of the host context; keep rounding explicit through a source-selected division step |
| Integer division | v0.1 specification retains broad `number` division for legacy compatibility | Exact finite decimal result, with an explicit failure for recurring decimals |
| Runtime values | Python values and dictionaries carry state dynamically | Explicit value variants and checked input contracts |
| Missing values | v0.2 deliberately unifies omitted optional values and JSON null | Retain one absent state for `optional`; use domain records when distinctions matter |
| Names and fields | Paths are interpreted during evaluation | Resolve root binding slots and validate field paths before execution |
| Evidence | Existing traces connect decisions, mutations, and source locations | Treat source locations and factual evaluation evidence as native execution outputs |
| Host effects | Host adapters supply observations around deterministic behavior | Retain this boundary; native expression execution performs no I/O |

## Implemented expression rules

### Values and input contracts

The current native layer supports boolean, integer, decimal, text, list,
record, finite scalar literal unions, and optional input contracts. It validates the whole supplied input
record before evaluation, including inputs not read by a short-circuited branch.
Contracts are closed: undeclared fields are rejected, including nested fields.
This makes accidental input spelling changes visible. The current native profile
deliberately keeps raw facts typed rather than adding Python's `any` escape hatch;
the [contact boundary adaptation](native-input-boundary-decisions.md) exercises
that choice without moving domain decisions into host code. Arbitrary open or
heterogeneous data still needs a concrete representation and worked requirement
before any extension; the example is not a general dynamic-data migration.

Booleans are distinct from numbers. Integers retain exact whole-number values
beyond a machine word. Decimals retain finite base-10 values. Decimal boundary
inputs accept decimal strings or integer JSON tokens, and reject fractional
JSON number tokens. This boundary avoids assuming that a host has preserved a
number's decimal provenance. JSON output uses number tokens for integers and
strings for decimals. Hosts must handle large integer tokens without silently
converting them to an inexact numeric type.

In native source declarations, `number` currently names the same exact type as
`decimal`. It does not retain the Python implementation's broad float boundary.
That deliberate experimental difference lets existing integer-valued examples
run while preserving the native rule against implicit approximation. Host
fractional inputs must use decimal strings. This spelling and migration choice
still needs review before a versioned native language release.

Omitted and null optional inputs normalize to one absent value. Required
missing inputs fail. Presence guards establish usable values on the relevant
short-circuit path, including nested optional records. Unguarded operations on
optional values fail checking. Missing, unknown, and not-applicable remain
distinct only when represented explicitly in the domain.

Presence proofs also apply inside native `IF` and `DECIDE` bodies and their
fallbacks. Later `DECIDE` conditions retain facts from earlier false conditions.
[Scoped presence rules](native-presence.md) define the supported boolean proof
forms, exact mutable argument contracts, and runtime protection against alias
or ancestor writes that would clear a value while a branch relies on it.

### Arithmetic and comparisons

- Integer addition, subtraction, multiplication, and negation produce integers.
- Mixed integer/decimal arithmetic produces a decimal.
- Division produces an exact decimal when its reduced denominator contains
  only factors two and five. Division by zero fails. A recurring result such as
  `1 / 3` fails with `nonterminating_decimal`; no rounding policy is invented.
  A separate [rounded division step](native-rounded-division.md) requires an
  explicit literal scale and mode and can round a recurring quotient.
- Decimal output is canonical by value: insignificant fractional zeros and
  signed zero are not preserved. Formatting and monetary scale are separate
  future concerns. For example, `"12.30"` serializes as `"12.3"`.
- Equality compares exact numeric values across integer/decimal types. Boolean
  and text equality require matching types. Boolean/numeric equality is a
  checker error. Lists compare in order and records compare corresponding fields
  structurally, with exact numeric comparison at each leaf. Incompatible element
  or field types fail checking. Comparison stops at the first difference.
- Ordered comparisons currently require numeric operands. Text collation is
  not implicitly inherited from either implementation language.
- Text addition concatenates text. `contains` supports text substrings and
  scalar membership in typed lists. It does not silently perform record-key
  membership or convert operand types.

The implementation uses arbitrary-precision integers and rational arithmetic
internally, then verifies finite decimal representability. Rational values are
not a new source-language type. This avoids adopting a fixed-width decimal
library's precision as the language's implicit policy. See the primary
[num-bigint](https://docs.rs/num-bigint/latest/num_bigint/) and
[num-rational](https://docs.rs/num-rational/latest/num_rational/) documentation.

### Evaluation and evidence

Expressions evaluate left to right. `and` and `or` require booleans and
short-circuit. Every branch is statically checked, including branches skipped
at runtime. A direct presence guard, its negation, and logically established
conjunction/disjunction guards can narrow an optional path.

The parser preserves UTF-8 byte offsets and one-based human line/column
locations. The checker resolves input names into slots and retains the source
spelling for evidence. Runtime execution never reparses expression text.

Evidence events record the evaluated source span, operation, operand event IDs,
and actual result. A short-circuit event identifies the skipped source span;
it does not fabricate an evaluation for that operand. A runtime failure returns
a diagnostic and evidence already collected, with no successful result.
Each invocation has fresh normalized input, budgets, and evidence.

Expression events use `gwt.native-expression`, schema version 1. Full native
request/scenario runs use the separate experimental `gwt.native-run`, schema
version 1. Neither replaces the existing `ExecutionResult.as_payload` envelope
or satisfies the Python Execution Case, comparison, or workbench contracts.
Native [case capture/replay and single-case comparison](native-cases.md) use
separate experimental envelopes and verify complete recorded executions.
File and bundle compilation also attach an exact dependency-closure identity
to each run. The single-source `compile_program` helper has no bundle identity;
it rejects imports and is intended for supplied source strings.

### Explicit resource limits

The initial profile bounds numeric literals/results to 512 base-10 digits,
source expressions to 65,536 UTF-8 bytes, expression tree depth to 64, and
expression nodes to 4,096. Type contracts have a 64-level nesting and 4,096-node
limit. Normalized inputs have a 64-level nesting, 16,384-value, and one-MiB JSON
limit. These are prototype execution limits, not a claim of unbounded numbers.

Default evaluation limits are 4,096 steps, one MiB of evidence, and one MiB for
a concatenated text result. Each expression evaluation and each list item
examined by `contains` consumes one step. Structural equality also charges each
visited list item or record field. Constructed lists and records have the same
64-level, 16,384-value, one-MiB JSON ceiling as inputs; constructors account for
items before retaining additional copies. Assignment checks its replacement
value before writing it. Exceeding a limit produces a source
diagnostic. These bounds are deterministic guards, not a wall-clock or memory
sandbox guarantee.

Modules have a one-MiB source limit; a source closure has a four-MiB byte limit,
256-module limit, 64-level import traversal limit, and 16,384 source-node limit.
Programs have a 64-level indentation limit. Each scope has at most 4,096 bindings. Default program
execution has 100,000 steps and shares the expression evidence/text budgets.
Statements and expressions use the same step counter. Calls, branch bodies, and collection bodies
share a 64-level execution nesting ceiling; `ProgramLimits.call_depth` can
reduce this ceiling. A caller cannot raise it above 64. Contract normalization,
allocation, and serialization have structural limits but are not fully charged
as execution steps; broader resource qualification remains required.

## Implemented program rules

### Declarations and checking

The parser accepts `PROGRAM`, `TYPE` aliases, ordinary `RECORD` declarations
(including nested fields), named requests, explicit behavior signatures, and
implicit or named scenarios. Declarations can reference types declared later;
cycles and duplicates fail checking. Finite scalar literal unions constrain values.
One-of records support closed kind payloads and selected-kind contracts, as
described in [native one-of contracts](native-one-of.md). [Finite scalar contracts](native-finite-literals.md) now support integer,
exact-decimal, and singleton boolean domains with exhaustive value dispatch.

Behavior parameters currently require explicit `GIVEN` type contracts.
Signatures must be unambiguous: two patterns that could match the same call
are rejected. Signature words cannot contain argument delimiters (`"()[]<>`),
except for complete `<parameter>` placeholders. Calls accept shared state paths
and copied values, as described under [call arguments](#call-arguments).
Returned behavior values use explicit contracts and `LET` bindings.

All included declarations, bodies, initializers, entry scenarios, and branches
are checked before execution. Unknown syntax is rejected in those bodies,
including in unselected branches.
This prevents an unsupported form from disappearing into an apparent success.

### Imports and exact source identity

`USE "relative/path.gwt"` imports a module's declarations: types, records,
behaviors, and requests. Imports are module-level statements. Dependencies are
visited in source order, shared dependencies contribute declarations once, and
cycles fail with the importing source location. Imports introduce no module
namespace. Duplicate type names, duplicate request names, and overlapping
behavior signatures are errors across the loaded declarations; these are
separate collision checks, not one namespace shared by all declaration kinds.
Imported `PROGRAM` headers do not replace
the entry's name. Imported scenarios and implicit scenario steps are excluded
from execution and semantic checking. Check/test those modules separately to
validate their examples; importing a module does not claim its examples pass.
Source layout, import syntax, nested import placement, background placement,
and example-table structure are still checked in every loaded module. Imported
backgrounds and example scenarios contribute no state or executions to the
entry program. Run those modules separately to check their scenario semantics.

`load_bundle(entry, root)` freezes the reachable UTF-8 source files into a
`SourceBundle` with a logical entry path and a sorted path-to-source map.
`compile_bundle` performs no filesystem access and rejects missing modules,
unreachable extra modules, and noncanonical map keys. `compile_file` combines
loading and compilation. A compiled program owns its snapshot; later file or
caller-bundle edits cannot change its execution or reported identity.

Logical paths are slash-separated and relative to a selected source root.
Imports may use `.` and `..` within that root; escaping it, absolute paths,
backslashes, colons, control characters, and empty components are rejected.
The default filesystem root is the entry file's parent. Supply an explicit
root for layouts that import sibling directories; the CLI accepts a trailing
`--import-root DIRECTORY` on `check`, `test`, and `run`. Symlinks below the
selected root are rejected, including symlinked directories. These rules make
module identity portable; the filesystem loader is not a hostile concurrent
filesystem sandbox or an atomic multi-file snapshot. Freeze reviewed files
before execution when concurrent edits matter.

Every bundle-backed run includes `programIdentity`, using the experimental
algorithm `gwt-native-program-sha256-v1`. Each module's digest is `sha256:` plus
the lowercase SHA-256 of its exact UTF-8 bytes, including comments and line
endings. The program digest hashes this byte sequence:

1. The UTF-8 algorithm name followed by a zero byte.
2. The entry path as a length-prefixed UTF-8 field.
3. The module count, followed by modules sorted by logical path.
4. For each module: its path field, its `sha256:…` digest field, its import
   count, and resolved import-path fields in source order (including repeats).

All counts and field byte lengths are unsigned 64-bit big-endian integers.
The resulting digest has the same `sha256:` prefix. Neither absolute paths nor
JSON formatting enter the hash. Exact relocation preserves identity, while
any reachable source change alters it. An independent known-answer fixture
checks this encoding. This fingerprint identifies source, not authenticity,
execution correctness, or a stable engine version. Native [captured cases](native-cases.md) also bind raw inputs, execution
settings, the engine source fingerprint, and the complete observed execution.

### Request and scenario execution

Request input bindings and output bindings currently name root values. The
host input record is validated before request-local setup runs. Request `GIVEN`
setup must precede `WHEN`; `OUTPUT` and `THEN` come after execution steps.
At runtime, setup and calls execute in order, output contracts validate, then
request postconditions run. Successful request `result` contains only declared
outputs; `state` contains initialized request inputs and local state.

Scenarios execute `GIVEN`, `WHEN`, `REQUEST`, and `THEN` steps in source order
with fresh state. `AND` continues the preceding step form. An implicit `Main`
scenario supports small programs such as hello-world. Implicit and explicit
scenario forms cannot be mixed. The CLI `test` command fails when no scenarios
exist; a declaration-only module can still pass `check`.

### Expected action failures

A scenario or background can attach an expected failure to its immediately
preceding `WHEN` or `REQUEST` action:

```gwt
WHEN print 1 / 0
THEN fails with "division_by_zero"
AND prints []
```

The annotation checks one action, not the whole scenario. Setup or an earlier
action cannot satisfy it. Both lines must belong to the same scenario or
background, with no intervening executable step. A matching failure allows later
steps to run. Unexpected success or a different supported failure stops with
`failure_assertion_failed`. A second failure annotation cannot attach to the
first assertion. Behavior bodies and request postconditions cannot catch errors
with this form.

The quoted code must be `assertion_failed`, `division_by_zero`, or
`nonterminating_decimal`. These identify defined behavior failures. Unknown
codes, invalid host inputs, engine invariants, collection safety errors, and
resource limits cannot be expected by this form. Unsupported runtime errors
propagate unchanged, even when they occur inside the annotated action. This
keeps exhausted execution/evidence budgets from passing a test accidentally.

There is no rollback: committed mutations and captured output remain. A failed
request does not publish new output bindings into its caller. Similarly, an
annotated `WHEN LET ...` cannot establish a binding for later steps; the checker
removes bindings introduced by the action. Existing caller bindings retain any
shared mutations. Traversal guards are released as execution unwinds.

The action uses its ordinary step/depth budgets. The expectation is charged
afterward, with no budget reset. It records an `assert failure` event containing
the expected code, `matched`, the action span, and the complete observed diagnostic
(or null on unexpected success). Its operands link the action's recorded events.
A budget failure before this record cannot claim a successful expectation.

The scenario's `ok` reports whether its steps and expectations passed. It does not
turn a rejected host request into a successful request: direct request execution
still reports the original failure. The review trail displays the observed error
and an independently checked excerpt of its source, even when the scenario passes.
Expectation matching checks the code, not the message or source location; additional
state/print assertions should express the domain consequences that matter.

The [stock-rejection example](../examples/native_expected_failures/README.md)
and `tests/failure_expectations.rs` cover these rules, partial-state regressions,
bounded/deep recursion, source-mapped example rows, and generation from verified
failed requests. This is native-only syntax; Python formatting preserves it,
but Python checking/execution does not implement it.

### Printed-output expectations

In a scenario or background, `THEN prints [...]` compares the complete captured
output so far against an explicit JSON array. `AND prints [...]` continues a
preceding `THEN`. For example:

```gwt
WHEN print "Packed"
WHEN print 3
THEN prints ["Packed", 3]
```

The outer array represents the ordered sequence of print calls. A single printed
list needs another array level: `THEN prints [[1, 2]]`. `THEN prints []` requires
no output. Mixed strings, integers, booleans, records, lists, and nulls are allowed.
Record key order is irrelevant; sequence order, length, values, and JSON types
must match. Decimal output uses canonical JSON strings (for example `"0.1"`);
fractional/exponent JSON numbers are rejected. Integers retain up to 512 digits.
This tests serialized output, so a decimal and a text value with the same JSON
string cannot be distinguished by this assertion.

The expectation is a JSON snapshot, not a GWT expression: it cannot read bindings
or invoke behaviors. `null` here describes emitted JSON and does not introduce a
null literal into ordinary GWT expressions. Duplicate object keys, including
equivalent escaped keys, are rejected. An expectation is limited to 16,384 values
and 64 levels within each emitted value, plus ordinary source-size limits.

Checking occurs exactly where the step appears. It includes prior background
output, does not consume that output, and cannot constrain later print calls.
Place it after the behavior under test to check its complete output. A mismatch
stops the scenario with `print_assertion_failed`, preserving prior state and
output. It does not catch a preceding execution failure; use a supported scoped
failure expectation first when rejection is intended. Behavior bodies and
request postconditions do not accept this scenario-only form.

The `assert prints` event records `matched`, `expected`, and `actual`, and links
every preceding print event. It is visible in the default review trail. The step
uses the shared execution and evidence budgets; a budget failure cannot record
a successful assertion. JSON comparison/serialization is structurally bounded,
not charged once per value. The [receipt example](../examples/native_print_expectations/README.md)
and `tests/print_expectations.rs` cover this native-only syntax. Python formatting
preserves it; Python checking and execution do not support it.

### Backgrounds and example tables

One optional `BACKGROUND` contains shared scenario steps and appears before all
explicit scenarios. It runs before each scenario with fresh state, in source
order, sharing that run's step/evidence budget. A background may initialize
values, call existing behavior or named requests, and assert expectations. It
cannot define block-form behavior. Declare reusable behavior before the
background. Background setup is for scenarios; host calls to named requests
use the request's own setup and input contracts.
An assertion in the background therefore checks shared setup before the
scenario starts. Put expectations about final scenario state in that scenario's
`THEN` steps; native execution does not defer background assertions until then.

A background requires at least one step and one explicit scenario. Implicit
steps cannot accompany it. Each scenario also needs its own executable step;
shared setup alone does not create a passing scenario. `AND` continuation resets
at the boundary between background and scenario, so each starts with an explicit
step keyword. Reinitializing an already declared binding remains a checker
error; mutate existing state through an explicit behavior instead.

An explicit scenario may end with one `EXAMPLES` table. The header contains
unique identifiers; each data row has exactly that many nonempty source cells.
Quote text values, including `""` for empty text. Pipes and comment markers
inside JSON-style quoted strings remain part of the cell. Blank cells, missing
rows, duplicate headers/tables, and steps after the table are errors.

Each row substitutes its cell source text once for `<header>` occurrences in
that scenario's steps and nested initializers. Values can be expressions or
state paths as well as literals; the expanded program must pass ordinary static
checking. This deliberately retains source-text substitution, rather than
silently coercing table values into strings. Substitution also applies inside
quoted template text; authors should normally put the complete quoted string
in a cell. Inserted text is not recursively substituted. Backgrounds and global
declarations are not templates. Unknown placeholders fail with their template
location. All rows are checked before any run starts, including rows that would
fail assertions at execution time.

Expanded names are `scenario name example N`, with one-based row numbers;
collisions with other expanded or ordinary scenario names are errors. Each row
has fresh normalized state and execution budgets. Runtime failure retains that
row's evidence and state, and does not suppress subsequent rows. CLI `test`
counts expanded rows and exits nonzero if any fails.

Expansion preserves the original frozen source. An `example row` event records
the selected row and raw source values. A token wholly inside a substituted
cell points to that cell; unchanged source tokens keep their original location.
An expression or statement spanning several substituted/source pieces points
to the whole original template line, while its operands retain specific spans.
Diagnostics identify the expanded scenario and map back to the offending cell
or template. The explanation API validates all resulting source spans against
the original source bundle; no generated source file is added to its identity.

A program has at most 1,024 expanded scenarios, 65,536 expanded scenario nodes,
and four MiB of expanded scenario text plus row names/values. Repeated
background steps count toward these totals. Each expanded line has a one-MiB
ceiling and at most 4,096 source pieces, in addition to ordinary expression
limits. Bounds are enforced while expanding, before retaining the next piece;
large tables cannot silently multiply a small template without limit. These
are deterministic structural guards, not a claim of a strict memory sandbox.

[Delivery quotes](../examples/native_delivery/README.md) demonstrates shared
setup and a table of weight boundaries and membership precedence. Native
scenario evidence can be inspected through CLI JSON and `explain_execution`.
`run --scenario NAME` executes one checked scenario. Native cases can freeze
that scenario, including backgrounds, expanded rows, printed output, failures,
and budgets; see [scenario capture](native-cases.md#capture-and-compare-a-scenario).
Revision comparison uses the same scenario name with each revision's own setup
and assertions. Request cases instead preserve supplied host input.

### State, control flow, and failure

`set` changes an existing checked path. `LET` creates a local value with an
inferred type, or constructs an explicitly typed local record with
`LET name be RecordType:` and indented fields. The colon distinguishes
construction from ordinary expression and returning-call bindings; see
[typed local records](native-local-records.md) for scope, failure, and migration.
Record initialization requires every non-optional field and
rejects extra or duplicate fields. Omitted optional fields become absent.
Scalar and field initializer literals can normalize at their declared boundary,
including exact decimal strings. Writes cannot add undeclared fields.

Bare-path behavior arguments refer to the caller's actual state locations;
value arguments use local copies. Passing the
same location twice creates explicit aliasing: successive writes observe each
other in source order. Locals belong to their call frame; branch-local bindings
do not escape their branch. Caller-owned JSON input remains unchanged because
each run first constructs its own normalized state.

`IF` selects its body or optional `ELSE`. `DECIDE` tests conditions in order and
executes the first true branch, or its required final `ELSE`. There is no
fallthrough. [Presence proofs](native-presence.md) and
[kind conditions](native-kind-conditions.md) narrow supported short-circuit
expressions and selected `IF`/`DECIDE` bodies. Later decision conditions retain
facts established by earlier conditions being false. Runtime address guards
protect those facts against invalidating alias or ancestor writes.
`REQUIRE` and `THEN` require true boolean expressions. Successful
[`REQUIRE` steps](native-require.md) retain supported presence/kind facts through
the remainder of their containing body, with runtime mutation guards and cleanup
on normal exit, return, or failure. `THEN` adds no new flow facts. Request output
contracts keep their original declared type despite local refinement.
`PASS` is explicit no-op;
`print` appends a JSON value to the run's captured output rather than performing
I/O from the library.

Program evidence includes calls and parameter-to-state bindings, selected and
skipped branches, initializations, assertions, output validation, and writes.
Most writes retain before/after values; append retains the inserted item and index
instead of repeating the surrounding list. All events share one sequence and expression operand
references. A write commits only after its type is validated and its evidence
fits the budget. A failure returns prior committed state and evidence, with
no successful result. Runs are not transactional rollbacks. A failing nested
request can mutate existing input state, but does not publish new output
bindings to its caller. This failure visibility needs consideration when
designing host APIs and review artifacts.

### Lists, iteration, and collection steps

List literals evaluate their items from left to right. Items must have a common
checked type; integer items may widen to decimal. Empty lists require a known
item type from a typed destination, another item in a nested list, or the other
operand of a comparison. Thus `set decision.missing to []` works when the field
is `list<text>`, and `[] == [1]` is false; an unconstrained `LET items be []`
fails checking. Lists and records constructed or assigned from other values
are copies. Explicit behavior parameters and traversal bindings provide aliases.

The native subset includes these behavior steps:

```gwt
add line.quantity to decision.reserved
subtract line.quantity from stock.available
append line.sku to decision.missing
count order.lines into decision.line_count
sum line.quantity in order.lines into decision.requested
sum quantities into decision.requested
```

`add` and `subtract` require numeric operands compatible with the destination.
`append` adds one item of the list's declared type. Its `append item` evidence
records the normalized item and zero-based insertion index instead of repeating
the surrounding list; see [append evidence](native-append-evidence.md) for the
payload and explicit case-migration implications. `count` writes the list's
length to an integer or decimal destination. `sum` accepts numeric lists or a
numeric field projection over a record list. It visits items in source order,
records each contribution and subtotal, and returns zero for an empty list.
Each intermediate sum must fit the numeric limit. Failure leaves the aggregate
destination unchanged; earlier completed statements remain committed.

`FOR item in collection` executes its body in source order. An optional
`WHERE predicate` selects items using a checked boolean condition. `FIND item
in collection WHERE predicate` executes its body for the first match and must
have an explicit `ELSE` for no match. Later predicates are not evaluated after
a match. The item binding and body-local bindings are unavailable outside the
body, including in the missing branch. Supported presence/kind facts from a
true filter now refine each selected body, with address guards that end when
that body exits. The fallback gains no filter facts, and the filter is evaluated
against live state on each visit. See [filter proofs](native-filter-proofs.md).

When the collection is a state path, each item binding aliases its actual
location. Scalar replacement and record-field updates change the source list.
Membership stays fixed during traversal, while each visit reads the current
item value: an earlier body may update a later item's fields, and the later
visit observes that update. A computed list, such as `[box.total]`, uses copied
temporary items instead. This rule is based on the source expression, not on
Python's distinction between mutable objects and immutable scalars.

The current profile deliberately uses these explicit `FIND ... ELSE` blocks
instead of lowercase required/optional lookup statements. Copying a found item
into another binding or returning it creates a snapshot; it does not extend the
item alias beyond the block. `ELSE PASS` retains an existing destination, whereas
a freshly constructed optional selection can represent absence. The
[stock lookup contracts](../examples/native_lookup/README.md) qualify previews,
retained selections, and mutation of the first matched inventory item separately.

Replacing or appending to an active source collection, or replacing an ancestor
record, fails with `collection_mutation` before the write. The guard follows
aliases through nested behaviors and nested traversals. Writes to individual
items and their fields remain allowed when they preserve active presence/kind
proofs. A `FIND` with no match releases its own
traversal guard before executing `ELSE`, so the missing branch may append a new
item; an enclosing traversal's guard still applies.

Traversal visits and sum contributions consume the shared step budget. `count`
uses the known list length without charging a scan per item. Evidence records
collection entry, actual item values and paths, selection results, completion,
and sum contributions. The native review page includes these events in its
ordinary decision trail. Evidence must fit before a mutation commits.

[Stock reservation](../examples/native_reservation/README.md) demonstrates these
rules with embedded scenarios, exact stock boundaries, missing items, and
independent host-input expectations.

### Call arguments

A bare path passes shared mutable state. A literal, list expression, or
parenthesized expression passes a value copied into the callee's local state:

```gwt
WHEN discount <amount> at <rate>
  GIVEN amount is decimal
  AND rate is decimal
  THEN returns decimal
  subtract amount * rate from amount
  RETURN amount
```

For this behavior, `discount basket.unit_price at 0.1` changes the caller's
unit price. `discount (basket.unit_price) at 0.1` changes only a copy.
`LET total be discount (basket.unit_price * basket.quantity) at 0.1` binds the
computed result without changing either input. Parenthesized records and lists
are also deep value copies; mutations to them cannot reach the original state.

Computed arguments require parentheses, even when an expression has no spaces.
Literals (including negative numbers) and list expressions such as `[1, 2 + 3]`
already have explicit boundaries. Whitespace separates signature words and
arguments only outside quoted strings and balanced parentheses/brackets.
Quoted text remains text: `"basket.unit_price"` never resolves to that path.
Unquoted unknown names fail checking. JSON string escaping applies, including
quotes and backslashes; `#` inside quotes remains part of the text.

Shared arguments require exact structural parameter types because the callee
may write through them. Copied values use ordinary assignment compatibility and
contract normalization, including integer-to-decimal widening and contextual
empty lists. Parenthesizing an integer path can therefore pass its value to a
decimal parameter without permitting decimal writes into the original integer.

Value arguments evaluate left to right in the caller before any callee body
statement runs. Argument expressions cannot invoke behaviors. An evaluation,
contract, or evidence-budget failure prevents entry into the callee; earlier
argument evaluation evidence remains available. Prior caller mutations are not
rolled back. Copied collections can change shape independently of an active
traversal over their source; shared paths retain the existing traversal guards.

Each copied value records an `argument value` event with its exact source span,
parameter name, normalized value, and expression operand. The `enter behavior`
event links those events through `inputs` and `valueArguments`; `bindings`
continues to identify shared paths. Copied parameter mutation paths use labels
such as `amount (value)`. The review page shows these argument events by default.

The [value-argument example](../examples/native_value_arguments/README.md) and
`tests/arguments.rs` cover copies, aliases, typing, quoting, failures, source
mapping, recursion, independent pricing expectations, and captured revisions.
This grouped-call syntax is a native extension. Python's formatter preserves
it, but Python's runtime/checker does not implement these call semantics.

### Returned behavior values

A native behavior can declare `THEN returns Type` after its parameter contracts:

```gwt
WHEN calculate subtotal for <order>
  GIVEN order is Order
  THEN returns decimal
  RETURN order.unit_price * order.quantity
```

Within another behavior, `LET subtotal be calculate subtotal for order` binds
the result with its declared type. Headers are checked before bodies, allowing
forward calls and recursion. The ordinary expression form of `LET` keeps
precedence: an existing binding named `rate` means its value in `LET x be rate`,
even if a zero-argument behavior has that name. Otherwise, a whole RHS matching
a behavior signature is resolved as a call. Calls inside larger expressions or
directly after `RETURN` remain unsupported; bind their results with `LET` first.

Native return contracts are explicit. `RETURN` without a contract, a `LET` call
to a behavior without one, duplicate/out-of-order contracts, and incompatible
return values fail checking. The contract provides context for empty lists and
normalizes valid numeric widening, optional values, literal unions, and records.
For example, returning integer `1` from a decimal behavior produces decimal
`"1"` in JSON. All included return statements are checked, even unreachable ones.

Every syntactic path to normal completion must return. A literal `REQUIRE false`
is an [explicit failure exit](native-failure-exits.md), so an alternative that
fails this way does not need a return. Complete `IF`, `DECIDE`, dispatch, and
`FIND` alternatives compose returns and explicit failures. A `FOR` can be empty
and cannot alone establish an exit. This conservative check does not evaluate
arbitrary expressions, infer helper failures, prove termination, or prevent runtime failures. Native checking
is stricter here than Python v0.2's check for the presence of a return statement.

`RETURN` exits the current behavior through enclosing branches and traversals.
It leaves the caller running; a statement call deliberately discards the value.
Earlier parameter mutations remain committed. Returned records/lists are value
snapshots; bare-path arguments share state and value arguments use local copies. Returning
from a traversal releases that traversal's mutation guard, preserving any active
caller guards. No purity, rollback, or exception-catching behavior is implied.

Return expressions share the existing step, depth, value, and evidence limits.
The runtime records the normalized return value and its expression operand,
then links behavior completion and the caller's initialized local to that value.
An evidence failure prevents an unrecorded caller binding; prior mutations remain
visible. Early collection exit records `exit: "return"` in its completion event.
The review page includes return steps in its default decision trail.

[Member pricing](../examples/native_return_values/README.md) demonstrates named
calculations, typed returns, and executable scenario rows. `tests/returns.rs`
covers independent totals, revisions/generated tests, typed values, early exits,
snapshots, aliasing/guards, budgets, recursion, and source-linked evidence.

## Migration examples

| Python-influenced behavior or assumption | Native expression rule | Author action |
| --- | --- | --- |
| Truthy text, numbers, or collections in conditions | Conditions must be boolean | Express the domain predicate explicitly, such as `amount > 0` |
| Default rounding of `1 / 3` | Explicit recurring-decimal error | Use an explicitly chosen scale and mode in the native rounded division step |
| Python decimal context can round large intermediates | Exact operations within the declared digit limit | Validate results against the domain's intended arithmetic |
| `true` can compare equal to integer `1` through host equality | Checker rejects the type mismatch | Normalize the host fact to its intended type |
| Host float can participate in decimal arithmetic | Decimal boundary rejects fractional JSON numbers | Supply an exact decimal string |
| Broad `number` admits host floating-point values | Native `number` currently aliases exact decimal | Review host boundaries and use exact strings for fractional values |
| Extra input fields are carried through | Closed native expression contracts reject them | Project the intended facts into the declared input record |
| Return values without an explicit contract, or a return in only one branch | Explicit return type and return on every normal path | Add `THEN returns Type` and returning alternatives or a fallback return |
| Shell-style quote removal or unknown call words used as text | Quoted strings remain literals; unknown names fail checking | Quote intended text and group computed arguments in parentheses |
| Every path argument must share state | Bare paths share state; parenthesized paths copy values | Use `state` for intended shared mutation and `(state)` for a local copy |

These are native working decisions. Existing Python programs still use the
current implementation and v0.2 specification. The [support and transition contract](native-language-transition.md) separates
worked adaptations from unavailable general translation and defines the
remaining versioned-release work.

## Typed setup tables

Native typed record tables now support scenario/background and request-local
setup, including existing collection fields, expression cells, and source-mapped
rows. See [typed setup semantics](native-setup-tables.md) for deliberate header,
empty-list, copying, failure, and resource rules.

## Readable request entries

Native request files explicitly `USE` their rules, then set up state and invoke
public requests. `run ENTRY.gwt` and `capture ENTRY.gwt` select exactly one entry
scenario; zero or multiple scenarios require explicit selection. Imported
scenarios do not execute. The existing source bundle, scenario evidence, and
case format retain the entire entry and dependency closure without rewriting
source. See [request entries](native-request-entries.md) for selection, output,
capture/comparison, host API, and the deliberate distinction from Python's
externally paired `--input REQUEST.gwt` form.

## Outstanding language work

The language tour now uses existing `FIND ... ELSE` to select its first policy
violation and handle no match explicitly. Its public contract is preserved, with
boundary/reuse scenarios and cross-engine integer-domain checks. The
[worked source adaptation](native-source-adaptation.md) records where this
refactor is justified and what remains unproven; it does not add the old
lowercase collection forms to the native language.

Standalone `exists` is deliberately expressed through a named boolean-returning
behavior using `FIND ... ELSE` in the current native profile. The
[subscription adaptation](native-existence-decisions.md) preserves the request's
decisions over an independent input matrix while making found/missing returns
explicit. It does not establish a general rewrite for legacy mandatory/optional
`find`, and does not add a parallel native existence statement.

One-of contracts now validate named kinds, active payloads, source initializers,
and common fields. [Their native rules](native-one-of.md) also define exhaustive
`DEPENDING ON` kind branches, scoped payload narrowing, and alias-safe kind guards.
Selected-kind type expressions such as `Contact of kind email` give helpers
explicit payload contracts and preserve exact shared-argument type requirements.

Scalar-value `DEPENDING ON` now supports checked literal cases, exhaustive
boolean/text-union coverage, explicit broad-type fallbacks, and one-time subject
evaluation. Its [exact numeric equality](native-value-dispatch.md) deliberately
matches native `==`, including integer/decimal equality, rather than retaining
Python's representation-sensitive dispatch.

[Kind comparisons](native-kind-conditions.md) now narrow short-circuit expressions,
`IF`/`ELSE`, and ordered `DECIDE` branches, including multi-kind complements and
optional ancestors. Nested optional record setup constructs present values.
Nested request binding paths, calls embedded in expressions, lowercase
`find`/`exists` steps,
indexed source paths, untyped collection setup tables, English condition aliases,
and `any` remain unsupported.
Optional presence now narrows `IF`/`DECIDE` bodies and later decision conditions.
Successful REQUIRE assertions now establish the same supported facts for later
steps in their body. FOR/FIND filters now refine selected bodies with the same
facts and scoped guards. [Early-return flow](native-early-returns.md) retains
common condition facts after IF/DECIDE, surviving kinds after kind dispatch,
and outer filter facts after a FIND with a returning fallback.
[Branch-exit joins](native-branch-proofs.md) now also retain common REQUIRE and
nested-continuation proofs across IF, DECIDE, kind/value dispatch, and FIND.
Local bindings, helper postconditions, possibly empty loops, arbitrary boolean
proofs, and broader domain numeric policies remain outside that inference.
Unsupported Python forms are candidates for an explicit retain, redesign, or
omit decision, not automatic native implementation requirements. Each decision
needs domain examples, a human-understanding rationale, and migration guidance.
The [language decision register](native-language-decisions.md) now records
decisions for explicit call results, comparison spelling, root request contracts,
and typed tables, with thirty focused probes and links to larger workflows.
General embedded calls and indexed expressions are not currently supported by
either engine; they should not be described as automatic Python migration work.
[Finite numeric and singleton boolean contracts](native-finite-literals.md) are
implemented, including exact boundary membership and exhaustive dispatch.
General alias-preserving optional-lookup adaptation remains unavailable; the
worked lookup contracts make snapshot and mutation choices explicit.
The full project goal remains broader than the currently supported profile.

The [feature-to-evidence matrix](native-conformance.md) identifies current
coverage and missing proofs. Larger unrelated workflows must exercise the
remaining language model before native compatibility or performance is claimed.


Explicit [rounded division](native-rounded-division.md) is implemented as a step
with a decimal destination, static scale 0..512, and a named rounding mode. The
language does not choose a business policy. `divide` is now reserved; previously
custom behaviors with that verb require source adaptation before engine migration.

An exact domain ratio need not use division. The
[underwriting adaptation](native-exact-ratios.md) represents numerator and
positive denominator explicitly and compares thresholds without rounding. This
uses ordinary records and behaviors, with a deliberate output-contract change;
it does not add general rational arithmetic or choose a display precision.
