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

## Engine proofs

CI checks all Rust engine proof harnesses on pull requests and pushes to main.
To run the same suite locally, use Kani 0.68.0 from the repository root:

```sh
cargo install --locked kani-verifier --version 0.68.0
cargo kani setup
cargo kani -p gwt-core --lib -Z stubbing
```

To run a single proof, append `--harness` and its name.

- `charge_respects_step_budget` checks every pair of counter and limit values on
  the target. A successful charge spends one step. An exhausted budget returns
  `execution_limit` and preserves the counter.
- `exhausted_path_evaluation_stops_before_read` checks the evaluator with a
  binding-path expression. For every counter at or above the limit, evaluation
  returns `execution_limit`, preserves the counter, emits no event, and never
  calls the binding reader. This harness replaces the dispatch method after the
  entry check with a panic, so reaching dispatch also fails the proof. Coverage
  goals exercise equality and strict excess.

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

## Repository maintenance

Read the [architecture map](architecture.md) before changing execution or evidence
boundaries. Keep [project status](project-goal-progress.md) concise and link dated
results through the [evaluation index](../evaluations/README.md).
Independent regression cases stay in the test suite; bulky raw run outputs do
not belong in normal source PRs. The [fixture guide](../crates/gwt-core/tests/fixtures/README.md)
explains the large exact-arithmetic corpora and their storage format.
