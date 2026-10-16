# GWT native foundation

Start with the [native language draft](../../docs/spec/native-draft.md) and the
[delivery review walkthrough](../../docs/native-review-walkthrough.md).

Use `gwt-native version --json` or the Rust `version_info()` API to identify the
package, experimental language profile, and engine fingerprint. The language
release version remains null. See the [support and transition contract](../../docs/native-language-transition.md)
for the distinction between package versions, language releases, and saved cases.

This experimental Rust crate runs typed requests, behaviors, decisions, state
changes, collection workflows, and embedded scenarios directly from `.gwt` source. It implements a
documented language subset toward the [project goal](../../docs/project-goal.md).
The Python package and CLI remain the complete implemented v0.2 toolchain.

Start with [the native execution model](../../docs/native-execution-model.md)
for requests, state, decisions, and failures, and the
[native grammar](../../docs/native-grammar.md) for source forms. See
[native semantics](../../docs/native-semantics.md) for detailed choices and limits,
and [the goal ledger](../../docs/project-goal-progress.md) for the full scope and
remaining work.

## Package and embed

The crate has a self-contained [Cargo package guide](PACKAGE.md) and a runnable
[`embed` example](examples/embed.rs). [Host integration guidance](../../docs/native-embedding.md)
covers package verification, exact JSON, thread sharing, and dependency/build
identity. The package remains unpublished; no registry release is implied.

## Run a program

From the repository root, with Rust 1.85 or newer:

```sh
cargo run --locked -p gwt-core --bin gwt-native -- check examples/refund_review/stage3.gwt
cargo run --locked -p gwt-core --bin gwt-native -- test examples/refund_review/stage3.gwt
cargo run --locked -p gwt-core --bin gwt-native -- run \
  crates/gwt-core/tests/fixtures/invoice.gwt \
  --request 'price invoice' --input crates/gwt-core/tests/fixtures/invoice-input.json
```

The invoice result is `{"decision":{"status":"priced","total":"47.88"}}`.
Request runs use an experimental `gwt.native-run` envelope containing state,
declared outputs, diagnostics, and source-located call/branch/write evidence.
Failed executions have no successful result. The CLI exits nonzero on a failed
check, request, scenario, or an empty test suite.

The library exposes `compile_file`, `load_bundle`, `compile_bundle`, reusable
`CompiledProgram::run_request`, and `CompiledProgram::test_scenarios`.
`compile_program` remains a single-source helper without imports or a source
identity. The compiler checks included bodies before execution. The runtime
performs no filesystem or network I/O.

