# Expense-tour first-match adaptation

The tour replaces `exists`, followed by a conditional second `find`, with one
`FIND ... ELSE`. The public request and output contracts remain unchanged.
The missing branch explicitly clears the violation flag and details so a reused
decision cannot retain a previous violation. See the
[adaptation rationale](../../../docs/native-source-adaptation.md).

`before.gwt` is the original source captured before editing; `after/rules.gwt`
freezes the revised source. `before-inspect.json` records the original public
vocabulary. No native engine source changed in this checkpoint.

## Semantic qualification

- `comparison/report.json` records 436 independent integer-domain expectations
  matched by original Python, revised Python, and the packaged native CLI.
  `comparison/observations.json` retains each input, expected output, and result.
  The sweep covers limits 0/1/100, ordered two-line amounts -1/0/1/99/100/101,
  both reimbursement flags, empty lists, and a four-line probe using the original
  sample's amounts and reimbursement flags with numbered line descriptions.
  Negative amounts are existing accepted contract values in this preservation
  check, not a new expense-policy decision.
- Deliberate mutations are detected: changing `>` to `>=` differs on 100 probes;
  ignoring non-reimbursable violations differs on 140. The oracle uses host
  integer arithmetic and explicit field expectations, not observed GWT output.
  The finite sweep does not prove equivalence for all decimal inputs.
- Three Rust tests in `tests/language_tour.rs` cover nine explicit expected
  decisions, first-match order, exact limits, non-reimbursable violations, empty
  inputs, eight embedded scenarios/72 expectations, source explanations,
  captured replay, and a changed-boundary comparison. A missing flag reset is
  detected by rerunning behavior against the same decision after emptying input.
- [Nine captured Python cases](python-corpus.json) reconcile against the frozen
  baseline with zero output changes, failure changes, mismatches, incompatible
  cases, or unavailable results. All nine have changed execution paths.
  `python-comparison.json` is the structured report;
  [refactor-review.html](refactor-review.html) presents it for review.

The previously qualified Rust 1.96.0 artifact was reused from the
[request-entry checkpoint](../../native_editor/2026-10-16-request-entries/package-1.96.0/qualification.json).
Its source fingerprint remains
`sha256:1e7863630663e0799d764f4f738740adcb2d3758a7f710509d54631de6ce4c40`.
The engine source/build inputs were checked against that checkpoint's hashes;
the executable hash is recorded in the comparison report. This is new domain
qualification on the same artifact, not a new package build or deployment.

The artifact validates [all eight rule scenarios](rules-validation.html) with
72 passing expectations and [the direct entry](entry-validation.html) with nine.
`packaged-entry-run.json` records the expected approved total `"60"`, first
violation `"monitor"`, and its amount `"225"`.

## Verification and findings

- All 614 Python tests pass. The first full run revealed three native-only
  examples incorrectly included in Python execution/checking. The example test
  runner now explicitly lists those three deliberate syntax differences with
  their Rust coverage. Every other example still undergoes Python checking and
  execution, and every example still undergoes formatting checks. The initial
  failed log is retained as `python-tests-before-engine-scope-fix.log`.
- Rust 1.85.0 and 1.96.0 pass all 237 tests (233 integration, four unit) and
  Clippy with warnings denied. Rust formatting, all example formatting,
  top-level example checks, both reference request commands, JavaScript syntax,
  and whitespace checks pass. Logs are in this directory.
- The initial shared reuse scenario placed a `THEN` expectation between actions.
  Python evaluates scenario assertions after all actions, whereas native steps
  execute in source order. The shared example now puts expectations at the end;
  both engines retain their documented semantics. The initial diagnostic remains
  in `python-validation-before-assertion-order-fix.json`.
- Chromium 153.0.8010.12 checks the refactor review at 1440px and 390px widths.
  All nine case selections, path filtering, and search work without horizontal
  overflow. Screenshots were visually inspected. The existing Playwright
  container ran offline, with no script errors or external requests.
  See `browser/report.json` and `../check_browser.py` at the parent evaluation
  directory. The reproducible semantic harness is `../qualify.py`.

`source-hashes.json` identifies changed sources, tests, and harnesses. No human
comprehension or review-time study was performed. Broader source adaptation,
remaining language features, deployment qualification, and human evidence still
keep the full project goal incomplete. No external pilot or publication occurred.
