# Facts established by collection filters

Native `FOR ... WHERE` and `FIND ... WHERE` carry supported true-condition facts
into the selected body:

```gwt
FOR parcel in queue.parcels WHERE parcel.route is present and parcel.route.kind == "counter"
  print parcel.route.code

FIND parcel in queue.parcels WHERE parcel.route is present and parcel.route.kind == "counter"
  set dispatch.first_code to parcel.route.code
ELSE
  set dispatch.first_code to ""
```

The body can use a present optional value and the selected kind's payload
directly. This reuses existing syntax and the same proof rules as
[IF/DECIDE conditions](native-kind-conditions.md) and
[REQUIRE steps](native-require.md).

## Selection and scope

Each visit evaluates its filter against the current item and current surrounding
state. Supported true facts apply only while that item's selected body runs.
They can describe the item, nested optional fields, or a surrounding binding
mentioned in the filter. Direct optional list items also become usable as their
inner type when the filter proves presence.

Conditions keep their existing short-circuit rules. Absent records and fields
of an unselected kind are not read. False filters run no body and introduce no
guards. FOR continues in source order; FIND stops after its first matching body.
A later filter sees earlier mutations to state or later collection items. This
is step-by-step traversal, not a set selected before mutations begin.

Item bindings and filter facts do not escape into following steps or FIND's
ELSE. The fallback gains neither true nor false filter facts: an empty collection
can reach it without evaluating the filter at all. Existing surrounding facts
remain available in that fallback.

Proof inference remains conservative: direct presence tests, literal kind
comparisons, negation, true conjunction, and the corresponding false-disjunction
rules. An alternative condition that can succeed without presence does not prove
presence. Ordinary boolean truth and numeric ranges are not refinement types.
[Early-return guards](native-early-returns.md) also retain supported facts on
continuing paths. A FIND whose ELSE returns can retain true filter facts about
outer state after it completes; its item binding still cannot escape.
[Branch-exit joins](native-branch-proofs.md) also include supported proofs made
inside either FIND body, retaining only facts common to every continuing exit.
FOR may still execute zero times and contributes no new facts afterward.

## Mutation and lifetime

The selected body protects proven state addresses using the existing presence
and kind guards. Other aliases cannot clear a proven-present item/field or
replace it or an ancestor with a value outside the proven kind set. Failures use
`presence_mutation` or `kind_mutation`, before successful write evidence or state
mutation. Replacement with another present value or a kind within the allowed
set is permitted. Exact shared-argument contracts and grouped copies retain
their existing rules.

These guards protect type facts, not the truth of the entire predicate. A body
can change an ordinary `ready` or `enabled` boolean used by its filter. That
change can affect later selection; the body is not reselected midway through.
The collection's existing structural guard still prevents appending to or
replacing an active traversal source or its ancestor.

Each selected body releases its filter proofs on normal completion, RETURN, or
failure, before another iteration or a caller resumes. A caught supported failure
retains earlier successful mutations while releasing the exited traversal/body's
own guards. Guards belonging to surrounding REQUIRE steps, branches, or nested
traversals remain active. FIND releases its own structural guard before its
missing-case body, as before.

## Evidence and compatibility

The checked iteration stores its guards. Execution continues to record the
actual item, short-circuit operands, selection, body events, and collection exit.
Proof registration adds no synthetic reads, assertions, or budget steps.
Navigation and hover follow the selected payload declaration through optional
items, nested records, mutation paths, copies, and unsaved imported types.

This deliberately changes some previously executable native programs: a filter
that proved presence could previously be followed by clearing that value through
a wider alias. The selected body now protects the proof. A refined bare-path
argument can also cease to match a wider mutable helper contract. Use a copy
when mutation is unnecessary, or move a deliberately invalidating operation
after the proof's scope. Do not assume all old programs preserve observations.

The [qualification checkpoint](../evaluations/native_editor/2026-10-16-filter-proofs/README.md)
retains an actual old/new engine comparison, unchanged previous case bytes,
and verified candidate guard failure. It remains an unapproved migration.

The [pickup example](../examples/native_filter_proofs/README.md) includes five
scenarios and 15 top-level expectations. Independent checks cover 57 empty,
single-item, and ordered two-item queues. Removing readiness changes 14 outcomes.
Additional checks cover optional scalar items, unsafe proof forms, nested aliases,
allowed kind sets, external-state filters, live later-item updates, exact helper
contracts, cleanup, returns, caught failures, Unicode/CRLF evidence, replay,
scenario generation, and execution budgets. These tests do not establish a
measured human-review benefit or full native language coverage.