Program commands freeze the reachable `USE` dependencies and report their
exact `programIdentity`. Source spans use portable paths within that snapshot.
Imports bring in declarations; imported scenarios are excluded and should be
checked/tested as their own entry programs. Imports stay below the entry file's
parent by default. For sibling directories, append `--import-root DIRECTORY`
to the command; paths below that root cannot contain symlinks. See the
[source identity rules](../../docs/native-semantics.md#imports-and-exact-source-identity)
for limits and the fingerprint encoding.

The [stock-reservation example](../../examples/native_reservation/README.md)
adds ordered iteration, first-match search, mutable inventory items, missing
handling, and exact totals.

The [delivery-quote example](../../examples/native_delivery/README.md) shows
shared background setup and ten scenario-table rows, with evidence pointing
to the original table cells and scenario source.

The [return-value pricing example](../../examples/native_return_values/README.md)
uses named calculations, explicit return contracts, and `LET` call results.
Return steps remain visible in source-backed review, including early exits from
branches and collections.
The [required inventory lookup](../../docs/native-failure-exits.md) returns a
matched snapshot or explicitly fails, without an unreachable fallback return.

The [value-argument example](../../examples/native_value_arguments/README.md)
passes literals and grouped calculations directly to behaviors. Bare paths share
state; parenthesized paths explicitly copy it. Recorded arguments distinguish
local value mutations from changes to caller state.

The [receipt example](../../examples/native_print_expectations/README.md) asserts
exact captured JSON output with `THEN prints [...]`. Generated regression
scenarios now preserve the complete print sequence, including empty output and
requests without declared outputs.

The [stock-rejection example](../../examples/native_expected_failures/README.md)
attaches `THEN fails with "assertion_failed"` to one action and then checks state
and output. Supported failed requests can now generate runnable regression
scenarios. Invalid host inputs and resource/engine failures remain replay-only.

## Capture and compare decisions

The native CLI supports `capture`, `replay`, single-case `compare`, and
`corpus`/`review` for an offline review page.
Cases freeze source, input, limits, engine fingerprint, and the full observed
execution. Replay verifies the observation; comparison refuses to execute the
candidate when the baseline does not reproduce. See
[native cases](../../docs/native-cases.md) for runnable commands, report fields,
exit statuses, and resource limits. [Native review](../../docs/native-review.md)
adds corpus reconciliation, exact source excerpts, decision trails, outcome
differences, and browser review. [Scenario generation](../../docs/native-scenarios.md)
turns verified successful cases into frozen runnable regression scenarios with
assertions over their declared outputs. [Saved reviewer decisions](../../docs/native-review-decisions.md)
can be restored in the offline page and assessed against a fresh report.

`run FILE --scenario NAME` executes one checked scenario; `capture FILE --scenario
NAME` freezes its full observation, including failures, printed output, and
expanded example rows. Scenario and request cases share replay, comparison,
corpus review, and saved decisions. Scenario comparison uses each revision's own
setup and assertions; request cases keep supplied host input fixed. See
[scenario capture](../../docs/native-cases.md#capture-and-compare-a-scenario).

## Propose an engine transition

Native `migrate CASE.json --previous-engine EXECUTABLE` verifies the original case
with the explicitly selected previous executable, then proposes a case for the
current engine using identical source, input, target, and limits. It preserves
the original, records differences and provenance, and never promotes or approves
the candidate. See [engine migration](../../docs/native-migration.md).

Migration review supports `migrate --html NEW_REVIEW.html --decision-template
NEW_FILE.json`, `assess-migration --decision FILE.json`, and `export-migration
--decision FILE.json --output NEW_CASE.json`, each with the original case and
explicit `--previous-engine`. Assessment and export freshly verify both engines;
export requires a matching acceptance and refuses existing output files. See the
[review workflow](../../docs/native-migration.md#human-review-decisions-and-case-export).
For mixed previous/current engines, [whole-corpus migration](../../docs/native-corpus-migration.md)
adds `migrate-corpus`, `assess-corpus-migration`, and `export-corpus-migration`.
Every entry must have verified evidence and a matching acceptance before the
separate new corpus can be exported.

## Inspect the expression boundary

```sh
cargo run --locked -p gwt-core --bin gwt-native -- expression \
  'facts.days <= 30 or (facts.member and facts.days <= 45)' \
  crates/gwt-core/tests/fixtures/refund-types.json \
  crates/gwt-core/tests/fixtures/refund-input.json
```

The JSON response contains the result, factual expression events, source
spans, operand-event references, and explicitly skipped operands. Failures have
diagnostics and a nonzero CLI exit status. The `gwt.native-expression` envelope
is experimental and separate from the existing GWT execution payload.

The expression-only command accepts a JSON type contract as a development
interface. Program commands derive their contracts from GWT declarations.

The library exposes `compile_expression`, `compile_expression_at`, and a
reusable `CompiledExpression::evaluate`. Evaluation performs no filesystem or
network operations. Runtime values and typed expression constructors are
private so callers cannot bypass checking.

## Verify

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
```

The checked-in fixture expectations are independently specified. The Python
interpreter is not used as an oracle for new semantic choices.

[Development performance measurements](../../evaluations/native_performance/README.md)
separate in-memory compilation, repeated request execution with full evidence,
and response serialization. They include reproducible workloads and exact
behavior comparisons; they do not establish production throughput or human benefit.

[Execution evidence profiling](../../docs/native-profiling.md) runs a selected
request or scenario and reports exact evidence bytes by operation and source
location. It retains partial accounting and diagnostics for failed executions.
The CLI `profile` command and Rust `profile_request` / `profile_scenario` APIs
use ordinary execution limits; these reports do not measure time or memory.

See [the feature matrix](../../docs/native-conformance.md) for proven coverage
and remaining work. Remaining collection forms,
calls embedded in expressions and boundary/resource scenario authoring remain unimplemented.
