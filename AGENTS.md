# AGENTS.md

Guidance for coding agents working in this repository.

## Project Shape

GWT is an experimental programming language built around executable
`GIVEN / WHEN / THEN` programs.

- Runtime/parser/checker code lives in `gwtlang/`.
- The VS Code extension lives in `vscode-gwt/`.
- Language examples live in `examples/`.
- The current versioned spec is `docs/spec/v0.1.md`.
- The EBNF grammar is `docs/grammar.md`.
- The longer language guide is `docs/language.md`.
- Design principles and language-shape guardrails are in
  `docs/design-principles.md`.

## Core Commands

Use module invocation while developing, because it does not require installing
the package first:

```sh
python -m gwtlang run examples/hello.gwt --json
python -m gwtlang test examples/v01_language_tour/rules.gwt
python -m gwtlang check examples/v01_language_tour/rules.gwt
python -m gwtlang format examples/v01_language_tour/rules.gwt --check
```

After `python -m pip install -e .`, the equivalent `gwt` command is available.

## Verification

Before committing language/runtime/checker changes, run:

```sh
python -m unittest discover
find examples -name '*.gwt' -print0 | while IFS= read -r -d '' file; do python -m gwtlang format "$file" --check >/dev/null || exit 1; done
for file in examples/*.gwt; do python -m gwtlang check "$file" >/dev/null || exit 1; done
python -m gwtlang run examples/order_fulfillment/rules.gwt --input examples/order_fulfillment/request.gwt --json >/tmp/gwt-order.json
python -m gwtlang run examples/v01_language_tour/rules.gwt --input examples/v01_language_tour/request.gwt --json >/tmp/gwt-tour.json
(cd vscode-gwt && npm run check)
git diff --check
```

For doc-only changes, run the relevant example commands from the changed docs
plus `git diff --check`.

## Language Design Rules

- Preserve the language's spec-as-code shape. OpenSpec's persistent-spec idea
  was an original inspiration, but GWT does not use or depend on OpenSpec. GWT
  takes the collaboration artifact further by making the spec executable rather
  than treating it as a prompt or handoff document for separate code. Cucumber,
  SpecFlow/Reqnroll, and BDD examples also shape the language. New features
  should read like executable behavior steps over state, not like SQL or a
  general query language.
- Prefer explicit behavior signatures: `WHEN review <report> into <decision>`.
- Keep parser/runtime/checker behavior aligned. If one changes, look for tests
  in `tests/test_runtime.py`, `tests/test_checker.py`, and
  `tests/test_spec_v01.py`.
- Keep docs aligned with implementation. Syntax or semantic changes usually
  require updates to `docs/spec/v0.1.md`, `docs/grammar.md`,
  `docs/language.md`, and often `README.md`.
- Do not add new syntax without at least one runtime test, checker coverage
  when applicable, and an example or spec note.
- For collection features, prefer narrow step-like operations with explicit
  missing/failure cases. Avoid `SELECT` / `UPDATE` / `JOIN` style vocabulary,
  general query pipelines, or implicit set-based mutation unless the design
  principles are intentionally revised first.
- Behavior names cannot use built-ins or behavior-body keywords such as `set`,
  `count`, `sum`, `find`, `exists`, `LET`, `RETURN`, `PASS`, `IF`, `FOR`, or
  `FIND`.
- `REQUEST` contracts validate after `GIVEN` setup and before `WHEN`
  execution. `OUTPUT` contracts validate after execution.
- Stable run payloads use the envelope returned by `ExecutionResult.as_payload`;
  keep single-scenario and multi-scenario shapes stable.

## Formatter Expectations

`gwt format` is the canonical source formatter for v0.1.

- Keep all example `.gwt` files formatted.
- Formatter validation is syntax-oriented and permits request files whose DTOs
  are supplied by a paired rules file.
- If the grammar changes, update the formatter or add a test proving the
  formatter preserves the new syntax.

## Examples

Use examples to teach new language features:

- `examples/hello.gwt`: smallest runnable program.
- `examples/v01_language_tour/`: compact current-language tour.
- `examples/order_fulfillment/`: larger state-transition workflow.
- `examples/loan_underwriting/`: larger rules/workflow sample.
- `examples/minilang_spec/`: executable spec pressure test for tokens, AST
  records, evaluator state, errors, and JSON host input.

When adding a substantial feature, prefer a focused example over expanding
large examples unless the feature specifically belongs there.

Substantial public examples should include embedded `SCENARIO` blocks with
top-level `THEN` assertions. JSON request files are useful for host-facing
execution, but they do not replace executable scenario coverage. Reusable
modules and request-only files may be exceptions.

## Git Hygiene

- Do not revert unrelated user changes.
- Keep commits focused and include tests/docs/examples with behavior changes.
- Avoid generated metadata churn unless it is required.
- Run verification before pushing.
