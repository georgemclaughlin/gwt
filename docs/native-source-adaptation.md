# Source adaptation: explicit first-match handling

For a second worked adaptation involving one-of dispatch and helper contracts,
see [the shared MiniLang evaluator](native-minilang-adaptation.md).

The language tour demonstrates a manual adaptation to GWT's existing
`FIND ... ELSE` step. It preserves public request and output contracts while
making the matched and missing cases visible in one place. No parser or runtime
feature is added.

The previous behavior first calculated whether a violation existed, then searched
again for its first matching record:

```gwt
  exists line in report.lines WHERE line.amount > report.policy_limit into decision.has_violation
  IF decision.has_violation
    find line in report.lines WHERE line.amount > report.policy_limit into policy_violation
    set decision.violation_description to policy_violation.description
```

The revised behavior selects the record once and explicitly updates both paths:

```gwt
  FIND policy_violation in report.lines WHERE policy_violation.amount > report.policy_limit
    set decision.has_violation to true
    set decision.violation_description to policy_violation.description
    set decision.violation_amount to policy_violation.amount
    set decision.status to "needs_review"
    set decision.reason to "line_over_policy_limit"
  ELSE
    set decision.has_violation to false
    set decision.violation_description to ""
    set decision.violation_amount to 0
    set decision.status to "approved"
    set decision.reason to "within_policy"
```

The false assignment matters when a decision record is reused. Fresh request
initialization alone cannot establish correct reuse. An embedded scenario first
reviews a violating report, empties its lines, and invokes the behavior again
against the same decision. Removing the false assignment makes that scenario fail.

The policy remains: any over-limit line triggers review, including a
non-reimbursable line; the first match in input order supplies the violation;
an amount equal to the limit is permitted; approved totals include only
reimbursable, within-limit lines. The output's `has_violation` field remains part
of its public domain contract.

## Evidence and limits

The [qualification](../evaluations/language_tour/2026-10-16/README.md) freezes the
previous source, compares both Python revisions with independent expected values,
and checks the revised source on the previously qualified packaged Rust engine.
Its 436 integer-domain inputs vary limits, amounts, order, and reimbursement flags,
including empty input and a four-line report. Nine captured Python
cases produce a source-backed refactor review. Native tests separately verify
explicit expected decisions, reuse, captured replay, and a changed-boundary review.
Mutations to the inclusive limit and non-reimbursable handling are detected.

These are finite semantic checks. They do not prove equivalence for every numeric
input, establish performance gains, or measure reviewer comprehension. Rewriting
this pattern is appropriate here because both searches had the same predicate,
the inspected collection/state did not change between them, and the selected
record had the same first-match meaning. This is not a general textual rewrite:
different predicates, intervening mutations, or dependencies on the destination
flag need separate analysis.

The native engine already executes source steps in order. Python groups scenario
assertions after scenario actions. Shared examples place their `THEN` expectations
at the end; this does not change or promise equivalence of those engine semantics.

The native engine does not implement the old lowercase `exists`/`find` forms.
This example demonstrates an existing behavior-shaped alternative for this
specific pattern. The later [subscription adaptation](native-existence-decisions.md)
addresses standalone existence through a named boolean-returning behavior.
Other legacy collection uses remain separate language decisions. Automated source migration, broader adaptations,
and representative human evidence are still open.
