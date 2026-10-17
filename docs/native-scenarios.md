# Native regression scenarios from verified cases

`scenario-from-case` turns a saved request observation into a runnable GWT
scenario. It first replays the complete case against its frozen source, input,
settings, and engine fingerprint. It refuses a mismatch rather than converting
an unverified observation into a test expectation.

The generated expectations reproduce an observation. Review them against the
intended domain policy before adopting them as acceptance criteria.
Successful requests and supported expected failures are eligible. Invalid host
inputs and resource/engine failures remain available for exact case replay.

## Generate and run

From the repository root, choose an output directory that does not exist:

```sh
cargo run --locked -p gwt-core --bin gwt -- capture \
  examples/native_delivery/rules.gwt --request 'quote delivery' \
  --input examples/native_delivery/input.json > /tmp/gwt-delivery.case.json
cargo run --locked -p gwt-core --bin gwt -- scenario-from-case \
  /tmp/gwt-delivery.case.json --name 'recorded delivery quote' \
  --output /tmp/gwt-delivery-regression > /tmp/gwt-delivery-generation.json
cargo run --locked -p gwt-core --bin gwt -- test \
  /tmp/gwt-delivery-regression/captured_scenario_1.gwt \
  --import-root /tmp/gwt-delivery-regression
```

The new directory contains the exact original source modules and a generated
entry module that imports them. Original backgrounds and scenarios are excluded
by declaration-import semantics, so the generated entry runs one independent
scenario. A name collision changes the entry filename; use `source.entry` in the
JSON response to discover the actual path.

The scenario initializes the original inputs, invokes `REQUEST quote delivery`,
and asserts that the returned quote equals a separately initialized expected
quote with status `"standard"` and fee `9`. Changing the frozen rule to charge
eight makes that scenario fail. Original source files outside the generated
directory are never consulted during its execution.

`--name` is optional and defaults to `recorded request outcome`. Names must be
nonempty, at most 256 UTF-8 bytes, and contain no control characters, comment
marker, or surrounding whitespace. Without `--output`, the command returns the
complete generated artifact as JSON and writes no files. With `--output`, the
destination must be new; existing directories and files are never replaced.
Validation happens before creating it. An I/O error can leave partial files in
the new directory and exits nonzero with that location; it does not claim a
completed export. The exporter is not a concurrent-filesystem sandbox.

## Contracts, expectations, and provenance

Inputs are normalized from the captured input, not copied from post-execution
state. This matters when the request mutates and returns its input inventory.
Assertions compare every declared output structurally against its observed
value, and `THEN prints [...]` checks the complete serialized print sequence,
including an empty sequence. Exact integers and decimals, text escaping, typed empty lists, text
unions, nested records, and absent/present optional values retain their types.

The generator reuses original request type names where possible. Additional
record types and helper values preserve contracts that inferred literals alone
cannot express, such as an empty list or an absent optional root. It uses existing
GWT value syntax plus the native printed-output assertion; it does not add casts
or host expressions. JSON nulls inside a print expectation describe serialized
output, not ordinary expression values. Generated
names avoid collisions with original declarations and request bindings.

The library function `scenario_from_case` returns an immutable
`GeneratedScenario`; `source_bundle()` exposes its complete source snapshot.
Generation performs no filesystem I/O. Before returning, it compiles the new
bundle, executes its one scenario, and independently checks that the resulting
request outputs and captured print sequence equal the verified observation.

The `gwt.native-generated-scenario` JSON envelope, schema version 3, records:

- the scenario name and complete generated source bundle;
- the captured program identity, engine identity, and case integrity digest;
- `expectationBasis: "verified_observation_not_approval"`;
- `assertionScope: "declared_outputs_and_printed_sequence"` on success, or
  `"failure_code_inputs_and_printed_sequence"` for a supported failure;
- `capturedFailure` with the original diagnostic on a failed observation;
- explicit default native limits used to validate the generated scenario.

The case integrity digest is an accidental-change identifier, not a signature
or proof of approval. The generated bundle has a new program identity because
it includes the scenario module. Its extra setup and assertions use default
native execution limits; it does not claim to reproduce the captured step count
or evidence budget. Preserve the original case for exact replay.

