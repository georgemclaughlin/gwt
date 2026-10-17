# GWT for VS Code

Language support for `.gwt` files using the installed Rust GWT engine. The default
command is `gwt`. Install the developer preview following the
[installation guide](../docs/installation.html); no Python runtime is used.

**GWT: Show Engine Information** reports the executable's identity without saving
or running an open source file. Every operation checks engine identity first.
An old Python command on PATH produces an actionable error, not a fallback.

## Settings

- `gwt.command`: installed command or explicit executable path; default `gwt`.
- `gwt.importRoot`: optional absolute path or workspace-relative import root.
- `gwt.limitsFile`: optional execution budget file for Run, Test, Validate, and Profile.

Explicit previous `gwt.native.*` settings are read as migration inputs when a new
setting is not supplied at the same or a more specific scope. Remove obsolete
`gwt.engine` and `gwt.server.*` settings; the extension explains old Python settings.
There is no engine selector. Changes apply on the next invocation.

## Capabilities

| Action | Behavior |
| --- | --- |
| Check | Diagnostics over unsaved documents and imported sources |
| Hover / Definition | Checked calls, bindings, type references, and record fields |
| Declaration completion | Behavior signatures, requests, and types |
| Outline | Source-backed declarations, including untitled buffers |
| Format | Canonical layout without losing unsaved edits or undo history |
| Validate | Save relevant files; check syntax, types, formatting, and scenarios |
| Test | Execute embedded scenarios |
| Run | Execute a sole scenario or select a request/scenario and JSON input |
| Profile Execution Evidence | Execute and report evidence bytes, steps, and diagnostics |

The output channel preserves exact numeric text. Import roots and source bounds
apply to editor snapshots. Stale results are discarded after edits; missing or
incorrect executables produce visible diagnostics. Untrusted workspaces do not
execute a configured tool.

The previous Python debugger and language-server integration are retired.
Stepping/debugging and broader completion are not current capabilities. See
[editor protocol details](../docs/native-editor.md) for the supported scope.

## Develop and check

```sh
npm ci
npm run check
npm test
```

From the repository root, an installed VS Code can run the isolated extension-host
qualification documented in the [contributor guide](../docs/contributing.md).
