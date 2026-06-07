# Deferred Language Ideas

This note tracks useful ideas that should wait for more example pressure before
they become language syntax.

## Explicit Initialization Helpers

Large decision records often require the same initialized fields in a named
`REQUEST` and in a reset behavior. Examples such as vendor onboarding and the
MiniLang VM make this visible through repeated zero, false, empty-list, and
`"new"` setup.

Do not add implicit record defaults just to reduce typing. Hidden defaults would
weaken the executable-spec shape by moving important initial state away from the
request or scenario that depends on it.

A future design should stay explicit, reviewable, and behavior-shaped. Possible
directions:

- a reusable setup/factory form that constructs a named record value
- a request-local initialization helper that is still visible in source
- checker lint that detects duplicated setup/reset blocks before adding syntax

Any proposal should include runtime tests, checker coverage, formatter support,
docs, and at least one public example that becomes clearer after the change.

## First-Match Collection

Some workflows need to scan a collection and apply only the first matching
domain rule. Today this can require guard booleans inside `FOR` loops. That is
awkward, but broad query syntax would violate GWT's design principles.

Do not add SQL-like filtering, joins, ordering, projection pipelines, or
implicit set-based mutation. If this feature becomes necessary, keep it narrow
and step-shaped.

Possible directions:

- a focused first-match behavior over a list with an explicit missing case
- better predicate support for existing `FIND` / `FIND ... ELSE` forms
- example-specific refactors that prove the need before syntax is added

This should wait until the current `DECIDE` cleanup and type-alias work have
settled. If examples still show repeated guard-state patterns afterward, write
a design note with pressure-test before/after code before implementing syntax.