Schema 1 artifacts asserted only declared outputs; schema 2 added printed-output
expectations. Their source remains runnable. Generation now emits schema 3 to
describe both successful and supported failed observations explicitly.
Successful requests without declared outputs are supported: their scenario checks
successful completion and the print sequence, even when that sequence is empty.

## Generate an expected-failure scenario

A verified `assertion_failed`, `division_by_zero`, or `nonterminating_decimal`
request can become a scenario with `THEN fails with "code"` immediately after
its request action. It then checks every request input against its observed
post-failure value and checks the complete print sequence. This catches mutations
that happened before rejection. Request-local values and outputs that were never
returned are not exposed as scenario bindings.

The generator validates the original input contracts, compiles and runs the new
scenario, and checks the complete observed failure diagnostic against the frozen
observation before returning it. The generated source asserts the failure code,
input state, and print sequence. It does not assert the diagnostic message or
source position in future revisions; `capturedFailure` preserves those original
details as provenance. A different rejection at another location can pass if its
code and observed consequences are the same. Review the domain intent explicitly.

For a concrete failed request, use the stock-rejection example and a fresh output
directory:

```sh
cargo run --locked -p gwt-core --bin gwt -- capture \
  examples/native_expected_failures/rules.gwt --request 'reserve stock' \
  --input examples/native_expected_failures/input.json > /tmp/gwt-rejection.case.json
cargo run --locked -p gwt-core --bin gwt -- scenario-from-case \
  /tmp/gwt-rejection.case.json --name 'insufficient stock stays rejected' \
  --output /tmp/gwt-rejection-regression
cargo run --locked -p gwt-core --bin gwt -- test \
  /tmp/gwt-rejection-regression/captured_scenario_1.gwt \
  --import-root /tmp/gwt-rejection-regression
```

The request failed, but its generated scenario passes by verifying that failure,
unchanged stock, and the `"checking stock"` message. Removing the stock guard or
mutating stock before the guard makes the generated scenario fail.

## Limits and remaining work

Generation refuses failure codes outside the supported expectation model with
`scenario_failure_unsupported`. This includes invalid host inputs, resource limits,
collection safety failures, and internal errors. Source scenarios require checked
typed setup and run under default validation budgets; they are not substitutes
for replay of boundary errors or exact resource observations. Every failed case
remains available for ordinary replay and revision comparison. The separate
[captured-case regression gate](native-regressions.md) can require those
observations to stay unchanged under their frozen input and limits.

Generated assertions cover declared outputs on success, or the failure code and
post-failure input state on expected failure, plus the complete print sequence.
They do not lock internal request locals, evidence paths, or resource usage. Use case/corpus
comparison when those differences matter. A test generated from an incorrect
observation will preserve that incorrect output until a reviewer corrects the
expectation from an independent policy requirement.

Generated source has a one-MiB module limit, and the complete bundle must still
fit the ordinary source/module/import limits. Binding, type, expression,
execution, and evidence limits also apply. An unsupported or oversized artifact
fails explicitly; no empty or partly asserted scenario is returned as success.

`tests/scenario_generation.rs` covers typed round trips, mutable inputs, output
regressions, forged observations, incompatible engines, naming collisions,
limits, and CLI export. `tests/print_expectations.rs` adds mixed serialized values,
empty/output-free requests, print regressions, bounds, source mapping, and replay.
All 336 independent refund revision probes retain their
expected changed/preserved classification when executed as generated scenarios.
`tests/failure_expectations.rs` covers 25 independent stock boundaries, partial-state
regressions, scoped errors, unsupported failures, budgets, source mapping, and
generated failure replay/comparison. These are engineering checks; human approval,
engine migration, and boundary/resource corpus testing remain separate workflows. Existing scenarios can
now be [captured and compared directly](native-cases.md#capture-and-compare-a-scenario),
including failures and printed output. `scenario-from-case` accepts request
cases only; a scenario case already contains its executable source. [Saved review
decisions](native-review-decisions.md) are available for native corpus reports.
