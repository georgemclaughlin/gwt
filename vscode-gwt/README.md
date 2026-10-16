# GWT VS Code Extension

**GWT: Show Engine Information** reports the engine active in the window, the
selected command, and its version JSON in the GWT output channel. It works with
no source document open and never saves or executes an edited file. Native mode
reports the experimental language profile, its unassigned language version
(`null`), package version, and exact engine fingerprint. Python mode reports the
existing Python package/spec versions. Reload after changing `gwt.engine`.

This extension registers `.gwt` files and adds syntax highlighting. The default
Python mode starts the GWT language server. An explicit native mode uses the
Rust checker and executor, including native-only language features.

## Native mode

Build the executable from the repository root:

```sh
cargo +1.96.0 build --workspace --locked
```

Set the following in your development workspace, using your actual repository
path, then reload the extension host window:

```json
{
  "gwt.engine": "native",
  "gwt.native.command": "/absolute/path/to/gwt/target/debug/gwt-native"
}
```

Diagnostics, hover, and go-to-definition use unsaved file-backed GWT documents
and their open imports.
The check does not save files or execute scenarios. Diagnostics point into the
exact checked source, including Unicode text. Obsolete results are discarded
after edits. An unavailable executable produces a visible diagnostic.

The import root defaults to the workspace folder, or the file's parent outside
a workspace. Set `gwt.native.importRoot` to an absolute path or a path relative
to the workspace folder when your program needs a narrower root. Open documents
under that root supply the in-memory source snapshot; imports cannot escape it.
Native source bounds apply: at most 256 documents, one MiB per document, and
four MiB of source per snapshot/closure. Semantic diagnostics and navigation require a file path; formatting and the
local outline also support untitled buffers.

| Command | Native behavior |
| --- | --- |
| Check Current File | Refresh static diagnostics for open GWT documents and imports |
| Validate Current File | Save dirty open GWT documents; check the captured closure, formatting, and entry scenarios; require at least one scenario |
| Test Current File | Save dirty open GWT documents, then execute the active file's scenarios |
| Run Current File | Save dirty open GWT documents; run a sole entry scenario directly, otherwise choose a scenario or request (with a JSON input file) |
| Profile Execution Evidence | Use the same entry/target selection as Run; execute once and report evidence bytes by operation/source location, steps, and any execution diagnostic |
| Format Current File / Format Document | Format the current buffer with native layout validation; retain unsaved edits and undo/redo |
| Debug Current File | Explain that native debugging is not implemented |

Execution output is shown in the GWT output channel with exact numeric text.
To use the same operating budget as your terminal or host, set a limit file:

```json
{
  "gwt.native.limitsFile": "examples/native_weighted_allocation/limits.json"
}
```

Run, Profile, Test, and Validate read this setting on each command; changing it
does not require a reload. Relative paths resolve against the active file's
workspace folder, or its parent outside a workspace, independently of the import
root. Absolute paths also work. An empty setting uses native defaults.

Execution saves dirty open GWT documents and the selected limit file's dirty
file-backed buffer before invoking the CLI. If saving is cancelled, execution
does not proceed. Diagnostics, navigation, outline, and formatting neither apply
execution budgets nor save the limit file. The GWT output channel identifies the
selected limit path or native defaults and retains exact CLI output.

The file must satisfy the [native limit-file contract](../docs/native-execution-limits.md).
Missing or malformed settings fail visibly; the extension does not retry with
defaults. This requires a native executable supporting `--limits` and `profile`.
The extension's existing 30-second command timeout and 32-MiB output bound still
apply independently of runtime budgets. Profiling reports retained evidence,
including partial traces on failure; it does not measure time or memory.
Python mode reports that profiling requires the native engine and does not switch
engines automatically.

[Native validation](../docs/native-validation.md) reports each gate separately;
formatting failures do not prevent scenario execution.
Passing validation can still report evidence gaps: scenarios without `THEN`
expectations, expectations without recorded results, or declarations with no
recorded calls. These produce a warning notification and details in the output.
Native hover shows resolved behavior contracts, binding and field types, and
type declarations. Go-to-definition follows behavior/request calls, variable
bindings, named type references, and declared record fields, including imported
definitions. Select the root of a field path to reach its binding, or a field
name to reach its declaration. Aliases, copied locals, return contracts, and
collection variables retain their declared type origins; identical record
shapes do not imply the same declaration. Inferred mixed lists without a unique
field origin fall back to the binding. Invalid source has no semantic
navigation results. Expanded table
scenarios can show several contexts, with an explicit limit of 64.

