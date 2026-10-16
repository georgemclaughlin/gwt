# Native formatting checkpoint — 2026-10-16

The native toolchain now formats source and VS Code buffers without invoking
Python. It preserves expression text, literals, grouping, and statement/table
order, and validates layout before and after transformation. Complete grammar
and semantic validation remain separate checker responsibilities.

## Results

| Check | Evidence |
| --- | --- |
| Rust 1.85.0 and 1.96.0 | 196 tests each: 193 integration, three unit; retained test logs |
| Clippy and rustfmt | Both toolchains pass Clippy with warnings denied; Rust 1.96.0 formatting passes |
| JavaScript | Syntax checks and five tests pass |
| Native examples | All six `examples/native_*/*.gwt` files already pass `format --check` |
| VS Code workspace executable | Fourteen checks; `native-verified/extension-host.json` |
| VS Code installed Cargo executable | Fourteen checks; `native-packaged/extension-host.json` |
| Separate package/host qualification | Rust 1.96.0 artifact verifies; eighteen independent observations, 288 concurrent executions, eighteen relocated replays; `package-1.96.0/qualification.json` |

Eight new tests in `tests/formatter.rs` cover:

- independently specified formatting of quoted pipes/hashes, comments, and
  Unicode table values, followed by exact expected scenario outputs;
- integers beyond JavaScript's safe range, decimal spelling, grouped copied
  arguments, and expected-failure action order;
- request fragments with unresolved external DTOs, without import reads;
- uniform CRLF preservation, mixed-newline normalization, original diagnostic
  byte offsets, and empty/comment-only buffers;
- malformed layout, unclosed strings/groups, invalid tables, excessive input,
  physical lines, columns, and table-padding expansion;
- idempotence and unchanged state/output/event-operation sequences across five
  native workflows, using the workflows' executable assertions;
- CLI preview, check, explicit write, unchanged invalid source, and stdin snapshots;
- symlink/read-only refusal, retained Unix permissions, and temporary-file cleanup.

The actual editor host tests the existing eleven native capabilities plus
formatting with undo/redo and no save, idempotence, rejection of stale responses
and malformed layout, and untitled-buffer formatting with exact numeric text.
Both source files stay unchanged on disk. The initial `native/` harness run
expected an empty array for an idempotent provider result; this VS Code version
returns `undefined`. The final assertion accepts either representation of no
edits while retaining all exact buffer, undo, and stale-response checks.

## Reproduction

From the repository root, with fresh output directories:

```sh
cargo +1.96.0 build --workspace --locked
target/debug/gwt-native format examples/native_delivery/rules.gwt --check
python evaluations/native_editor/qualify.py --output /tmp/gwt-native-format-editor
python evaluations/native_packaging/qualify.py --toolchain 1.96.0 --output /tmp/gwt-native-format-package
```

The editor runner requires installed extension dependencies, an installed
VS Code, and a graphical session. It uses a private profile/workspace and checks
the success artifact, not just the editor launcher's exit code. Pass
`--native /path/to/gwt-native` to use the installed package executable.

`source-hashes.json` records implementation and fixture inputs. Package evidence
retains the unpublished artifact, host observations, dependency lockfile/graph,
executable hashes, and command log. Engine identity is recorded in the package
qualification JSON; workspace and normalized-package identities differ by design.

## Limits

Layout formatting does not establish that a program is valid or passes its
scenarios. It preserves internal expression/domain-phrase spacing and does not
dedent invalid code. Table widths count Unicode scalars; rendered width may vary
with font. Formatting changes source identity and evidence locations when text
changes, and does not modify frozen captured cases.

File replacement is atomic on the tested Linux filesystem, with a best-effort
source comparison before rename; no transactional concurrency or crash-durability
claim is made. Other operating systems are not qualified. The editor logs retain
the previously observed host SIGPIPE warning during deliberate cancellation;
subsequent assertions pass. Formatting time/memory and comparative human review
benefits are not measured here. Completion, debugging, language completeness,
and broader deployment/human evidence remain unfinished. No package was published
or external pilot started.
