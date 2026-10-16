# Native validation

`gwt-native validate` checks one captured import closure, checks its formatting,
and executes the entry's scenarios. It never rewrites source.

```sh
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- validate examples/native_delivery/rules.gwt
```

The command accepts `--import-root DIRECTORY`, `--limits FILE.json`, `--allow-no-scenarios`, and
`--html NEW_REPORT.html` in any order after the entry path. Duplicate or unknown flags are rejected.
Exit zero means every required gate passed. Source and execution failures return
exit one with a JSON report; invalid command arguments return stderr and no report.
The [limit-file guide](native-execution-limits.md) defines strict settings and
per-scenario budgets. Resource failures remain failed scenarios.

## Gates

The report has kind `gwt.native-validation`, schema version 1, and these phases:

| Phase | Meaning |
| --- | --- |
| `load` | Capture the entry and reachable imports under the selected source root |
| `check` | Compile and check the captured closure using native semantics |
| `format` | Check each captured module with the native layout formatter |
| `scenarios` | Run every entry scenario with fresh state and execution budgets |

Each phase has a `status`, optional `reason`, and optional source-located
`diagnostic`. Status is `passed`, `failed`, `skipped`, or `notExercised`.
Load failure skips subsequent gates; check failure skips formatting and execution.
Once compilation succeeds, formatting failure does not prevent scenario execution,
and one failing scenario does not stop later scenarios.

An entry with zero scenarios reports `scenarios.status: "notExercised"` and fails
validation by default. `--allow-no-scenarios` explicitly permits this for reusable
declarations, while keeping the phase marked `notExercised`. The flag does not
waive load, compile, format, or execution failures. Imported scenarios do not count
as entry scenarios and are not executed; imported source is still format-checked.

`modules` lists each file with `changed: false` for canonical layout, `true` when
formatting is needed, or `null` with a diagnostic when formatting cannot proceed.
`results` lists each executed scenario's name, `ok`, step count, and diagnostic.
It also lists the scenario's declared expectations and their recorded outcomes.
The report releases each execution's state, output, and trace before running the
next scenario. Use `run --scenario NAME` or `test` for full execution evidence.

Successful compilation supplies `programIdentity`, including exact module hashes.
Load/check failure leaves that identity null. `limits` records the per-scenario
budgets; `allowNoScenarios` records the selected policy. A passing report establishes
only the listed checks on this source. It does not measure assertion coverage,
exercise all inputs or behaviors, or establish human comprehension or correctness
of the intended policy.

## What did the scenarios actually check?

Validation includes a factual evidence inventory alongside its pass/fail gates.
This is an additive part of the version 1 report:

- `results[].expectations` lists each scenario/background `THEN` expectation,
  including `AND` continuations. Each item has its original source `span`, a
  `kind` (`condition`, `printedOutput`, or `failure`), an `outcome` (`passed`,
  `failed`, or `notObserved`), and the matching execution `event` ID, or null.
  Event IDs are local to that scenario; use its full run for the recorded event.
- `evidence.scenarioExpectations` totals declared, passed, failed, and
  `notObserved` expectations. Background expectations count separately for each
  scenario, and every expanded example row has its own observations.
- `evidence.scenariosWithoutExpectations` names scenarios with no scenario or
  background expectations. Behavior `REQUIRE`, request postconditions, and
  assertions invoked through `WHEN` remain runtime checks; they do not count as
  scenario `THEN` expectations.
- `evidence.callables` lists all checked behavior/request declarations, including
  imports, with their kind, name, and definition span. `recordedEntries` counts
  entry events across these runs; `scenariosWithEntries` counts distinct scenario
  runs with at least one entry. Nested and repeated calls count. Imported
  scenarios are excluded as usual, so their calls do not contribute observations.

`notObserved` means there is no recorded assertion result. Execution may have
stopped before the expectation, during its expression evaluation, or because
the execution/evidence budget was exhausted. It does not mean the expectation
was necessarily skipped. A recorded call entry likewise does not mean that the
call completed, succeeded, or exercised every branch.

`warnings` summarizes three possible evidence gaps, with stable codes
`scenarios_without_expectations`, `unobserved_expectations`, and
`unobserved_callables`. The detailed locations and counts remain in the
inventory. Warnings do not change the gates or exit status: declarations may
legitimately be reusable helpers, and scenario expectations remain a language
convention rather than a syntax requirement. Load/check failure leaves
`evidence` null; an empty warning list in that case does not mean anything was
exercised. With an explicitly allowed declaration-only entry, the inventory is
available but has no recorded execution observations.

