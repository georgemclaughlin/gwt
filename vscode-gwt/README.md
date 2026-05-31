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

Open the extension folder in VS Code:

```sh
code /home/g/code/gwt/vscode-gwt
```

Press `F5` to launch an Extension Development Host. In that new VS Code window,
open `/home/g/code/gwt/examples/typed_contracts.gwt`.

Expected behavior:

- `.gwt` files use GWT syntax highlighting.
- diagnostics appear for `gwt check` errors.
- hover shows DTO, behavior, parameter, local, and field information.
- go-to-definition works for behavior calls.
- completion offers known GWT symbols.

## Settings

By default the extension starts:

```sh
gwt lsp
```

If `gwt` is not on VS Code's PATH, set the command explicitly:

```json
{
  "gwt.server.command": "/absolute/path/to/gwt",
  "gwt.server.args": ["lsp"]
}
```
