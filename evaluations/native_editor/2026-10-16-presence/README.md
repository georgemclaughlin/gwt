# Native optional-presence checkpoint

Native `IF` and `DECIDE` carry proven optional presence into their selected
bodies. Later `DECIDE` conditions also retain facts established by earlier
conditions being false. Nested optional records can therefore be handled as
explicit missing-data decisions before their fields are read. Zero, false, and
empty text remain present. See [the semantic rules](../../../docs/native-presence.md).

Runtime guards protect the actual shared state address while a body relies on
presence. An alias cannot clear the value or replace an ancestor with a record
that loses it. Present replacements remain allowed. Guards compose with kind
and collection guards and are released on normal exit, return, and failure.
The checker preserves exact shared argument contracts and permits copied or
returned refined records to satisfy their original optional contracts.

## Verification

- Rust **1.85.0** and **1.96.0** each pass **285** workspace tests (281
  integration and four unit tests), with Clippy warnings denied. The full logs
  are `rust-*-tests.log`. The two affected suites were rerun after adding direct
  assertions for the example JSON request files: all **18** tests pass on each
  toolchain (`request-fixtures-*.log`). Final Clippy checks cover those additions.
- Ten `presence.rs` test groups cover 80 independently specified policy inputs,
  two invalid inputs, six embedded scenarios with 18 top-level expectations,
  omitted/null equivalence, false/zero/empty values, nested proofs, aliases and
  ancestor replacement, copied values and returned records, shared helper
  contracts, early returns and failures, resource limits, original Unicode/CRLF
  source spans, capture/replay, generated scenarios, and revision comparison.
  Changing the limit comparison from `>` to `>=` changes exactly nine valid
  exact-limit probes.
- Actual VS Code **1.137.0** passes **24** checks using the installed executable
  (`editor-installed/extension-host.json`). The new check accepts an optional
  record's guarded field, resolves its declaration in an unsaved imported file,
  and reports the exact unsafe path when the guard is removed. Restoring the
  guard clears the error without writing either buffer to disk.
- All **621 Python tests** pass (`python-tests-final.log`). The initial failure
  is retained in `python-tests.log`: the JSON example smoke loop did not use the
  native-only example registry already used for program execution. It now uses
  that registry, and both affected native JSON fixtures have direct Rust output
  assertions. This is a profile boundary, not a claim of cross-engine parity.
- Rust and example formatting, top-level Python example checking, the existing
  order/tour request workflows, extension syntax and five JavaScript tests, and
  whitespace checks pass. `final-checks.json` records the final documented
  reimbursement commands and checks.

## Installed package and behavioral review

Package qualification verifies the independent engine fingerprint and dependency
graph, **18** host observations, **288** concurrent executions, and **18**
relocated replays (`package-1.96.0/qualification.json`). The installed executable
is `/tmp/gwt-package-host-w0d9qqx1/installed/bin/gwt-native`, SHA-256
`74ccbb28339e7637acf0315787680713e3fab5a6ee9f2ecb1a71a06d888b1056`.
Its engine source identity is
`sha256:3dd860926b482effd9586ec0181b8b485d65b16db9d205c34d4d2626f5f9c589`.
`package-source-verification.json` independently compares all **48** archived
implementation/build inputs with the workspace, including the new presence
module. These checks qualify the tested Linux host; they do not establish all
deployment targets.

The installed package validates the six reimbursement scenarios and captures
and verifies eight representative requests. The
[offline review](reimbursement/presence-review.html) identifies exactly two
changed outcomes for the `>` to `>=` revision: `approved-boundary` and
`empty-reference`. All eight cases compare, with no baseline mismatch, candidate
failure, or unavailable case. All eight have changed source/evidence identities;
those flags do not imply eight changed policy outcomes.

A separate aliased-state case captures and replays `presence_mutation`: clearing
an active present field through a wider alias is rejected before a successful
write event, and the original value remains four. This programming failure is
replayable but is intentionally outside the allowed `THEN fails with` set.
`qualify_presence.py` retains source revisions, inputs, captures, corpus,
validation, comparison, and guard-failure evidence in `reimbursement/`.

`check_presence_review.py` verifies the review at **1440px** and **390px** in
offline Chromium **153.0.8010.12**. All eight cases can be selected, branch
decisions are visible, the changed-case filter returns exactly two cases, and
operand links expose the compound presence check and its component. Missing
records do not produce fabricated reads of their payload fields. No script
errors, external requests, or horizontal document overflow occurred. Both
`reimbursement/browser/presence-decisions-*.png` screenshots were visually
inspected; the selected presence evidence and links remain readable at both
widths. These checks establish UI behavior, not reviewer comprehension.

## Explicit limits

Python formatting and checking accept the reimbursement example, but the Python
runtime rejects `facts.policy.limit` through an optional record. The separate
`python-reference-limitation.json` records that failure. Native execution has its
own independent expected outcomes and is not made to inherit this limitation.

Proofs are branch-local. Assertion/early-return flow, collection-filter
refinement, and `IF`-based kind refinement remain outside this change. The full
project goal also still requires broader language and deployment decisions and
actual human-benefit evidence. No participant study or external pilot was run.
`source-hashes.json` records the final relevant source, tests, documentation,
examples, and qualification helpers for this checkpoint.
