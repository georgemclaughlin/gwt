# Rust architecture and maintenance guide

GWT compiles a captured source bundle into a checked program, executes it over
bounded state, and records evidence for replay and review. The public Rust API
is exported from `crates/gwt-core/src/lib.rs`; the CLI is an adapter to that API.

| Boundary | Main modules | Maintenance constraint |
| --- | --- | --- |
| Source closure and identity | `bundle.rs`, `source.rs`, `version.rs`, `cases.rs` | Retain source locations, digest domains, and exact engine identity |
| Parsing and checking | `program_source.rs`, `program.rs`, `expression.rs`, `value.rs` | Check before execution; preserve explicit scope, type, and alias rules |
| Execution and evidence | `program_runtime.rs`, `evaluation.rs`, `explanation.rs`, `profiling.rs` | Meter work and evidence; observations must explain actual execution |
| Review and migration | `review/`, `migration/`, `scenario_generation.rs` | Reverify baseline cases; never silently carry approvals across changes |
| Editor and presentation | `editor*.rs`, `formatter.rs`, `validation*.rs` | Keep lexical/contextual assistance distinct from semantic validation |
| Command-line adapters | `main.rs`, `*_cli.rs`, `cli_options.rs` | Preserve command diagnostics, bounded inputs, and no-overwrite exports |

Paths in the table are relative to `crates/gwt-core/src/`.

## Cleanup review

The October 2026 cleanup examined the module boundaries, large parser/runtime
files, repeated command option handling, and the two largest test corpora.

Five CLI parsing loops shared the same pair/duplicate validation. They now use
one small helper, with each caller retaining its allowed vocabulary and required
options. Black-box CLI tests cover unknown, duplicate, and unpaired flags across
ten commands; existing integration tests exercise successful calls and exports.

`program.rs` and `program_runtime.rs` remain the largest semantic modules.
Their size alone is not a reason to split or generalize them. Focused operations
already live in separate modules (for example rounded division, refinement,
setup tables, and failure expectations). Extract further pieces when a concrete
change exposes an independent responsibility; avoid coupling the checker and
executor merely to eliminate superficially similar code. Their separate checks
and independent outcome fixtures are useful defenses against shared mistakes.

The 1,072 underwriting and 630 rounding cases are distinct, so none were removed.
Their JSON values and order are preserved in a compact case-per-line layout.
Bulk historical observations are retrieved through the
[evidence archive](../evaluations/README.md), not loaded by the regression suite.

This was a focused maintainability review, not proof that every runtime path is
optimal or defect-free. Future optimization should be driven by profiles and
preserve independent tests, resource behavior, and execution evidence.

## Making changes

Follow the [contributor checks](contributing.md). Any Rust source edit changes
engine identity, even a behavior-preserving CLI refactor. Rebuild the public
example/site artifacts with the new engine, verify old cases using their old
engine, and use explicit migration to compare observations. Do not relabel
historical cases or turn a pending decision into an approval.
