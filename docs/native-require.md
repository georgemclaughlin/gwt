# Facts established by REQUIRE

A successful native `REQUIRE` can establish optional presence or a one-of kind
for the remaining statements in its containing block:

```gwt
REQUIRE facts.method is present
REQUIRE facts.method.kind == "bank"
REQUIRE facts.method.verified
set transfer.account to facts.method.account
```

This lets validation steps precede their dependent work directly. No new grammar
is introduced. The experimental native checker and runtime implement this
semantics; it is not a change to the Python v0.2 specification.

## Facts and scope

`REQUIRE` evaluates its checked boolean condition once. If false, it records the
failed assertion and stops with `assertion_failed`. On success, the checker uses
the same conservative true-condition facts as [IF presence](native-presence.md)
and [kind conditions](native-kind-conditions.md):

- `path is present`, and negations of absence, establish presence.
- Comparing `path.kind` with a literal selects or excludes that kind. Either
  operand order is supported; ordinary fields called `kind` remain ordinary.
- A true conjunction retains both operands' facts. Negation and false
  disjunction compose through the existing short-circuit rules.

Each subsequent `REQUIRE` sees earlier facts. Only the named source path is
refined; another alias retains its declared type. Arbitrary boolean equivalence,
common facts across alternative disjuncts, numeric ranges, or the truth of an
ordinary boolean field are not added to the type system. For example,
`REQUIRE item is present or allowed` does not prove `item` present.

Facts apply to subsequent steps in the same behavior, branch, or traversal body.
[Branch-exit joins](native-branch-proofs.md) also retain supported facts proved
on every continuing alternative. They do not infer postconditions from a called
behavior or promote local bindings. A new traversal iteration establishes its own proofs;
[collection filters](native-filter-proofs.md) can establish them before the
selected body starts. [Early-return guards](native-early-returns.md) can retain
condition and body-exit facts on continuing paths. FOR may execute zero times
and provides no new facts afterward.

Root `WHEN REQUIRE ...` steps in requests and scenarios establish facts for
later steps in that request or scenario. Background steps are part of each
expanded scenario's body. A caught `THEN fails with` action restores the
pre-action checking environment; failed assertions cannot establish facts.
Ordinary `THEN` expectations and request postconditions do not establish new
facts for subsequent statements. They can read facts already established in
their scope. Repeating a presence test after a value is already nonoptional
remains a type error under the existing native presence rules.

## Mutations and contracts

The runtime protects the actual state addresses represented by live proofs.
Another alias cannot clear a proven-present value or replace an ancestor so
that the value disappears. That fails with `presence_mutation`. A kind proof
prevents replacement with a kind outside its allowed set, using `kind_mutation`.
Both checks happen before successful mutation evidence and the write.

A proof does not freeze a value. Replacing a present value with another present
value is allowed. Excluding one kind can leave several allowed kinds, and a
replacement within that set is allowed. Nested proofs enforce their intersection;
existing traversal guards also remain active.

Every body releases its own assertion proofs on normal exit, `RETURN`, or
failure. It retains guards owned by callers and surrounding branches. A caller
can replace a value after a helper that proved its presence has returned. Earlier
successful mutations remain visible after a later failure; this is not rollback.

Shared arguments still require exact checked types. A refined value can be
passed to a helper with the matching narrower contract. Use a grouped value
argument to pass a copy to a wider contract. Returns normalize to their declared
contract. A request's `OUTPUT` declaration continues to match the original
state declaration, independently of temporary local refinement.

## Compatibility and evidence

This deliberately changes some previously accepted native programs. A rule
that asserted presence and then cleared the same value through an unrefined
alias now fails instead of invalidating its proof. A formerly optional shared
argument can also become incompatible with a wider mutable parameter after
an assertion. To allow a later change, put the proven work in a focused helper
or a nested block whose scope ends before the replacement; use a copy where
shared mutation is unnecessary. Review existing cases before accepting a new
engine. Do not assume that unchanged source implies unchanged behavior.

The [qualification checkpoint](../evaluations/native_editor/2026-10-16-require/README.md)
retains an actual previous-engine success followed by a new-engine
`presence_mutation`, including unchanged prior case bytes and verified candidate
replay. It is an unapproved migration proposal, not automatic acceptance.

Execution uses the existing assertion, expression, call, and mutation events.
Proof registration creates no extra successful reads, assertions, or budget
steps. Source mapping retains original Unicode/CRLF and expanded-example
locations. Editor hover and definitions follow checked payload types after
sequential assertions, including copied values and unsaved imported declarations.

The [bank transfer preparation example](../examples/native_require/README.md)
contains seven scenarios, including supported expected failures. Independent
native tests cover 24 amount/method combinations. Removing verification changes
exactly two outcomes in that corpus. Additional tests cover alias and ancestor
replacement, allowed kind sets, returns, caught failures, nested scopes, loop
iterations, request boundaries, source mapping, budgets, replay, and scenario
generation. These are correctness checks, not measured human-understanding gains.
