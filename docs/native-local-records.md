# Typed local records

The native profile constructs a new record at the point where a behavior needs
it, with an explicit type and visible field values:

```gwt
LET share be Share:
  label: recipient.label
  participates: recipient.eligible and recipient.weight > 0
  amount: 0.0
  remainder_score: 0.0
  received_extra_cent: false
```

The trailing colon selects record construction. Without it, `LET name be
expression` and `LET name be returning behavior call` keep their existing
resolution. A binding or behavior named `Share` does not interfere with the
explicit `Share:` annotation. No `new` keyword, implicit record defaults, or
host-provided template is needed.

## Contracts and scope

The type uses the same resolution as `GIVEN` annotations: named records, aliases,
one-of records, selected-kind contracts, and optional wrappers around records.
Scalar and list annotations cannot be constructed with a field block. A field
may hold an ordinary expression, a list expression, an existing record value, or
a nested record block. One-of initializers require an explicit quoted `kind`.

Every required field must be supplied exactly once. Unknown and duplicate fields
are errors; omitted optional fields become absent. A constructor with no field
lines is valid only when its record has no required fields. For example, a
record containing only optional fields can use `LET empty be Notes:`. This is
the same absence rule as existing record setup, not a new default-value system.
Constructing an optional record produces a present value, but its static declared
contract remains optional and ordinary presence checks apply to later access.

Field expressions see the surrounding scope. They cannot refer to the new local
while it is being constructed, nor to bare sibling field names. Fields evaluate
in source order; nested blocks evaluate depth first. Values are copied, so a
record-valued field does not create a shared mutable alias to its source.
The local follows existing `LET` scope and cannot overwrite an existing binding.
Branch and iteration locals do not escape their body.

Construction can appear in a behavior body, including nested control flow, or
after a request/scenario `WHEN LET`. Such a step with indented fields is an
executable action, not a behavior definition. Request locals are excluded from
the caller input contract. A reusable returning behavior can construct and
return a result, and the request can bind that result normally.

## Failure and evidence

The compiler lowers the constructor to the existing checked initialization
operation. It checks field names, values, and the type before execution. At
runtime, it evaluates all fields, normalizes the complete value, records the
`initialize` event, then installs the binding. Its evidence dependencies identify
the field expressions that produced the value. Expression and constructor spans
retain the original source, including imported types and expanded example rows.

An operand error or resource refusal before installation cannot expose a partial
record. Completed expression events may remain. A failure after installation
can retain the complete record and earlier state; the surrounding execution is
not transactional. Existing value, source, step, and evidence limits apply.

The native editor resolves constructor type annotations, initializer references,
and subsequent local/field uses. `gwt format` preserves the spelling through a
syntax-only projection for the Python parser; that projection never executes
and is not the formatted output. Python runtime support is not implied.

## Compatibility

A trailing colon on the right-hand side of `LET` now means a type annotation.
An old returning behavior call whose last token ends in `:` must be renamed
before migration. The qualification captures an actual old `produce:` behavior:
the old case replays, the new engine reports `candidate_unavailable`, and its
original bytes remain unchanged. Renaming it to `produce` on the old engine
before migration preserves the complete observation. Calls without a trailing
colon retain their prior expression/behavior precedence. Colons inside quoted
text are unaffected.

## Worked refactor and evidence

The [allocation example](../examples/native_weighted_allocation/README.md)
previously passed a `draft` record through two behavior signatures. It now
constructs each share locally. The public budget input and allocation output are
unchanged; the request's internal `draft` state is removed deliberately.

All 1,004 independent oracle cases and 11 embedded scenarios still pass. An
actual 52-case engine migration preserves the old program's complete observations.
Reviewing the refactored program then reports zero outcome changes, 52 state
changes from removing `draft`, and source/evidence changes. Fifteen existing
domain rejections remain failures. This is executable equivalence evidence for
the public outcomes, not measured improvement in human comprehension.

See the [qualification checkpoint](../evaluations/native_editor/2026-10-16-local-records/README.md)
for boundary tests, replay, source mapping, formatter checks, editor evidence,
and compatibility artifacts. The allocation's scaling limits and the broader
project goal remain open.
