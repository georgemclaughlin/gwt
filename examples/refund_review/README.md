# Repeated refund-rule review

This synthetic adoption rehearsal exercises three consecutive maintenance
requests in equivalent GWT and Python programs:

1. Damaged goods become refundable even without a receipt.
2. Clearance goods are excluded, taking precedence over damage.
3. Members receive a 45-day ordinary refund window; others keep 30 days.

Each stage retains the same normalized facts and declared decision fields.
GWT stages contain executable scenarios; Python stages expose `decide(state)`.
Independent acceptance inputs live in the maintenance manifest. This example
does not contact a real merchant or count as an external pilot.

From a source checkout, run:

```sh
python -m gwtlang validate examples/refund_review/stage0.gwt
python examples/refund_review/run_trial.py /tmp/gwt-refund-review
```

Use a new output directory. The runner freezes the four source revisions,
checks all 112 acceptance inputs per change in both languages, and creates a
smaller review queue with changed and preserved outcomes. Each change directory
contains:

- `corpus.json` and captured baseline cases;
- `comparison.json` and a self-contained `review.html`;
- `observed-baseline.gwt`, a replay-verified scenario of actual old behavior;
- `expected-candidate.json`, independently authored desired results for review.

The generated scenario and candidate expectations describe different revisions.
Capturing old behavior does not approve it as future policy.

The root `report.json` reconciles expected output changes with comparison
counts; `acceptance-manifest.json` preserves the complete acceptance fixture.
`human-review.csv` starts empty and records reviewer identity, elapsed
review time, detected/missed changes, interventions, verdict, and reuse intent
for GWT and Python conditions. Automation does not fill human observations.

Default review samples contain 12, 12, and 9 cases, with 6, 6, and 3 output
changes respectively. Other cases may have changed execution paths. Sampling
keeps human review compact; full acceptance still runs.

For a real trial, use a workflow maintained by an outside owner, record intent
before showing candidates, and follow the
[external pilot runbook](../../docs/external-pilot-v0.4.md). Measure host fact
normalization work as well as rule authoring. Use the
[paired benchmark protocol](../../docs/maintenance-evaluation.md) for model
comparisons and counterbalanced human review.
