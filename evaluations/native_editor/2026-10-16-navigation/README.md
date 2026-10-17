# Native semantic navigation — 2026-10-16

The explicit Rust editor mode now provides semantic hover and definition
navigation from compiled targets and binding slots. This checkpoint extends
the [initial editor qualification](../2026-10-16/README.md).

## Evidence

- Rust 1.85.0 and 1.96.0: 182 tests each (179 integration and three unit),
  Clippy with warnings denied, and formatting pass. Logs are retained here.
- Five JavaScript tests and syntax checks pass, including UTF-16 cursor to
  UTF-8 offset conversion and refusal of split surrogate pairs.
- `native-final/extension-host.json` records nine checks in VS Code 1.137.0.
  The seven initial checks still pass. Added checks invoke the actual hover
  and definition providers over unsaved imported source, assert an imported
  return contract and exact local-definition position, verify that disk files
  are unchanged, and require no definition after an invalid edit.
- `native-packaged-final/` exercises those providers using the separately installed
  Cargo executable; executable hashes and editor logs identify the run.
- `package-final-1.96.0/` retains the unpublished artifact, independent host
  expectations, dependency graph/lockfile, installed/relocated hashes, and
  command log. Eighteen observations, 288 concurrent executions, and eighteen
  relocated replays pass. This checkpoint does not repeat old-engine migration
  or claim package qualification on additional targets.

The six added Rust tests cover imported call resolution, same-named parameters
in separate behaviors, returning-call locals, branch-local identity, traversal
variables, aggregate projections, checked field types, request outputs and calls,
expected-failure actions, Unicode/CRLF source, invalid query positions, comments,
invalid source, and seventy table contexts with an explicit sixty-four-result
limit. Large structural types and Unicode literal unions explicitly mark truncation.
The tests assert independently specified declaration positions rather
than comparing navigation to a second name-based index.

`source-hashes.json` records the implementation and fixture inputs. Both full
Rust suites ran against these native sources. The packaged engine source digest
is `sha256:76c94ae6018c814b67d11d06c4809e3fe61a34c2aacc82c7d69a6d49410ea0ee`.
The runtime retains additional declaration metadata; this checkpoint does not
measure its compilation-time or memory cost.

## Qualification corrections

`native/` and `native-corrected/` retain intermediate failing harness runs.
The fixture was corrected to derive cursor offsets from the actual editor
buffer after line-ending normalization and to account for MarkdownString's
escaped spaces when asserting rendered hover content. `native-verified/`, `native-packaged/`, and `package-1.96.0/` record the passing
implementation before the final long-field-name ellipsis correction; the
`*-final` directories and final Rust logs include that correction. The successful run still
requires the exact return-contract words and definition positions; it does not
weaken the expected semantic result to merely checking for a nonempty hover.

The editor logs include a host SIGPIPE warning during deliberately cancelled
process tests. It did not fail the assertions or prevent later diagnostics,
execution, or navigation. No claim of warning-free editor operation is made.

## Reproduction and limits

Use the [same isolated runner](../qualify.py), a current native build, installed
extension dependencies, an installed VS Code, and a graphical session:

```sh
cargo +1.96.0 build --workspace --locked
python evaluations/native_editor/qualify.py --output /tmp/gwt-navigation-native
```

Pass `--native /absolute/path/to/gwt-native` for an installed Cargo artifact.
Use a fresh output directory. The runner requires the assertion artifact in
addition to the launcher's exit status.

Hover covers behavior contracts, binding types, and type declaration headers.
Field-path definitions target the root binding. Type-reference navigation,
record-field declaration navigation, completion, formatting, debugging, and
error-tolerant navigation remain open. The installed-editor runner is qualified
on this Linux host; broader platform and performance evidence is absent. No
external pilot or comparative human-benefit claim follows from these checks.
