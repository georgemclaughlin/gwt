# Profile native execution evidence

Use profiling to see which operations and source locations contribute most to
an execution's evidence budget:

```sh
cargo run -p gwt-core --bin gwt-native -- profile examples/native_weighted_allocation/rules.gwt --request "allocate budget" --input examples/native_weighted_allocation/request.json
```

An installed executable accepts the same `profile FILE.gwt` command. Use
`--scenario NAME` to select an embedded scenario, including an expanded example
row. Omitting the selector requires exactly one entry scenario. `--import-root
DIRECTORY` works as for `run`. Output is JSON; no `--json` flag is needed.

Profiling executes the selected entry once with ordinary execution limits. It
does not raise the evidence budget, retry a refused operation, or change the
rules. Use `inspect` to discover contracts without execution and `validate` to
check formatting and all embedded scenarios.
Use [a limit file](native-execution-limits.md) with trailing `--limits FILE.json`
to profile the same explicit operating budget used by the host or validation.
VS Code's native **GWT: Profile Execution Evidence** command uses the same entry
selection as Run and the configured `gwt.native.limitsFile`, if any. Results
appear in the GWT output channel; see [editor setup](../vscode-gwt/README.md).

## Read the report

Reports have `kind: "gwt.native-profile"` and `schemaVersion: 1`.

| Field | Meaning |
| --- | --- |
| `ok`, `diagnostic` | The ordinary execution's status and diagnostic |
| `file`, `program`, `programIdentity` | Entry, optional title, and frozen source identity; identity is null for single-string library compilation |
| `request`, `scenario` | Selected execution entry |
| `limits` | Supplied execution limits, without modification |
| `effectiveCallDepthLimit` | The smaller of the supplied call-depth limit and the engine's hard limit of 64 |
| `steps` | Ordinary execution's total step counter |
| `evidence` | Totals for recorded events |
| `byOperation` | The same totals grouped by event operation |
| `byLocation` | The same totals grouped by exact source span |

Every usage object contains `events`, `bytes`, `valueBytes`, and `metadataBytes`:

- `bytes` sums the compact UTF-8 JSON encoding of each retained event. It matches
  the runtime's evidence accounting, excluding the surrounding array, commas
  between events, run envelope, and pretty-print whitespace.
- `valueBytes` sums the encoded `value` field, including `null` where present.
  This can contain operation-specific metadata as well as domain values.
- `metadataBytes` is the remainder of each encoded event: field names, operation,
  source span, input dependencies, and other event fields.

Both groupings independently sum to the complete totals. They are separate views
of the same events, so do not add one grouping to the other. Rows sort by
descending bytes. Ties use operation name, or source file/start/end/line/column
for locations. Spans preserve original imported files and expanded-example
locations, using half-open UTF-8 byte offsets and one-based lines and columns.

A source location may produce several kinds of event. A large location total can
reflect many inexpensive repeated evaluations, expensive individual values, or
both; inspect event counts and the actual rule before choosing a change.
Profiling reports global execution steps, not step counts per location.

## Failed executions and bounds

A failed execution still produces a report with `ok: false`, its diagnostic,
and all retained evidence. The CLI exits one. An event refused by the evidence
budget was never recorded and is not counted. Partial totals do not estimate the
budget needed to finish or establish that no partial state changes occurred.
An expected-failure scenario can have `ok: true` when its expectations pass.

Normal source, input, type, and execution limits apply. Profiling additionally
bounds the total encoded input events and the complete report to eight MiB each.
If either bound is exceeded, it returns `profile_limit` without truncated groups;
the CLI emits the diagnostic with `phase: "profile"` and exits one. Compilation
or malformed-input failures can occur before a profile is created.

The extra profiling bound is checked after execution. A Rust caller that selects
an evidence budget above eight MiB can execute successfully and still have the
profile refused. It should choose execution limits appropriate to its workload.
Profiling does not measure wall time, peak memory, peak call depth, or all
resource consumption. The separate [performance exercises](../evaluations/native_performance/)
address runtime measurements.

## Rust hosts and review

After compilation, call
`program.profile_request(name, &input, limits)?` or
`program.profile_scenario(name, limits)?`. Both return an `ExecutionProfile`;
`to_json()?` checks the complete report bound again and produces the same JSON
used by the CLI. Execution failure is represented inside the report; a profiling
failure is returned as an error. Direct serialization is available but bypasses
the additional serialization-time size check on a caller-modified report.

The report omits state, results, printed output, and individual event values.
It still contains source names, identities, and diagnostics, which can include
input details; it is not a redaction mechanism. Preserve ordinary captured cases
when you need to explain decisions or review a behavioral change. A smaller
trace alone does not establish equivalent behavior or improved human understanding.

[Qualification](../evaluations/native_editor/2026-10-16-profiling/README.md)
records independently checked accounting and the tested host/deployment boundaries.
