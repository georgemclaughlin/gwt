# GWT Language Specifications

This directory contains versioned language specifications. Each spec describes
the syntax, execution model, checker expectations, and tool-facing contracts for
one implemented language surface.

- [v0.2](v0.2.md) is the current implemented language version.
- [v0.1](v0.1.md) records the previous program-contract/entry-boundary model.

Use `gwt version --json` to inspect the installed package version, current
language spec version, and stable CLI/API payload schema version:

```sh
python -m gwtlang version --json
```

These version surfaces move independently:

- `packageVersion` identifies the installed Python package.
- `languageSpecVersion` identifies the current implemented source language.
- `payloadSchemaVersion` identifies the JSON payload contract used by commands
  such as `check`, `inspect`, `validate`, and `version`.

The formatter targets the current spec's source layout rules. Grammar-only
changes should update the versioned spec, [../grammar.md](../grammar.md), and
the v0.2 conformance tests in
[`../../tests/test_spec_v02.py`](../../tests/test_spec_v02.py).

Non-normative design guidance lives in
[../design-principles.md](../design-principles.md). Use it when evaluating new
syntax so GWT stays close to BDD-style executable examples instead of drifting
toward SQL-like query syntax.

The broader product thesis is in [../spec-is-code.md](../spec-is-code.md):
natural language may describe intent, but executable GWT defines normative
behavior for deterministic workflows.

Forward-looking stabilization work is tracked in
[../roadmap-v0.3.md](../roadmap-v0.3.md). The concrete release-candidate gate is
[../release-v0.3-checklist.md](../release-v0.3-checklist.md). Real workflow
trials should use [../pilot-evaluation.md](../pilot-evaluation.md) so syntax
pressure is grounded in executable examples.
