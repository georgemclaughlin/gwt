# Native scalar-dispatch checkpoint

`DEPENDING ON expression` now supports literal scalar cases, exhaustive boolean
and text-union coverage, explicit fallbacks, and source-backed decision evidence.
Numeric matching deliberately follows native exact equality: `1` and `1.0`
match the same value and cannot be separate labels. The subject is evaluated
once; mutations in the selected body do not dispatch again. See the
[semantic decision](../../../docs/native-value-dispatch.md).

## Verification

- Rust **1.85.0** and **1.96.0** each pass **274** workspace tests (270
  integration and four unit tests) and Clippy with warnings denied. Raw logs
  are `rust-*-tests.log` and `rust-*-clippy.log`.
- Eight `value_dispatch.rs` tests cover 30 independent policy inputs, two invalid
  attempts, six example rows, exact mixed numeric equality and high precision,
  finite coverage, unknown/duplicate/impossible cases, body scope and returns,
  subject snapshots, aliases, collection guards, budget failure, source evidence,
  capture/replay, revision comparison, and generated scenarios. An existing
  kind-dispatch return test had its `compile_program` source/file arguments
  reversed; that false-positive negative check is corrected and passes against
  the intended program.
- `editor_types.rs` now checks subject fields, branch-local bindings, and calls
  through unsaved imports with Unicode/CRLF source. Actual VS Code **1.137.0**
  passes **23** checks with the installed package after the editor fix below
  (`editor-installed-fixed/extension-host.json`). The new live check accepts a
  decimal label on an integer subject, locates subject/local definitions, and
  rejects a numerically equal duplicate at its exact branch span.
- All **621 Python tests** pass (`python-tests.log`). Every example still passes
  Python formatting; top-level examples pass Python checking and the fulfillment
  and language-tour request commands pass. The new delivery example is explicitly
  native-only for execution because plain boolean coverage differs from Python.
- Extension syntax and all five JavaScript process/range tests pass. Rust
  formatting and `git diff --check` pass.
- Rust 1.96.0 package qualification passes independent source-fingerprint and
  dependency-graph checks, 18 host observations, 288 concurrent executions, and
  18 relocated case replays (`package-1.96.0/qualification.json`). The installed
  executable is `/tmp/gwt-package-host-90cj1m_b/installed/bin/gwt-native`, SHA-256
  `1d0846a2a6045edaa93f0bd5fae22dc91511715bc64840eb38ce3dd7ebd45b3c`.
  Its source identity is
  `sha256:4e18e89e6609b3d893014e65bfb90b26ecb8c51cf46f56a373c889502d4d9337`.
  `package-source-verification.json` checks the archived implementation/build
  inputs against the workspace independently of those binary hashes.

## Installed policy and review

[`delivery/validation.html`](delivery/validation.html) validates six scenarios
with 18 top-level expectations and six positive-attempt requirements. The
packaged engine captures and verifies six representative requests. A candidate
changes the second retry delay from 15 to 25. The
[`offline review`](delivery/delivery-review.html) reconciles all six cases and
identifies exactly two changed outcomes, with no baseline mismatch, unavailable
case, or candidate failure. All six have source/evidence changes because the
candidate source and its identity differ; those flags are not extra outcome
regressions.

`qualify_value_dispatch.py` retains inputs, source revisions, cases, replay
results, corpus, validation, and review. `check_value_review.py` verifies all six
case selections, visible scalar-decision evidence, the two changed-case filter,
and operand navigation at 1440px and 390px in offline Chromium **153.0.8010.12**.
No script errors, external requests, or horizontal document overflow occurred.
Both `delivery/browser/value-decisions-*.png` screenshots were visually inspected.
This qualifies the review's behavior and rendering, not human comprehension.

## Editor race found during qualification

The initial workspace editor run passed. The first installed editor run failed
at the existing readable-entry Run check (`editor-installed/` retains the failed
logs and launcher metadata). A late file-save notification cancelled the
`check-editor` process used by explicit Run because it was classified as a
background diagnostic job. The launcher returned zero, but the qualification
correctly refused success because its final assertion artifact was absent.

Run now marks its preflight check as part of the explicit command. Save watchers
continue cancelling obsolete diagnostics; source hashes still reject a changed
preflight snapshot. The extension-host test uses a deliberately delayed native
executable while Run saves unsaved entry/import buffers. The fixed installed
run passes all 23 checks. The failure is retained rather than overwritten or
counted as a passing trial. The earlier workspace run predates this adapter fix;
the installed fixed result is the final editor evidence.

`source-hashes.json` identifies the final implementation, tests, example,
qualification helpers, and relevant documentation. No release was published
and no external pilot was initiated. IF-based narrowing, remaining language
forms, broader deployment qualification, and actual human-benefit evidence
remain open; the full project goal is not achieved.
