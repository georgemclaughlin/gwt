# Validation evidence inventory checkpoint

Local Linux qualification of scenario expectation and callable-entry observations.
No external pilot or package publication was performed.

- Rust 1.85.0 and 1.96.0 pass all 211 workspace tests (208 integration, three
  unit) and Clippy with warnings denied. Logs are `test-*.log` and `clippy-*.log`.
  Rust formatting, JavaScript syntax checks, and five JavaScript unit tests pass.
- Eight tests in `tests/validation_evidence.rs` use explicit expected counts and
  outcomes. They distinguish scenario expectations from behavior requirements,
  request postconditions, and `WHEN` assertions; exercise true/false/missing
  condition, print, and expected-failure results; and check aborted evaluation,
  exhausted budgets, backgrounds, Unicode/CRLF example spans, imported/nested/
  repeated calls, uncalled declarations, and invalid-source refusal.
- The runtime event format and evaluation behavior are unchanged. The compiler
  retains scenario expectation indices, including background and expanded-row
  locations. Validation correlates those with events from the same execution,
  and matches callable entry events by declared definition site. It releases
  execution state/output/traces after collecting each scenario's observations.
- All six native example files pass validation across 28 scenarios, with 68
  recorded passing scenario expectations. Exact reports are in `examples.json`.
  The delivery example reports `quote delivery` as having no recorded request
  entry: its ten embedded scenarios call the quoting behavior directly. Separate
  host tests in `tests/scenarios.rs` exercise 16 request inputs and two invalid
  weights. Those host calls are deliberately outside this embedded-scenario
  inventory. The warning accurately identifies the inventory's scope.
- Actual VS Code 1.137.0 passes 17 checks with the workspace executable
  (`native/extension-host.json`) and the installed Cargo artifact
  (`native-packaged/extension-host.json`). The added check removes and restores
  the print expectation, verifying a passing run with an evidence warning and
  its subsequent correction. The existing diagnostic/navigation/formatting/
  validation checks remain in these runs.
- Rust 1.96.0 package qualification independently verifies the source fingerprint,
  dependency graph, 18 host observations, 288 concurrent shared-program runs, and
  18 relocated replays. See `package-1.96.0/qualification.json`. The installed
  artifact's source fingerprint is
  `sha256:05a44755e0dcde7fc11a54c25f1251cd81c279fc3e5c258ef5e708c10fe80803`;
  executable and artifact hashes are recorded separately.

`source-hashes.json` records the implementation and test files used. Editor logs
retain the existing SIGPIPE message around deliberately cancelled processes;
the success artifacts are required in addition to the launcher exit code.

The inventory establishes recorded observations, not branch coverage, oracle
quality, completed/successful calls, or correctness of the intended policy.
An assertion without a recorded outcome may have been reached before its
evaluation failed. Warnings do not change execution or validation exit policy.
The full project goal remains incomplete, including comparative human evidence.
