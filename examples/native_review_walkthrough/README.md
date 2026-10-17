# Native delivery change walkthrough

Follow [Read, change, explain, review](../../docs/native-review-walkthrough.md).
This example extends the delivery policy's low-fee band from 1,000g to 1,500g
inclusive while preserving membership, overweight precedence, and rejection.

- Baseline: [`../native_delivery/rules.gwt`](../native_delivery/rules.gwt).
- Candidate: [`candidate.gwt`](candidate.gwt), including 14 executable scenarios.
- [`cases.json`](cases.json): nine explicitly specified before/after requests.
- [`input.json`](input.json): the 1,500g nonmember request for the quick example.
- [`prepare.py`](prepare.py): validate, capture, compare, check expected outcomes,
  and generate HTML plus all-pending decisions in a new directory.

```sh
cargo +1.96.0 build --locked -p gwt-core --bin gwt
python examples/native_review_walkthrough/prepare.py /tmp/gwt-delivery-review
```

Expected: nine verified comparisons, two changed outcomes (`new-band`,
`new-limit`), one preserved rejection (`invalid-weight`), and nine pending
decisions. `complete` describes comparison coverage; it is not approval.
Use `--native /path/to/gwt` to select another executable explicitly.
Fresh artifacts include source copies, captured inputs/cases, engine identity,
explicit expectations, validation reports, and source/executable hashes.

The walkthrough uses authored synthetic facts. Human sessions and external
pilots remain pending. No Rust language or runtime behavior changes here.
