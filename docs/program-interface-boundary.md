# Program Interface Boundary

Status: design rationale implemented by GWT v0.2.

This note records the design discussion that led to the v0.2 public interface:
named `REQUEST` blocks are the callable unit. Some earlier sections describe
the old v0.1 shape for contrast.

This note names the issue succinctly so it can be debated before more language
surface is added.

## The Issue

The core question is:

> What exactly is externally callable from a GWT program, and by what name?

Today, the answer is split across multiple mechanisms:

- `REQUEST` and `OUTPUT` define external state shape.
- Block-form `WHEN` defines reusable behavior.
- Single-line `WHEN` executes behavior or a built-in statement.
- `SCENARIO` and `EXAMPLES` define executable spec coverage.
- `EXPORT` can give a stable public name to a behavior call.
- CLI JSON execution accepts `--entry` as either an `EXPORT` name or raw
  behavior-call text.
- Tooling infers entry candidates from `REQUEST` paths when no `EXPORT`
  declarations exist.

Those mechanisms all work, but together they make the public program interface
feel implicit.

## What Is Already Clear

Records are state shape only. They are not objects with methods.

Behaviors are free executable steps over state:

```gwt
WHEN fulfill <order> from <inventory> into <fulfillment>
```

This should be read as a behavior signature, not as a method attached to
`order`, `inventory`, or `fulfillment`.

`SCENARIO` and `EXAMPLES` are executable examples and regression coverage. They
prove behavior, but they are not themselves the host-facing API.

`REQUEST` and `OUTPUT` are data contracts. They say what state must exist before
execution and what state is returned after execution. They do not, by
themselves, choose which behavior is the public workflow.

`EXPORT` is the closest current concept to a public entrypoint:

```gwt
EXPORT price_cart_v1 as price cart
```

## Where It Gets Confusing

The same word, `WHEN`, does two different jobs:

- block-form `WHEN` defines behavior
- single-line `WHEN` calls behavior

The same behavior dispatcher is used for:

- scenario steps
- `.gwt` request-file steps
- internal helper calls inside behavior bodies
- CLI JSON `--entry` execution

That means the runtime has no separate concept of "public behavior" versus
"internal helper behavior".

For example, a program may intend this as the public workflow:

```gwt
WHEN fulfill <order> from <inventory> into <fulfillment>
```

But helper behaviors may also take only `REQUEST`-rooted state:

```gwt
WHEN reset_fulfillment <fulfillment>
WHEN authorize <order> into <fulfillment>
```

If there are no `EXPORT` declarations, inspection/type tooling may infer all of
those as entry candidates. The CLI can also run a raw helper call if the caller
passes it through `--entry`.

That is not a parser bug. It is an interface-boundary ambiguity.

## Working Resolution: `REQUEST` Is The Callable Unit

The clearest direction is to make a named `REQUEST` block the public callable
unit.

Instead of adding `ENTRY`, and instead of keeping `EXPORT` as the public API,
the program declares the request it can handle:

```gwt
PROGRAM inventory allocation

REQUEST fulfill order
  GIVEN order is OrderRequest
  AND inventory is InventoryState

  GIVEN fulfillment is FulfillmentState
    requested_units: 0
    reserved_units: 0
    backordered_units: 0
    unknown_sku_count: 0
    package_count: 0
    shipping_fee: 0
    status: "new"
    reason: "new"

  WHEN fulfill order from inventory into fulfillment

  OUTPUT fulfillment is FulfillmentState
  AND inventory is InventoryState
```

This reads as a public request/response operation:

- `PROGRAM` names the component or ruleset.
- `REQUEST fulfill order` names the callable public request.
- `GIVEN order is OrderRequest` declares caller-provided input state.
- `GIVEN fulfillment is FulfillmentState ...` creates request-local setup state.
- `WHEN fulfill order from inventory into fulfillment` executes the operation.
- `OUTPUT` declares what the caller receives.
- Optional `THEN` assertions can express postconditions.

The reusable implementation still lives in ordinary block-form behavior:

```gwt
WHEN fulfill <order> from <inventory> into <fulfillment>
  GIVEN order is OrderRequest
  AND inventory is InventoryState
  AND fulfillment is FulfillmentState
  reset_fulfillment fulfillment
  count_units order into fulfillment
  authorize order into fulfillment
```

