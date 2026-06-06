# GWT Language Specifications

This directory contains versioned language specifications. Each spec describes
the syntax, execution model, checker expectations, and tool-facing contracts for
one implemented language surface.

- [v0.2](v0.2.md) is the current implemented language version.
- [v0.1](v0.1.md) records the previous program-contract/entry-boundary model.

The formatter targets the current spec's source layout rules. Grammar-only
changes should update both the versioned spec and [../grammar.md](../grammar.md).

Non-normative design guidance lives in
[../design-principles.md](../design-principles.md). Use it when evaluating new
syntax so GWT stays close to BDD-style executable examples instead of drifting
toward SQL-like query syntax.

The broader product thesis is in [../spec-is-code.md](../spec-is-code.md):
natural language may describe intent, but executable GWT defines normative
behavior for deterministic workflows.
