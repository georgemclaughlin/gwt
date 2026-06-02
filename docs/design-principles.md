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
in [spec/v0.1.md](spec/v0.1.md), but new syntax and runtime features should be
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

## Design Checklist

Before adding syntax, answer these questions:

- Does it make a medium-sized realistic example read more like a behavior spec?
- Can the feature be explained as a concrete step over state?
- Is the missing or failure case explicit?
- Does it preserve deterministic execution and debuggable state?
- Can it be checked, formatted, documented, and covered by examples?
- Would a Cucumber or SpecFlow user recognize the shape as behavior-oriented?
- Is there a smaller behavior-shaped primitive than a general query feature?

If the answer trends toward query language design, stop and look for a narrower
BDD-shaped operation.
