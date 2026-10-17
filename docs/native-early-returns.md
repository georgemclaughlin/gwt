# Facts after early-return guards

Native behavior can handle an exceptional case and then continue with facts
established by the remaining path:

```gwt
IF facts.proof is absent
  RETURN "missing_proof"
IF facts.proof.kind != "receipt"
  RETURN "gift_route"
IF not facts.proof.verified
  RETURN "unverified"
RETURN "receipt_available"
```

The behavior declares `THEN returns text`. The
[worked exchange rule](../examples/native_early_returns/README.md) also reads
receipt fields after these guards. The first guard establishes presence for
later steps. The
second establishes the receipt kind. Neither needs an ELSE around the rest of
the behavior. This extends native checking/execution over existing syntax.

## Which paths contribute facts

For IF and ordered DECIDE, a branch proven to exit on every path cannot reach
subsequent statements. The continuation retains only supported condition facts
common to every remaining branch. An IF without ELSE has an empty false branch
that can continue. A sole surviving true or false branch can therefore carry
its corresponding presence/kind facts forward.

Presence must be established for the same source path on every continuing
alternative. Kind restrictions along one path intersect; continuing alternatives
join by union. If phone and pickup can continue but email returns, the later
value can be either phone or pickup. Only fields valid for that remaining set
are usable. Nested ancestors are established before their children. A path that
is not available under the joined parent kinds does not escape the branch.

Kind DEPENDING ON likewise removes definitely exiting alternatives from the
continuation's possible-kind set. Its branch bodies still protect the selected
runtime kind. The continuation instead protects the union of kinds that can
continue, so it can allow replacements that the individual branch could not.
Scalar-value dispatch does not introduce new scalar refinement types.

FIND can establish outer-state facts from its true filter when its missing-case
body definitely exits and its selected body can continue. The item binding
itself remains local. A selected-body return does not establish false filter
facts in a continuing ELSE: the collection could have been empty. FOR may
execute zero times and establishes no facts after the loop.

## Deliberate inference boundaries

Exit analysis recognizes RETURN and literal `REQUIRE false`, including a
parenthesized false literal. Complete decisions/dispatch and FIND with both
alternatives exiting can prove a containing branch exits. A helper's return or
failure is not inferred as an exit from its caller. Other assertions and
ordinary FOR bodies cannot prove that their containing branch always exits.
See [explicit failure exits](native-failure-exits.md) for the required-lookup
example and deliberate compatibility changes.

The join now also includes successful REQUIRE proofs and nested continuation
proofs established within each continuing body. The
[branch-exit rules](native-branch-proofs.md) retain only facts common to every
continuing alternative, including dispatch and both FIND outcomes. Local
bindings and filter items retain their local scope. This is conservative flow
analysis, not arbitrary theorem proving or inferred helper postconditions.
When every alternative exits, later source is still checked without
manufacturing an impossible-state proof.

## Lifetime, mutation, and contracts

Condition guards protect each selected body. On normal continuation, the common
facts become guards owned by the containing body and remain active for its
remaining steps. Errors or returns do not activate a continuation. Normal exit,
return, and failure release only guards introduced in the exited scope; caller
and surrounding guards remain active.

Other aliases cannot clear a proven-present path or replace a value/ancestor
with a kind outside the surviving set. Failures use presence_mutation or
kind_mutation before successful write evidence or mutation. Present replacements
and kinds inside the surviving set remain allowed. Shared arguments still need
exact checked contracts; grouped arguments pass copies. Declared return and
request-output contracts retain their original boundary types.

This intentionally changes some old native programs. An absence-return guard
could previously be followed by clearing the optional value through a wider
alias. The new continuation protects its presence. A narrower checked argument
can also stop matching a wider mutable helper contract. Review captured cases
when moving engines; unchanged source is not a compatibility guarantee.

## Evidence and editing

The checked statement records continuation guards. Runtime registration adds
no synthetic reads, assertion events, or budget steps. Actual condition tests,
selected/skipped branches, returns, calls, and mutations remain the evidence.
Unicode/CRLF source spans and saved-case formats retain their existing meaning.
Hover and definitions follow a uniquely selected payload declaration in later
reads and copies, including unsaved imported types. Ambiguous kind sets retain
the existing binding fallback instead of guessing a declaration.

The [checkpoint](../evaluations/native_editor/2026-10-16-early-returns/README.md)
qualifies 20 independent exchange inputs, eight scenarios, exact boundary fault
detection, and a nested-ELSE-to-guard-clause source adaptation. Every old nested
case first migrates with its full observation preserved; comparison with the new
source then preserves all decisions and state while retaining changed execution
evidence. A separate migration captures the deliberate alias-clearing failure.
These proposals are unapproved and do not measure human comprehension benefit.
