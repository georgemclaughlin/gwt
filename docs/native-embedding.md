# Package and embed the native engine

The native crate now builds independently of the repository directory layout.
The Cargo source artifact contains its Rust code, review assets, build inputs,
MIT license, a small embedding example, and an invoice fixture with two scenarios.
It provides both `gwt-core` and `gwt`. It remains an unpublished development
package with `publish = false`.

## Build a local artifact

With the locked dependencies available locally:

```sh
cargo package -p gwt-core --locked --offline --allow-dirty
```

This creates `target/package/gwt-core-0.1.0.crate` and verifies an extracted build.
`--allow-dirty` permits a development artifact from the current worktree; nothing
is uploaded. Omit it when requiring a clean Git tree. A fresh environment needs
the declared dependencies cached before using `--offline`.

Extract the artifact into a new directory. From its root:

```sh
cargo build --locked --bin gwt
cargo run --locked --example embed
cargo run --locked --bin gwt -- test tests/fixtures/invoice.gwt
cargo install --path . --locked --root /path/to/local/install
```

The example runs both embedded scenarios, compiles a frozen source bundle, then
executes `price invoice` with exact facts. The result is
`{"decision":{"status":"priced","total":"47.88"}}`. The installed executable
is under the selected installation root's `bin` directory. Local qualification
covers development and release profiles on Linux. Use `cargo build --release`
for an optimized executable; `cargo install` uses release by default. The
[release checkpoint](../evaluations/native_packaging/2026-10-16-release/README.md)
records optimized execution, binary extraction, runtime compatibility, and
separate fresh-process measurements.

The artifact excludes repository-wide integration tests and the profiling
harness because they depend on domain sources and acceptance corpora outside the
crate. Those tests still run in the repository and CI. `cargo test --lib` in the
extracted artifact runs its three library unit tests. Package verification is an
additional check, not a replacement for the full suite.

## Use the library from a host application

Add the extracted package as an ordinary path dependency:

```toml
[dependencies]
gwt-core = { path = "../gwt-core-0.1.0" }
serde_json = { version = "=1.0.154", features = ["arbitrary_precision"] }
```

Retain the host project's own Cargo lockfile. The self-contained
[`embed.rs`](../crates/gwt-core/examples/embed.rs) shows the public API; its source
fixture is included in the artifact. A host can load files with `compile_file`
or supply a `SourceBundle` directly to `compile_bundle`. Bundle compilation and
subsequent execution use the captured source; they do not reopen it for each run.

Compile once, then call `CompiledProgram::run_request` with a request name,
`serde_json::Value` input, and `ProgramLimits`. Check `ok` before using `result`.
Failures keep their diagnostic, state, prints, and evidence but have no successful
result. The host owns persistence, networking, scheduling, and other effects
around the rules. The core does not provide a server or C ABI.

For raw JSON with a known shape, declare the fields the rules actually use.
The [typed input boundary example](native-input-boundary-decisions.md) keeps
validation decisions in GWT while preserving explicit absent/domain states.
Project an external envelope only when needed; do not hide policy in the host
adapter or assume Python's `any` acceptance is the native contract.

A compiled program can be shared using `Arc<CompiledProgram>` across Rust threads.
Invocation state, normalized input, budgets, and evidence remain separate. The
qualification runs four threads against one compiled program, including successes,
failures, scenarios, and reduced budgets. This demonstrates the tested sharing
boundary, not unlimited concurrency, memory isolation, or cancellation support.

Exact numbers are part of the host contract. Integer JSON tokens remain arbitrary
precision; decimal inputs and outputs use strings. A value rounded before reaching
GWT cannot be restored. Enable arbitrary-precision JSON handling throughout the
host boundary, and avoid converting recorded integer tokens to floating-point
values. Closed input contracts reject unknown fields, missing required values,
boolean-as-number values, and fractional JSON number tokens for decimals.

Input-contract failures retain the diagnostic code and source contract span.
Messages name the expected GWT type and supplied JSON kind, with nested field
and zero-based item locations. For example:

```text
field 'facts': field 'lines': item 1: field 'count': expected integer; found JSON boolean
```

