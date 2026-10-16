# How native GWT executes behavior

For a runnable introduction, use [Read, change, explain, review](native-review-walkthrough.md).
The [native draft specification](spec/native-draft.md) is the consolidated language
reference; this guide explains the execution model in narrative form.

GWT describes behavior over explicit domain state. A program declares the shapes
of that state, names the actions that change it, exposes requests to a host, and
uses scenarios to show expected outcomes. The Rust engine checks this source
before executing it and records the steps that actually ran.

This guide describes the **current experimental native profile**. It is a
reading path through the [detailed semantic decisions](native-semantics.md),
not a new language release. The published [v0.2 specification](spec/v0.2.md)
and [Python reference](reference.md) describe the existing Python toolchain.
The profiles share substantial syntax but differ intentionally in arithmetic,
calls, checking, and some source forms. Select the engine explicitly when
authoring, validating, or reviewing a program.
The [native grammar](native-grammar.md) collects the source forms and context
rules accepted by this profile.

## Follow one request

The checked-in [member-pricing example](../examples/native_return_values/rules.gwt)
illustrates the execution model:

```gwt
REQUEST quote order
  GIVEN order is Order
  GIVEN quote is Quote
    total: 0.0
  WHEN quote order into quote
  OUTPUT quote is Quote
  THEN quote.total >= 0
```

Here `Order` declares `unit_price: decimal`, `quantity: integer`, and
`member: boolean`; `Quote` declares `total: decimal`. The uninitialized `order`
binding is supplied by the host. The initialized `quote` binding is local setup,
not an additional host input. The example's behaviors calculate a subtotal and
apply a ten-percent member discount, requiring a nonnegative price and positive
quantity.

From the repository root:

```sh
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- validate examples/native_return_values/rules.gwt
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- run examples/native_return_values/rules.gwt --request "quote order" --input examples/native_return_values/input.json
```

The input is `{"order":{"unit_price":"19.95","quantity":2,"member":true}}`.
The successful run's `result` is `{"quote":{"total":"35.91"}}`. Its separate
`state` contains initialized request bindings, including the order. Decimal
strings preserve exact values at the JSON boundary; the quote is not rounded
by a host floating-point or decimal context.

| Phase | What happens | What failure means |
| --- | --- | --- |
| Load and check | Freeze the source/import closure; resolve types, names, calls, and included bodies | No request executes, even if the error is in an unselected branch |
| Accept host input | Validate the entire closed input record and normalize values | No request-local setup or behavior executes |
| Set up state | Execute request-local initializers in order | Previously completed setup remains observable; an incomplete constructor installs no partial binding |
| Execute behavior | Run the request's actions in order, sharing state and budgets | Prior committed mutations and captured output remain |
| Validate outputs | Check the declared output contracts | No successful request result is published |
| Check postconditions | Evaluate request `THEN` assertions | Even a correctly typed output is not a successful result if a postcondition fails |
| Return observation | Expose success/result or diagnostic, plus state, captured output, and evidence | The host decides what to persist or do next |

This input timing concerns a direct JSON request. In a scenario, `GIVEN` first
constructs the caller's checked state; a subsequent `REQUEST` binds the declared
inputs from that state. Request-local setup then runs. A nested request shares
its existing input locations and publishes new outputs only after success.

## Know which state can change

Record contracts are closed: required fields must exist, extra fields fail,
and writes cannot invent fields. Initializers explicitly supply every required
field; omitted optional fields become absent. A one-of record contains its
declared `kind` and that kind's payload, with no inactive payload placeholders.
Kinds represent domain alternatives, such as delivery by email or collection.

Each independent host request or scenario starts with fresh state. Host JSON
is normalized into engine-owned values; execution does not mutate the caller's
JSON object. Within a run, sharing is explicit:

| Source form | State relationship |
| --- | --- |
| Bare path passed to a behavior, such as `adjust order.total` | Shared mutable location; the callee can change the caller's value |
| Parenthesized path, such as `adjust (order.total)` | Copied value; callee mutation stays local |
| Literal, list argument, or grouped calculation | Copied value, evaluated before entering the callee |
| Ordinary `LET`, record construction, assignment, or returned record/list | Value snapshot, not a new alias to the source |
| `FOR`/`FIND` item from a state-path collection | Alias to the selected item |
| Item from a computed collection expression | Temporary copied value |

