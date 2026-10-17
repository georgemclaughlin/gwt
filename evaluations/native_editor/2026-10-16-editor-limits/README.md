# Editor operating budgets and evidence profiling

This checkpoint connects the existing native limit-file and profiling commands
to VS Code. `gwt.native.limitsFile` is a resource-scoped setting read for each
explicit execution. **GWT: Profile Execution Evidence** shares Run's entry/target
selection. The [editor guide](../../../vscode-gwt/README.md) documents saving,
path resolution, error handling, and independent extension process bounds.

## Verification

- `editor-native-verified/extension-host.json`: 38 checks pass in installed VS Code
  1.137.0 with an isolated profile and fixture workspace. The final qualification
  records seven extension/harness file hashes and verifies they remain unchanged
  during the run, along with the frozen native executable hash. Successful
  launcher exit alone is not accepted as evidence.
- Three new native-host groups verify exact profile output against the CLI,
  dirty limit-buffer saving, a relative path containing spaces, matching
  Run/Profile/Test/Validate failures under zero steps, static checking with that
  budget, absolute paths, changing settings without reload, malformed/missing
  files without default fallback, and restoring defaults. Existing diagnostics,
  navigation, outline, formatting, validation, and imported-buffer checks remain.
- `editor-python/extension-host.json`: two checks pass in the same installed
  editor. Default Python diagnostics, correction, and hover remain available;
  profiling returns an explicit native-only failure and does not switch engines.
- Ten JavaScript tests pass, including four command-adapter tests and a new
  process-diagnostic test. They exercise request/input selection, exact raw JSON
  preservation, workspace-relative budgets independent of import roots,
  cancelled saves/selection preventing execution, outside-workspace paths,
  configuration clearing, and malformed setting types without disabling static
  checks. These use deterministic dialogs/process responses; they do not claim
  a manual picker interaction. Actual scenario/CLI agreement is tested separately
  in the installed extension host.
- JavaScript syntax checks and `git diff --check` pass. The retained native
  executable and all 56 engine source/build inputs still match the preceding
  CLI-limit qualification. No Rust runtime or Python implementation changed;
  their preceding suite results are not presented as new runs here.

`editor-native/` retains the initial successful run, before the additional
defensive setting-type check. The attempted `editor-native-final/` run then failed an existing navigation assertion when a definition response was empty; its logs are retained. That positive assertion now uses the harness's existing bounded retry while requiring an unchanged document version and the same exact target. The verified native run checks the final implementation and harness. A logged SIGPIPE does not by itself establish the cause of the empty response.
`command-tests.log` records an intermediate adapter check; the final verification
records all ten passing JavaScript tests. No generated review HTML was browsed,
and no participant comprehension or external-pilot evidence was collected.

## Behavioral details and limits

Static diagnostics, navigation, outline, and formatting ignore execution budget
settings. Execution saves dirty open GWT documents, then the selected limit
file's dirty file-backed buffer. Cancelling that save prevents execution; it
does not undo GWT saves already completed. Unrelated JSON buffers are not saved.
The output channel identifies the configured file or native defaults and retains
the CLI's original stdout, including integers outside JavaScript's exact range.

Limit-file errors arrive on stderr. The process adapter now reports a bounded
command-failure diagnostic for stderr-only exit-one responses instead of
mislabeling them as malformed JSON. Structured execution failures remain
structured failures. Missing settings or unsupported executable flags never
trigger an automatic retry with different budgets or another engine.

The existing 30-second explicit-command timeout and 32-MiB process-output bound
remain distinct from native execution budgets. Profiling executes the selected
entry once and reports retained evidence and steps; it does not measure wall time
or memory. Native completion/debugging, larger-workload efficiency, broader
deployment qualification, and measured human benefit remain open.
