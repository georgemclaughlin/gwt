# Local document outline checkpoint

Native VS Code mode now provides Outline and Go to Symbol in Editor for local
program/type/record declarations, fields, behaviors, requests, backgrounds,
scenarios, and example tables. It uses the shared Rust layout parser and precise
UTF-8 source spans. See the [protocol and limits](../../../docs/native-editor.md#local-document-outline).

This index works in unsaved/untitled buffers and does not depend on imports,
types, expression validity, or successful execution. It does not claim semantic
validity. Layout errors and resource overflow return no guessed structure.
Declarations between scenario steps close the preceding outline range to keep
siblings disjoint; execution still follows the scenario semantics.

## Verification

- [Rust commands and logs](rust-checks.json): **333 tests** on Rust **1.85.0** and
  **1.96.0**, with Clippy warnings denied on both, in development mode. Five new
  groups cover exact/hierarchical ranges, Unicode/CRLF, declaration/step
  distinctions, interleaved sections, invalid bodies/imports, empty documents,
  layout/resource refusal, and CLI snapshot identity/request validation.
- [Python log](python-tests.log): **627 tests passed**.
- [Reference checks](reference-checks.json): **71 examples** pass canonical
  formatting; all top-level examples check; order fulfillment and language tour
  reference executions pass.
- JavaScript syntax checks and all **five unit tests** pass; Rust formatting and
  `git diff --check` pass. [Final checks](final-checks.json) retain these results.
- [Installed VS Code 1.137.0](editor-installed-final/extension-host.json):
  **31 checks passed**, including broken imports/expressions, unsaved Unicode
  and CRLF symbol ranges, record fields and example-table nesting, no source
  writes, stale response rejection, invalid layout, and untitled source.

The [first host run](editor-installed/qualification.json) failed the new stale
response assertion because VS Code reused its previous symbol result before the
edit. This was a test synchronization defect: the corrected test changes the
snapshot, then waits for an actual delayed outline process to start before
editing. The [final host run](editor-installed-final/qualification.json) passes
and both runs are retained. A zero launcher exit alone is never counted as
success.

## Execution preservation and scope

The [frozen development executable](native-binary.json) is the one used by the
installed editor tests. It was built with Rust 1.96.0; no new static package or
container qualification is claimed in this checkpoint.

[Actual engine-transition checks](migration-checks.json) cover all 18 invoice
cases from the preceding static executable. Every migration preserves the full
observation, including failures and execution evidence; originals remain byte
identical and proposals remain unapproved. Individual `migration-0.json` through
`migration-17.json` retain the comparisons and candidate cases. The new source
fingerprint reflects tool additions, with no intended execution-semantic change.
These cases do not prove universal compatibility.

To reproduce the outline checks:

```sh
cargo test --test editor_outline --locked
cargo build --workspace --locked
python evaluations/native_editor/qualify.py --output /tmp/gwt-outline-editor
```

Use a fresh output directory. The host runner needs the installed editor and a
graphical session. Source hashes for this checkpoint are in
[source-hashes.json](source-hashes.json).

The project goal remains active. Completion/debugging, broader semantic error
recovery, language/deployment work, and comparative human evidence remain open.
No human-benefit claim, external pilot, or publication is made.
