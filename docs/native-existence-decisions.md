# Native existence checks: name the domain question

For the current native profile, express standalone collection existence as a
named boolean-returning behavior using `FIND ... ELSE`. Keep the existing
first-match block as the selection primitive rather than adding a second
lowercase `exists` statement. This is a deliberate source-adaptation decision,
not a claim that every Python collection form already has a native equivalent.

The [subscription example](../examples/pressure_tests/subscription_entitlements.gwt)
previously used:

```gwt
exists invoice in account.invoices where invoice.status == "past_due" into decision.has_past_due_invoice
```

It now gives the domain question a reusable name:

```gwt
WHEN has past due invoice in <invoices>
  GIVEN invoices is list<Invoice>
  THEN returns boolean
  FIND invoice in invoices WHERE invoice.status == "past_due"
    RETURN true
  ELSE
    RETURN false
```

The caller keeps the result visible in its decision record:

```gwt
LET has_past_due be has past due invoice in account.invoices
set decision.has_past_due_invoice to has_past_due
```

Both paths return explicitly. Empty input and no match return false. A matching
invoice returns true without evaluating later predicates. No arbitrary fallback
record, persistent loop flag, or second search is required. The boolean belongs
in this output because the existing public decision exposes the account's facts,
including when an override bypasses a blocker.

This costs a helper definition and two caller steps. It provides a place to name,
document, test, and reuse the domain question, while retaining one collection
selection model. It does not establish shorter source, faster execution, or
measured readability. A future representative workflow showing that this form
obscures intent is reason to revisit the choice; duplicating a Python keyword is
not sufficient by itself.

## Preserve the actual policy

The adaptation preserves the named `decide entitlement` request and its resolved
input/output shapes. Invoice status determines past-due presence; positive
`days_overdue` is not an alternative predicate. Seat usage blocks only when
strictly greater than the limit.

Precedence is: active first matching override, past-due invoice, excessive seats,
unknown feature, sufficient plan, otherwise upgrade required. An override for
another feature is ignored. If the first matching override is inactive, a later
active duplicate does not replace it. That last rule was already in the source;
this adaptation documents and tests it without claiming it is the right policy
for every subscription product.

The helper `plan rank for <plan>` now accepts the named `SubscriptionPlan` union
used by the account, rather than arbitrary text. Its signature words are unchanged,
but its input contract is deliberately narrower. All account requests already
restrict the plan to free/pro/enterprise. A direct helper caller supplying some
other text previously fell through to rank three; it must now supply a declared
plan or explicitly model an unknown-plan policy. This change is not transparent
compatibility for arbitrary helper callers. Native mutable path arguments require
exact contracts; the named domain type makes this boundary explicit.

## Evidence and migration limits

[Qualification](../evaluations/subscription/2026-10-16/README.md) freezes the old
source and checks 3,276 valid integer-domain inputs against an independent policy
model under both Python revisions and the packaged native engine. The matrix
crosses all three plans, four feature classes, seat boundaries, thirteen ordered
invoice lists, and seven override arrangements. Native numeric JSON strings are
checked explicitly; boolean/text/list fields retain their exact types and values.

Thirteen scenario executions include status-versus-age cases, first-inactive
duplicate overrides, and decision reuse after clearing blockers. Rust tests
capture/replay presence cases and detect four incorrect rule changes; removing
the seat reset is also detected by the reuse scenario. Ten Python cases retain
a source-backed comparison of the actual old and new programs. Its retained HTML
now passes [browser interaction and visual checks](../evaluations/workbench/2026-10-16-adaptations/README.md): path-only queue behavior, filtering, selection,
and rendered predicates and source locations. No approval is recorded.

The request's results match on those inputs; execution steps, source locations,
and evidence change. An additional call and return can also change resource
behavior. This is not a proof of equivalence for all numeric values, budgets,
caller contexts, or both engines' failure semantics. Native `number` retains its
exact-decimal boundary rather than Python's broad numeric boundary.

The previous [expense first-match adaptation](native-source-adaptation.md)
covered an existence check immediately followed by a second search. Subscription
covers a standalone boolean result. Neither justifies a textual rewrite of
legacy `find optional`, arbitrary mandatory-match handling, indexed access, or
queries whose predicates/collection change between steps. Those require their
own domain examples and explicit decisions. The later
[required inventory inspection](native-failure-exits.md) supplies one worked
mandatory-match adaptation with explicit failure and snapshot semantics.
No native syntax or runtime behavior
is added here, and actual human comprehension remains unmeasured.
