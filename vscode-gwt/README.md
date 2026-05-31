# GWT VS Code Extension

This extension registers `.gwt` files, adds syntax highlighting, and starts the
GWT language server with `gwt lsp`.

## Local Development

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
- hover shows DTO, behavior, parameter, local, and field information.
- go-to-definition works for behavior calls.
- completion offers known GWT symbols.
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
