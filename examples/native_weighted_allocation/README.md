# Weighted cent allocation

This example distributes a nonnegative, whole-cent budget among eligible
recipients in proportion to nonnegative integer weights. It demonstrates a
specific allocation policy in existing GWT syntax. The host supplies only a
`budget` with `total` and `recipients`; all policy and result construction lives
in [rules.gwt](rules.gwt).

```sh
cargo run --locked -p gwt-core --bin gwt -- inspect examples/native_weighted_allocation/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- validate examples/native_weighted_allocation/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- run examples/native_weighted_allocation/rules.gwt --request "allocate budget" --input examples/native_weighted_allocation/request.json
```

The supplied one-unit budget produces shares `0.34`, `0.33`, and `0.33`.
Eleven embedded scenarios cover ties, unequal remainders, multiple leftover
cents, exclusions, empty inputs, rejected budgets/weights, and a surprising
consequence of the policy.

## Policy and explanation

1. Reject negative totals, fractional cents, and any negative weight, including
   an excluded recipient's weight. A positive budget requires positive eligible
   weight. A zero budget permits no eligible recipients.
2. Round each eligible positive-weight recipient's exact weighted share down
   to whole cents. Other recipients receive zero and remain in the result.
3. Award the remaining cents to the largest fractional remainders, at most one
   extra cent per recipient. Equal remainders use input order. Labels are display
   text: duplicates are allowed and alphabetic order has no effect.
4. Return shares in input order and require their total to equal the budget.

Each result row exposes `participates`, `amount`, `remainder_score`, and
`received_extra_cent`. The score is `total * weight - initial_amount *
eligible_weight`, using the initial rounded-down amount. All participants have
the same positive denominator, so comparing these exact scores gives the same
ordering as comparing their fractional remainders. An excluded row has score
zero. The score stays unchanged after a bonus cent, preserving the explanation
of the choice. Execution evidence links the arithmetic, selection, and mutation
to their source steps. Decimal JSON values are exact strings.

This policy conserves the budget, but does not guarantee that every person's
share grows when the budget grows. With weights `1, 3, 3`, a budget of `0.03`
gives `0.01, 0.01, 0.01`; a budget of `0.04` gives `0, 0.02, 0.02`.
Both results are executable scenarios. A workflow requiring individual budget
monotonicity would need a different policy.

## What this teaches about GWT

The request reads as allocation intent, and its helpers expose the rounding
and remainder selection. Neither a sort primitive nor new syntax was needed.
The implementation repeatedly scans the shares, with quadratic worst-case work.
It iterates over the fixed recipient list to bound the number of extra-cent
awards, then checks that no budget remains.

The original example required a request-local `draft` and template arguments.
It now uses [typed local construction](../../docs/native-local-records.md):
`prepare` creates a `Share` with explicit fields and returns it. The request
and behaviors no longer pass a template; callers still supply only budget facts.
The [refactor review](../../evaluations/native_editor/2026-10-16-local-records/README.md)
preserves all 52 captured public outcomes while recording the deliberate removal
of internal `draft` state. This establishes semantic checks, not measured human
readability improvement.

Execution evidence also limits scale. With default limits, the tested equal-weight
inputs with 1, 3, 8, and 16 recipients succeed. The tested 32- and 64-recipient
inputs fail with `evidence_limit` and publish no result. Earlier partial state
and evidence can remain on failure; execution is not transactional. These probes
use a budget of one fewer cent than the recipient count, requiring many bonus
awards. They establish neither a universal maximum recipient count nor production
capacity. See the [recorded probes](../../evaluations/native_editor/2026-10-16-weighted-allocation/resource-probes/results.json).

The subsequent [append-evidence change](../../docs/native-append-evidence.md)
reduces growing-list snapshots while building the result. Current
[old/new probes](../../evaluations/native_editor/2026-10-16-evidence-growth/qualification/allocation-profiles.json)
still refuse the tested 32/64-recipient inputs: repeated remainder scans remain a
separate scaling cost. The original probe files describe their frozen checkpoint.

The adjacent `limits.json` supplies a smaller, explicit operating budget for
local validation and profiling. Pass it with `--limits` to native `validate`,
`run`, `profile`, `test`, or `capture`; see the
[limit-file workflow](../../docs/native-execution-limits.md). Passing the embedded
scenarios under that budget does not guarantee that every recipient list fits.

## Independent checks and fault review

The [rational-arithmetic oracle](../../evaluations/native_editor/weighted_allocation_oracle.py)
uses `Fraction` quotas and a stable sort, independently of GWT's decimal
rounding step and repeated scans. The Rust integration test compares complete
results or expected rejection codes on 1,004 inputs, including exhaustive small
weight/eligibility combinations and seeded cases with exact large values.
Rejected policy inputs leave allocation state empty.

A captured-case review changes the largest-remainder equality test to `<=`.
That plausible mistake awards leftover cents in input order even when remainders
differ. Across 52 inputs, the oracle predicts 12 changed outputs, all detected by
review. Fifteen invalid inputs remain rejected on both sides. All 104 baseline
and candidate captures replay; the baseline files remain unchanged. Embedded
scenarios also reject the faulty revision. The [review evidence](../../evaluations/native_editor/2026-10-16-weighted-allocation/README.md)
is a local correctness exercise, with no human approval or comprehension result.

```sh
cargo test --locked --test weighted_allocation
python evaluations/native_editor/weighted_allocation_oracle.py --output /tmp/gwt-allocation-oracle.json
python evaluations/native_editor/qualify_weighted_allocation.py --native /path/to/gwt --output /tmp/gwt-allocation-review
```

The review destination must be new. Python formats the example, but its runtime
does not support the native rounded-division step; the example is explicitly
registered as native-only.
