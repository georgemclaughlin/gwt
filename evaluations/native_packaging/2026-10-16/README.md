# Native packaging and embedding checkpoint

The original `cargo package` verification failed because the build script read
`../../Cargo.lock` and `../../Cargo.toml`. Those workspace ancestors do not exist
at the extracted crate location. [The failure log](package-before.log) retains
the observed failure.

The crate now declares its own package/dependency metadata and retains its
qualified dependency baseline locally. Its source fingerprint v2 uses only
package-local inputs, including embedded review assets. Cargo artifacts contain
the MIT license, library/CLI, self-contained embedding example, and executable
invoice fixture. They remain unpublished. The repository suite stays in the
repository because it depends on larger domain corpora.

Both Rust 1.85.0 and 1.96.0 passed this qualification on x86_64 Linux:

1. Build and verify a Cargo source package with offline, locked dependencies.
2. Verify the included license, pinned direct dependencies, and baseline lock.
3. Run three packaged library unit tests, both invoice scenarios, and the
   embedding example; install the CLI into a temporary local prefix.
4. Build an unrelated Rust project against the extracted package and compare its
   actual target-specific dependency versions/features with the package graph.
5. Verify fourteen independent request outcomes: exact prices, zero price,
   integers beyond JavaScript and machine-word precision, policy rejections,
   missing/extra fields, wrong types, and fractional JSON-number refusal.
6. Capture/replay two reduced-budget failures and both named scenarios, bringing
   the total to eighteen recorded observations. Check source-backed explanations
   and preservation of caller input.
7. Share one compiled program across four host threads for 288 executions;
   every complete observation must equal its independently checked serial case.
8. Match all eighteen host cases through the installed CLI's full replay, and
   match direct CLI run/capture for the sixteen default-budget cases.
9. Relocate the package to a different directory depth, rebuild it, and replay
   all eighteen cases with identical observations and source identity.
10. Verify one transition from the retained pre-packaging engine: the old
    observation is preserved and the candidate uses the packaged engine identity.

The two tested toolchains produced the same package-local source identity; this
is an observed result, not a promise of identical manifests or binaries across
all Cargo/toolchain versions. Cargo-normalized package manifests deliberately
have a different identity from the source-workspace manifest. Compiler, target,
flags, binary bytes, and arbitrary host dependency graphs are not authenticated
by this source fingerprint. Tested executable hashes, compiler details, actual
host graphs, and host lockfiles are retained separately.

- [Verification summary](verification.json)
- Rust 1.85.0: [qualification](1.85.0/qualification.json), [full host observations](1.85.0/host-observations.json),
  [dependency/features](1.85.0/dependency-graph.json), [host lock](1.85.0/host.Cargo.lock),
  [exact Cargo artifact](1.85.0/gwt-core-0.1.0.crate), [migration](1.85.0/packaging-migration.json),
  [command log](1.85.0/commands.log), [170 native tests](1.85.0/tests.log), [Clippy](1.85.0/clippy.log).
- Rust 1.96.0: [qualification](1.96.0/qualification.json), [full host observations](1.96.0/host-observations.json),
  [dependency/features](1.96.0/dependency-graph.json), [host lock](1.96.0/host.Cargo.lock),
  [exact Cargo artifact](1.96.0/gwt-core-0.1.0.crate), [migration](1.96.0/packaging-migration.json),
  [command log](1.96.0/commands.log), [170 native tests](1.96.0/tests.log), [Clippy](1.96.0/clippy.log).
- [Previous engine source and identity](../../native_migration/2026-10-16-corpus/native-verification.json)
  and its [source archive](../../native_migration/2026-10-16-corpus/target-engine-source.tar.gz).

Reproduce with `evaluations/native_packaging/qualify.py` and fresh output
directories. To reproduce this exact engine after later source changes, extract
the retained `.crate` artifact and build with its Cargo lock. The host source and
qualification script are retained beside this dated directory. The optional
migration requires the previous engine and an original case from the retained
proposal; a rebuilt previous executable may have different binary bytes and
therefore produce a different proposal digest while still verifying the case.

The full repository suite now contains 170 tests, including two checks for
package-local source identity and dependency-baseline drift. Tests and Clippy
pass on both toolchains; formatting passes. CI is configured to repeat the
package/consumer qualification for both toolchains; no remote CI run or package
publication is claimed here.

These are development integration checks. They do not establish production
readiness, release-mode throughput, other-platform compatibility, a stable FFI,
resource isolation, or improved human comprehension. No external pilot was run.