This keeps the BDD rhythm inside the callable unit without turning every
block-form `WHEN` into an external API.

### Scenarios And Public Requests

`SCENARIO` remains top-level executable example coverage.

The scenario syntax should make it clear whether an example is testing a public
request flow or an internal behavior. A single-line `REQUEST` should invoke a
named public request:

```gwt
SCENARIO partial allocation
GIVEN order is OrderRequest
  order_id: "LIST-100"
  payment_status: "paid"
  fraud_score: 12
  expedited: true
  items: []

GIVEN inventory is InventoryState
  items: []

REQUEST fulfill order

THEN fulfillment.status == "partial"
AND fulfillment.reason == "partial_inventory"
```

That reads as: set up example state, run the public request, then assert the
example-specific result.

A scenario can still test a helper behavior directly with `WHEN`:

```gwt
SCENARIO reserve known item
GIVEN order_item is OrderItem
  sku: "widget"
  quantity: 2

GIVEN inventory_item is InventoryItem
  sku: "widget"
  available: 5
  reserved: 0

GIVEN fulfillment is FulfillmentState
  requested_units: 0
  reserved_units: 0
  backordered_units: 0
  unknown_sku_count: 0
  package_count: 0
  shipping_fee: 0
  status: "new"
  reason: "new"

WHEN reserve_known_item order_item using inventory_item into fulfillment

THEN inventory_item.available == 3
AND inventory_item.reserved == 2
AND fulfillment.reserved_units == 2
```

This gives scenarios two clear call forms:

- `REQUEST fulfill order` tests the public request boundary.
- `WHEN reserve_known_item ...` tests reusable behavior directly.

This avoids overloading scenario `WHEN` with both public request calls and
helper behavior calls.

### `OUTPUT` Versus `THEN`

`OUTPUT` and `THEN` should stay separate.

They are both post-execution forms, but they answer different questions.

`OUTPUT` is the response contract. It declares which state paths the caller
receives and what type those paths must satisfy:

```gwt
OUTPUT fulfillment is FulfillmentState
AND inventory is InventoryState
```

It answers:

- What does this request return?
- What shape must returned state have?
- Which final state paths are part of the public response?

It should not encode expected example values. This should stay a shape
declaration:

```gwt
OUTPUT fulfillment is FulfillmentState
```

not:

```gwt
OUTPUT fulfillment.status is "partial"
```

Exact values belong in `THEN`.

`THEN` is an assertion. It declares a condition that must be true after the
request or scenario runs:

```gwt
THEN fulfillment.status != "new"
AND fulfillment.requested_units >= fulfillment.reserved_units
```

It answers:

- What invariant should this request always preserve?
- What example-specific result should this scenario prove?
- What behavior must fail if the condition is false?

Inside a named request, `THEN` is a public postcondition or invariant:

```gwt
REQUEST fulfill order
  GIVEN order is OrderRequest
  AND inventory is InventoryState

  GIVEN fulfillment is FulfillmentState
    status: "new"
    reason: "new"

  WHEN fulfill order from inventory into fulfillment

  OUTPUT fulfillment is FulfillmentState
  AND inventory is InventoryState

  THEN fulfillment.status != "new"
```

Inside a scenario, `THEN` is an example assertion:

```gwt
SCENARIO paid order with partial inventory
GIVEN order is OrderRequest
  payment_status: "paid"
  fraud_score: 12
  expedited: true
  items: []

GIVEN inventory is InventoryState
  items: []

REQUEST fulfill order

THEN fulfillment.status == "partial"
AND fulfillment.reason == "partial_inventory"
```

The run order should be:

1. Scenario `GIVEN` setup.
2. Scenario `REQUEST` call.
3. Named request input validation.
4. Named request local `GIVEN` setup.
5. Named request `WHEN` execution.
6. Named request `OUTPUT` validation.
7. Named request `THEN` postconditions.
8. Scenario `THEN` assertions.

So `OUTPUT` says what is returned and validates type/shape. `THEN` says what
must be true.

The practical rule:

- request-level `OUTPUT` is required for public requests that return state
- request-level `THEN` is optional but useful for public invariants
- scenario-level `THEN` should be expected for executable examples
- exact expected values belong in `THEN`, not `OUTPUT`

This keeps the public response shape separate from behavior assertions.

### Simplest Complete Program

With this model, the smallest complete public program can be:

```gwt
PROGRAM hello

REQUEST say hello
  WHEN set greeting to "hello world"

  OUTPUT greeting is text

  THEN greeting == "hello world"
```

There is no separate host entry name. The callable unit is `REQUEST say hello`.
The request has no caller-provided input, runs one `WHEN`, validates one output,
and checks one postcondition.

A request with caller input stays natural:

```gwt
PROGRAM greetings

REQUEST greet person
  GIVEN name is text

  WHEN set greeting to "hello, " + name

  OUTPUT greeting is text
```

### How A Named Request Would Run

A named `REQUEST` block compiles to a boundary run plan:

1. Select the request by its natural-language name.
2. Load program `BACKGROUND` setup, if any.
3. Load caller-provided JSON state.
4. Validate caller-provided `GIVEN name is Type` bindings.
5. Run request-local `GIVEN` setup blocks and assignments.
6. Run the request's `WHEN` steps as ordinary behavior calls or built-ins.
7. Validate `OUTPUT` bindings.
8. Evaluate request `THEN` assertions, if present.
9. Return only declared output paths as `result`.

This uses the existing behavior-call model. The request-level `WHEN`:

```gwt
WHEN fulfill order from inventory into fulfillment
```

matches the reusable behavior:

```gwt
WHEN fulfill <order> from <inventory> into <fulfillment>
```

and binds:

- `<order>` to the state path `order`
- `<inventory>` to the state path `inventory`
- `<fulfillment>` to the state path `fulfillment`

The named request is public. The behavior remains reusable implementation.

When a scenario uses:

```gwt
REQUEST fulfill order
```

it invokes that same named request run plan using the scenario's current state
as the caller-provided state.

### What Happens To `ENTRY` And `EXPORT`

This direction deletes `ENTRY` as a separate language concept.

It also demotes or removes `EXPORT`. Stable machine-oriented names should not
be the primary source-level interface. If host adapters need machine aliases,
they can derive them from request names or maintain an adapter-side mapping.

The GWT source should privilege the natural request phrase:

```gwt
REQUEST fulfill order
```

not:

```gwt
EXPORT fulfill_order_v1 as fulfill order
```

## Alternatives Considered For `WHEN` And Public Calls

The `WHEN` question is the most important part to settle.

The working resolution above supersedes `ENTRY` and `EXPORT` as the primary
model. The options below remain useful because they show the tradeoffs that led
to named `REQUEST` as the callable unit.