For example, a scenario that only invokes a request can run successfully while
reporting `scenarios_without_expectations`. Adding `THEN total == 25` declares a
specific outcome to check. Even a passed expectation such as `THEN true` does
not establish a useful test: this inventory does not assess oracle quality,
branch/condition coverage, unseen inputs, or the intended business policy.

## Frozen source and embedding

The library exports `validate_file(entry, root, ValidationOptions)` and
`validate_bundle(&SourceBundle, ValidationOptions)`. Both return a typed
`ValidationReport`; options allow host-selected execution limits and an explicit
no-scenario exception. A bundle is validated for normal import closure/path/size
constraints by the compiler before formatting or execution.

File validation loads once. All later gates consume those captured bytes, even
if files subsequently change or disappear. Loading multiple files is not an atomic
filesystem snapshot. Native source/scenario limits and per-execution budgets
apply; there is no additional whole-validation time budget in the library or CLI.

## Readable validation reports

Add `--html` to produce a self-contained report that opens offline:

```sh
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- validate examples/native_delivery/rules.gwt --html /tmp/gwt-delivery-validation.html
```

The destination must be new; an existing file, including a source file, is never
overwritten. Failed validation still produces the HTML report and JSON stdout,
with exit one. A destination or rendering error instead fails the command with
stderr. Source is captured once for both the validation and the HTML; exporting
does not reload files or rerun scenarios.

The page separates gate outcomes from evidence gaps, lets reviewers search and
filter scenarios, and shows each expectation with its recorded outcome. Source
links open the exact captured text, preserving UTF-8/CRLF locations and example
template spans. A declaration inventory shows call entry counts, with a filter
for declarations without entries and pagination for large lists. Missing source
after a loading failure is explicitly unavailable. Type-check failures can still
show captured source. Allowed declaration-only entries remain visibly unexercised.

Download buttons export the original JSON report and the captured source bundle.
Large numeric tokens, string content, and line endings are preserved. Source
and names are displayed as text; embedded JSON escapes markup delimiters. The
page loads no external assets or services, and its content policy blocks network
connections. JavaScript is required for the interactive view. Full execution
traces remain available through `run`/`test`; the HTML summarizes observations
and provides no approval controls or claim of policy correctness.

For embedding, `validate_file_document(entry, root, options)` and
`ValidationDocument::from_bundle(source, options)` construct an immutable
report/source pair. `report()` and `source()` provide shared read access;
`into_report()` returns the JSON-oriented report. `render_validation_html(&document)`
renders that captured document without I/O or execution. A rejected in-memory
bundle beyond the presentation's source bounds is not retained: 256 modules,
one MiB per module, four MiB total, and 4096 bytes per path. Rendering is bounded
to 64 MiB, including escaped JSON, while serialization is in progress. A source
snapshot does not make a multi-file filesystem read atomic, and a saved HTML
file is a presentation of local checks rather than authenticated evidence.

## VS Code

With `gwt.engine` set to `native`, **Validate Current File** saves dirty open GWT
documents, aborts on a failed save, and invokes this command on the active file.
It uses the configured native executable and import root, a thirty-second process
timeout, and the existing 32 MiB output bound. The complete JSON summary appears
in the GWT output channel. Validation uses the strict scenario policy; use the CLI
for the explicit declaration-only exception. Later edits are not covered by the
saved-source report.
Successful validation with evidence warnings shows a warning notification and
prints the gap summaries beside the JSON report, so it is distinguishable from
a run without those gaps.

**Check Current File** remains an unsaved static check. **Format Current File**
edits the buffer with undo support. **Test Current File** retains full scenario
execution output. Python mode continues to use its existing validation command.

## Evidence

`crates/gwt-core/tests/validation.rs` covers the gates, exact source identity,
zero-scenario policy, independent formatting/execution failures, later scenarios
after failure, imported formatting, frozen source, execution budgets, and CLI
exit/argument/write behavior. Formatter coverage includes imports followed by
explicit scenarios. The extension-host test checks saving imported edits,
independent failures, corrected validation, and refusal of an unexercised entry.
`tests/validation_evidence.rs` independently checks all expectation outcomes,
contract/action separation, stopped evaluation, resource failures, backgrounds,
Unicode/CRLF example locations, nested/repeated/imported call observations,
unobserved declarations, and failed compilation. The editor test also removes
and restores an expectation to verify that successful execution and recorded
expectations remain distinguishable.
`tests/validation_document.rs` covers frozen report/source pairing, render-only
access after files change/disappear, escaped source and names, failure/no-scenario
states, source bounds, exact numeric limits, and CLI failure/no-overwrite behavior.
The [report qualification](../evaluations/native_validation/2026-10-16/README.md)
records offline browser interactions and desktop/mobile visual checks.
