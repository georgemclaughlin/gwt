# Native evidence profiling qualification

This checkpoint completes the profiling work recovered after the reported
computer crash. The [usage guide](../../../docs/native-profiling.md) defines its
accounting, execution behavior, and limits. It adds diagnostic tooling; ordinary
execution semantics and evidence formats remain unchanged.

## Evidence

- `rust-1.85.0-tests.log` and `rust-1.96.0-tests.log`: 376 native tests pass on
  both supported toolchains. The corresponding Clippy logs have no warnings.
  Six profiling groups cover independent exact accounting, deterministic ordering,
  failure limits, imported/expanded source locations, report bounds, and CLI
  entry selection. Formatting and whitespace checks pass.
- `python-tests.log`: all 629 Python tests pass. `example-checks.json` records
  73 formatted examples, 16 top-level checker runs, and both reference workflows.
  The extension's syntax check and five JavaScript tests pass. The documented
  profiling command succeeds; its report is `documented-example.json`.
- [Workload qualification](workloads/qualification.json): 22 profiles match an
  independent Python serialization/accounting implementation, including both
  groupings, ordering, execution diagnostics, and repeated-report equality.
  Five fixed-size text collectors, four allocation sizes, Unicode/escaped text,
  invalid host input, and all eleven allocation scenarios are exercised.
- The same qualification migrates 57 actual cases owned by the retained
  append-evidence executable: all have `observation_preserved`, including full
  evidence, diagnostics, state, and results. All old cases replay on their
  owning engine; all candidates replay on the new engine. Original files are
  unchanged and proposals remain unapproved. `migration-*.json` and
  `candidate-*.json` retain the complete evidence.
- [Package qualification](package-1.96.0/qualification.json): Rust 1.96.0 static
  musl release built from an offline Cargo source package, then consumed by an
  unrelated Rust host. Four packaged unit tests, two embedded scenarios, 18
  independently specified observations, 288 concurrent ordinary executions,
  and all 18 library profiles pass. Sixteen default-limit profiles agree exactly
  with installed and relocated CLIs. The other two use zero-step/evidence library
  limits, which the CLI does not expose as flags. All 18 cases replay through
  installed, relocated, and binary-only executables. Dependency graphs match;
  the packaged engine fingerprint is independently reproduced.
- [Container qualification](static-runtime/qualification.json): the release
  passes request, scenario, inspection, profile, and 18 exact replay checks in
  existing local Alpine (musl 1.2.5) and Debian (glibc 2.36) images, using their
  immutable IDs, network disabled, a read-only filesystem, and an empty PATH.
  Both containers share the host kernel; this does not establish independent
  kernel or architecture coverage.

`commands.json` files and package `commands.log` preserve invocation details.
The package includes its source archive, binary bundle, dependency graph, host
lockfile, observations, and ELF linkage evidence. The packaged executable has
no dynamic interpreter, needed libraries, or GLIBC symbol dependencies.
`engine-source-manifest.json` records 55 current source/build inputs checked
against the extracted source package (using Cargo's retained original manifest
for the workspace manifest comparison).

## What the profiles reveal

For this checkpoint's `allocation.gwt` source and equal-weight pressure inputs:

| Recipients | Execution | Steps | Recorded events | Evidence bytes | Metadata bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| 8 | Success | 1,198 | 1,366 | 261,687 | 202,190 |
| 16 | Success | 3,646 | 4,170 | 816,194 | 627,540 |
| 32 | Evidence limit | 4,792 | 5,395 | 1,048,445 | 804,029 |
| 64 | Evidence limit | 4,857 | 5,426 | 1,048,465 | 800,368 |

The 16-recipient profile attributes roughly 77% of bytes to event metadata.
Its largest operation group is `collection item` (128,178 bytes across 408
events). Repeated scan conditions also contribute substantial metadata. This
supports investigating repeated traversal/evaluation and representation costs;
it does not establish a particular optimization or justify dropping evidence.
Partial 32/64-recipient reports describe only retained events and cannot predict
the cost of completing either run.

All tested collectors through 128 labels succeed. That input records 224,919
event bytes with the logical filename `collector.gwt`. Exact byte counts depend
on source names and spans as well as values, so they differ slightly from the
previous append checkpoint's `rules.gwt` fixture. This is not a new append
optimization. Invalid host input records zero events and zero execution steps.

## Scope and follow-up

The [qualifier](../qualify_profiling.py) uses the ordinary run payload as input to
an independent accounting implementation and explicitly checks the expected
success/refusal matrix. Rust tests independently cover the eight-MiB input and
output bounds, source locations, and library-selected budgets. Packaging checks
exercise the public API outside the repository's build context.

No new editor UI, browser interaction, external pilot, or actual human study was
performed. The profile omits individual values but retains potentially sensitive
diagnostic text and source metadata. It measures evidence bytes and execution
steps, not wall time or memory. Large allocation resource handling and measured
human comprehension benefits remain open parts of the project goal.
