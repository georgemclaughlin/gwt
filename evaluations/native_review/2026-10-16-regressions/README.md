# Captured-case regression gate — 2026-10-16

The [regression command](../../../docs/native-regressions.md) adds an explicit
preservation check across successful executions, domain rejections, invalid host
inputs, and resource failures. The caller must select outcome/state preservation
or execution preservation. Every baseline replays before the candidate runs;
unavailable or mismatched observations fail the gate. A matching failed execution
remains failed in the complete nested review.

Six new Rust integration groups cover both scopes, exact values, partial state,
prints, diagnostic messages, source movement, missing targets, mixed request and
scenario corpora, corrupted/forged/incompatible cases, paired step budgets, CLI
exits, required options, and corpus preservation. The final full-suite logs record
**416 tests passing on both Rust 1.85.0 and 1.96.0**, and Clippy passes on both.
The final logs are `final-tests-*.log`, `final-clippy-*.log`, and
`final-checks.json`. Earlier logs predate the final report metadata addition.

`workflow/` runs the actual packaged CLI through **nine captured cases** and
**twelve regression reports**: six source revisions under both scopes. Cases
include a successful invoice with the independent expected total `"36.9"`, missing
host input, domain rejection, a named scenario, success at the measured step
budget, failure one step below it, and zero step/evidence/depth budgets. Reports
detect a changed tax rate, state mutation before rejection, and changed behavior
at budget thresholds. Moving source positions preserves outcomes/state while
failing execution preservation. All reports retain the original case integrity
and limits; the source corpus is unchanged.

`package-final/` is the authoritative offline Cargo/static musl qualification.
It verifies an independent Rust host, installed and relocated binaries, eighteen
profiles and replays, and 288 shared-program concurrent executions. Its four
packaged unit tests are separate from the full workspace integration suites.
`package/` is an earlier successful build before adding per-row case identities
and captured limits; use the final package for this checkpoint.

`external-regression-host.json` separately verifies the new `test_corpus` API
against that extracted package: a matching boundary failure passes, source
movement passes outcome/state matching, and the same movement fails execution
matching. The standalone consumer is
[`regression_host.rs`](../regression_host.rs); the exact build command is retained
in `external-regression-host.log`.

The source change creates a new engine fingerprint. `migration/` replays **63
retained cases** with the previous completion engine, then the new engine. Every
full observation is preserved and every proposed candidate case replays. No
approval, corpus replacement, or release publication was performed.

The three commands in the new regression guide were executed successfully; their
recorded invoice total is `"47.88"`. Formatting, relative documentation targets,
and whitespace were checked. `verification.json` records file hashes and checks.
Python runtime and extension sources were unchanged in this turn, so their
previous test results are not presented as fresh regression-gate qualification.

Reproduce the CLI rehearsal into a new directory using an explicit executable:

```sh
python evaluations/native_review/qualify_regressions.py \
  --native /path/to/gwt-native --output /path/to/new-regression-checks
```

This establishes a preservation workflow for observations. It does not prove
desired policy behavior, universal capacity, or comprehension benefit. Pair
failure cases with useful successful workloads, review intentional changes, and
retain independent policy assertions. Human evidence and the live native model
comparison remain outstanding; external pilots remain deferred.
