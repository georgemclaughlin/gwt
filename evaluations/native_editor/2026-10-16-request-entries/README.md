# Readable request entry checkpoint

Native entries explicitly `USE` their rules and retain ordinary source/scenario
semantics. This checkpoint makes a sole entry directly runnable/capturable and
qualifies the complete imported-request workflow. It does not add Python's
command-line pairing convention or introduce a separate input grammar.

- Rust 1.85.0 and 1.96.0 pass all 234 workspace tests (230 integration, four
  unit) and Clippy with warnings denied. See `test-*.log` and `clippy-*.log`.
  Formatting, JavaScript syntax, and five JavaScript unit tests pass.
- Six tests in `tests/entry_files.rs` cover implicit/named/example-row selection,
  refusal of ambiguous or declaration-only entries before execution, failed-run
  capture, sequential public calls, fresh state/shared budgets, import isolation,
  Unicode/CRLF sources, root/contract diagnostics, exact frozen replay after source
  deletion and relocation, and revision comparison with unchanged input source.
- The order-fulfillment entry has independently expected partial fulfillment:
  four requested, three reserved, one backordered, fee 19.5, and remaining widget/
  gadget/cable inventory of 4/0/4. It agrees with the existing JSON request for
  declared outputs. The test also checks the deliberate result difference: entry
  execution includes setup bindings; a JSON request exposes declared outputs.
- Nine example files pass native validation across 37 scenarios and 131
  expectations (`examples.json`). These are seven native examples plus the order
  rules and entry. The entry also passes Python inspection and validation with
  ten expectations in one scenario (`python-*.json`). The unsupported language
  tour is not included: its lowercase `exists`/`find` forms remain a native gap.
- Actual VS Code 1.137.0 passes 19 checks with both the workspace executable
  (`native/extension-host.json`) and installed artifact
  (`native-packaged/extension-host.json`). The added check runs an implicit entry
  without a target/input dialog and verifies that its dirty entry and imported
  request declarations are saved. Large integer output is preserved. Existing
  cancellation-related SIGPIPE messages remain in logs.
- Rust 1.96.0 package qualification passes the independent fingerprint and
  dependency-graph checks, 18 host observations, 288 concurrent executions, and
  18 relocated replays (`package-1.96.0/qualification.json`). The installed source
  fingerprint is
  `sha256:1e7863630663e0799d764f4f738740adcb2d3758a7f710509d54631de6ce4c40`.
  Package/executable hashes are recorded separately.

The packaged CLI generates [the order validation report](order-validation.html)
with ten passing expectations and no evidence warnings. Its direct run matches
its captured observation exactly; replay verifies the case (`order-run.json`,
`order.case.json`, `order-replay.json`).

[The changed-rule review](order-review.html) holds the entry bytes fixed and
changes the imported expedited base fee from 15 to 16. The shipping fee becomes
20.5 and the entry's existing expectation of 19.5 fails at its original source
location. The corpus comparison reports one changed outcome and one candidate
failure. `candidate/` is an intentional failing comparison fixture, not an
accepted policy. The unchanged review renderer was not requalified in a browser
at this checkpoint; its desktop/mobile checks are recorded in earlier checkpoints.

`source-hashes.json` records the implementation, tests, and example used.
Remaining language features, source adaptation, boundary/resource authoring,
editor capabilities, broader deployment qualification, and comparative human
evidence keep the full goal incomplete. No external pilot or publication occurred.
