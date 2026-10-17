# Native dispatch on scalar values

`DEPENDING ON expression` selects behavior from one evaluated value. Use it for
named statuses, modes, flags, or exact numeric cases. Use `DECIDE` for ordered
priority rules with different conditions. This extends the native
[kind-dispatch foundation](native-one-of.md#exhaustive-kind-branches) while
keeping its exhaustive-branch requirement.

```gwt
DEPENDING ON facts.status
  WHEN the value is "sent"
    set decision.action to "done"
  WHEN the value is "retry"
    set decision.action to "retry"
  ELSE
    set decision.action to "manual"
```

## Subject, labels, and coverage

The subject may be any checked boolean, integer, decimal, text, or text-union
expression, including [finite numeric and boolean contracts](native-finite-literals.md). Arithmetic subjects such as `facts.attempt - 1` are allowed. The
engine evaluates the expression once before selecting a body. An error in that
evaluation produces no branch comparisons or branch-body execution.

Value labels are scalar literals: text, booleans, integers, and finite decimals,
including a numeric minus sign. Parentheses around literals do not change their
meaning. Names, arithmetic, function calls, lists, absent values, and conditions
are not labels. All labels and bodies are checked before any execution,
including unselected bodies. Kind and value labels cannot be mixed.

Provide at least one `WHEN` branch. Each body must contain a step; `PASS` is an
explicit no-op. Use a final `ELSE` unless every possible value is covered:

- Boolean subjects are covered by `true` and `false`.
- Finite scalar subjects are covered by every declared value.
- Ordinary text, integer, and decimal subjects require `ELSE`.

Values outside a finite scalar domain, fractional labels on integer subjects, duplicate
equal values, branches after `ELSE`, and `ELSE` after complete finite coverage
are errors. Both `true` and `false` are required to omit `ELSE` for booleans;
the Python profile currently requires `ELSE` for a plain boolean subject.

Optional subjects, ordinary records, and lists are not scalar dispatch subjects.
One-of records use named-kind branches instead. Scalar branch selection does
not narrow the static contract of a path, so it does not introduce a kind-style
mutation lock. A selected body may change the subject, including through an
alias, within its original contract. That mutation does not re-evaluate the
subject or execute another branch. Existing collection-traversal guards still
apply. Branch-local bindings remain local; every normally completing path in a
returning behavior needs a return, in its branch or subsequent reachable code.
Literal `REQUIRE false` is an [explicit failure exit](native-failure-exits.md).

## Exact numeric equality is intentional

Native value matching uses the same equality as native `==`. Integers and
decimals compare by exact mathematical value, independent of machine width or
decimal context. Thus `1` and `1.0` match the same subject value, and writing
both as labels is a duplicate-value error. Likewise, `0`, `-0.0`, and `0.000`
are equal; decimals that differ beyond a host's floating-point precision remain
distinct. Boolean `true` and text `"1"` are not numeric labels and are rejected
for numeric subjects.

This deliberately differs from the Python profile's type-sensitive integer
versus decimal dispatch. A single native `WHEN the value is 1` also matches a
decimal subject whose value is exactly one. When adapting a Python policy that
contains separate `1` and `1.0` branches, decide whether those branches represent
the same domain state. Merge them only if the policy intends identical
behavior. If provenance or category matters, model it explicitly as a named
domain field or one-of kind. Native decimal normalization already removes
insignificant zeros; source spelling and host representation are not domain
states. `number` follows native exact decimal semantics, not Python float rules.

This is an experimental native-profile decision. It does not alter the
published Python v0.2 behavior or promise transparent migration.

## Execution evidence and limits

Each literal comparison consumes a program step and records a `value branch`
event containing the actual value, candidate value, and selected flag. All
events depend on the single subject-evaluation event. The engine records every
literal comparison in source order before running the chosen body. Labels are
already checked constants; this does not evaluate unselected bodies. Duplicate
rejection ensures at most one selected label. A final `ELSE` has either an
`else selected` or `branch skipped` event.

Subject evaluation, comparisons, body steps, and nested calls share execution,
depth, value, and evidence limits. A budget failure stops execution at that
point; it does not fabricate later branch comparisons or state changes. State
changes that occurred before an unrelated later failure remain observable,
as with ordinary native execution.

Capture/replay, revision comparison, generated scenarios, source-backed
explanations, and offline review retain these events and original source spans.
The editor traverses subject expressions and branch bodies for diagnostics,
hover, and definitions. Canonical source formatting preserves the syntax.

The [delivery-response example](../examples/native_value_dispatch/README.md)
combines exhaustive status and boolean dispatch with an explicit numeric
fallback. `tests/value_dispatch.rs` covers independent policy inputs, numeric
precision, impossible/duplicate cases, aliases, returns, scopes, traversal
guards, budgets, replay, revisions, scenario generation, and Unicode/CRLF
example evidence. Tests demonstrate language behavior; they do not establish
human readability benefits.