Cucumber and Gherkin provide a useful comparison. In
[Gherkin](https://cucumber.io/docs/gherkin/reference/), `Given`, `When`, and
`Then` are scenario steps. They are public-readable examples, not the
implementation itself. Cucumber then maps those steps to
[step definitions](https://cucumber.io/docs/cucumber/step-definitions/) in a
host language.

GWT intentionally removes that split: the behavior lives in GWT, not in hidden
step-definition code. That is one of the language's core strengths. But it
means GWT still needs an equivalent distinction between:

- a scenario/request step that says what happens
- a reusable behavior definition that implements what happens
- a public entry that outside callers may invoke
- a helper behavior that only other GWT behavior should call

Different languages and frameworks solve similar boundary questions in
different ways. Common patterns include:

- explicit exports, where only named exports are public
- visibility modifiers, such as public/private
- naming conventions, where private helpers use a recognizable name shape
- separate declaration forms, where callable API declarations look different
  from internal helper definitions
- separate test/spec syntax and implementation syntax, as in Cucumber-style
  scenarios plus step definitions

GWT can borrow from those patterns without losing its `GIVEN / WHEN / THEN`
shape.

### Option A: Keep `WHEN`, Make `EXPORT` The Boundary

In this model, block-form `WHEN` continues to define all reusable behavior:

```gwt
WHEN fulfill <order> from <inventory> into <fulfillment>
```

`EXPORT` alone defines what external callers may invoke:

```gwt
EXPORT fulfill_order_v1 as fulfill order from inventory into fulfillment
```

Non-exported behaviors are helpers. A development command may still allow raw
behavior-call text for local experiments.

This is the smallest change from today's language. It keeps the source close to
BDD language and avoids adding another definition keyword. The tradeoff is that
tooling and docs must be strict: inferred entries become a migration aid, not
the public interface model.

### Option A2: Put The Entry With The Boundary Contracts

This is a tighter version of Option A. Instead of leaving public entry metadata
separate from `REQUEST` and `OUTPUT`, the public operation is declared beside
the external state contracts.

For the inventory allocation spike, the current boundary is:

```gwt
REQUEST order is OrderRequest
AND inventory is InventoryState
AND fulfillment is FulfillmentState

OUTPUT fulfillment is FulfillmentState
AND inventory is InventoryState
```

That tells us the external state shape, but not the external operation. The
most BDD-shaped boundary form keeps an explicit `WHEN` between request and
output:

```gwt
ENTRY fulfill order
REQUEST order is OrderRequest
AND inventory is InventoryState
AND fulfillment is FulfillmentState

WHEN fulfill order from inventory into fulfillment

OUTPUT fulfillment is FulfillmentState
AND inventory is InventoryState
```

In this shape, `ENTRY` names or groups the public operation, while the `WHEN`
line is the behavior call that runs at the boundary. This preserves the
familiar BDD rhythm:

1. `REQUEST`: what the caller provides
2. `WHEN`: what happens
3. `OUTPUT`: what the caller receives

The entry header is not a machine identifier. A stable machine-oriented name
such as `fulfill_order_v1` can still exist, but it should be secondary metadata
or an alias, not the primary source spelling.

The implementation remains ordinary behavior:

```gwt
WHEN fulfill <order> from <inventory> into <fulfillment>
  GIVEN order is OrderRequest
  AND inventory is InventoryState
  AND fulfillment is FulfillmentState
  reset_fulfillment fulfillment
  count_units order into fulfillment
  authorize order into fulfillment
```

This has a useful reading:

- `ENTRY` names or groups the external component operation.
- `REQUEST` declares what state the caller must provide.
- `WHEN` declares the public behavior call that runs at the boundary.
- `OUTPUT` declares what state the caller receives.
- Block-form `WHEN` still defines implementation behavior.

For `examples/inventory_allocation_spike`, this would mean `fulfill_order_v1`
could be an external alias for the entry whose boundary call is `fulfill order
from inventory into fulfillment`. Behaviors such as `reset_fulfillment`,
`count_units`, `authorize`, `allocate`, `classify_inventory`, and
`plan_shipping` are helper behaviors unless separately declared in another
`ENTRY`.

This fits the BDD spirit because the public operation still reads as a `WHEN`
step. It also avoids treating every reusable `WHEN` as an external API.

#### `PROGRAM` Versus `ENTRY`

`PROGRAM` and `ENTRY` should not mean the same thing.

`PROGRAM` names the ruleset, module, or component:

```gwt
PROGRAM inventory allocation spike
```

It is document-level identity. It helps humans, manifests, imports, generated
artifacts, and tooling understand what file or component they are looking at.
It is not itself callable.

`ENTRY` names or groups a callable operation inside that program:

```gwt
ENTRY fulfill order
REQUEST order is OrderRequest
AND inventory is InventoryState
AND fulfillment is FulfillmentState

WHEN fulfill order from inventory into fulfillment

OUTPUT fulfillment is FulfillmentState
AND inventory is InventoryState
```

It is operation-level identity. It says, "this is one public way to run this
program through its boundary contracts."

A program can reasonably have:

- zero entries, when it is only executable spec coverage or a reusable imported
  library
- one entry, when it exposes one host-facing decision or workflow
- many entries, when it represents a component with several public operations

For example:

```gwt
PROGRAM inventory allocation

ENTRY fulfill order
REQUEST order is OrderRequest
AND inventory is InventoryState
AND fulfillment is FulfillmentState

WHEN fulfill order from inventory into fulfillment

OUTPUT fulfillment is FulfillmentState
AND inventory is InventoryState

ENTRY quote order
REQUEST order is OrderRequest
AND fulfillment is FulfillmentState

WHEN quote order into fulfillment

OUTPUT fulfillment is FulfillmentState
```

This means the program is the inventory-allocation component, while each entry
is a separate public operation. The entries may share records and helper
behaviors, but each entry owns its public request/output boundary.

If stable machine names are needed, there are two possible directions:

```gwt
EXPORT fulfill_order_v1 as fulfill order from inventory into fulfillment
```

or:

```gwt
ENTRY fulfill order
EXTERNAL fulfill_order_v1
```

The first direction reuses today's `EXPORT` concept. The second direction keeps
all public interface metadata inside the `ENTRY` block. Either way, the natural
`WHEN` phrase should remain primary in source.

#### How An Entry Would Run

An `ENTRY` should not introduce a second implementation mechanism. It should
compile to a boundary run plan over existing GWT behavior.

Given:

```gwt
ENTRY fulfill order
REQUEST order is OrderRequest
AND inventory is InventoryState
AND fulfillment is FulfillmentState

WHEN fulfill order from inventory into fulfillment

OUTPUT fulfillment is FulfillmentState
AND inventory is InventoryState
```

the runtime behavior would be equivalent to:

1. Select the entry by its label or public `WHEN` phrase.
2. Load program `BACKGROUND` setup, if any.
3. Load caller-provided JSON state.
4. Validate this entry's `REQUEST` bindings.
5. Execute the entry's single-line `WHEN` as an ordinary behavior call.
6. Validate this entry's `OUTPUT` bindings.
7. Return only this entry's declared output paths as `result`.

The `WHEN` line inside the entry is not a new implementation body. It resolves
against a normal block-form behavior:

```gwt
WHEN fulfill <order> from <inventory> into <fulfillment>
  GIVEN order is OrderRequest
  AND inventory is InventoryState
  AND fulfillment is FulfillmentState
  reset_fulfillment fulfillment
  count_units order into fulfillment
  authorize order into fulfillment
```

The concrete entry call:

```gwt
WHEN fulfill order from inventory into fulfillment
```

matches the parameterized behavior signature:

```gwt
WHEN fulfill <order> from <inventory> into <fulfillment>
```

and binds:

- `<order>` to the state path `order`
- `<inventory>` to the state path `inventory`
- `<fulfillment>` to the state path `fulfillment`

So the program functions the same way behavior calls already function today.
The change is that the callable boundary becomes explicit and entry-scoped.

If an `ENTRY` label feels redundant, another variant is to make `ENTRY` only a
block marker and let the `WHEN` line be the entry's full identity:

```gwt
ENTRY
REQUEST order is OrderRequest
AND inventory is InventoryState
AND fulfillment is FulfillmentState

WHEN fulfill order from inventory into fulfillment

OUTPUT fulfillment is FulfillmentState
AND inventory is InventoryState
```

This is even closer to `REQUEST / WHEN / OUTPUT`, but it gives tooling less
short human-facing text for entry lists. That tradeoff should be decided
explicitly.

### Option B: Add Public `WHEN`

In this model, visibility lives on the behavior definition itself:

```gwt
PUBLIC WHEN fulfill <order> from <inventory> into <fulfillment>
```

or:

```gwt
ENTRY WHEN fulfill <order> from <inventory> into <fulfillment>
```

Helper behavior stays plain:

```gwt
WHEN reset_fulfillment <fulfillment>
```

This makes the public/helper distinction visible where behavior is defined.
`EXPORT` could still provide stable host names, but the behavior definition
would already declare intent.

The tradeoff is new syntax and a second public-entry concept unless `EXPORT`
and `PUBLIC WHEN` are carefully related.

### Option C: Split Step Calls From Behavior Definitions

In this model, `WHEN` is reserved for scenario/request calls. Reusable behavior
gets a different declaration form:

```gwt
BEHAVIOR fulfill <order> from <inventory> into <fulfillment>
  GIVEN order is OrderRequest
  AND inventory is InventoryState
  AND fulfillment is FulfillmentState
```

Scenarios keep the BDD shape:

```gwt
WHEN fulfill order from inventory into fulfillment
```

This mirrors Cucumber more closely: scenario steps and implementation
definitions are different forms. It also removes the current visual overload of
block-form `WHEN` versus single-line `WHEN`.

The tradeoff is that GWT source no longer uses only `WHEN` for behavior. That
may be clearer technically, but it moves the language a little farther from its
spec-as-code feel.

### Option D: Use Sections For Public Workflows

In this model, the file separates public entries from helper behavior by
section:

```gwt
ENTRIES
WHEN fulfill <order> from <inventory> into <fulfillment>

BEHAVIORS
WHEN reset_fulfillment <fulfillment>
```

This makes the program shape easy to inspect and review. It can also scale to
larger programs with several workflows.

The tradeoff is ceremony. Sections may make GWT feel more like an interface
definition language and less like a compact executable behavior document.

### Option E: Naming Convention Only

In this model, the language keeps today's syntax and treats names as the clue:

```gwt
WHEN fulfill <order> from <inventory> into <fulfillment>
WHEN _reset_fulfillment <fulfillment>
```

or:

```gwt
WHEN helper reset_fulfillment <fulfillment>
```

This follows languages that use naming conventions for private helpers. It is
simple and cheap.

The tradeoff is weak enforcement. It documents intent, but it does not create a
hard public boundary unless the checker and tooling enforce the convention.

## Working Vocabulary

Use these terms when discussing the design:

- Program file: a `.gwt` file that declares records, contracts, behavior, and
  embedded scenarios.
- Program: the document-level ruleset or component named by `PROGRAM`.
- Named request: a public callable request/response operation declared with
  `REQUEST <name>`.
- Request input: caller-provided state declared by a typed `GIVEN` inside a
  named request.
- Request setup: request-local state created by ordinary `GIVEN` setup inside a
  named request.
- Scenario: executable spec coverage inside a program file; it may call public
  requests with single-line `REQUEST` or helper behavior with `WHEN`.
- Request file: a `.gwt` input script containing `GIVEN`, `WHEN`, and optional
  `THEN` steps, run against a program file.
- JSON boundary run: host-style execution that selects a named request.
- Behavior: any block-form `WHEN` definition.
- Helper behavior: a behavior intended only to be called by other GWT behavior.
- Public request: a named request that external callers are meant to invoke.
- External alias: an optional host-adapter name for a public request, not the
  primary source-level interface.

## Open Design Questions

These are the basics to settle before adding more language surface:

1. Should a named `REQUEST` require at least one `WHEN`, or may pure setup/output
   requests be valid?
2. Should `GIVEN name is Type` inside a named request always mean
   caller-provided input when it has no value/body?
3. Should raw behavior-call text remain accepted by the CLI, or should callers
   always select a named request outside development/debug modes?
4. Should `.gwt` request files remain as a separate input-script concept, or
   should named requests cover most of that use case?
5. Should block-form `WHEN` remain the behavior definition form, or should GWT
   split scenario/request `WHEN` calls from behavior declarations?
6. Should top-level `REQUEST path is Type` and `OUTPUT path is Type` be removed
   from the public boundary model and replaced by named requests?
7. Should `EXPORT` be removed from the source language, with any machine aliases
   handled outside GWT source?
8. Should stable machine names live outside GWT source in host adapter config,
   or should GWT provide optional alias metadata for named requests?

## Leading Direction

The leading direction from this discussion is:

- `SCENARIO` / `EXAMPLES` are for executable specification.
- `.gwt` request files are for language-native request scripts and local
  experiments.
- JSON runs select explicit named `REQUEST` blocks as the external program
  boundary.
- Each named `REQUEST` owns its public `GIVEN / WHEN / OUTPUT / THEN` run plan.
- Request-level `GIVEN` declares caller input or request-local setup.
- Request-level `WHEN` is a normal behavior call or built-in, not a new
  implementation body.
- Scenario-level `REQUEST` calls a named public request.
- Scenario-level `WHEN` calls reusable behavior directly.
- `OUTPUT` declares returned state shape; `THEN` asserts required truth.
- Block-form `WHEN` continues to define reusable behavior.
- Behaviors not referenced by a named request are helpers unless they are called
  by scenarios, request files, or a development-only raw-call command.
- `ENTRY` is not needed.
- `EXPORT` is not needed in the source language.
- Stable machine-oriented names, if needed, should be secondary metadata rather
  than the primary source spelling, preferably outside GWT source.

This keeps GWT's public interface in natural BDD-shaped language while making
external callability explicit instead of inferred.

## Plan

This should be approached as a language-interface cleanup, not as a small parser
feature. A reasonable path is:

1. Freeze the named-request shape in a design note before implementing it:

   ```gwt
   REQUEST fulfill order
     GIVEN order is OrderRequest
     AND inventory is InventoryState

     GIVEN fulfillment is FulfillmentState
       requested_units: 0
       reserved_units: 0
       backordered_units: 0
       unknown_sku_count: 0
       package_count: 0
       shipping_fee: 0
       status: "new"
       reason: "new"

     WHEN fulfill order from inventory into fulfillment

     OUTPUT fulfillment is FulfillmentState
     AND inventory is InventoryState
   ```

2. Decide the exact request-local `GIVEN` rule:

   ```gwt
   GIVEN order is OrderRequest
   AND inventory is InventoryState
   ```

   means caller-provided input, while:

   ```gwt
   GIVEN fulfillment is FulfillmentState
     status: "new"
   ```

   means request-local setup.

3. Decide whether a named request must contain at least one `WHEN`. Requiring a
   `WHEN` preserves the BDD shape; allowing no-`WHEN` requests makes simple
   setup/output programs possible.

4. Since the language is experimental, choose the clearest model rather than
   preserving older public-boundary surfaces:

   - introduce named request blocks as the new public boundary
   - replace top-level `REQUEST path is Type` / `OUTPUT path is Type` as the
     primary request/response interface
   - remove `EXPORT` from the source model
   - stop presenting inferred entry candidates as the public interface

5. Add parser support for named `REQUEST` blocks and represent them explicitly
   in the program model. A named request should contain:

   - natural-language request name
   - caller input bindings from typed `GIVEN`
   - request-local setup `GIVEN` statements
   - public request calls in scenarios as single-line `REQUEST <name>`
   - one or more `WHEN` steps, depending on the final rule
   - `OUTPUT` bindings
   - optional `THEN` assertions
   - optional external alias metadata only if the design keeps it

6. Add checker rules:

   - named request names must be unique within a program
   - typed input `GIVEN` and `OUTPUT` types must be known
   - input and output contract paths must not overlap within the same direction
   - request `WHEN` calls must resolve to known behavior or built-ins
   - scenario `REQUEST` calls must resolve to named requests
   - request `WHEN` arguments should be checked against request input/setup
     scope
   - request `THEN` assertions should be checked like scenario assertions
   - helper behaviors remain callable from other behaviors and scenarios

7. Update runtime/API/CLI semantics:

   - JSON execution selects an explicit named request
   - runtime loads JSON state, validates request input `GIVEN`s, runs
     request-local setup, runs request `WHEN`s, validates `OUTPUT`, evaluates
     `THEN`, and returns the request's declared result
   - scenario `REQUEST` calls run the same named-request plan against scenario
     state before scenario `THEN` assertions
   - raw behavior-call execution moves behind a development-oriented option, if
     kept at all

8. Update inspection and type generation:

   - `gwt inspect` reports named requests separately from all behaviors
   - generated host types expose a request-name union instead of inferred
     behavior entries
   - inferred entry candidates become warnings, migration hints, or disappear
     from the public manifest when named requests exist

9. Migrate examples in order of usefulness:

   - `examples/inventory_allocation_spike`
   - `examples/order_fulfillment`
   - `examples/language_tour`
   - `examples/vendor_onboarding`
   - smaller examples only after the model is stable

10. Add tests at each layer:

   - parser tests for named request blocks
   - checker tests for request input/setup/output rules
   - checker tests for missing or ambiguous request `WHEN` calls
   - checker/runtime tests for scenario `REQUEST` calls
   - runtime tests for named-request execution
   - CLI tests for JSON request selection
   - inspect/typegen tests proving helpers are not public requests

11. Only then update the normative docs:

    - `docs/spec/v0.1.md` or a future versioned spec
    - `docs/grammar.md`
    - `docs/language.md`
    - README examples and command snippets
