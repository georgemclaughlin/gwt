# Facts established on every continuing branch

Native checking now retains presence and kind facts proved inside every branch
that can reach the next statement. Authors can keep distinct policy checks in
their relevant branches and use the common result afterward:

```gwt
IF facts.mode == "counter"
  REQUIRE facts.staff_checked
  REQUIRE facts.proof is present
  REQUIRE facts.proof.kind == "receipt"
ELSE
  REQUIRE facts.locker_checked
  REQUIRE facts.proof is present
  REQUIRE facts.proof.kind == "receipt"
REQUIRE facts.proof.reference != ""
RETURN facts.proof.reference
```

The [collection authorization example](../examples/native_branch_proofs/README.md)
has independent policy probes, successful scenarios, and explicit rejection
scenarios. The common receipt access needs no repeated presence/kind assertion
or extra surrounding branch. This is a change to native checking and proof
lifetime over existing syntax, not a new condition language.

## What can reach the continuation

For each continuing branch, the checker combines facts from its entry condition
with successful `REQUIRE` steps and nested statement continuations. Only facts
common to every continuing alternative become available afterward. A branch
that structurally returns or fails on every path contributes no continuation. An IF without ELSE
still has an empty false alternative, which supplies no new facts. If all
alternatives exit, later source is checked without inventing an impossible-state
proof.

Presence requires the same path on every continuing alternative. Successive kind
restrictions within an alternative intersect; alternatives join by union. If one
branch permits only phone and another permits phone or pickup, the continuation
permits phone or pickup. Ancestor presence/kinds are established before nested
fields. A field absent or incompatible under the joined parent type does not
escape the branch. The actual outer binding slot must match; equal local names
or aliased values do not establish a fact about another source path.

The rule applies to IF, ordered DECIDE, kind dispatch, scalar-value dispatch,
and FIND. Scalar dispatch contributes body proofs but no new scalar singleton
or numeric-range types. FIND joins its selected and missing bodies; true filter
facts contribute only to the selected body. Its missing body has no false-filter
proof because an empty collection can reach it without testing a filter.

FOR may execute zero times and establishes no new continuation facts. Local
bindings and FIND items never become outer bindings. A helper's successful
REQUIRE does not refine its caller's aliases. Boolean theorem proving, facts
across alternative disjuncts, numeric ranges, and arbitrary inferred
postconditions remain outside this analysis. Literal `REQUIRE false` is now a
[structural failure exit](native-failure-exits.md); other failing expressions
are not evaluated to infer exits. Failed expected actions do not manufacture proofs.

## Runtime lifetime and deliberate compatibility change

The runtime already protects a branch's entry/REQUIRE proofs until that branch
exits. On normal completion it now registers the joined proofs in the containing
body before executing another statement. There is no intervening user operation.
Errors or returns do not activate a continuation. Normal exit, return, and
failure release only guards owned by the exited scope; caller guards remain.

An alias cannot clear a proven-present path or replace it or an ancestor with a
kind outside the joined set. Such writes fail before successful mutation evidence
or state change. Replacement values that preserve presence and an allowed kind
are valid. The continuation protects the union of surviving kinds, not whichever
narrower branch happened to execute. Declared request/return boundaries remain
unchanged; shared parameters still require exact checked contracts.

This deliberately changes some previously valid native programs. A branch-local
proof shared by every exit used to expire at the branch boundary; an alias write
afterward could clear that value. The same source now retains the proof and can
fail with `presence_mutation` or `kind_mutation`. A later presence test can also
become redundant and fail checking, or a shared argument can stop matching a
wider mutable contract. Use explicit engine migration and review every retained
case, including unavailable candidates. Do not silently move saved cases to the
new engine or assume unchanged source preserves behavior.

The proof metadata adds no synthetic reads, assertion events, or execution steps.
Actual assertions, selected/skipped branches, return values, and mutations remain
the explanation. Existing limits, exact source spans, capture/replay, and
source-backed navigation apply. The checker annotates later paths with the
joined types, so navigation can use a uniquely known payload declaration.

The [qualification checkpoint](../evaluations/native_editor/2026-10-16-branch-proofs/README.md)
records tests, actual engine transitions, and current limitations. It does not
establish human comprehension benefit or complete language coverage.
