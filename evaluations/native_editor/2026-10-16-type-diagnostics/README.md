# Static type-diagnostic checkpoint

Selected static errors now explain types using GWT vocabulary and report the
received and required types. Optional-record access identifies the exact path
that needs a presence guard. Shared-state arguments receive copy advice only
when the copied value is type compatible, with an explicit explanation that
changes to the copy do not reach the original. See the
[diagnostic scope and limits](../../../docs/native-editor.md#type-error-explanations).

The existing compact hover renderer and detailed diagnostic renderer share a
bounded implementation. Diagnostic one-of descriptions include payload fields,
so two variants with the same name but different field contracts are visibly
different. No syntax, accepted program, runtime semantics, error code, or
source-span behavior was intentionally changed. Diagnostic message text changes;
other categories, including host-input validation, retain existing messages.

## Verification

- [Rust results](rust-checks.json): **338 tests** and warning-free Clippy on both
  Rust **1.85.0** and **1.96.0**, in development mode. Five added groups cover
  operator-specific errors, expected/actual types, optional read/write paths,
  absence of false scalar-presence advice, conditional copy advice, demonstrated
  copy isolation, distinct one-of payload contracts, and bounded Unicode output.
- [Actual old/new checks](diagnostic-comparison.json): four frozen source pairs
  retain identical diagnostic codes and spans. Each repaired source checks with
  the new executable. The previous executable is the retained outline build.
- [Installed VS Code 1.137.0](editor-installed/extension-host.json): **33 checks**
  pass, including imported optional records in unsaved Unicode/CRLF source,
  exact highlighted paths, applying the stated guard, conditional copy advice,
  and correction without saving. Existing navigation, outline, formatting,
  execution, and cancellation checks also pass.
- [Python](python-tests.log): **627 tests** pass.
  [Reference checks](reference-checks.json): **71 formatted examples**, top-level
  checking, and order/tour execution pass. Five JavaScript unit tests, syntax
  checks, Rust formatting, and diff checks pass; see [final checks](final-checks.json).

The [frozen development executable](native-binary.json) is the one used for the
editor and engine comparisons. [Eighteen retained invoice cases](migration-checks.json)
migrate from the earlier static engine with full observation preservation.
Original bytes are unchanged, candidate proposals remain unapproved, and each
comparison is retained as `migration-0.json` through `migration-17.json`.
This checkpoint does not claim a new static package or production qualification.

Reproduce focused checks from the repository root:

```sh
cargo test --test type_diagnostics --locked
cargo build --workspace --locked
python evaluations/native_editor/qualify.py --output /tmp/gwt-type-diagnostics-editor
```

Use a fresh output directory and an installed VS Code with a graphical session.
[Source hashes](source-hashes.json) identify the checked implementation and docs.

The full goal remains active. These are authoring-tool and execution checks,
not evidence that people comprehend or review policies faster. Other diagnostic
categories, completion/debugging, broader semantic recovery, language/deployment
work, and actual comparative participant evidence remain open. No external pilot
or publication occurred.
