# Contributing to GWT

The only runtime is the Rust engine in `crates/gwt-core`; the binary is `gwt`.
The current language contract is the [draft reference](spec/native-draft.md).

From a checkout, with rustup installed:

```sh
rustup toolchain install 1.96.0 --component clippy,rustfmt
cargo +1.96.0 build --locked -p gwt-core --bin gwt
cargo +1.96.0 fmt --all -- --check
cargo +1.96.0 clippy --workspace --all-targets --locked -- -D warnings
cargo +1.96.0 test --workspace --locked
python -m unittest discover
npm --prefix vscode-gwt ci
npm --prefix vscode-gwt run check
npm --prefix vscode-gwt test
python tools/verify_product.py --gwt target/debug/gwt
```

Python and Node are development tools for qualification and browser/host tooling;
users do not need them to run the compiled executable. The project also tests
Rust 1.85.0 as its minimum toolchain.

## Site and example generation

```sh
python tools/build_site.py --gwt target/debug/gwt
```

This validates the baseline and candidate, checks nine independent cases, and
regenerates the offline review, downloadable example, checksums, and source/engine
manifest under `docs/`. The generated reviewer decisions remain pending.
Use any static server to preview `docs/`. Changes to engine identity require fresh
captures; never rewrite a saved case's identity to make it replay.

## Package qualification

```sh
python evaluations/native_packaging/qualify.py --toolchain 1.96.0 --profile release --output /tmp/gwt-package-check
```

Use a fresh output directory. The harness verifies the Cargo source package,
installed CLI, independent Rust host, relocation, and local binary bundle.
The manual `Build distribution` workflow builds GNU and static musl Linux
artifacts without publishing a release. See the [release checklist](release-checklist.md).

## Editor qualification

With VS Code and a graphical session installed:

```sh
python evaluations/native_editor/qualify.py --native target/debug/gwt --output /tmp/gwt-editor-check
```

This uses an isolated profile/workspace and checks actual extension behavior.
It does not install or modify extensions in your ordinary editor profile.
