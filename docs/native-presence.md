# Native presence proofs in behavior steps

An optional value is either absent or a value of its declared inner type.
Omitted input and JSON null normalize to the same absence. Zero, false, and
empty text are present values. Presence is separate from truthiness.

Native `IF` and `DECIDE` carry proven presence into their selected bodies:

```gwt
IF facts.policy is present
  REQUIRE facts.amount <= facts.policy.limit
ELSE
  set decision.reason to "missing_policy"
```

The guard makes `facts.policy` usable as its inner record within that body.
Nested guards can establish further optional fields. The subject may also be a
root binding, a common one-of field, or a collection item. No new syntax or host
null convention is introduced. These facts compose with
[kind comparisons](native-kind-conditions.md) in the same condition and body.

## What a branch proves

The native checker uses these conservative rules, matching the existing
short-circuit expression rules:

- A true `path is present`, or false `path is absent`, proves that path present.
- `not` reverses the required truth value.
- A true `and` proves the presence facts established by both operands.
- A false `or` proves the presence facts established by both operands.

For example, this body can access the reference as text:

```gwt
IF facts.receipt is present and facts.receipt.reference is present
  set decision.reference to facts.receipt.reference
```

The right operand can read the optional record because the left operand has
established its presence. The body retains both facts. In contrast,
`path is present or other_condition` does not establish presence in its true
body: the other condition could be sufficient on its own. These rules do not
attempt arbitrary boolean theorem proving or infer a common fact across
alternative disjuncts.

An `ELSE` body uses facts established by the condition being false. A `DECIDE`
also knows that each earlier condition was false when checking a later
condition or its body:

```gwt
DECIDE
  WHEN facts.policy is absent
    set decision.reason to "missing_policy"
  WHEN facts.receipt is absent
    set decision.reason to "missing_receipt"
  WHEN facts.amount > facts.policy.limit
    set decision.reason to "over_limit"
  ELSE
    set decision.payable to facts.amount
```

The third condition knows both records are present. Its body and the final
fallback retain that knowledge. Conditions have no side effects; no earlier
branch body executes on the path to a later condition. This property is required
for those proofs to remain valid.

Only the guarded source path is refined. A second variable or parameter that
aliases the same state retains its declared optional type. Supported facts
established on every continuing branch now survive through
[branch-exit joins](native-branch-proofs.md). Successful
[`REQUIRE` steps](native-require.md) now retain supported facts for subsequent
statements in their containing body. [Collection filters](native-filter-proofs.md)
now establish true facts for each selected body. [Early-return guards](native-early-returns.md)
now retain supported condition facts common to the paths that can continue.
Absent branches retain the optional type; there is no separate public
absent-only type. A redundant presence check on an already nonoptional refined
value remains a type error, as in expression checking.

## Mutation must preserve a live proof

While a branch, REQUIRE, or filter proof is active, a present value can be
updated or replaced with another present value. A guarded integer can be passed to a helper requiring an integer:

```gwt
IF facts.maximum is present
  increase facts.maximum
```

Bare-path shared arguments still require exact types. A helper accepting a
wider optional contract could clear the value, so passing the narrowed path to
that helper as mutable state is rejected. A grouped value argument such as
`(facts.maximum)` creates a copy and may be normalized into a wider optional
contract without changing the original.

An independent alias may still have a wider declared type. The runtime protects
the actual state address, including nested fields and collection-item addresses.
Clearing a protected value, replacing an ancestor with a value in which that
path is absent, or removing its path fails with `presence_mutation`. Normalization
and the presence check occur before mutation evidence or the write, so a rejected
replacement is not published as a successful state change. A replacement that
keeps the protected path present is allowed; presence does not freeze its value.

Presence guards compose with kind-dispatch and collection-traversal guards.
They remain active across calls and nested branches. Normal exit, `RETURN`, and
failure release only the guards introduced by the exited scope. A caught
supported behavior failure can therefore be followed by a later operation that
clears a formerly guarded value. Earlier successful mutations are not rolled
back. `presence_mutation` is a programming/guard failure, not an allowed
`THEN fails with` expectation; such captured observations remain replayable but
do not automatically become scenario expectations.

## Values, copies, and declared boundaries

A copied record whose optional fields have been proven present can satisfy its
original wider record contract. Returning that record normalizes it back to the
declared boundary. This does not introduce numeric widening inside ordinary
record fields or relax exact mutable argument types. A direct optional scalar
still cannot participate in arithmetic or scalar comparison without a guard.

The compiler records proven paths in the checked branch representation.
Execution records actual presence tests, short-circuit operands,
selected/skipped conditions, calls, and mutations using original source spans.
It does not fabricate reads for a skipped optional path. Replay and comparison
use the complete execution; generated successful scenarios assert the declared
observable result, including normalized absence. Editor navigation retains the
underlying field declarations through optional record paths.

## Example and profile boundary

The [reimbursement example](../examples/native_presence/README.md) has six
scenarios with 18 top-level expectations. Independent native tests cover 80
amount/policy/receipt combinations, missing versus null input, invalid amounts
and limits, alias/ancestor mutation, copy and return behavior, nested scopes,
boolean false, resource failure, generated scenarios, replay, revisions, and
Unicode/CRLF evidence.

The Python formatter and checker accept this example, but its current runtime
rejects `facts.policy.limit` through the optional record. That is recorded as a
reference-engine limitation, not adopted as native semantics or hidden as a
passing cross-engine result. The example's execution is explicitly assigned to
the native suite. This work does not claim full Python compatibility or measured
human-comprehension benefit.
