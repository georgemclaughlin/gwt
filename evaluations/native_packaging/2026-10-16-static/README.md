# Static Linux deployment checkpoint

This checkpoint addresses the GNU release's observed GLIBC 2.36 loader failure
by building and qualifying a separate `x86_64-unknown-linux-musl` release target.
No GWT syntax, runtime semantics, or engine source changed.

## Artifacts

| Rust | Static x86_64 Linux archive | Executable bytes | Archive bytes |
| --- | --- | ---: | ---: |
| 1.85.0 | [Bundle](rust-1.85.0/gwt-native-0.1.0-x86_64-unknown-linux-musl.tar.gz) | 4,087,424 | 1,503,421 |
| 1.96.0 | [Bundle](rust-1.96.0/gwt-native-0.1.0-x86_64-unknown-linux-musl.tar.gz) | 4,085,672 | 1,515,178 |

Each bundle includes the executable, license, manifest, README, and invoice
source/input; an adjacent `.sha256` identifies the archive. No Rust or Python
installation is needed to run the extracted executable. Bundles are local,
experimental, unpublished artifacts, with checksums rather than signatures.

Executable SHA-256 identities:

- Rust 1.85.0: `246b1c8ff5d2cf6a2cbd3946797cafae20cbcaaf4ed9a0ca5274bba5978cfa30`.
- Rust 1.96.0: `677c27f0f1f42e33182aeb26c34942c894455192a87bfc24e1bb89c11da01949`.

Both retain the previous packaged engine identity
`sha256:638369358550c066f4cfe8375adfbca193702c05e47f68ba265b6d3d8fa9caaa`.
This source identity does not identify a compiler, target, or executable.
[Complete target comparisons](target-equivalence.json) separately prove equality
of all 18 captured host records with the retained GNU release.

## Builds and verification

The package harness now accepts `--target`, defaults to the compiler host, and
passes the selected target through source-package verification, package tests,
embedding example, installed CLI, external Rust consumer, dependency metadata,
and relocated builds. Cargo package verification remains development-profile;
subsequent qualification stages use the requested release profile.

For musl, the harness defaults to the selected compiler's bundled `rust-lld`
and target flags `-C link-self-contained=yes -C target-feature=+crt-static`.
It preserves existing environment overrides and records relevant settings.
See the [Rust linking option documentation](https://doc.rust-lang.org/rustc/codegen-options/index.html#link-self-contained).
Only the Rust target components were installed; system musl development packages
were unnecessary. Cargo package/build operations used cached dependencies offline.
The harness runs the result locally and is not a general cross-target emulator.

Raw `readelf` program headers, dynamic sections, and symbol-version inspection
are saved in each package's `elf-linkage.txt`. Both musl release executables have
no ELF interpreter, required shared libraries, or GLIBC version symbols. The
harness asserts those properties before producing a musl release bundle.

- **301 native release tests** and Clippy with warnings denied pass on both
  toolchains. Full logs are at this checkpoint root.
- Each package passes three library tests, two embedded scenarios, **18**
  independent host observations, **288** shared-program executions, **18**
  relocated-build replays, and **18** extracted-binary replays with empty PATH.
- A new default-target GNU release qualification passes the same package/host
  checks and exactly preserves the previous complete host observations.
- [Source verification](package-source-verification.json) matches all three
  archives against the workspace's **48** implementation/build inputs.
- **627 Python tests** pass, including the archive integrity/refusal tests.
- The extracted Rust 1.96.0 static executable passes **26 actual VS Code checks**
  in [the retained editor result](editor-static/extension-host.json), covering
  diagnostics, navigation, unsaved edits/imports, formatting, test, run, and
  validation. Five extension unit tests and syntax checks also pass.
- Rust formatting, Python harness compilation, CI YAML/matrix validation, and
  whitespace checks pass. CI is configured for four GNU compiler/profile jobs
  and two musl release jobs; no hosted run is claimed.

## Runtime matrix

Both static binaries pass the exact invoice request, two scenarios, and all
18 complete captured observations in each environment:

| Local image | Probed runtime | Rust 1.85.0 | Rust 1.96.0 |
| --- | --- | --- | --- |
| `alpine:latest` | musl 1.2.5 | Pass | Pass |
| `node:20.20.1-bookworm-slim` | GLIBC 2.36 | Pass | Pass |
| `mcr.microsoft.com/playwright/python:v1.63.0-noble` | GLIBC 2.39 | Pass | Pass |
| `python:3.12-slim` | GLIBC 2.41 | Pass | Pass |

The helper inspects already-present images and runs their immutable IDs; it pulls
nothing. Results retain image IDs/digests, actual libc and kernel probes, command
output, and binary identity in [1.85.0](runtime-1.85.0/qualification.json) and
[1.96.0](runtime-1.96.0/qualification.json). Alpine's libc identity comes from
its loader's version output; the static GWT executable does not use that loader.
Every container has networking disabled, a read-only filesystem, read-only
artifact/case mounts, and empty PATH.

The [GNU runtime regression](gnu-runtime-regression/qualification.json) still
records the old binary's GLIBC 2.36 loader failure and succeeds on GLIBC 2.39.
Adding musl support did not turn that incompatibility into a passing check.

## Limits and reproduction

All containers share the host's Linux `7.2.4-200.fc44.x86_64` kernel. These checks
establish the observed user-space compatibility only, not support for arbitrary
older kernels, other architectures, Windows/macOS, or production environments.
No performance advantage, human comprehension benefit, public release, or
external pilot is claimed. The full project goal remains active.

Use the [embedding guide](../../../docs/native-embedding.md#static-linux-build)
for target installation/build commands. For each toolchain, full-suite commands
used the bundled-linker/target-flags environment described above and a separate
temporary target directory:

```sh
cargo +1.96.0 test --release --workspace --locked --offline --target x86_64-unknown-linux-musl
cargo +1.96.0 clippy --all-targets --release --workspace --locked --offline --target x86_64-unknown-linux-musl -- -D warnings
```

The same checks ran with `+1.85.0`. Container qualification uses
`qualify_binary_runtime.py --qualification <new-package-evidence>`, repeated
`--image` arguments for the four images above, and a new `--output` directory.
