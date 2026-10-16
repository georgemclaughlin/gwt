# Native validation checkpoint

Local Linux qualification of combined native validation. No external pilot or
package publication was performed.

- Rust 1.85.0 and 1.96.0: workspace tests pass (203 total: 200 integration and
  three unit tests), and Clippy passes with warnings denied. See `test-*.log`
  and `clippy-*.log`. Rust formatting also passes.
- Seven validation tests cover independent gates, scenario absence, source
  identity, source freezing after files change/disappear, imported formatting,
  entry-only scenarios, budgets, and CLI exit/argument/no-write behavior.
- Formatter regression coverage includes an unresolved `USE` followed by an
  explicit scenario. The formatter excludes module imports from its scenario
  partitioning, as the bundle loader already does.
- All six native example files pass all gates, totaling 28 scenarios. See
  `examples.json` for exact program identities and individual summaries.
- JavaScript syntax checks and all five process/range unit tests pass.
- Actual VS Code 1.137.0 passes 16 extension-host checks with both the workspace
  executable (`native-verified/extension-host.json`) and independently installed
  Cargo package (`native-packaged/extension-host.json`). New checks exercise
  saving dirty imported files, simultaneous format/scenario failures, corrected
  validation, and refusal of a declaration-only entry. Earlier editor/navigation/
  formatting checks remain in the same run.
- `package-1.96.0/qualification.json` records independent package fingerprint
  verification, dependency comparison, 18 host observations, 288 concurrent
  shared-program executions, and 18 relocated replays. The installed package's
  source identity is
  `sha256:810c0f3c68be3b2396c66b29645346344465538380681ae82388bbaa4571878a`.
  This is a source fingerprint, not a digest of the compiled executable or its
  actual host dependency graph; those are recorded separately by qualification.

`native/` retains the initial failed editor test. Its assertion expected generic
`assertion_failed` for a print expectation; the correct established code is
`print_assertion_failed`. The fixture was corrected and the full run repeated in
fresh directories. Editor logs also retain the existing SIGPIPE message around
deliberately cancelled processes; all required assertions in the verified runs
completed. A zero launcher exit alone is not treated as a passing editor test.

`source-hashes.json` binds the implementation/test sources to this checkpoint.
Validation summarizes bounded individual executions and releases their full
traces between scenarios. There is no whole-validation time budget in the CLI
or library, and a passing report does not prove assertion coverage, complete
policy correctness, cross-platform deployment, or comparative human benefit.
The full project goal remains incomplete.
