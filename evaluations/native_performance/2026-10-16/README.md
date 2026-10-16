# Read only the expression paths that execute

The program runtime previously cloned every in-scope binding into an expression
input vector before evaluating any expression. Even a literal copied unrelated
state, and a field read copied its entire parent record. The evaluator now asks
the runtime for each path when it executes; the runtime follows its existing
state address and copies the selected value. Short-circuited paths are not read.
The standalone expression API and program runtime share the same field traversal.

This changes no public syntax, numeric policy, budgets, or evidence format.
Full input normalization, contract checks, state snapshots, and execution
evidence remain enabled. A record/list used as a value is still copied; this
does not claim to eliminate all allocation or input-size-dependent work.

## Measurements

Both binaries used Rust 1.96.0, the locked dependencies, and the release profile
on a shared AMD RYZEN AI MAX+ 395 machine. CPU affinity and frequency were not
controlled. Each number below is the median of seven batches of 100 operations.
Two complete before/after pairs were measured, in that order, without running
builds or test suites concurrently with the measurements.

| Workload | Before, µs/run (first / repeat) | After, µs/run (first / repeat) |
| --- | ---: | ---: |
| Delivery quote | 17.7 / 29.9 | 15.9 / 16.6 |
| Exact invoice pricing | 39.3 / 37.1 | 22.5 / 24.0 |
| Stock reservation | 207.5 / 145.7 | 105.4 / 104.4 |
| Scalar updates, unrelated empty list | 138.8 / 141.8 | 134.9 / 203.1 |
| Scalar updates, sibling empty list | 134.8 / 137.2 | 134.8 / 130.9 |
| Scalar updates, unrelated 100-item list | 202.8 / 214.8 | 148.5 / 149.4 |
| Scalar updates, sibling 100-item list | 197.6 / 202.5 | 148.2 / 151.1 |
| Scalar updates, unrelated 4,000-item list | 2,202.8 / 2,300.9 | 893.3 / 888.9 |
| Scalar updates, sibling 4,000-item list | 2,258.4 / 2,338.4 | 887.7 / 1,047.5 |

The large-payload workloads improve by 2.2–2.6× across these measurements.
They execute the same 64 scalar additions while carrying unused values either
in a separate binding or in a sibling field. This specifically exercises the
removed copying. The remaining input normalization and state/result work still
scales with input size.

There is substantial noise on smaller workloads, including a slower repeat for
the empty unrelated-list workload. Unchanged compilation and serialization
phases also vary. These observations do not establish a general speedup, a
stable latency bound, or a Rust-versus-Python comparison. All raw batch values
are retained rather than selecting only favorable runs.

## Behavior and resource checks

Both before/after pairs match **189 complete execution observations**: nine
normal runs and 20 step/evidence-budget combinations per workload. Matching
hashes cover results, state, output, diagnostics, step counts, and complete
source-located evidence. The harness separately checks independently written
expected successful outputs.

Three new unit tests verify that literals/skipped operands request no binding,
optional guards read only reachable fields in source order with their original
spans, and exhausted step budgets prevent path reads. The existing conformance,
aliasing, collection, scenario, capture/replay, comparison, and review tests
remain the broader behavioral checks.

The full 98 integration tests plus three unit tests, and Clippy for all targets,
pass on Rust 1.85.0 and 1.96.0. Formatting passes on 1.96.0. All nine benchmark
sources also pass Python canonical-format checking and validation for their
shared language syntax; Python is not the performance or numeric oracle here.

## Artifacts and reproduction

- [Harness methodology and commands](../README.md).
- [Environment and file hashes](environment.json), including engine/build
  provenance and the harness hash.
- First pair: [before](before.json), [after](after.json),
  [verified comparison](comparison.json).
- Repeat pair: [before](before-repeat.json), [after](after-repeat.json),
  [verified comparison](comparison-repeat.json).
- [Exact runtime change](runtime-change.patch), including the new unit tests.

The raw reports embed workload sources and inputs, expected outputs, default
execution hashes, and all budget observations. To reconstruct the baseline from
this checkpoint, make an isolated copy of the repository and reverse the saved
patch with `patch -R -p1 < evaluations/native_performance/2026-10-16/runtime-change.patch`.
Build the same example in each copy using the commands in the methodology.
Check the resulting engine identities against the reports before comparing.
Later source changes may make this patch inapplicable; it describes this exact
checkpoint rather than a generic downgrade procedure.

Cold start, isolated evidence-construction overhead, memory/allocator behavior,
broader deployment qualification, and measured human benefit remain open.
