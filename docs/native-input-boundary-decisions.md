# Native raw-input boundary: declare the observed facts

The current native profile keeps request inputs typed and closed; it does not
add the Python `any` escape hatch. A host supplies the facts the rules use, while
GWT decides what those facts mean. When raw JSON has a known shape, a declared
record can be that boundary directly. A host adapter is useful when an external
envelope needs projection or representation changes; it must not hide domain
validation or outcome selection outside the executable spec.

The adapted [contact example](../examples/input_normalization/README.md) had
four known reads behind its old `any` input. It now declares those fields:

```gwt
RECORD RawContactInput
  name: text
  email: text
  middle_name_state: text
  middle_name: optional<text>
```

The request and helpers use this record. The request is still named
`normalize contact profile`, the host binding is still `raw`, and the public
`ContactProfile` output is unchanged. The input contract is intentionally
stricter; this is not a drop-in replacement for every previously accepted JSON.

## Structural facts and domain decisions

Text types establish that values are text, not that they are valid names or
email addresses. Empty name/email checks, ordered validation messages, and the
result's `normalized`/`invalid` status remain GWT behavior. The state label stays
`text` rather than a three-value union so the domain can report unknown labels
using its existing `invalid_middle_name_state` error.

An optional field unifies omitted and null. The separate state label carries the
provided/missing/not-applicable distinction. If `provided`, a presence branch
permits the text read; its missing branch fails an assertion. Empty text is
present, preserving the previous accepted policy. Other states ignore a
well-typed supplied middle name and use an empty output value.

No host code chooses a default state, trims text, repairs spelling, substitutes
an empty string, or silently converts wrong types. Such transformations require
their own explicit contract and policy. This example needs no new host adapter
or language syntax.

| Input or outcome | Native treatment |
| --- | --- |
| Missing/null middle name with `missing` or `not_applicable` | Accepted; domain state determines the profile |
| Present empty middle name with `provided` | Accepted as text |
| Missing/null middle name with `provided` | Behavior assertion fails; prior state remains, no successful result |
| Unknown text state label or empty name/email | Successful execution returns the existing invalid profile and error list |
| Wrong declared type, including an unused middle-name object | Contract failure before setup or behavior |
| Extra raw field or top-level request binding | Closed native contract rejects it before setup |

A returned invalid profile is a domain decision; a failed run is not an approved
result. Rejection does not imply rollback after behavior starts. The new assertion
can change diagnostic and partial-state details compared with the old failed
attempt to assign an absent value to text; no full failure-equivalence claim is made.

## Python compatibility and a validation fix

The shared source runs on both engines. The supplied shape matrix preserves all
56 successful ordinary results, and both reject eight provided-but-absent cases.
Malformed-input acceptance changes deliberately: typed fields are validated even
when a later branch would not read them.

The audit also found a Python bug: record flattening dropped explicit empty
objects. An empty object in an optional text field could become absence, and
unknown empty fields could disappear from validation. Flattening now preserves
that supplied value. Optional scalar/unknown-field failures, one-of payloads,
and an explicit Python `any` field containing an empty object have regression
checks. This fixes the existing typed-contract rule; it does not remove Python's
`any` type or solve every difference in nested-record handling.

One measured profile difference remains: Python accepts an extra top-level
request binding, while native rejects it. Both reject the extra field inside
the typed raw record. Use the intended engine when reviewing boundary behavior;
the same source is not a guarantee of identical host acceptance.

## Evidence and remaining scope

[Retained qualification](../evaluations/input_normalization/2026-10-16/README.md)
checks 94 inputs against an independent native boundary/policy model: 56 results,
eight behavior failures, and thirty pre-execution contract failures. It records
both Python source revisions, including changed acceptance and the remaining
engine difference. Native failed boundary observations have empty state and no
execution events. Six source scenarios exercise ordinary domain outcomes, while
native tests cover failed input, capture/replay, and three policy regressions.

The retained Python report now passes [browser checks](../evaluations/workbench/2026-10-16-adaptations/README.md) for all sixteen comparisons, including exact
boundary errors and source-linked predicates. Its ten incompatible cases remain
distinct from the changed failure and five path-only changes. The mobile layout
measurement also identifies excessive identity detail before the rejection text.

This supports typed facts for this workflow. It is not an automatic migration
for arbitrary dictionaries, recursive JSON, heterogeneous data, or applications
that preserve unknown fields. Such needs require an explicit representation and
worked behavior before extending the native language. External effects and
wire-format handling remain host responsibilities. Human benefit is unmeasured.
