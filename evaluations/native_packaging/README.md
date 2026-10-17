# Native package and Rust-host qualification

`qualify.py` builds a self-contained Cargo source artifact and tests it outside
the repository workspace. It installs the CLI into a temporary prefix, compiles
an unrelated Rust consumer using the extracted package, and compares their full
observations. `host.rs` is the consumer harness, with independent expected
invoice values/failures and shared-program concurrency checks.

Run with a new evidence directory and cached dependencies:

```sh
python evaluations/native_packaging/qualify.py \
  --toolchain 1.96.0 --output /tmp/gwt-packaging-evidence
```

The script leaves its temporary build/consumer/install directories in place for
inspection and records their location. It publishes nothing. Optional paired
`--previous-engine PATH --previous-case CASE.json` arguments qualify an explicit
transition from a trusted retained executable. They are never discovered from
case contents.

Use `--profile release` to run the optimized qualification and create an
unpublished standalone binary bundle with its license, example, manifest, and
archive checksum. The default remains `--profile dev`. `binary_artifact.py`
checks all file identities and paths before extraction, and refuses overwrites.
`qualify_binary_runtime.py` checks an extracted release binary in explicitly
supplied local container images and retains incompatible-runtime diagnostics.

Current checks target Linux. The package's unit tests are supplemented by the
full native repository suite and independent host/CLI checks; omitting the
repository-dependent integration harnesses from the distributable artifact does
not remove them from CI.

The [Node host checkpoint](2026-10-16-node-host/README.md) adds a dependency-free
process adapter with exact bigint/decimal handling, bounded child execution,
failure separation, and a copied host running with an empty PATH. Its thirteen
tests also run after package qualification in CI.

See [2026-10-16 evidence](2026-10-16/README.md) and the
[embedding guide](../../docs/native-embedding.md). Production deployment,
broader targets and host languages, and human benefit remain separate
requirements. The [release checkpoint](2026-10-16-release/README.md) records
release-profile and standalone-runtime evidence, including the GLIBC 2.36
incompatibility and separate fresh-process measurements.

The [static Linux checkpoint](2026-10-16-static/README.md) adds explicit
`--target x86_64-unknown-linux-musl` builds and qualification on both compilers.
The harness uses the selected toolchain's bundled linker by default, records
target-specific overrides, and verifies actual static ELF linkage. Both binaries
pass Alpine and GLIBC 2.36/2.39/2.41 container checks; these use the host kernel.
The runtime helper records immutable image IDs, actual libc/kernel probes, and
full command output. General target execution requires a runnable build host.

Build scratch space follows Python's standard `TMPDIR` selection. If the default
temporary filesystem has insufficient capacity or quota, set `TMPDIR` to an
existing writable directory on another filesystem before invoking the harness.
The evidence report records the resulting workspace; retained executables and
cases remain available independently of subsequent scratch locations.
