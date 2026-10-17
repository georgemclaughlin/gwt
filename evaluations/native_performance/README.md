# Native development measurements

The original harness measures the Rust implementation's workloads. It does not
compare languages, establish production throughput, or measure human benefit.
The first experiment is recorded in [2026-10-16](2026-10-16/README.md).

A separate [Python versus Rust CLI comparison](2026-10-16-python-cli/README.md)
now measures three shared policies with 360 fresh-process invocations. It shows
substantial CLI latency differences, including process/import costs; it does
not establish an equivalent speedup for an embedded or long-running service.

## Reproduce a measurement

From the repository root:

```sh
cargo +1.96.0 build --release --locked -p gwt-core --example profile_requests
target/release/examples/profile_requests 100 7 > /tmp/gwt-profile.json
```

The arguments are operations per batch and number of batches. Each phase has
three untimed warmup operations. The JSON records all per-batch measurements,
engine source identity, exact workload source and inputs, independently written
expected outputs, and full execution hashes. There are nine workloads: delivery,
invoice pricing, stock reservation, and 64 scalar updates with zero, 100, or
4,000 unrelated values. The latter place the unused list either in a separate
binding or alongside the accessed scalar in the same record.

The three timings are deliberately separate:

- **Compile:** `compile_program` from in-memory source, including checking and
  disposal of the compiled program. This excludes file loading, source-bundle
  hashing, and process startup. The source may contain scenarios, which are
  compiled but not run in this phase.
- **Run:** `run_request` on a previously compiled program and in-memory JSON,
  including input validation/normalization, request execution, full evidence
  construction and metering, state/result conversion, and disposal. It excludes
  JSON input parsing, final JSON serialization, and host I/O. Each call gets
  fresh state and default budgets; evidence is never disabled.
- **Serialize:** encode a previously produced full `ProgramExecution` as JSON,
  including disposal of the byte vector. It excludes execution and file I/O.

These measurements do not isolate evidence-construction cost. Serialization of
the whole response is not a measurement of evidence overhead. Process cold
start is not isolated by this harness. The separate fresh-process harness below
measures end-to-end CLI invocation and peak RSS. Allocator counts, isolated
evidence-construction cost, long-running services, broader concurrency, host
bindings, and other machines remain unqualified.

## Compare implementations

Build the same example against each engine under equivalent conditions, save
their output, then run:

```sh
python evaluations/native_performance/compare.py /tmp/before.json /tmp/after.json
```

The comparison refuses changed source, input, expected output, event/step counts,
or observation hashes. In addition to each successful execution, the harness
records all combinations of five step budgets and four evidence budgets: 189
full execution observations across nine workloads. Hashes cover state, result,
output, diagnostics, steps, and complete events with source spans and operand
links. They check preservation against a baseline; independently stated expected
outputs and the conformance tests supply separate correctness evidence.

Compare batch ranges as well as medians. Compile and serialization timings can
help identify environmental noise when the corresponding code is unchanged.
Repeat noisy measurements before attributing a change to the implementation.
Do not treat small differences on a shared machine as established improvements.

An implementation change alters the engine fingerprint. Existing execution cases
remain bound to their original engine; these timing reports do not authorize
relabeling or silently migrating captured cases.

## Fresh-process CLI measurements

`measure_process.py` takes qualified development/release packages from the same
Rust toolchain and engine source identity:

```sh
python evaluations/native_performance/measure_process.py \
  --dev /tmp/gwt-dev-evidence --release /tmp/gwt-release-evidence \
  --output /tmp/gwt-process-measurements
```

Each sample launches a new executable and measures through captured/decoded
stdout. It includes process creation/loading, reading source and JSON input,
compilation/checking, execution, full evidence construction, and JSON output.
Verification and independent expected-result assertions happen outside timing.
Every observation must exactly match the frozen baseline. The invoice and
contact policies have complete independent result expectations; fulfillment
assertions cover the documented stock/fee outcomes, with full cross-profile
observation equality checked separately.

There are two passes of 30 samples per profile and workload by default, with
profile order alternating. Three separate invocations per profile/workload use
GNU `time` for peak RSS. All timings and RSS observations are retained. `jsonBytes`
is the size of the canonical stored observation, not the CLI's pretty-printed
transport payload. File/loader caches are not cleared, and baseline verification
runs precede measurement. This is neither isolated process-start cost nor
cold-disk latency or service throughput. Avoid concurrent builds/tests during
measurement; the shared machine's frequency and load still require caution.

The [release results](../native_packaging/2026-10-16-release/README.md) report
these measurements separately from correctness, model performance, and human
comprehension evidence.
