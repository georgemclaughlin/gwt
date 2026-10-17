# Native editor checkpoint — 2026-10-16

The Rust snapshot checker and explicit VS Code native mode pass local checks on
x86_64 Linux. Python remains the extension's default. This checkpoint supports
the practical-adoption objective without establishing complete editor support
or a human comprehension benefit.

## Recorded results

| Check | Result and evidence |
| --- | --- |
| Rust workspace, 1.85.0 | 176 tests passed, Clippy with warnings denied passed; `rust-1.85.0-*.log` |
| Rust workspace, 1.96.0 | 176 tests passed, Clippy with warnings denied passed; `rust-1.96.0-*.log` |
| Rust formatting | `cargo +1.96.0 fmt --all -- --check` passed |
| JavaScript | `npm run check` and five `npm test` tests passed |
| Python LSP/service | Nine tests passed: `python -m unittest tests.test_lsp tests.test_service` |
| VS Code native, workspace binary | Seven checks passed in VS Code 1.137.0; `native/extension-host.json` |
| VS Code native, installed Cargo artifact | Same seven checks passed; `native-packaged/extension-host.json` |
| VS Code default Python mode | Unsaved error, correction, and type-alias hover passed; `python-verified/extension-host.json` |
| Packaged Rust host/CLI, both toolchains | Package verification, 18 independent observations, 288 concurrent executions, and 18 relocated replays passed; `package-*/qualification.json` |

The 176 Rust tests comprise 173 integration tests and three unit tests. Six new
integration tests cover editor snapshots, including static-only checking,
unchanged disk source, never-saved imports, Unicode/CRLF error source, closure
identity, unreachable overlays, path/symlink refusal, and bounded CLI input.

The seven native extension-host checks exercise native-only `THEN prints`,
unsaved Unicode/CRLF ranges, unsaved imported parse errors and deduplication,
cancellation of a deliberately delayed executable, a missing executable,
scenario execution with an integer beyond JavaScript's safe integer range, and
closing/reverting an imported buffer. The test asserts returned outcomes and
the actual VS Code diagnostic collection, not only launcher exit status.

`qualify.py` creates separate workspaces, profiles, and extension directories.
Successful host runs include `qualification.json`, the success artifact, and
editor logs. A launcher exit of zero alone is insufficient: the installed
launcher also returned zero for failed extension assertions.

## Failures found and resolved

An explicit native check could be invalidated by a pending save watcher before
it published diagnostics. It now waits for a current result. Shutdown cleanup
also attempted to clear an already disposed diagnostic collection; cleanup no
longer touches it after disposal. Native settings now have resource scope to
match multi-folder lookup.

The default Python language server failed because explicitly selecting stdio
transport made the installed language-client library append `--stdio` to the
CLI. GWT's CLI does not accept that flag. Omitting the explicit transport uses
the library's default stdio transport without adding arguments.

`python/` retains the startup failure. `python-fixed/` records an intermediate
test failure: that fixture expected the Python checker to report an unknown
name in a top-level assertion, which it does not currently check. The final
test uses a known invalid behavior call and a supported alias hover; it does
not claim broader Python checking coverage. `python-verified/` is the passing
default-mode run. The top-level `extension-host.json` is the earlier native
pass; the `native/` and `native-packaged/` directories contain reproducible runs
with executable hashes and logs.

## Reproduction

From the repository root, with extension dependencies and a graphical session:

```sh
cargo +1.96.0 build --workspace --locked
python evaluations/native_editor/qualify.py --output /tmp/gwt-editor-native
python evaluations/native_editor/qualify.py --engine python --output /tmp/gwt-editor-python
python evaluations/native_packaging/qualify.py --toolchain 1.96.0 --output /tmp/gwt-editor-package
```

Use fresh output directories. Pass `--native /absolute/path/to/gwt-native` to
qualify an installed artifact. The runner uses the installed editor; it does
not download one. The bundled test's delayed executable requires a POSIX host
and Node on PATH. Windows/macOS and remote extension hosts are not qualified.

`source-hashes.json` identifies the implementation and test inputs at this
checkpoint. Each packaged qualification retains the exact unpublished Cargo
artifact, dependency graph, host lockfile, observations, and executable hashes.
Both package builds have source digest
`sha256:ea868647b2d5071ec0710b6b47cb2f263dce76a5b4b71f1fa7edb3db6443be1e`.
Workspace and Cargo-normalized package identities intentionally differ. This
checkpoint did not repeat old-engine transition qualification or publish a
package. CI includes the JavaScript tests; no remote CI result is claimed.

Native run-selection UI, formatting, hover, completion, navigation, and debugging
are not comprehensively qualified here. Native language completeness, source
migration, boundary/resource authoring, broader deployments, and comparative
human review evidence remain open. No external pilot was started.
