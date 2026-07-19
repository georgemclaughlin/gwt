# GWT Design Principles

GWT is an executable behavior language originally inspired by OpenSpec's
persistent-spec idea and shaped by Cucumber, SpecFlow/Reqnroll, spec-driven
development, and BDD-style examples. GWT does not use OpenSpec or depend on its
workflow. The connection is conceptual: OpenSpec showed a stronger version of
spec-driven development than prompt-heavy planning workflows, and GWT takes the
idea of a durable collaboration spec in a more executable direction. Its source
should read like a concrete specification of state, behavior, and expected
outcomes.

This document is non-normative. The implemented language surface is specified
in [spec/v0.2.md](spec/v0.2.md), but new syntax and runtime features should be
judged against these principles before they are added.

## Influences

GWT sits at the intersection of a few related traditions:

- OpenSpec treats repo-local specs as the source of truth for how the system
  behaves, with proposed changes captured as artifacts and delta specs before
  they are archived into the main specs. GWT borrows from that durable source
  of truth idea, but is a separate language with a different endpoint: the
  behavior spec is also the runtime program.
- GitHub Spec Kit and BMAD represent the broader agent-era move toward
  structured prompts, planning artifacts, product scenarios, tasks, and
  lifecycle workflows. They are useful context, but they also show the boundary
  GWT is trying to cross: spec-driven development should not stop at better
  prompting or better handoff documents.
- Cucumber and SpecFlow/Reqnroll make Given/When/Then scenarios executable as
  automated tests. GWT borrows the readability and scenario shape, but avoids a
  split where feature files describe behavior and separate step-definition code
  implements it. In GWT, reusable `WHEN` behavior is part of the same language.

The practical synthesis is: GWT should be a persistent, reviewable, executable
specification for domain behavior.

The important difference is semantic, not cosmetic. A Markdown spec can guide
an agent, but the final behavior still depends on a translation step into
separate code. A GWT program should not require that semantic handoff. Once a
behavior is expressed in GWT, its meaning is the parser, checker, runtime, and
observable outputs.

## Core Intent

GWT programs should stay close to `GIVEN / WHEN / THEN` thinking:

- `GIVEN` describes relevant state.
- `WHEN` names behavior that happens.
- `THEN` checks the observable result.

Reusable behavior should also read as behavior, not as low-level data plumbing:

```gwt
WHEN reserve <order_item> from <inventory> into <fulfillment>
```

The language is for deterministic workflows, rules, examples, and
request/response programs whose behavior should be inspectable by people who
care about the domain outcome.

## GWT Programs Define Domain DSLs

GWT is an executable domain-language workbench. Its fixed grammar is a
construction substrate rather than the final domain language seen by an author
or an agent. Each checked program defines a narrower domain DSL through its
`TYPE` and `RECORD` vocabulary, named `REQUEST` boundaries, behavior
signatures, and executable scenarios.

In Domain-Driven Design terms, those elements capture the executable slice of
a team's ubiquitous language:

- types and records name domain nouns and explicit states;
- behavior signatures name domain verbs in the team's normal vocabulary;
- request and output contracts identify supported system boundaries;
- scenarios establish the meaning, boundaries, and precedence of those words.

This is not a grammar-builder claim. Programs do not invent new parsing rules,
and GWT should not grow syntax merely to make every domain phrase legal. It is
also not a claim that all domain knowledge is executable: motivations,
heuristics, context, and unresolved product decisions can remain outside the
runtime program.

For example, `WHEN reserve <order_item> from <inventory> into <fulfillment>` is
more than a reusable function. It is a sentence in the order-fulfillment DSL.
Once that vocabulary exists, authors and agents should prefer it over spelling
the same intent repeatedly with low-level mutation.

This distinction matters for agent-assisted work:

- during domain discovery, an agent can help compare names, boundaries, record
  shapes, and scenario pressure tests, but humans must own those design choices;
- after the vocabulary stabilizes, an agent can act as a natural-language
  interface that proposes changes entirely within the checked domain language;
- the generated `.gwt` program, not the prompt or transcript, remains the
  normative and maintainable artifact;
- reliability comes from the program-specific vocabulary plus deterministic
  checking, formatting, and scenarios, not from `GIVEN / WHEN / THEN` spelling
  alone.

See [dsl-and-llms.md](dsl-and-llms.md) for the full model and
[agent-authoring.md](agent-authoring.md) for the authoring and repair loop.
`gwt agent-context` makes the program-specific vocabulary and a bounded set of
worked scenarios available to any agent without duplicating durable domain
knowledge into a provider-specific skill.

## Spec Is The Code

Spec-driven development is increasingly useful in agent-assisted software work,
but too much of it can collapse into fancy prompting: better instructions,
better generated plans, and better task lists, while the executable behavior
still lives somewhere else.

OpenSpec-style persistent specs point in a more durable direction. They give
humans and agents a shared collaboration point before implementation changes
are made, and the spec/change/archive loop keeps behavior intent visible over
time. That loop is the clearest precursor for GWT's product direction.

GWT takes that idea further. The spec is not just planning material that an
agent translates into separate application code. The spec is the executable
program.

This has practical consequences:

- Domain behavior should remain visible in GWT source, not disappear into
  generated host code.
- Agent-generated changes should improve the executable spec and its examples,
  not bypass them.
- Runtime behavior, tests, docs, and editor tooling should all reinforce the
  same source of truth.
- Host applications can integrate with GWT through JSON/API boundaries, but the
  durable business behavior should stay in the GWT rules.

This makes GWT different from workflows where a persistent spec is only a
collaboration artifact. In GWT, the collaboration artifact is also the runtime
artifact.

## No Semantic Handoff