Native Outline and Go to Symbol in Editor list local types, record fields,
behaviors, requests, backgrounds, scenarios, and example tables. They follow
unsaved edits and also work in untitled documents. Missing imports and type or
expression errors do not hide the outline; invalid indentation does. Outline
entries describe source structure and do not imply that a rule or test passed.

Native type errors report expected and actual GWT types. Optional-record errors
name the path that needs a presence guard. Shared-argument errors offer a copied
argument only when its type is compatible, and explain that a copy cannot update
the original. These hints do not apply edits automatically.

Native formatting also supports untitled GWT buffers and does not load imports
or resolve DTOs. See the [native formatting rules and limits](../docs/native-formatting.md).

Native completion suggests declared behaviors, request names, and types from
the current import closure, including unsaved imported edits. Behavior suggestions
include parameter tab stops and declared contracts; `LET` suggestions require a
declared return contract. Type names complete inside `list` and `optional` too.
These source-based suggestions remain available on incomplete call/type lines;
they do not establish that the resulting program type-checks. Imported load or
layout failures produce no suggestions. Field/local completion and native
debugging remain open. Native mode never starts Python automatically. Python mode
retains its existing features; switch `gwt.engine` and reload to change engines.
The extension requires a trusted workspace to run engines.

The [native editor protocol](../docs/native-editor.md) documents snapshot checks
and their limits. Run `npm run check` and `npm test` in this directory for the
JavaScript checks. For actual extension-host verification with an installed
VS Code and graphical session, run from the repository root:

```sh
python evaluations/native_editor/qualify.py --output /tmp/gwt-editor-native
python evaluations/native_editor/qualify.py --engine python --output /tmp/gwt-editor-python
```

Use fresh output directories. The runner creates a separate profile, extensions
directory, and fixture workspace, and requires a success artifact from the
extension host rather than relying only on the editor launcher's exit code.

## Python mode and local development

Install the Python package from the repo root so VS Code can find `gwt`:

```sh
cd /home/g/code/gwt
python -m pip install -e .
gwt --help
```

Install extension dependencies:

```sh
cd /home/g/code/gwt/vscode-gwt
npm install
```

Open the repo root in VS Code:

```sh
code /home/g/code/gwt
```

Choose **Run GWT VS Code Extension** in the Run and Debug panel, then press
`F5`. In the Extension Development Host window, open
`/home/g/code/gwt/examples/typed_contracts.gwt`.

Expected behavior:

- `.gwt` files use GWT syntax highlighting.
- diagnostics appear for `gwt check` errors.
- hover shows record, behavior, parameter, local, and field information.
- go-to-definition works for behavior calls.
- completion offers known GWT symbols.
- **GWT: Check Current File** saves the active file and runs `gwt check`.
- **GWT: Validate Current File** saves the active file and runs `gwt validate`.
- **GWT: Test Current File** saves the active file and runs `gwt test`.
- **GWT: Run Current File** saves the active file and runs `gwt run --json`.
- **GWT: Format Current File** saves the active file and runs `gwt format`.
- command output streams to the **GWT** output channel.
- pressing `F5` on a `.gwt` file runs it through the GWT debugger adapter.
- line breakpoints pause execution before matching executable GWT lines.
- breakpoint markers are verified against executable GWT lines before launch.
- Continue resumes execution; Step Over advances to the next executable line.
- the Call Stack panel shows active behavior calls while paused.
- the Variables panel shows locals for the selected stack frame and GWT state.

The debugger currently supports line breakpoints, continue, step over, stop,
source-level call stacks, and state/local inspection. It does not yet support
step into/out, conditional breakpoints, watch expressions, or variable editing.

## Settings

When running from this repo, the extension starts the repo-local language server:

```sh
python -m gwtlang lsp
```

It sets `PYTHONPATH` to the repo root for the language server process, so it
does not depend on VS Code inheriting your shell's `gwt` PATH.

To override the command explicitly:

```json
{
  "gwt.server.command": "/absolute/path/to/gwt",
  "gwt.server.args": ["lsp"]
}
```
