# Compare the outcomes of two policies

Which parcels get a different quote after the low-fee limit moves from 1,000
to 1,500 grams? With a development build of GWT, run this from the checkout:

```sh
gwt policy-diff examples/native_delivery/rules.gwt \
  examples/native_review_walkthrough/candidate.gwt --request "quote delivery" --text
```

The report finds **one changed region out of ten**. Nonmembers weighing 1,001
through 1,500 grams inclusive pay 5 instead of 9. It shows the two fee-setting
lines, the branch decisions leading to each, and replayable request inputs for
both endpoints. All member quotes, manual handling above 5,000 grams and
rejections for nonpositive weights agree across the two revisions.

To try a change the nine saved requests miss, copy the candidate to
`mutant.gwt` and insert this arm immediately before `WHEN parcel.weight_grams <= 1500`
in the behavior's `DECIDE`:

```gwt
    WHEN parcel.weight_grams == 1237
      set quote.fee to 99
```

Compare the candidate with that copy. The only changed region is a nonmember
parcel weighing exactly 1,237 grams. Replay the witness with either revision:

```sh
gwt policy-diff examples/native_review_walkthrough/candidate.gwt mutant.gwt --request "quote delivery" --text
printf '%s\n' '{"parcel":{"member":false,"weight_grams":1237}}' > parcel-1237.json
gwt run mutant.gwt --request "quote delivery" --input parcel-1237.json
```

## What a completed comparison establishes

For the selected request, both revisions must accept the same input contract.
The reviewer starts with every normalized input allowed by that contract.
It splits each Boolean into both values and each integer at every relevant
literal threshold in **either** revision. For example, `x <= 1500` introduces
a boundary at 1501, while `x == 1237` introduces boundaries at 1237 and 1238.
Taking all combinations of those intervals and flags partitions the input space.

Within each region every accepted predicate gives the same decision and every
assignment supplies a fixed value. The reviewer runs the actual GWT engine
on a representative input to obtain each revision's declared output or
`assertion_failed` rejection. It also checks the input combining the widest
signed integers in the region, since longer values can consume more execution
evidence bytes. Other runtime failures make the comparison inconclusive.
A changed region can share its outcome with an adjacent region. The report keeps
the original boundaries so each witness and decision trail can be inspected.

The comparison covers declared output values and domain rejections under the
default engine limits. Intermediate state, trace equality, the identity of a
rejecting assertion, malformed host payloads, and user intent are outside that
claim. Use the [corpus review walkthrough](native-review-walkthrough.md) to
inspect captured executions and record human decisions.

## Supported policies and limits

- Inputs can be Booleans, GWT integers (up to 512 decimal digits), and nested
  records of those types.
- Policies can test flags, compare integer input fields against integer literals
  in either operand order, combine conditions with Boolean operators, and read
  locally assigned constants. The reviewer follows calls, including input
  aliases, and checks request postconditions.
- Literal assignments to local or output state, assertions, and branches are
  supported. Input mutation, copying an input to the output, input-to-input
  integer comparisons, arithmetic on input values, loops, and recursion produce
  a source-located diagnostic. The checker examines every reachable behavior's
  syntax, including arms that might never execute.
- Limits are 32 input fields, 1,024 regions, 4,096 expanded statements per
  revision, 64 nested behavior calls, and eight MiB of serialized changes.

Omit `--text` for JSON. A completed comparison exits successfully even when
outcomes changed. Use `changedRegions` for a change gate. Each entry in
`changes` contains field constraints, outcomes, request witnesses, and the
source-located rules executed for the first witness in each revision. Integer
bounds are inclusive decimal strings. A null bound extends to the corresponding
GWT integer limit. An unsupported or inconclusive comparison exits unsuccessfully
and returns a diagnostic in place of a change count.

## What Kani checks

Two Rust harnesses exercise the production boundary helpers. One checks that
splitting any nonempty half-open interval with signed 16-bit endpoints preserves
unique membership for every signed 16-bit probe. The other checks that each of
the six integer comparisons is constant between its cuts for all signed 8-bit
thresholds and input pairs, in either operand order. Native integration tests
exercise the full comparison, including 512-digit integers, aliases, rejections
and replay of reported witnesses. The Kani claims apply to the helpers and
integer widths stated here.
