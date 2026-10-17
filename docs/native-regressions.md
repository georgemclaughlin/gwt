# Test captured native observations

`gwt test-cases` makes a saved corpus an explicit preservation gate for a
candidate program. It covers successful requests, failed input contracts, domain
rejections, resource failures, and named scenarios. Every frozen baseline must
replay before its candidate executes. Inputs, entry names, and execution limits
come from the case; this command cannot override them.

The expectation is an observation selected for preservation. Passing does not
establish that a policy is correct, approve a change, or turn a failed execution
into a successful domain scenario. Keep independent policy expectations and
[human review](native-review-decisions.md) alongside these regression checks.

## Choose what must stay the same

`--match` is required. Both scopes compare success/failure, returned values, the
complete printed sequence, diagnostic code and message, and the full retained
state, including mutations committed before a failure.

| Scope | Additional comparison | Suitable use |
| --- | --- | --- |
| `outcomes-and-state` | None; evidence differences remain visible in the report | Preserve observed results and state while allowing implementation and source-position changes |
| `execution` | Step count, complete event sequence, and full diagnostic including source position | Preserve measured execution and evidence, including exact failure behavior under the captured budget |

Neither scope requires identical source bytes or program identity. Both retain
source-change information. `execution` does not compare program titles or other
execution-envelope metadata beyond the listed fields. A trailing comment can
pass it; inserting a comment before an executed statement changes its positions
and can fail it. No evidence is stripped from the report to make a check pass.

Diagnostic messages are compared exactly. `outcomes-and-state` may preserve a
different path or rejection location if its message and consequences match.
Use `execution` when those differences must fail the gate, and review differences
when intentionally changing the implementation.

## Run a preservation check

From the repository root, capture and explicitly select a case for the corpus:

```sh
cargo run --locked -p gwt-core --bin gwt -- capture \
  crates/gwt-core/tests/fixtures/invoice.gwt --request 'price invoice' \
  --input crates/gwt-core/tests/fixtures/invoice-input.json \
  > /tmp/gwt-regression-invoice.case.json
cargo run --locked -p gwt-core --bin gwt -- corpus \
  /tmp/gwt-regression-invoice.case.json > /tmp/gwt-regression-corpus.json
cargo run --locked -p gwt-core --bin gwt -- test-cases \
  /tmp/gwt-regression-corpus.json \
  --candidate crates/gwt-core/tests/fixtures/invoice.gwt \
  --match outcomes-and-state > /tmp/gwt-regression-report.json
```

The unchanged invoice returns `"47.88"` and passes. Use the revised rules file
as the candidate when testing a change. `--import-root DIRECTORY` supports
sibling imports. The command reads the corpus and candidate and writes JSON to
stdout; it does not update cases, approval decisions, or source files.

Exit zero requires every case to match the chosen scope. Changes, baseline
mismatches, unavailable cases, invalid corpora, or candidate compilation errors
exit one. A baseline mismatch is failed verification, not proof of a candidate
regression. The existing `review` command continues to report comparison
coverage: its successful exit alone is not a preservation gate.

## Boundary and budget cases

Capture invalid host input directly with `capture --request ... --input ...`.
For budgets, provide the intended [limit file](native-execution-limits.md) at
capture time. Keep a successful representative case at the operating budget
alongside cases that deliberately exceed it. A failure-only corpus can miss
loss of useful capacity, especially with `outcomes-and-state` when two failures
retain the same result, state, prints, and diagnostic.

Budget settings are per case, and each run starts with its own fresh budget.
Tests demonstrate a successful invoice at its measured step count and a failure
one step below it. Adding an extra requirement makes the former fail; removing
an existing requirement makes the latter succeed. Both are changed observations
requiring review. A faster implementation may be desirable, but preservation
testing does not silently decide that for the maintainer.

Matching a resource failure passes this corpus check while its nested execution
still has `ok: false`. Native scenario testing continues to treat resource
exhaustion as failure. No `THEN fails with` support is added for resource or host
boundary errors, and no limit increase is inferred from a passing rerun.

## Report and library API

The schema-1 `gwt.native-regression` report contains:

- `expectationBasis: "verified_observation_not_approval"`, the selected `scope`,
  and aggregate `passed`;
- `totals`, where `total = passed + changed + baselineMismatch + unavailable`;
- one ordered row per corpus ID, with status `passed`, `changed`,
  `baseline_mismatch`, or `unavailable`;
- `caseIntegrity` and `capturedLimits` for entries that reached replay, including
  mismatched observations; unavailable rows have null metadata;
- the complete native `review`, with both executions, source snapshots,
  explanations, and independent outcome/state/evidence/source change flags.

The nested review now uses schema 2 and binds the complete corpus through
`corpusIntegrity`. Its case metadata can remain present for an integrity-valid
case whose replay is unavailable; the regression row only exposes that metadata
after the case reaches replay, as described above.

A regression row can be `passed` while its review row is `candidate_failed` or
`evidence_changed`. These describe different facts: preservation of the selected
observation, execution success, and evidence differences. A case integrity digest
detects accidental changes; it is not a signature or proof of approval.

The Rust API is `test_corpus(&Corpus, &CompiledProgram, RegressionScope)`. Scopes
are `OutcomesAndState` and `Execution`; the API returns `CorpusRegression` or a
diagnostic. It reuses the existing replay, comparison, and explanation machinery.
Corpora retain their 64-MiB/256-entry limits; the full regression report is bounded
to 128 MiB. Existing case resource limits still apply. No process memory or
wall-clock bound is introduced.

Cases belong to their captured engine fingerprint. An engine change still
requires [explicit migration](native-corpus-migration.md); this command neither
ignores incompatible engines nor recaptures their observations automatically.
Intentional behavior changes should receive policy tests and review before a
maintainer explicitly selects replacement observations.

`tests/corpus_regressions.rs` covers both scopes, exact results, partial state,
prints, diagnostics, source movement, paired resource thresholds, scenario
targets, invalid and forged observations, incompatible engines, and CLI exits.
These are engineering checks, not evidence of human comprehension benefit.

[Qualification](../evaluations/native_review/2026-10-16-regressions/README.md)
records packaged CLI and independent Rust-host checks, both supported toolchains,
and preservation of retained observations through the engine transition.
