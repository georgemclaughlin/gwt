# Deferred Language Ideas

This note tracks useful ideas that should wait for more example pressure before
they become language syntax.

## Explicit Initialization Helpers

The native [typed local record form](native-local-records.md) now addresses
the template-passing problem demonstrated by weighted allocation. A returning
domain behavior can construct its result using `LET name be RecordType:` with
visible fields. This does not introduce implicit defaults or eliminate repeated
policy-specific initialization; those broader ideas remain subject to the
criteria below.

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

`FIND ... ELSE` now provides a first matching item and an explicit missing case
in both toolchains. The [expense adaptation](native-source-adaptation.md) replaces
an existence check followed by a second search. The
[subscription adaptation](native-existence-decisions.md) uses the same primitive
inside a named boolean-returning behavior for a standalone existence question.
These implemented paths no longer require a loop flag just to stop at a match.

Do not add SQL-like filtering, joins, ordering, projection pipelines, or
implicit set-based mutation. If this feature becomes necessary, keep it narrow
and step-shaped.

Remaining questions:

- broader migration of mandatory lowercase `find`, beyond the
  [required inventory inspection](native-failure-exits.md), and optional lookup's
  unchanged-on-missing behavior; check failure semantics and destination sharing;
- predicate needs that the existing expression and flow-proof rules cannot
  express clearly;
- example-specific evidence that justifies another primitive.

External pilots remain deferred by the owner. Further local examples can expose
design needs, but cannot establish human benefit. Require a concrete before/after
workflow and independent behavior checks before extending syntax.
