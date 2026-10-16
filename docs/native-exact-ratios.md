# Exact ratios without implicit rounding

The [native underwriting example](../examples/loan_underwriting/native_rules.gwt)
represents a ratio as an `ExactRatio` record containing decimal `numerator` and
`denominator` fields. The denominator must be positive when a behavior uses the
ratio. These are ordinary GWT records and behaviors; no rational number type,
new operator, or runtime implementation is introduced.

This is an alternative to converting every ratio into a decimal quotient.
The original example cannot execute all of its scenarios under native exact
division: monthly income or reserves can produce recurring decimals. Choosing
a display precision to fix execution would also affect threshold decisions.
Keeping the two amounts lets the source express the threshold exactly:

```gwt
WHEN within <ratio> limit <limit>
  GIVEN ratio is ExactRatio
  AND limit is decimal
  THEN returns boolean
  REQUIRE ratio.denominator > 0
  RETURN ratio.numerator <= limit * ratio.denominator
```

The decision behavior names the resulting predicates `affordable`, `secured`,
and `adequate_reserves`. A separate `covers` behavior compares minimum reserves.
Positive denominators make these comparisons equivalent to comparisons of exact
rational quotients. The positivity requirement is necessary: multiplying an
inequality by a negative denominator would reverse its direction.

## The illustrative policy

Debt-to-income uses monthly debt times twelve over annual income; loan-to-value
uses principal over home price; reserves use remaining cash over principal times
the example's existing `0.006` payment estimate. The source retains the credit,
debt, loan, employment, history, bankruptcy, classification, and pricing thresholds
of the original illustrative workflow. It does not select lending policy for a
real deployment or claim that the payment estimate models an actual loan.

The native variant requires positive annual income, home price, and principal.
It does not add general real-world eligibility constraints: negative history
points, debt, or remaining cash are still governed by the written rules. A real
domain specification would need to decide their acceptance explicitly.

## Deliberate migration differences

- `dti`, `ltv`, and `reserve_months` become records, so the public output contract
  changes. Their fields retain the calculated amounts without reduction; pair
  equality is not a universal mathematical ratio-equivalence operation.
- Native decimal inputs use exact strings and outputs retain exact strings.
  Python's `number` boundary uses numeric values. The comparison retains both
  actual input representations instead of claiming byte-identical host inputs.
- Nonpositive denominators fail an explicit assertion before ratio calculations.
  Reset steps have already run; this is not transactional rollback. Some negative
  inputs accepted by Python are deliberately refused, and zero-denominator
  failures change diagnostic and partial state.
- Exact thresholds can differ from the old floating-point path. In a retained
  case, reserves are precisely one payment, but Python computes
  `0.9999999999999994`, denying the application rather than selecting manual review.
- The source uses multiplication instead of division. Existing numeric digit,
  execution, and evidence limits still apply; it is not unlimited rational arithmetic.

The original `rules.gwt` and its Python requests remain available. This separate
native variant requires host adaptation and policy review; it is not a transparent
replacement. If a product needs a displayed quotient, specify its display rounding
separately from decision thresholds. The existing
[rounded division step](native-rounded-division.md) remains appropriate when the
rounded value itself is the domain result.

## Evidence

[Qualification](../evaluations/underwriting/2026-10-16/README.md) records 1,072
independent `Fraction`-based expectations. Every native result matches, including
the exact output pairs. The Python comparison differs in status, reason, and rate
on 52 cases; principal and risk points match across the full corpus. Fifteen
embedded scenarios exercise original outcomes, threshold neighbors, and refused
denominators. Native tests also verify captured fault detection and failure replay.

Six original-source native captures compare with the new source in a saved review.
Four baselines succeed with scalar ratios; two fail on recurring division. All six
candidate executions succeed, with their contract, state, and evidence differences
retained. This native-to-native report is distinct from the Python comparison.
The retained report now passes [browser interaction and visual checks](../evaluations/workbench/2026-10-16-adaptations/README.md), including exact rendered
ratios, baseline failures, changed paths, and operand navigation. This checks the
historical schema-1 artifact; current approval requires a regenerated review with
complete capture identity. No approval or human-comprehension benefit is claimed.
