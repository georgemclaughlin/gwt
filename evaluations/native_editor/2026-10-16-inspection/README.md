# Checked native contract inspection checkpoint

`gwt-native inspect` and `CompiledProgram::inspect()` expose checked contracts,
source identity, and original locations without executing the program. The
[protocol documentation](../../../docs/native-inspection.md) distinguishes caller
inputs from request-local setup and successful inspection from passing tests.
The borrowed library descriptors expose complete resolved types; `to_json()`
refuses reports above eight MiB rather than truncating their contracts.

## Verification

- [Rust results](rust-checks.json): **349 tests** and warning-free Clippy on
  **1.85.0** and **1.96.0**, in development mode. Six new groups cover exact
  invoice contracts, local initialization exclusion, optional omission, declared
  contracts after refinement, return metadata, imported aliases/kind selectors,
  Unicode/CRLF spans, frozen identities, scenario/row metadata without execution,
  60-level types, oversized report refusal, and CLI errors/source preservation.
- [Representative reports](example-inspection-checks.json) for
  [exchange assessment](early-returns-inspection.json),
  [contact routing](one-of-inspection.json), and
  [MiniLang](minilang-inspection.json) match their checked source identities and
  entry names. These are discovery reports, not execution evidence.
- [Python](python-tests.log): **627 tests pass**.
  [Reference checks](reference-checks.json): **71 examples** format, top-level
  examples check, and order/tour workflows pass. Five JavaScript unit tests,
  syntax checks, Rust formatting, and diff checks pass; see
  [final checks](final-checks.json).
- [Installed VS Code 1.137.0](editor-installed/extension-host.json): **33 existing
  checks** pass against the packaged executable. No new editor UI is claimed.

## Host, package, and runtime checks

The [static musl package](package-1.96.0/qualification.json), built with Rust
1.96.0, passes three packaged library tests, two embedded scenarios, 18 independent
host cases, 288 concurrent calls, and 18 relocated/extracted-binary replays.
All [53 archived source/build inputs](package-source-verification.json) match the
workspace. The package remains unpublished.

The [independent Rust host](../../native_packaging/host.rs) now checks expected
inspection contracts before execution. The package qualifier compares this
report with installed and relocated CLI inspection. The
[Alpine and GLIBC 2.36 runtime checks](static-runtime/qualification.json) also
compare inspection with the same host report, then run the invoice example,
two scenarios, and all 18 captured cases. They use empty PATH, no network, and
read-only filesystems; they share the host kernel and do not establish general
platform or production support.

All [18 complete invoice observations](invoice-comparison.json) equal those from
the preceding engine. An explicit previous-case migration also preserves its
complete observation. This supports the intended absence of execution changes
for the tested cases; it is not a universal compatibility proof.

## Reproduce

```sh
cargo test --test inspection --locked
cargo run -p gwt-core --bin gwt-native -- inspect examples/native_early_returns/rules.gwt
```

For packaged host/CLI comparisons, use the existing packaging qualifier with a
fresh output directory. It now retains the host's inspection report and asserts
its equality with both CLIs. [Source hashes](source-hashes.json) bind this
checkpoint's implementation and documentation.

The full project goal remains active. Remaining language/tooling work, production
qualification, and actual participant evidence remain open. No human-benefit
claim, external pilot, or publication occurred.
