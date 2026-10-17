# Typed setup tables checkpoint

Local Linux qualification of native record collection setup. No external pilot
or package publication was performed.

- Rust 1.85.0 and 1.96.0 pass all 228 workspace tests (224 integration, four
  unit) and Clippy with warnings denied. Logs are `test-*.log` and
  `clippy-*.log`. Formatting, JavaScript syntax, and five JavaScript unit tests
  pass. The first Clippy run identified inefficient string construction in the
  new test fixtures; its log is retained and the corrected tests pass.
- Nine tests in `tests/setup_tables.rs` cover exact expression values, aliases,
  optional omissions, empty tables, nested values, ordered rows, malformed
  headers/cells/targets, atomic replacement under row and budget failures,
  resource boundaries, Unicode/CRLF example spans, formatting, capture/replay,
  and revision comparison. One added `tests/editor_types.rs` test checks table
  type, cell-binding, target-field, and collection-item provenance.
- All seven native example files pass across 31 scenarios and 71 recorded
  expectations (`examples.json`). The new receiving example independently
  expects totals 6, 4, and 0; Python also passes its check, format, and three
  scenarios (`python-validate.json`). This shared example is not evidence of
  full Python/native equivalence.
- VS Code 1.137.0 passes 18 checks with the workspace executable
  (`native-final/extension-host.json`) and installed Cargo artifact
  (`native-packaged/extension-host.json`). The added check exercises item-field
  and cell-binding definitions, unsaved cell errors, correction, Unicode/CRLF,
  and unchanged disk contents. The initial run in `native/` failed because the
  test read a diagnostic from the command summary instead of the editor's
  diagnostic collection; no production editor change was needed. Existing
  cancellation-related SIGPIPE messages remain in editor logs.
- Rust 1.96.0 package qualification independently verifies the source
  fingerprint, dependency graph, 18 host observations, 288 concurrent runs, and
  18 relocated replays. See `package-1.96.0/qualification.json`. The installed
  artifact's source fingerprint is
  `sha256:6a332cd747d549be2615cca0188c33058d1c378a2691871ea25afbafdce85d57`;
  executable and artifact hashes are recorded separately.

The installed executable also generates [the receiving validation report](receiving-validation.html)
with all three expectations passing and no evidence warnings. Each scenario is
captured and replayed (`receiving-*.case.json`, `receiving-*.replay.json`). A
candidate changing the first quantity from 2 to 3 produces
[a review report](receiving-review.html): one of three outcomes changes, its total
becomes 7, and its existing expectation of 6 fails. The other totals remain 4 and
0. All three cases record changed source/evidence identity; these are distinct
from outcome changes. The candidate is an intentional failing comparison fixture,
not an accepted policy change.

`evaluations/native_review/check_setup_tables.py` checks that report at 1440px
and 390px widths. Row and field-assignment events appear in the default trail,
operand links open the recorded inputs, JSON downloads match the report, and
there is no horizontal overflow. Screenshots in `browser/` were visually
inspected. Chromium 153.0.8010.12 ran in the existing Playwright container with
network access disabled; no script errors or external requests were observed.
`browser/report.json` records the results.

`source-hashes.json` identifies the implementation, tests, and example used.
Separate native GWT request-file execution remains pending. These local checks
do not establish human-comprehension benefits or complete the project goal.
