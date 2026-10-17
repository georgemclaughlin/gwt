# AGENTS.md

Guidance for coding agents working in this repository.

## Project shape

GWT is an experimental executable GIVEN / WHEN / THEN language. The Rust engine
in `crates/gwt-core/` is the only active implementation and installs `gwt`.
The Python runtime is retired; see `docs/python-retirement.md` and the file-level
`docs/retirement-inventory.json` for its immutable reference.

- Current contract: `docs/spec/native-draft.md`, `docs/native-grammar.md`, and
  `docs/native-semantics.md`.
- Product goal and evidence: `docs/project-goal.md`, `docs/project-goal-progress.md`.
- Editor: `vscode-gwt/`.
- Validated examples: `examples/catalog.json`; other retained examples may be
  historical comparison fixtures and are not promised language support.
- Authoring: `docs/agent-authoring.md` and `.agents/skills/gwt-authoring/SKILL.md`.

## Commands

```sh
cargo +1.96.0 build --locked -p gwt-core --bin gwt
target/debug/gwt validate examples/native_delivery/rules.gwt
target/debug/gwt run examples/native_review_walkthrough/candidate.gwt --request "quote delivery" --input examples/native_review_walkthrough/input.json
```

Public instructions should use installed `gwt`, not a build-directory path.

## Verification

For Rust changes, run:

```sh
cargo +1.96.0 fmt --all -- --check
cargo +1.96.0 clippy --workspace --all-targets --locked -- -D warnings
cargo +1.96.0 test --workspace --locked
```

CI also tests the minimum Rust version and optimized GNU/static Linux builds.
For a product cutover, packaging, or tooling change also run:

```sh
python -m unittest discover
npm --prefix vscode-gwt run check
npm --prefix vscode-gwt test
GWT_NATIVE_PATH="$PWD/target/debug/gwt" node --test tests/native_node_host.test.mjs
python tools/verify_product.py --gwt target/debug/gwt
git diff --check
```

Python here orchestrates independent research and package tests; it does not
implement or validate GWT semantics. For doc-only changes, exercise changed
commands and check links/whitespace. Regenerate site artifacts after engine or
walkthrough changes with `python tools/build_site.py --gwt target/debug/gwt`.

## Language design

Preserve the spec-as-code shape: named executable behavior over state, not SQL
or general query pipelines. Prefer explicit behavior signatures such as
`WHEN review <report> into <decision>`.

Keep parser, checker, executor, formatter, reference, grammar, and evidence
aligned. Add independent runtime/checker cases and a focused executable example
for new syntax. Prefer narrow collection operations with explicit missing and
failure cases. Do not carry forward Python conventions without a domain reason.

Substantial examples need embedded scenarios and THEN assertions. Format active
examples with the native formatter. JSON host input does not replace scenarios.

Preserve artifact schemas, digest domains, and historical evidence. Changing the
CLI name is not permission to rewrite captured cases or reviewer decisions.

## Git hygiene

Do not revert unrelated changes. Keep commits focused and include relevant tests,
docs, and examples. Run verification before pushing. Preserve dated evaluation
artifacts unchanged; new checks are new evidence. Merge and publication remain
separate from preparing and pushing a development branch.