Passing the same location twice creates aliases: a write through one parameter
is visible through the other. Shared parameters require exact structural types
because they permit writes. Copied arguments allow assignment-compatible
normalization, such as an integer value passed to a decimal parameter. A return
type does not make a behavior pure; it may mutate shared parameters before
returning. See [call rules](native-semantics.md#call-arguments).

`LET` names an intermediate value or a whole returning behavior call. A returning
behavior declares `THEN returns Type`; every syntactic path to normal completion
must return; a literal `REQUIRE false` is an
[explicit failure exit](native-failure-exits.md). `RETURN` leaves that behavior, including any enclosing loop, and
the caller continues. Branch/item locals do not escape their bodies. Expressions
cannot invoke behaviors; bind a calculation's result before using it in a larger
expression. [Typed local construction](native-local-records.md) uses a trailing
colon to distinguish `LET name be RecordType:` from a value or call.

## Read decisions in execution order

Statements, expression operands, supplied initializer fields, list elements,
and copied call arguments evaluate in source order. `and` and `or` short-circuit;
their skipped operand has no evaluation or value. All branches are still checked
statically. Conditions must be boolean: zero, empty text, and empty lists have no
implicit truth value.

| Construct | Selection rule |
| --- | --- |
| `IF` / optional `ELSE` | Evaluate one condition and run the selected body |
| `DECIDE` | Test conditions in order; run the first true body, otherwise the required `ELSE` |
| `DEPENDING ON` | Evaluate the subject once; select a checked kind or literal-value branch with exhaustive coverage or a valid fallback |
| `FOR` with optional `WHERE` | Visit items in source order; run the body for each selected item |
| `FIND ... WHERE ... ELSE` | Run the body for the first match; otherwise run the explicit missing body |

Dispatch has no fallthrough. Scalar dispatch compares exact values, so numeric
`1` and `1.0` are equal labels and cannot appear as separate cases. Plain numeric
and text subjects require a fallback; finite boolean, text, and numeric subjects can be
covered exhaustively. See [value dispatch](native-value-dispatch.md) and
[kind dispatch](native-one-of.md#exhaustive-kind-branches).

Collection visits read live state. Earlier iterations can change later items'
fields, and later visits observe those changes. Active traversal fixes membership:
appending to or replacing the source collection, or an ancestor, is refused.
Item updates remain possible within their contracts and active proofs. A missing
`FIND` releases its own traversal guard before `ELSE`; enclosing guards still
apply. `sum` reads contributions in order and writes its destination only after
the aggregate succeeds. See [collection rules](native-semantics.md#lists-iteration-and-collection-steps).

## Make absence and domain alternatives explicit

`optional<Type>` has one absent state: omitted JSON and JSON null normalize to
the same value. Zero, false, and empty text remain present. There is no ordinary
source `null` literal. If missing, unknown, and not applicable have different
meanings, represent them as named domain alternatives.

A presence test establishes when an optional path is usable. A known one-of kind
establishes which payload fields are available. Supported facts can follow
short-circuit conditions, selected branches, successful `REQUIRE` steps, selected
collection filters, and common exits of continuing branches. For example, both
branches of [collection authorization](../examples/native_branch_proofs/rules.gwt)
prove that a receipt exists, allowing its reference to be read afterward.

This is conservative checking, not arbitrary theorem proving. A possibly empty
`FOR` proves nothing afterward; a helper's internal assertions do not refine
its caller; numeric-range proofs are not inferred. `THEN` checks an expectation
but adds no new flow facts. Declared request outputs and behavior return contracts
remain their declared types despite local refinement.

Proofs affect legal mutations as well as reads. While a scope relies on presence
or a set of kinds, aliases cannot clear that value or replace it with an excluded
kind. Guards end with their owning scope, including on return or failure; caller
guards remain. A common branch proof can last through the rest of the containing
body. These rules can reject a later write that would otherwise meet its declared
type. [Branch-exit semantics](native-branch-proofs.md) describes the joins and
their deliberate migration consequences.

## Treat arithmetic and failure as part of the policy

Integers and finite base-ten decimals are exact within explicit digit limits.
Native `number` currently aliases decimal. Booleans are distinct from numbers.
Decimal JSON inputs use strings or integer tokens; fractional JSON number tokens
are refused. Integer outputs use JSON number tokens, which hosts must preserve
without floating-point conversion. Decimal output strings normalize insignificant
zeros; monetary display scale is a separate concern.

Ordinary `/` succeeds only for an exact finite decimal quotient. Division by
zero fails, and `1 / 3` fails with `nonterminating_decimal`. The separate
[rounded division step](native-rounded-division.md) requires a literal scale and
named rounding policy. GWT does not choose that business rule for the author.

An assertion, invalid operation, mutation guard, or resource refusal stops the
current execution unless a supported scenario expectation handles that action's
failure. There is no transaction rollback. Writes validate the replacement and
retain their evidence before committing; earlier writes survive later failure.
Hosts must not interpret a failed run's partial state as an approved decision.

Scenario `THEN fails with "code"` can expect `assertion_failed`,
`division_by_zero`, or `nonterminating_decimal` from the immediately preceding
action. It does not catch setup errors, arbitrary engine errors, or resource
exhaustion. A passing rejection scenario means the rejection matched its
expectation, not that the underlying request succeeded. Add state and print
expectations when those consequences matter. See [expected failures](native-semantics.md#expected-action-failures).

## Understand what execution evidence establishes

The compiled program retains source locations and resolved meanings. Events
record actual reads, decisions, calls, returns, assertions, output, and mutations
with operand links. Skipped source is identified without inventing results.
Most writes include before/after values; append records the inserted item and
index without repeating the whole list. A failed run retains the evidence
collected before failure. This is an execution explanation, not a generated
justification of the author's intent.

Source identity includes the exact reachable files, comments, and line endings.
Imports contribute declarations, not their scenarios or backgrounds. Check and
test imported modules separately to exercise their examples. A compiled snapshot
does not change when files are subsequently edited; filesystem loading itself
is not an atomic snapshot against concurrent writers.

[Captured cases](native-cases.md) additionally bind the engine, target, inputs,
budgets, and complete observation. Replay checks that observation. Request-case
comparison keeps host input fixed; scenario-case comparison runs each revision's
own setup and expectations. [Review](native-review.md) separates source, evidence,
state, and outcome changes, retaining failed or unavailable cases. A matching
result alone does not prove the explanation unchanged. Engine changes need
[explicit migration review](native-migration.md), even with identical source.

`check` proves static acceptance. `format --check` checks layout. `test` executes
entry scenarios. `validate` combines static, formatting, and scenario gates and
reports which expectations were observed. None establishes that examples cover
every important case or match the intended policy. The [validation guide](native-validation.md)
explains unexercised modules and evidence gaps.

## Keep the host boundary visible

The runtime performs no persistence or networking; `print` appends captured
output. The host supplies observations, chooses a request, interprets the result,
and performs external effects. The Rust library executes checked GWT directly;
it does not compile each GWT program into generated Rust.

Execution has explicit step, evidence, text, depth, and structural bounds. Calls
and nested bodies share a run's budgets; independent scenarios receive fresh
ones. These bounds do not provide a wall-clock or process-memory sandbox.
[Operating limits](native-execution-limits.md) belong to deployment and review:
raising a budget does not erase a recorded failure. Profiling measures retained
execution evidence, not general runtime performance.

The native profile is still experimental. The
[language decision register](native-language-decisions.md) records the current
choices for explicit calls, symbolic comparisons, root request records, typed
tables, existence/required lookup, exact numbers, and typed host facts. It also
distinguishes actual Python migrations from proposed forms neither engine supports.
[Finite scalar contracts](native-finite-literals.md) now cover numeric and
singleton boolean domains. Indexed source access and general alias-preserving
lookup migration still need further design work. See the
[feature/evidence matrix](native-conformance.md) for coverage and limitations.

The [support and transition contract](native-language-transition.md) consolidates
current scope, migration responsibilities, and versioned-release preparation.
The [project goal](project-goal.md) still requires a deliberate version transition,
broader implementation and deployment evidence, and measured human understanding
and review benefit. This guide makes the current model easier to find; it does
not establish those remaining outcomes.
