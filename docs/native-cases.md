# Native execution cases and revision comparison

Status: experimental native artifacts, separate from the Python Execution Case
and workbench schemas. This is one part of the
[project goal](project-goal.md); [native corpus review and source-backed explanations](native-review.md) now
connect these cases to an offline review page. Human-benefit evidence remains
unproven.

## Capture and replay a decision

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt-native -- capture \
  crates/gwt-core/tests/fixtures/invoice.gwt \
  --request 'price invoice' \
  --input crates/gwt-core/tests/fixtures/invoice-input.json \
  > /tmp/gwt-native-invoice.case.json
cargo run --locked -p gwt-core --bin gwt-native -- replay \
  /tmp/gwt-native-invoice.case.json
cargo run --locked -p gwt-core --bin gwt-native -- compare \
  /tmp/gwt-native-invoice.case.json \
  --candidate crates/gwt-core/tests/fixtures/invoice.gwt
```

The captured total is the exact decimal string `"47.88"`. Replaying reports
`verified: true`; comparing the identical source reports `status: "compared"`
and false for all change flags. A candidate can be a different source revision.
`capture` and `compare` accept a trailing `--import-root DIRECTORY` for layouts
with sibling imports. Replay only reads the case file: it uses the frozen
source closure and needs neither the original paths nor the original input file.

A case records an observation. It does not establish that the result was the
intended domain outcome. Independent expected results and human review remain
necessary, even when replay verifies every byte of normalized execution data.
Capture accepts a trailing [`--limits FILE.json`](native-execution-limits.md)
to record an explicit budget at or below the native defaults. Replay and review
always use the frozen budget; they do not accept a limit override.

[`test-cases`](native-regressions.md) applies an explicit preservation scope to a
corpus and exits nonzero for changes or unverified baselines. It includes boundary
and resource failures without treating those failures as passing domain scenarios.

## Capture and compare a scenario

```sh
cargo run --locked -p gwt-core --bin gwt-native -- run \
  examples/native_delivery/rules.gwt \
  --scenario 'weight and membership determine the quote example 3'
cargo run --locked -p gwt-core --bin gwt-native -- capture \
  examples/native_delivery/rules.gwt \
  --scenario 'weight and membership determine the quote example 3' \
  > /tmp/gwt-native-delivery-scenario.case.json
cargo run --locked -p gwt-core --bin gwt-native -- replay \
  /tmp/gwt-native-delivery-scenario.case.json
cargo run --locked -p gwt-core --bin gwt-native -- compare \
  /tmp/gwt-native-delivery-scenario.case.json \
  --candidate examples/native_delivery/rules.gwt
