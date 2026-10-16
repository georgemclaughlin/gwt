# Read, change, explain, review

This short walkthrough uses the experimental **Rust engine**. The policy is
delivery pricing: nonmembers pay 5 up to 1,000g and 9 above that; members pay
zero; anything above 5,000g needs manual handling, even for members. Nonpositive
weights are rejected. Fees are illustrative integer units.

The proposed change is to extend the low-fee band to **1,500g inclusive**.
Membership, overweight precedence, and invalid-weight rejection must remain.

## 1. Read the executable policy

Open the [baseline rules](../examples/native_delivery/rules.gwt). `Parcel` names
the supplied facts; `Quote` names the outcome. `REQUEST quote delivery` accepts
a parcel, initializes a quote, invokes the behavior, and declares the output.
The behavior's `DECIDE` runs the first matching arm:

```gwt
  DECIDE
    WHEN parcel.weight_grams > 5000
      set quote.status to "manual"
      set quote.fee to 0
    WHEN parcel.member
      set quote.status to "standard"
      set quote.fee to 0
    WHEN parcel.weight_grams <= 1000
      set quote.status to "standard"
      set quote.fee to 5
    ELSE
      set quote.status to "standard"
      set quote.fee to 9
```

Order matters: a 5,001g member parcel reaches manual handling before the member
benefit. `REQUIRE parcel.weight_grams > 0` rejects invalid weight before this
decision. `THEN` and `EXAMPLES` below the behavior describe expected outcomes.

## 2. Change one policy boundary

The [candidate](../examples/native_review_walkthrough/candidate.gwt) changes
`<= 1000` to `<= 1500`. It also updates the 1,001g expectation, adds 1,499g,
1,500g and 1,501g examples, and explicitly tests zero-weight rejection without
changing the initialized quote. Both revisions stay available.

From the repository root, build and run the candidate:

```sh
cargo +1.96.0 build --locked -p gwt-core --bin gwt-native
target/debug/gwt-native validate examples/native_review_walkthrough/candidate.gwt
target/debug/gwt-native run examples/native_review_walkthrough/candidate.gwt --request "quote delivery" --input examples/native_review_walkthrough/input.json
```

Validation checks layout, types, and all 14 candidate scenarios. The request
input is a nonmember parcel weighing 1,500g. Its `result` should be:

```json
{"quote":{"status":"standard","fee":5}}
```

Passing new examples alone would not tell us what changed for previously
captured requests. That is the next step.

## 3. Compare the same facts and explain the difference

Generate the review in a **new** directory:

```sh
python examples/native_review_walkthrough/prepare.py /tmp/gwt-delivery-review
```

The helper validates both sources, captures nine baseline requests, and compares
the candidate against those same frozen inputs. It checks explicit expectations
from [cases.json](../examples/native_review_walkthrough/cases.json), writes the
review, and creates an all-pending decision file. It refuses to reuse an existing
output directory. Use a new path for another run, with the same native executable
for capture and review.

Open `/tmp/gwt-delivery-review/review.html` in a browser. Select **Outcome changed**:
only `new-band` (1,001g) and `new-limit` (1,500g) should appear. Select `new-limit`
and compare baseline/candidate results: fee **9 → 5**. Follow the condition and
write events in each decision trail to the frozen source. The baseline condition
`1500 <= 1000` is false; the candidate condition `1500 <= 1500` is true.

That trace establishes which branch actually ran. The stated policy change is
why a reviewer might consider it correct; the engine does not infer that intent.

| Captured case | Expected baseline → candidate |
| --- | --- |
| Nonmember at 1,000g | Fee 5 → 5 |
| Nonmember at 1,001g | Fee 9 → 5 |
| Nonmember at 1,500g | Fee 9 → 5 |
| Nonmember at 1,501g | Fee 9 → 9 |
| Member at 1,500g | Fee 0 → 0 |
| Nonmember at 5,000g | Standard handling, fee 9 → 9 |
| Nonmember at 5,001g | Manual handling → manual handling |
| Member at 5,001g | Manual handling → manual handling |
| Zero weight | `assertion_failed` → `assertion_failed` |

There are nine compared cases, two outcome changes, and one candidate failure.
That failure is the preserved zero-weight rejection. Select **Candidate failed**
to inspect it; do not assume a failure is newly introduced. Source/evidence
changes can also appear on cases whose outcome is preserved. `complete: true`
means every baseline was verified and compared, not that anyone approved them.

## 4. Review the proposal

Return to all cases. Inspect the changed band, the unchanged 1,501g boundary,
overweight precedence, and the rejected input. Check that the evidence supports
the intended change and identify any missing real-world cases.

The page offers Pending, Accept, Reject, and Needs information, with reviewer
and note fields. **The generated decisions remain pending.** When a person is
ready to review, they can make their own choices and download a decisions file.
No participant response or approval is required just to run this walkthrough.

To see the pending gate now:

```sh
target/debug/gwt-native assess-review /tmp/gwt-delivery-review/corpus.json --candidate examples/native_review_walkthrough/candidate.gwt --decisions /tmp/gwt-delivery-review/pending-decisions.json
```

Expect exit status **1**, `pending: 9`, `accepted: 0`, and `allAccepted: false`.
The command re-executes the comparison. A later reviewer can pass their downloaded
file instead; decisions must match the exact fresh report. Neither review nor
assessment deploys the candidate.

This walkthrough demonstrates an executable review path, not a completed human
study. For language rules use the [native draft specification](spec/native-draft.md);
for saved-choice details use the [review decision contract](native-review-decisions.md).
