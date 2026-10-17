# Choose and verify native execution limits

Execution budgets are part of a host's operating contract. Keep a complete JSON
limit file beside the rules or deployment configuration and use it consistently
for validation, request execution, profiling, and case capture:

```sh
cargo run -p gwt-core --bin gwt -- validate examples/native_weighted_allocation/rules.gwt --limits examples/native_weighted_allocation/limits.json
cargo run -p gwt-core --bin gwt -- profile examples/native_weighted_allocation/rules.gwt --request "allocate budget" --input examples/native_weighted_allocation/request.json --limits examples/native_weighted_allocation/limits.json
```

The example budget is an illustrative operating envelope for the checked inputs,
not a capacity guarantee for all allocation requests. Include representative
host inputs as well as embedded scenarios when evaluating a deployment budget.

## Limit file

The file uses the existing Rust `ProgramLimits` representation. Every field is
required; omitted fields do not inherit defaults. The normal defaults are:

```json
{
  "execution": {
    "steps": 100000,
    "evidenceBytes": 1048576,
    "textBytes": 1048576
  },
  "callDepth": 64
}
```

| Setting | Existing runtime meaning |
| --- | --- |
| `steps` | Shared statement/expression execution counter for one invocation |
| `evidenceBytes` | Maximum sum of compact serialized event bytes; evidence refusal precedes the operation's mutation |
| `textBytes` | UTF-8 byte limit for a concatenation result; not a total-memory limit or a replacement for host-input/source bounds |
| `callDepth` | Combined call/branch nesting allowance, additionally capped by the engine's hard limit of 64 |

Values must be nonnegative integers representable as the platform's `usize`.
Zero is permitted and can exercise immediate budget refusal. Negative numbers,
fractional numbers, booleans, missing/duplicate/unknown fields, invalid JSON or
UTF-8, and files larger than 4,096 bytes are rejected. Limit-file errors produce
stderr and exit one before source loading, execution, or HTML report creation.
The file is read once for that command. Execution does not reopen it.

In VS Code, set `gwt.limitsFile` to this same file. Run,
Profile, Test, and Validate use it, saving a dirty open limit buffer before
execution. See [editor setup](../vscode-gwt/README.md) for path resolution and
command behavior. Static diagnostics do not execute or apply budgets.

Omitting `--limits` preserves the normal defaults. These settings do not change
the grammar, input contracts, exact-number bounds, source/import limits, case
size bounds, or the engine's other hard limits. They do not impose a wall-clock
timeout, cancellation boundary, or total process memory limit.

## Supported commands

For `run`, `profile`, and `capture`, place `--limits FILE.json` after any request
or scenario selector. It can precede or follow the trailing `--import-root
DIRECTORY`. `test FILE.gwt` accepts the same trailing options. `validate` accepts
`--limits` in any order with its other options after the entry path. Duplicate
options and missing values fail; `check` and `inspect` reject execution limits.

- `run` and `profile` exit one when execution fails. Profiling records the chosen
  limits, effective depth ceiling, diagnostic, and partial evidence accounting.
- `test` and `validate` give every scenario a fresh copy of the selected budget.
  A resource failure is a failed scenario, and later scenarios still run.
  Both reports include `limits`; `test` adds this field to its existing envelope.
- `capture` records the exact limits and full observation. It exits zero when it
  successfully captures a failed execution, which does not make that execution
  successful. Inspect the captured observation when enforcing a pass/fail gate.
- `replay`, comparison, and review use the case's frozen limits. They do not
  accept an override that could silently alter the observation being verified.

Successful `validate` establishes only that the scenarios pass under this budget.
Use `capture` and comparison for representative request workloads, and inspect
partial failures before retrying. Previously committed in-memory state can remain
after a later operation exhausts a budget; failure does not imply rollback.

## Higher budgets and retained cases

`run`, `profile`, `test`, and `validate` accept explicitly selected budgets above
the defaults. They do not change or clamp those settings, except for the existing
hard depth ceiling. Higher limits can increase work and retained evidence; the
separate [profiling bounds](native-profiling.md) still apply.

The existing case contract permits only limits at or below the native defaults.
`capture` refuses a higher budget with `case_limits`, before executing the entry.
This restriction also protects replay, comparison, and migration. A high-budget
diagnostic run cannot be promoted silently into an ordinary replayable case.

To investigate a resource regression, capture a representative baseline using
the intended operating limits, compare the proposed source under those same
limits, and use profiles to locate the work that increased. Changing a budget is
a separate operating decision; a passing high-budget rerun does not erase the
original failure or approve the candidate. Use
[`test-cases`](native-regressions.md) to enforce preservation of selected cases,
including both successful operating-budget probes and retained failures.

[Qualification](../evaluations/native_editor/2026-10-16-cli-limits/README.md)
covers CLI/library agreement, malformed settings, retained failures, and a local
allocation regression rehearsal. No new budget-expectation syntax is introduced;
resource failure remains distinct from an expected domain rejection.