Missing required values name the expected type. Decimal type mismatches explain
that decimal inputs use quoted base-10 text or a JSON integer; malformed decimal
text and digit overflow retain their specific errors. One-of failures distinguish
missing/nontext `kind` values from unknown text tags and list the allowed tags.
Unknown field/tag names are JSON-escaped and abbreviated after 128 characters.
Type descriptions are bounded as in the [static diagnostic renderer](native-editor.md#type-error-explanations).
Type mismatch messages describe the supplied category without echoing its value.

Contract normalization still finishes before request execution or input-state
installation. A rejected host input produces no behavior events or prints and
no successful result. Input acceptance, closed-record rules, optional omission,
exact-number encoding, and first-error ordering are unchanged. The normalizer is
also used for internal value checks, which share these message improvements.

Message wording is explanatory text, not a protocol. Saved failures include it
in their complete observation, so an engine migration can correctly report an
observation change when only the message changed. Preserve old cases and use
explicit migration; do not rewrite or ignore the recorded diagnostic to obtain
a passing replay. [Boundary and package evidence](../evaluations/native_editor/2026-10-16-input-diagnostics/README.md)
separates message-only changes from other execution differences.

`capture_request`/`capture_scenario` create frozen cases; `replay_case` verifies
their complete observations. `explain_execution` supplies source/operand evidence.
The packaged CLI and a host using the same packaged crate can share cases when
their engine identities and actual observations match. Both parts of that check
matter; the source digest alone is not execution verification.

## Run a local browser preview

The [browser host experiment](../examples/native_browser_host/README.md) builds
the same core as WebAssembly for an offline invoice what-if preview. Its worker
accepts a frozen source bundle and raw JSON facts, preserving native numbers,
diagnostics, and execution evidence. Both qualified Rust builds match all 263
requests in Chromium, Firefox, and Linux WebKit in the
[current browser checkpoint](../evaluations/native_browser/2026-10-16-finite/README.md).
The worker adapter loads before the host reports readiness, so the first GWT
request can run after going offline. This establishes the recorded Linux browser
integrations; Safari, mobile devices, other versions/OSes, and production
deployment remain open. Offline reload is not supplied.

## Call the executable from Node

For a Node process host, the [native Node example](../examples/native_node_host/README.md)
calls the packaged executable directly and preserves exact integer tokens as
`bigint` where needed. It keeps rule failures separate from process/protocol
errors and bounds input, output, and wall time. The local qualification includes
a copied host outside the repository with no Python or Rust on its command path.
It recompiles per invocation; use the Rust library above for compile-once sharing.

## Discover contracts before supplying inputs

`gwt inspect FILE.gwt` reports checked request inputs/outputs, named types,
behavior signatures, scenarios, and the frozen source identity. Rust hosts can
use `program.inspect()` and its bounded `to_json()` method. The report excludes
locally initialized request state from caller inputs and distinguishes optional
omission from required inputs. See [native inspection](native-inspection.md) for
its type representation and limits. Inspection does not execute the rules.

For resource investigation, `gwt profile` executes a selected request or
scenario and groups exact retained evidence bytes by operation and source span.
Rust hosts use `profile_request` or `profile_scenario` with explicit limits.
See [native profiling](native-profiling.md) for partial-failure accounting and
report bounds. These reports measure evidence and steps, not time or memory.
The CLI accepts the same complete `ProgramLimits` object through
[`--limits FILE.json`](native-execution-limits.md), allowing hosts and local
validation to exercise the same operating budget.

## Build identity and dependency qualification

The build script reads only package-local inputs. Its v2 source fingerprint covers
all files under `src/`, including embedded JavaScript and CSS, plus `build.rs`,
the actual `Cargo.toml`, and `engine-dependencies.lock`. Component-wise sorted
relative paths use `/`; each path and raw-content field has an unsigned 64-bit
big-endian byte-length prefix. The SHA-256 input starts with
`gwt-native-engine-source-v2` and a zero byte. The case engine profile remains
`gwt-native-case-engine-v1`; source-fingerprint revision does not change the case
schema or runtime semantics.

Cargo normalizes manifests during packaging. Therefore a source-workspace build
and its packaged build have distinct fingerprints even when they produce identical
observations. Keep the previous executable and use [explicit migration](native-migration.md)
when moving saved cases to the packaged engine. Relocating an unchanged extracted
package preserves its source fingerprint. The dated qualification independently
recomputes the fingerprint and checks exact replay after relocation.

Direct dependencies are pinned to the qualified versions in the crate manifest.
`engine-dependencies.lock` records the complete repository qualification baseline;
a repository test fails if it drifts from the workspace lock. The generated
package's Cargo lock is checked against that baseline. A dependency update must
update the baseline and repeat the native and consumer qualifications.

A dependency crate cannot override an application's Cargo resolution. A host's
other dependencies may change transitive versions or unify features. The source
digest identifies the packaged build inputs and declared baseline, **not** the
host's complete resolved dependency graph, compiler, target, flags, or binary.
Keep that host's lockfile and qualify its actual versions/features and observations.
The supplied qualification compares the external consumer's resolved registry
packages and features with the extracted package for the tested target. It does
not certify arbitrary host graphs. Compiled executable hashes are retained
separately in the evidence.

## Reproduce the development qualification

```sh
python evaluations/native_packaging/qualify.py \
  --toolchain 1.96.0 --output /tmp/gwt-package-evidence
```

The default `--profile dev` retains the development qualification. To qualify
optimized package tests, the embedding example, installed CLI, external host,
relocated source build, and extracted standalone binary:

```sh
python evaluations/native_packaging/qualify.py \
  --toolchain 1.96.0 --profile release --output /tmp/gwt-release-evidence
```

The output directory must be new. The script uses a separate temporary workspace
outside the repository. It verifies the Cargo artifact, checks the included
license and dependency baseline, runs library unit tests and the embedding
example, installs the CLI locally, and builds an unrelated Rust host. It then
compares full CLI/library observations and captures, replays cases from a relocated
build, and retains the exact package and evidence. Cargo operations use `--offline`;
the dependency cache must already contain the target's required packages.

An optional `--previous-engine PATH --previous-case CASE.json` also verifies a
transition from a retained older executable. Neither option is inferred from
case content. The harness and checked-in evidence currently target Linux; other
platforms require their own qualification.

The [dated results](../evaluations/native_packaging/2026-10-16/README.md) cover
Rust 1.85.0 and 1.96.0 on x86_64 Linux. CI now runs the packaging/host check for
both toolchains and both development/release profiles after the matching full
native suite. These are local and configured CI checks; a hosted CI run is not
claimed. The subsequent [release qualification](../evaluations/native_packaging/2026-10-16-release/README.md)
adds standalone artifacts and runtime checks. A subsequent
[static Linux checkpoint](../evaluations/native_packaging/2026-10-16-static/README.md)
qualifies musl release builds on both toolchains, also configured in CI.
Production rollout, broader target
qualification, cancellation, broader memory/concurrency measurements, other host
languages, and human-benefit evidence remain open.

## Static Linux build

For x86_64 Linux deployment across the qualified GLIBC and Alpine environments,
build the explicit musl target:

```sh
rustup target add --toolchain 1.96.0 x86_64-unknown-linux-musl
python evaluations/native_packaging/qualify.py \
  --toolchain 1.96.0 --profile release --target x86_64-unknown-linux-musl \
  --output /tmp/gwt-static-evidence
```

`--target` defaults to the selected compiler's host. It applies to Cargo package
verification, library tests, embedding, installation, the external consumer,
relocated builds, and dependency graph filtering. Initial Cargo package
verification still uses its development profile; the requested release profile
applies to the subsequent qualification stages. The harness must run its target
executables on the build host; it is not a general cross-platform runner.

For this musl target, the harness defaults to the selected toolchain's bundled
`rust-lld` and target flags `-C link-self-contained=yes -C target-feature=+crt-static`.
Existing environment overrides are retained and recorded. The underlying linking
options are described in the [Rust compiler documentation](https://doc.rust-lang.org/rustc/codegen-options/index.html#link-self-contained).
No system musl development packages were needed in the qualified builds.
Regardless of flags, release qualification requires the actual ELF to have no
interpreter, needed shared libraries, or GLIBC version symbols before bundling.

Both Rust 1.85.0 and 1.96.0 static builds pass the example and all 18 captured
host cases in Alpine (musl 1.2.5), Debian Bookworm (GLIBC 2.36), and the retained
GLIBC 2.39/2.41 images. Their full host observations equal the GNU release's
observations. The [static checkpoint](../evaluations/native_packaging/2026-10-16-static/README.md)
retains exact images, binary identities, raw ELF inspection, full native suite
results, and editor qualification. These checks do not establish compatibility
with older kernels, other architectures, or other operating systems.

## Standalone release bundle

Release qualification also produces `gwt-0.1.0-<target>.tar.gz` and an
archive checksum. It contains `bin/gwt`, the MIT license, a README,
`manifest.json`, and an invoice source/input example. No Rust or Python
installation is needed to execute the extracted binary. The manifest records
file hashes, modes and sizes; compiler/target/profile; engine and source-package
identities; dependency-graph identity; selected build-environment overrides;
and the ELF loader, shared libraries, and GLIBC version symbols.

The archive format is deterministic for identical supplied bytes. This does not
establish reproducible compilation across machines or capture every possible
Cargo configuration. Checksums identify bytes and are not publisher signatures.
The package remains experimental and unpublished.

The supplied local x86_64 GNU/Linux bundles require GLIBC 2.39 symbols. Both
qualified toolchains run the example and all 18 captured host observations in
GLIBC 2.39 and 2.41 containers, with networking disabled, a read-only filesystem,
and an empty command path. GLIBC 2.36 fails at the loader; that is recorded as
incompatible rather than a passed runtime. GNU/Linux binaries do not imply musl,
Alpine, macOS, Windows, or older Linux support. A broader baseline needs a build
against that baseline or a separately qualified target.

The exact image identities and loader diagnostics are retained in the release
checkpoint. To assess images already available locally:

```sh
python evaluations/native_packaging/qualify_binary_runtime.py \
  --qualification /tmp/gwt-release-evidence \
  --image mcr.microsoft.com/playwright/python:v1.63.0-noble \
  --output /tmp/gwt-release-runtime
```

The helper inspects the existing image and executes its immutable image ID; it
does not pull an image. Qualified runtime rows require exact observation equality,
not merely a successful process exit. An incompatible row retains its diagnostic.
These container checks exercise user-space compatibility on the host kernel;
they are not qualification of arbitrary kernels or production environments.