Agent-assisted workflows are welcome in GWT, but the durable behavior must not
hide in the agent transcript or in generated host code. Agents may explore,
draft, critique, refactor, and extend GWT programs. The committed behavior
change should still land as executable GWT source, executable scenarios, record
contracts, examples, or docs that explain those runtime artifacts.

This gives GWT a different standard from prompt-centered spec workflows:

- Natural language may describe intent, but executable GWT defines normative
  behavior.
- If a requirement cannot yet be expressed as state, behavior, contracts, and
  assertions, it is still underspecified.
- Host code can call GWT through JSON/API boundaries, but it should not
  reimplement durable domain rules that belong in GWT.
- Tests should exercise the GWT behavior itself, not only a generated host
  translation of it.

This does not remove every kind of ambiguity. Product goals, UX judgment,
architecture, naming, and domain modeling can still require human decisions.
GWT's claim is narrower and stronger: deterministic behavior ambiguity should
be resolved before the spec is treated as executable.

## Anti-Goals

GWT should not become a SQL-like query language.

Avoid adding features that make programs read like:

```sql
UPDATE inventory.items
SET reserved = reserved + quantity
WHERE sku = order_item.sku
```

Avoid broad query concepts unless a concrete workflow example proves they are
necessary:

- `SELECT` / `UPDATE` / `JOIN` vocabulary
- grouping, ordering, or projection syntax
- general-purpose query pipelines
- implicit set-based mutation

The point is not that GWT can never inspect collections. It already can. The
constraint is that collection features should read like steps in an executable
example, not like a database algebra.

GWT should also not be positioned as a policy decision point like Open Policy
Agent. OPA and Rego are designed for declarative policy evaluation and
distributed enforcement decisions. GWT is for executable behavior specs and
deterministic request/response workflows where state transitions, scenarios,
contracts, and outputs stay visible in one durable artifact.

Avoid describing GWT as an authorization engine, admission controller, or
general policy engine. A GWT workflow can produce a decision record, but that is
part of an executable behavior spec, not an OPA-style policy query service.

## Feature Shape

When a workflow needs collection behavior, prefer narrow, action-oriented forms
that name a domain object and immediately describe what happens with it.

For example, the pressure-test example in
[`examples/inventory_allocation_spike`](../examples/inventory_allocation_spike)
originally exposed this awkward pattern:

```gwt
exists inventory_item in inventory.items WHERE inventory_item.sku == order_item.sku into inventory_match_found
IF inventory_match_found
  find inventory_item in inventory.items WHERE inventory_item.sku == order_item.sku into selected_inventory_item
  reserve_known_item order_item using selected_inventory_item into fulfillment
ELSE
  add 1 to fulfillment.unknown_sku_count
```

That was evidence for a first-class matched-record behavior, not evidence for
SQL. The current step-like form is:

```gwt
FIND inventory_item in inventory.items WHERE inventory_item.sku == order_item.sku
  reserve_known_item order_item using inventory_item into fulfillment
ELSE
  add 1 to fulfillment.unknown_sku_count
```

This binds one matched record as an obvious local name, runs behavior against
it, and makes the missing case explicit.

## One-Of Record Data

When an example needs tagged domain cases, prefer a record-like design that
keeps cases explicit without forcing placeholder fields. MiniLang currently
shows the problem with an AST statement record that has one `kind` field and
many fields that only apply to some cases.

The current design is documented in
[`variant-match-design.md`](variant-match-design.md). The important guardrail
is that kind-based branching should remain a behavior-body step over domain
state, not a general-purpose pattern matching expression system.

Deferred ideas that need more pressure before syntax, including explicit
initialization helpers and first-match collection, are tracked in
[`deferred-language-ideas.md`](deferred-language-ideas.md).

## Missing Values

GWT should treat missing, unknown, and not-applicable values as domain states,
not as silent placeholders. When those cases have different meanings, durable
GWT behavior should normalize boundary data into explicit fields or one-of
records before workflow logic depends on it.

`optional<Type>` is the deliberately narrow exception for a boundary where
absence is the only relevant fact. A missing property and JSON `null` collapse
to the same absent value, there is no source-level `null` literal, and behavior
must use an explicit `is present` guard before operating on the inner value.
Do not use `optional<Type>` when the distinction between missing, unknown, and
not-applicable matters. Prefer a domain-shaped representation such as
`status: "provided" | "missing"`, or a one-of record with `provided`, `missing`,
and `not_applicable` cases. A separate `has_value` boolean is only useful when
that boolean is independently meaningful; it should not be boilerplate that
duplicates an optional field's presence.

## Scenarios As Evidence

Substantial public examples should include embedded `SCENARIO` blocks with
top-level `THEN` assertions. JSON request files are important for host-facing
execution, but they should not be the only proof that an example behaves as
intended.

This should remain a strong convention, not a hard language requirement.
Reusable behavior modules, imported helper files, and request-only files can be
valid without scenarios. A future checker warning can reinforce the convention
for files that define behavior but provide no scenarios or assertions, as long
as it avoids those legitimate module/request cases.

## Design Checklist

Before adding syntax, answer these questions:

- Does it make a medium-sized realistic example read more like a behavior spec?
- Can the feature be explained as a concrete step over state?
- Is the missing or failure case explicit?
- Does a public example include executable scenarios with assertions?
- Does it preserve deterministic execution and debuggable state?
- Can it be checked, formatted, documented, and covered by examples?
- Would a Cucumber or SpecFlow user recognize the shape as behavior-oriented?
- Is there a smaller behavior-shaped primitive than a general query feature?
- Could a reusable domain behavior, a better example, richer inspection
  context, or a more precise diagnostic solve the authoring problem without new
  syntax?

If the answer trends toward query language design, stop and look for a narrower
BDD-shaped operation.
