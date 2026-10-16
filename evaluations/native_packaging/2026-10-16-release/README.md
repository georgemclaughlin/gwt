# Native release build and standalone runtime checkpoint

The package qualification now accepts `--profile dev` (the existing default)
or `--profile release`. Release qualification uses optimized library tests,
embedding example, installed CLI, external consumer, and relocated source build.
It also creates and verifies an extracted standalone binary bundle. Cargo's
initial source-package verification remains a development build and is recorded
separately. No source syntax or runtime rule changed in this checkpoint.

## Local artifacts

| Toolchain | Bundle | Executable bytes | Compressed archive bytes |
| --- | --- | ---: | ---: |
| Rust 1.85.0 | [GNU/Linux x86_64](rust-1.85.0/gwt-native-0.1.0-x86_64-unknown-linux-gnu.tar.gz) | 3,874,352 | 1,442,565 |
| Rust 1.96.0 | [GNU/Linux x86_64](rust-1.96.0/gwt-native-0.1.0-x86_64-unknown-linux-gnu.tar.gz) | 3,956,816 | 1,450,861 |

Each archive has an adjacent `.sha256` file and contains the executable, MIT
license, README, manifest, and runnable invoice source/input. The manifest binds
the included bytes, modes and sizes to compiler/target/profile, source package,
dependency graph, engine identity, selected environment overrides, and ELF
loader/library/version requirements. It is a byte-identity record, not a signed
release or complete compiler-environment attestation. Deterministic archive
headers do not imply reproducible compilation across machines.

Both release engines and the development comparison have source identity
`sha256:638369358550c066f4cfe8375adfbca193702c05e47f68ba265b6d3d8fa9caaa`.
Executable hashes differ by compiler and build profile. The Rust 1.96.0 release
binary is `fcc205123300659e6c7e58d48bb3b69f8613cf05f658ee760da78a643489f5b0`;
the Rust 1.85.0 binary is
`fdb4c1459194988a70671aecebe910504e3bd2bb7ff9a35514270ec9c99a6784`.
These are local experimental artifacts; nothing was published.

## Correctness and packaging

- **301** workspace tests pass in release mode on each Rust toolchain. The
  explicit development-profile command used in the updated CI matrix also
  passes all 301 tests on 1.96.0. Raw logs are retained at this checkpoint root.
- Each release package passes independent source/dependency checks, three
  packaged library unit tests, two example scenarios, **18** independent host
  observations, **288** concurrent executions, and **18** relocated source-build
  replays. Extracting the binary-only bundle and clearing `PATH` still passes
  the example request, both scenarios, and all 18 replays.
- The default development qualification still passes. `profile-equivalence.json`
  compares all 18 complete host records and cases from that run with both release
  toolchains; every record is equal, including outcomes, state, errors, evidence,
  budgets, and capture identity. Source identity alone was not treated as proof.
- `package-source-verification.json` compares all **48** implementation/build
  inputs in each of the three source archives to the workspace. Archive
  sidecar checksums were also verified.
- All **627 Python tests** pass, including six binary-archive test groups for
  exact bytes/modes, deterministic containers, changed content, unsafe/duplicate/
  undeclared entries, malformed manifests, size limits, and overwrite refusal.
  The archive verifier checks every entry before writing an extraction.
- Actual VS Code **1.137.0** passes all **26** checks using the executable
  extracted from the release bundle (`editor-release/extension-host.json`).
  No editor implementation changed.
- CI is configured for both Rust versions and both profiles, including the
  matching package qualification. This records configuration and local checks;
  no hosted CI run or public release is claimed.

## Runtime compatibility

The following results apply to **both** supplied release builds:

| Available local image | Observed libc | Result |
| --- | --- | --- |
| Playwright Python Noble | GLIBC 2.39 | Exact example execution, two scenarios, and 18 verified case replays |
| Python 3.12 slim | GLIBC 2.41 | Exact example execution, two scenarios, and 18 verified case replays |
| Node 20 Bookworm slim | GLIBC 2.36 | Loader rejects missing `GLIBC_2.39`; zero cases executed |

Image IDs and repository digests, commands, and diagnostics are in
`runtime-*/qualification.json`. The helper uses already-present images by their
immutable IDs; it does not pull anything. Execution has an empty `PATH`, disabled
networking, and a read-only filesystem. This demonstrates no Rust/Python command
dependency for the tested executable operations. The containers still share
the host kernel, and their installed libraries remain part of the runtime.

These Fedora-built GNU/Linux binaries require GLIBC 2.39 symbols, including
`pidfd_spawnp`/`pidfd_getpid`. The Bookworm failure is an incompatibility, not a
passed runtime or a GWT rule failure. Older GLIBC, musl/Alpine, other operating
systems/architectures, and independent kernels need separately built and
qualified artifacts. The target triple alone does not promise broad Linux
portability. See [embedding and bundle usage](../../../docs/native-embedding.md).

## Separate process measurements

The Rust 1.96.0 development and release executables were measured after the builds
and test jobs completed, on a shared AMD RYZEN AI MAX+ 395 host. Each workload has
two passes of 30 fresh invocations per profile, with profile order alternating.
Every sample returns the same complete execution observation across profiles.
Independent result assertions are recorded separately from preservation checks.

| Workload | Development median, ms (first / repeat) | Release median, ms (first / repeat) | Separate peak RSS, KiB (dev / release ranges) |
| --- | ---: | ---: | ---: |
| Exact invoice | 1.852 / 1.768 | 0.806 / 0.789 | 8,104–8,252 / 5,356–5,436 |
| Contact decision | 3.739 / 3.682 | 1.334 / 1.453 | 7,660–8,168 / 5,336–5,356 |
| Order fulfillment | 12.754 / 10.419 | 3.641 / 3.067 | 9,448–9,576 / 6,336–6,460 |

Timings include process creation/loading, source/input reads, parsing/checking,
execution, full evidence construction, JSON output, and host stdout capture/
decoding. Verification occurs after timing. RSS comes from three separate GNU
`time` invocations per profile/workload. All 360 timed values, 18 RSS readings,
source/input snapshots, independent assertions, and full observations are in
`process-measurements/`. Baseline verification runs precede measurement, and
filesystem/loader caches were not cleared. Affinity/frequency were not controlled.

Release is faster on these measured workloads, but the values are not isolated
startup cost, cold-disk latency, throughput, a Rust/Python comparison, or a stable
production latency bound. Full ranges and p95 observations are retained; for
example, development fulfillment spans roughly 9.2–16.7 ms. This evidence is
separate from model maintenance quality and human comprehension.

## Remaining goal

The work provides an optimized artifact and a tested deployment boundary. It does
not complete production rollout, broader target compatibility, stable integration
APIs, the remaining language/tooling work, or comparative human evidence. No
external pilot, participant recruitment, release publication, or migration
approval occurred. `source-hashes.json` identifies the qualification tools, tests,
workflow configuration, documentation, and unchanged native implementation.
