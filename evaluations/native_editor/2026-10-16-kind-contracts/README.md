# Kind-specific contract checkpoint

Native type expressions can select a declared kind, for example
`TYPE Email is Contact of kind email`. Helpers can name the payload they require
without accepting unrelated kinds or duplicating the record definition. The
discriminator remains part of the value. Shared calls still require exact types;
dispatch supplies the proof for a narrowed argument.

## Verification

- Rust 1.85.0 and 1.96.0 each pass all 265 workspace tests (261 integration and
  four unit tests) and Clippy with warnings denied (`test-*.log`, `clippy-*.log`).
  Five tests in `tests/kind_contracts.rs` cover independent results, selected
  request boundaries, containers, generated scenarios/replay, proven calls,
  rejected widening, invalid selections, read-only kinds, and protection against
  a second alias changing a specialized helper's payload kind.
- A new editor test resolves selected payload fields through aliases and imports,
  distinguishes same-named fields in different kinds, and follows base-type and
  kind references across Unicode/CRLF source. Both actual VS Code 1.137.0 runs
  pass 22 checks (`native/extension-host.json`, `native-packaged/extension-host.json`).
  The new live-editor check uses unsaved selected contracts and rejects an invalid
  kind selector, then clears the diagnostic after correction.
- All 615 Python tests pass (`python-tests.log`). Formatter coverage preserves
  selectors, wrappers, quoted strings, comments, and imported files. Projection
  is confined to layout validation; Python execution still rejects the native
  type form. The new public example is explicitly assigned to the Rust suite.
- Example formatting, top-level Python checks, both reference request workflows,
  Rust formatting, and whitespace pass (`final-checks.log`, `python-*.json`).
  Extension JavaScript syntax and all five JavaScript unit tests also pass.
- Package qualification passes independent fingerprint/dependency checks, 18
  host observations, 288 concurrent executions, and 18 relocated replays
  (`package-1.96.0/qualification.json`). All 47 implementation/build inputs in
  its archive match the current workspace. The source identity is
  `sha256:b494556ae237d8188ce2cf470c3eca6b1e8d32faa6c0bb4dd3938905ef838da3`;
  binary/archive hashes are recorded separately.

[Expression validation](expression-validation.html) passes five scenarios with
ten expectations. A separate packaged selected-request probe rejects a phone
value at an email-only boundary with `one_of_kind` and no execution events
(`selected-request-rejected.json`). The probe source/input are retained beside it.

## MiniLang pressure test

`evaluations/minilang/kind_contracts.py` constructs one explicit candidate from
the shared MiniLang engine. It replaces scalar-payload helper calls with selected
statement contracts, retaining the public request and body policies. For example,
the long threshold call becomes `compare sum statement into runtime`, and its
helper declares `statement is ThresholdStatement`.

The packaged engine executes both sources against all 943 existing independent
probes: every one of 720 statement orderings, 125 arithmetic cases, and the
missing/duplicate/stale-state fixtures. Every complete result matches the host
oracle and is structurally identical JSON between these two native revisions (`minilang/report.json`, `minilang/observations.json`). Both scenario
entries validate their 15 expectations. Numeric coverage remains integer-domain;
this is not evidence of arbitrary fractional equivalence.

Five fresh baseline cases replay and compare against the candidate with no
outcome/state changes, mismatches, candidate failures, or unavailable cases.
[The review](minilang-review.html) records changed source/evidence for all five.
The unchanged HTML renderer was not browser-qualified again at this checkpoint;
its desktop/mobile checks are recorded in the preceding MiniLang checkpoint.

The candidate under `minilang/selected/` is a frozen experiment, not a second
maintained policy module. The shared engine remains a cross-engine reference
fixture. Shorter calls and checked field access are demonstrated; improved human
comprehension or review time is not. Scalar dispatch, `IF` narrowing, general
branch field provenance, broader workflows, deployment, and human evidence keep
the full project goal open. No external pilot or publication occurred.

`source-hashes.json` records the implementation, examples, tests, formatter,
documentation, and experiment script used at this checkpoint.