```

`check` lists the exact compiled names, including expanded example-row names.
`Main` selects an implicit scenario. Capture requires an existing scenario and
executes only that scenario with its background in fresh state. Other scenarios
are still checked during compilation. Failures, printed output, partial state,
and resource diagnostics are captured faithfully; a failed scenario can replay
successfully without becoming a passing test. `run --scenario` exits nonzero for
an execution failure, whereas `capture --scenario` exits zero when it records it.
Scenario selection cannot be combined with `--request` or `--input`.

For an entry with exactly one scenario, `run ENTRY.gwt` and `capture ENTRY.gwt`
select it automatically and produce the same execution/case as explicit
selection. [Readable request entries](native-request-entries.md) use this path
with explicit imports and public calls. Zero or multiple scenarios are refused
before execution; captured cases still record the selected scenario's exact name.

**Scenario comparison runs each revision's own setup and assertions.** It selects
the exact same compiled name in the candidate, including the row ordinal for an
example table. Renaming or removing it produces `unknown_scenario`; reordering
example rows can select different candidate data. The full frozen baseline and
candidate sources remain available for review. Use request cases when the
supplied host input must stay fixed across revisions.

A successful scenario result is its complete scenario state, including setup
and helper bindings. A failed scenario has no successful result, while retaining
partial state and output. This is distinct from a request's declared outputs.
Both case types can share one corpus, review page, and saved-decision file.

## What is frozen

Request cases use `gwt.native-case` schema version 1. Their `record` contains:

- `engine`: the experimental execution profile and engine source fingerprint;
- `source`: the entry path and complete reachable module texts;
- `programIdentity`: the source-closure identity described in
  [native semantics](native-semantics.md#imports-and-exact-source-identity);
- `request`, `input`, and `limits`: the exact named request, supplied JSON
  values, and explicit execution settings;
- `observed`: the full native run, including success or failure, result, state,
  captured output, diagnostic, step count, and evidence events.

Scenario cases use the same kind with schema version 2. Their record replaces
`request` with `scenario`, the exact compiled scenario name, and uses `input: null`.
All other fields and integrity rules are the same. Version 1 requires only a
request target; version 2 requires only a scenario target and null input. Mixed
or missing targets are rejected. Request capture continues emitting version 1;
supporting its shape does not waive engine-fingerprint checks on older artifacts.

Explicitly migrated cases use schema version 3 with one request or scenario
target and mandatory parent/previous-engine provenance. Ordinary capture still
emits schemas 1/2. See [engine migration](native-migration.md) for the complete
proposal, verification process, and trust boundary.

The top-level `integrity` is an accidental-change check. It is not a signature,
proof of origin, or proof that the observation happened. It hashes the parsed
artifact with the `integrity` property removed, using SHA-256 with the UTF-8
prefix `gwt-native-case-sha256-v1` followed by a zero byte. The remaining value
is compact JSON with object keys recursively sorted by Unicode scalar order,
array order preserved, UTF-8 strings without ASCII-only escaping, and no extra
whitespace. Numeric tokens retain the native JSON parser's arbitrary-precision
representation; this is not a general cross-language numeric canonicalization
standard. The lowercase digest has the `sha256:` prefix. Property ordering and
insignificant whitespace in a case file do not affect this check.

The engine profile is `gwt-native-case-engine-v1`. At build time, a separate
`gwt-native-engine-source-v2` SHA-256 fingerprint covers all package-local files
under `src/` (including embedded review assets), `build.rs`, the actual package
manifest, and the retained `engine-dependencies.lock` baseline. File paths use
Rust's component-wise ordering (for example, `src/review/` sorts before
`src/review.rs`) and `/` separators. Relative paths and exact contents are encoded
as pairs of UTF-8 path / raw-content fields, each prefixed by an unsigned 64-bit
big-endian byte length, following the algorithm name and a zero byte.

The earlier v1 source fingerprint included repository ancestor manifests and
lockfile and was not package-portable. Existing cases keep their original digest;
the engine profile and case schemas remain unchanged. Cargo normalizes the
packaged manifest, so workspace and packaged builds deliberately have different
source fingerprints. See [packaging and host identity](native-embedding.md#build-identity-and-dependency-qualification).

The digest changes conservatively even for source comments or review-only edits.
It identifies package source/build inputs and the declared dependency baseline,
not the compiled binary, compiler, target, flags, or a host application's actual
resolved dependency/feature graph. It is not a formal language version or an
authenticity signature. Actual replay still checks the complete execution.
Engine mismatch requires the original engine build or an explicit
[migration proposal](native-migration.md); ordinary replay never silently
reinterprets old cases.

## Verification and comparison rules

Loading checks the artifact version, required fields, allowed execution limits,
input shape, and integrity digest. Replay then verifies the engine fingerprint,
compiles the supplied source closure, checks its claimed program identity,
runs the recorded request or scenario under the recorded limits, and compares the entire
resulting run with `observed`.

The `gwt.native-replay` report has `verified`, `actual`, and JSON-pointer
`differences`. A reproduced failure has `verified: true` and `actual.ok: false`.
A result, state, diagnostic, step-count, or evidence mismatch has
`verified: false`. Artifact, engine, or source errors produce explicit diagnostic
responses instead of a successful verification report. A valid checksum alone
never marks an observation verified.

The `gwt.native-comparison` report first replays the baseline. If it does not
match, the status is `baseline_mismatch`; `candidate` and `changes` are null,
and the candidate is not executed. With a verified baseline, the status
is `compared`. Request cases run with the same raw input and limits; scenario
cases run the exact scenario name under the same limits. Its
complete execution and source identity remain in the report, including failures.
Change flags distinguish:

- `source`: exact source-closure identity changed;
- `outcome`: success, declared results, captured output, or diagnostic
  code/message changed;
- `state`: initialized execution state changed;
- `evidence`: events, diagnostic details, or consumed steps changed.

Outcome differences exclude diagnostic source locations so moving a failing
line does not itself claim a different outcome. Evidence differences include
source locations; a line shift can change evidence without changing a decision.
These flags do not claim causal proof, correctness, or that a change is safe.
`outcomeDifferences` identifies changed fields with JSON pointers. Difference
values explicitly distinguish a missing field from a present JSON null.

CLI exit status reports whether the operation completed:

| Command | Exit zero | Exit nonzero |
| --- | --- | --- |
| `capture` | A case was produced, including a recorded execution failure | Compilation, input decoding, capture, or resource failure |
| `replay` | The complete observation was reproduced, including a recorded failure | Invalid/incompatible case or observation mismatch |
| `compare` | Baseline verified and candidate execution was compared, including candidate failure or changed outcomes | Invalid/incompatible case, candidate compilation failure, or baseline mismatch |

Automation must inspect the report's execution and change fields for its own
acceptance policy. A successful comparison command is not approval of a change.

## Library and limits

The public entry points are `capture_request`, `capture_scenario`, `ExecutionCase::from_json`,
`replay_case`, and `compare_case`. Cases are immutable; accessors expose borrowed
input, observed execution, source, and identity. Capture and comparison require
bundle-backed programs. `compile_program` alone cannot provide a source snapshot.
Capture executes once and stores that observation; replay is a separate action.

`ExecutionCase::request()` now returns `Option<&str>` in this experimental API;
`scenario()` returns the selected scenario name for scenario cases. Exactly one
is present in a validated case. `input()` returns JSON null for a scenario.
`CompiledProgram::run_scenario(name, limits)` executes one checked scenario and
returns a normal `ProgramExecution`, including an `unknown_scenario` diagnostic
when the name does not exist. It uses the same executor as `test_scenarios`.

Captured settings may reduce but cannot exceed the default native profile:
100,000 steps, one MiB of evidence, one MiB of text, and 64 execution nesting
levels. Zero limits are permitted and can capture the corresponding execution
failure. Raw inputs retain the native one-MiB/depth/value-count limits. Cases
are limited to sixteen MiB, 96 JSON value levels, and 500,000 JSON values. The
JSON parser also applies its recursion limit. Difference lists retain at most
128 entries and explicitly indicate truncation; the verification verdict always
compares the complete executions. These are deterministic resource guards, not
a memory or hostile-filesystem sandbox.

Captured artifacts contain full input, state, source, and evidence values.
No redaction or omitted-value replay policy has been implemented. CLI artifact
output goes to stdout so callers choose storage; the library performs no I/O.

## Evidence and remaining work

`crates/gwt-core/tests/cases.rs` checks complete round trips, import snapshots
with original files removed, known invoice totals, recorded failures and budgets,
corruption, forged observations with recomputed hashes, engine/source mismatch,
missing/null distinction, bounded differences, CLI statuses, and source-only
changes. All 336 independently specified refund probes also pass through
capture, serialization, replay, and revision comparison, with their expected
changed/preserved classification and candidate outcome checked independently.

Native [corpus review](native-review.md) reconciles every entry and presents
source-backed explanations in an offline page. Successful cases and supported
behavior failures can produce [verified regression scenarios](native-scenarios.md)
with output, input-state, failure, and print expectations appropriate to the case.
`tests/scenario_cases.rs` covers selected
scenarios, failures/prints/budgets, imported source, example rows, unambiguous
versioned targets, forged baselines, mixed corpora, and CLI behavior. Python
case/corpus schema compatibility remains unfinished.
[Whole-corpus migration](native-corpus-migration.md) reconciles mixed engines and
exports a separate corpus only after every verified entry is accepted.
[Engine migration review](native-migration.md) provides previous-engine replay,
offline comparison, saved decisions, fresh assessment, and accepted case export.
[Saved reviewer
decisions](native-review-decisions.md) now bind case choices to an exact report. Existing Python workbench validation
does not establish native capabilities.
