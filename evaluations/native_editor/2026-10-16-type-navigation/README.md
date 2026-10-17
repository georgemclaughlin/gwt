# Native type and field navigation — 2026-10-16

This checkpoint extends [native semantic navigation](../2026-10-16-navigation/README.md)
with compiler-recorded type uses and declaration provenance. It does not change
GWT's structural type compatibility or execution rules.

## Evidence

| Check | Recorded result |
| --- | --- |
| Rust 1.85.0 | 188 tests, Clippy with warnings denied; `rust-1.85.0-*.log` |
| Rust 1.96.0 | 188 tests, Clippy with warnings denied; `rust-1.96.0-*.log` |
| Rust formatting | `cargo +1.96.0 fmt --all -- --check` passed |
| JavaScript | Syntax checks and five tests passed |
| Installed VS Code 1.137.0, workspace executable | Eleven checks passed; `native/extension-host.json` |
| Installed VS Code, packaged executable | Eleven checks passed; `native-packaged/extension-host.json` |
| Rust 1.96.0 package and unrelated host | Eighteen independent observations, 288 concurrent executions, eighteen relocated replays; `package-1.96.0/qualification.json` |

The Rust total comprises 185 integration tests and three unit tests. Six new
tests in `tests/editor_types.rs` assert specific source locations for:

- imported named references, alias chains, nested list/optional annotations,
  field-type references, and field declaration hover;
- identical record shapes whose contracts, local copies, and declared return
  types must remain separate navigation targets;
- nested and optional field paths, traversal bindings, and sum projections;
- inferred homogeneous lists and conservative binding fallback for mixed origins;
- implicit request outputs and exact Unicode/CRLF byte positions;
- different record types substituted into different `EXAMPLES` rows, with
  per-row definitions and context names; quoted type names are not references.

The existing editor test now distinguishes selecting a path's root from
selecting its field. Root selection retains the variable declaration; field
selection reaches the appropriate record field. The full previous suite passes.

Two new actual VS Code checks follow type and field references into unsaved
imported declarations, distinguish two equal record shapes, verify the root
binding target, then edit one imported field and require the old definition
to disappear. Both source files remain unchanged on disk. The nine previous
authoring/navigation checks also pass.

The optional-value test initially assumed that an `IF ... is present` condition
narrows the entire body. The current native checker only supplies the necessary
narrowing within a guarded expression. The fixture therefore uses
`value is present and value.metadata.code == "x"`, matching the documented
current semantics. No control-flow narrowing feature was introduced here.

## Reproduction and identity

From the repository root, using fresh output directories:

```sh
cargo +1.96.0 build --workspace --locked
python evaluations/native_editor/qualify.py --output /tmp/gwt-type-navigation
python evaluations/native_packaging/qualify.py --toolchain 1.96.0 --output /tmp/gwt-type-navigation-package
```

The editor runner requires installed extension dependencies, an installed VS
Code, and a graphical session. It creates an isolated profile, extensions
directory, and fixture workspace, and requires the assertion artifact in
addition to the launcher's exit status. Use `--native /path/to/gwt-native` to
exercise the installed Cargo artifact.

`source-hashes.json` identifies the implementation and tests. The package
directory retains the exact unpublished artifact, host observations, dependency
graph/lockfile, executable hashes, and command log. Its engine source digest is
`sha256:a03770a38b65b8d2d053c7a6a5f10240b90c45b8a9788a5093e2ce9f82f45b33`.
No old-engine migration or additional target qualification is claimed here.

## Limits

Declaration provenance explains the checked contract, not runtime value history.
An inferred mixed list can have a shared structural type without one record
declaration. Navigation retains the binding target in that case. Substituted
spans without an exact component spelling also retain their mapped source site.
Invalid source yields no stale semantic result.

The editor logs retain the host SIGPIPE warning during deliberate process
cancellation; later diagnostic, execution, and navigation assertions pass.
Compilation time and memory cost of retained metadata were not benchmarked.
Completion, formatting, debugging, error-tolerant navigation, broader platform
qualification, and comparative human-understanding evidence remain open.
No external pilot was started and no package was published.
