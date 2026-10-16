# GWT native core (experimental)

GWT expresses domain behavior as executable `GIVEN / WHEN / THEN` programs.
This Rust library and `gwt-native` CLI implement an experimental language subset.
The crate is MIT-licensed and remains unpublished (`publish = false`).

The source package is self-contained. With Rust 1.85 or newer, extract it into a
new directory and run:

```sh
cargo build --locked --bin gwt-native
cargo run --locked --bin gwt-native -- version --json
cargo run --locked --example embed
cargo run --locked --bin gwt-native -- test tests/fixtures/invoice.gwt
```

The embedding example compiles frozen source, tests its two scenarios, and runs
a typed request. Its result includes an exact decimal total of `"47.88"`, source
identity, and factual execution evidence. Inspect `ok` before using `result`;
failed requests retain diagnostics/evidence and have no successful result.

`gwt-native version --json` and the library's `version_info()` identify the
compiled package, experimental language profile, and case engine fingerprint.
The language release version is null: crate version 0.1.0 is not a language
version. The command works without source files and does not execute a program.

To embed in a separate Rust project, use a path dependency on the extracted
package. Retain that host's Cargo lockfile:

```toml
[dependencies]
gwt-core = { path = "../gwt-core-0.1.0" }
serde_json = { version = "=1.0.154", features = ["arbitrary_precision"] }
```

See `examples/embed.rs` for the public API. `compile_bundle` accepts a
`SourceBundle` in memory; `compile_file` loads a bounded source/import closure.
A compiled program can be shared across threads. Each invocation has independent
normalized inputs, local state, budgets, and evidence. The host owns persistence,
networking, and other effects. This is not a server, sandbox, or stable C ABI.

Integers use exact JSON number tokens, including values beyond JavaScript's safe
integer range. Decimals use strings. Keep arbitrary-precision JSON handling at
host boundaries; an already-rounded host value cannot be repaired by the engine.
Default execution limits are explicit and can be reduced using `ProgramLimits`.

Engine identity hashes package-local source/build inputs, its actual manifest,
and the retained `engine-dependencies.lock` baseline. Cargo normalizes manifests
when packaging, so a workspace build and its packaged build deliberately have
different fingerprints. Use a single packaged artifact for CLI and library
consumers when shared case replay identity matters. Replay always verifies the
full recorded execution. The digest is not a compiled-binary signature and does
not identify a consumer's complete dependency resolution or feature union.
`engine-dependencies.lock` records the qualified baseline; it does not override
a host application's lockfile. Qualify the actual host graph before deployment.

The package contains the library, CLI, embedded review assets, license, and a
self-contained host example with executable scenarios. Repository-wide test and
performance harnesses depend on additional domain corpora and stay in the source
repository. They are run separately from package verification. `cargo test` on
the extracted package runs library unit tests, not the entire project suite.

Full semantics, conformance evidence, integration guidance, and remaining goals
are in the [GWT repository](https://github.com/georgemclaughlin/gwt). Packaging
checks establish a development integration path, not production readiness,
complete language support, or demonstrated human-comprehension benefit.
