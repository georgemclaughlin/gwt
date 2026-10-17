# Exact-ratio underwriting qualification — 2026-10-16

The [native example](../../../examples/loan_underwriting/native_rules.gwt) replaces
quotient-valued ratio outputs with explicit numerator/denominator records and
compares thresholds without division. The original Python example remains intact.
Read the [design and migration note](../../../docs/native-exact-ratios.md) before
treating this as a replacement: the output shape, host numeric boundary, failure
behavior, and some threshold decisions differ deliberately.

`fixtures.py` independently computes rational quotients using Python `Fraction`.
It generates 972 joint boundary cases (nine debt ratios, nine loan ratios, six
reserve ratios, two credit bands), 96 credit/history/bankruptcy/employment cases,
and four recurring-ratio cases. The checked-in Rust fixture has 1,072 complete
expected outputs. Every result matches native execution, including unreduced
numerator/denominator amounts. Tests cover fifteen embedded scenario executions,
five independently detected policy faults, six failing denominator inputs,
direct helper validation, and successful/failed capture replay.

`comparison-verified/observations.json` retains 1,072 native and 1,072 Python
executions. Native receives exact decimal strings; Python receives numeric tokens
representing the intended facts. Both inputs are recorded. Fifty-two cases differ
in status, reason, and interest rate; principal and risk points match throughout.
Thirty-two move from denial to manual review, and twenty from manual review to
approval under the exact policy.
`policy-differences.json` retains every difference, including Python reserve values
slightly below the mathematically exact threshold. The differing input number
representations and source arithmetic are both part of this comparison; it does
not isolate a single floating-point operation as the cause of every difference.

The first comparison attempt incorrectly supplied native decimal strings to the
Python `number` contract and failed before execution. Its traceback is retained
in `comparison-initial.log`; the corrected completed run is `comparison.log`.

`denominator-boundaries.json` separately records six zero/negative inputs through
both native source revisions and Python. All new-native requests fail explicitly;
three old-Python negative inputs succeed. These are acceptance changes, not cases
included in the positive-denominator matrix. Native tests inspect the reset
decision state before ratio writes and verify failed-case replay.

`review/` contains six original-source native captures, selected inputs, the
corpus, comparison JSON, and `adaptation.html`. Every baseline verifies. Four
original executions succeed and two fail with `nonterminating_decimal`; all six
candidate executions succeed. All six outcomes, states, and evidence change,
with no unavailable entries or baseline mismatches. This is a native source
adaptation review, not a replay of Python evidence. No approval is recorded.
Interactive browser validation remains pending. Six candidate captures also
replay in `comparison-verified/`.

All 404 Rust tests and Clippy pass on Rust 1.85.0 and 1.96.0; all 666 Python tests
pass. Remaining repository checks and file identities are in `verification.json`.
The native engine implementation and retained packaged executable are unchanged.
No live model comparison, participant study, or deployment is claimed.

Reproduce the independent expectations and comparison from the repository root:

```sh
python -m evaluations.underwriting.fixtures
cargo +1.96.0 test --locked -p gwt-core --test underwriting
python -m evaluations.underwriting.qualify --native /path/to/gwt-native --output /path/to/new-underwriting-comparison
```

The generator intentionally replaces its checked-in fixture; inspect any diff.
The comparison requires a new output directory and fails on an unexpected result.
