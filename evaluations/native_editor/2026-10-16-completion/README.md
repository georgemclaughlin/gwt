# Native declaration completion — 2026-10-16

The [editor protocol](../../../docs/native-editor.md#declaration-completion) now
indexes current imported behavior, request, and type declarations for completion.
It supports incomplete call/type lines, parameter snippets, declared contracts,
returning-only `LET` suggestions, and nested container type names. It does not
infer local bindings or fields, complete arbitrary broken syntax, or claim that
suggested declarations are semantically valid. No rules execute while completing.

Five Rust integration groups cover fresh unsaved entry/import snapshots, contract
details, behavior/request/type contexts, literal domain words, Unicode/CRLF
ranges, suppression in strings/comments/expressions, duplicate declaration keys,
128-item truncation, missing imports, invalid UTF-8 queries, and the required-query
CLI contract. Existing loader tests govern source, import, and protocol bounds.
The packaged `completion-request.json` / `completion-response.json` probe reads
the real native underwriting example and returns its declared input record type.

`editor-current/` is the final installed VS Code **1.137.0** qualification:
**41 checks pass** against the packaged static executable. The new check inserts
the returned snippet, verifies its parameters and declared contract text, checks
the filled call, restricts `LET` results, tests nested type names, and confirms
that an imported rename cancels an already-running completion request. The
source files remain unsaved and their original disk contents remain unchanged.
The earlier `editor-final/` run also passes; `editor-current/` includes the final
extension package description. This is extension-host integration, not visual
browser validation or a participant study.

Two failed editor attempts remain available. `editor/` exposed an adapter bug:
a VS Code position was passed where the UTF-16-to-UTF-8 helper required a numeric
offset. The corrected adapter calls `document.offsetAt(position)` first; a new
JavaScript regression checks Unicode/CRLF conversion through the provider.
`editor-verified/` reached completion but had an incorrect test expectation about
MarkdownString's escaped spaces. The test now normalizes the editor's safe
plain-text encoding before comparing contract text. No trusted Markdown was added.

All **409 Rust tests** pass on **1.85.0 and 1.96.0**, with final focused reruns for
the completed completion test group. Clippy passes on both. The minimum toolchain
initially rejected a test fixture's `format!` collection style; its retained log
and corrected loop are recorded. All **666 Python tests**, **11 JavaScript tests**,
and **97 repository checks** pass. File identities are in `verification.json`.

`package/` qualifies an offline Cargo artifact and static musl release, a separate
Rust host, installed and relocated binaries, eighteen profiles and replays, and
288 shared-program concurrent executions. It records four packaged unit tests;
the full integration-suite results are the separate workspace logs above.

The new editor module changes the engine source fingerprint even though execution
semantics are unchanged. `migration/` explicitly replays 57 retained portfolio
cases and six recent exact-ratio underwriting cases through the previous engine,
then the new engine. All **63 full observations are preserved** and all candidate
cases replay. Baseline files are unchanged. No review approval, corpus replacement,
publication, or production deployment is implied.

Reproduce against a new output directory and an explicit executable:

```sh
cargo +1.96.0 test --locked -p gwt-core --test editor_completion
python evaluations/native_editor/qualify.py --native /path/to/gwt-native --output /path/to/new-editor-checks
```

The editor qualification uses an installed editor and isolated workspace/profile;
it does not download an editor. Field/local completion, native debugging, broader
error-tolerant semantic navigation, and actual comprehension evidence remain open.
