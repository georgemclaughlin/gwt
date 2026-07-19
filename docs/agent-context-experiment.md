# Retired Agent Context Experiment

GWT briefly exposed an experimental `gwt agent-context` command that combined
inspection data, selected scenario source, authoring guidance, worked syntax
examples, and validation commands into Markdown or a versioned JSON payload.
The command, schema, and public Python API were removed before release.

## What We Learned

The experiment confirmed useful ingredients for agent-assisted GWT work:

- program-specific records, requests, and behavior signatures ground domain
  vocabulary;
- canonical worked examples help models author unfamiliar GWT syntax;
- structured diagnostics and bounded repair loops improve recovery;
- ambiguous domain policy should produce clarification rather than invented
  behavior.

The exact-pack matrix was a meaningful middle condition. After two public
repair rounds, Luna/low passed 2/5 authoring, 6/6 repair, and 4/4 clarification
cases; Sol/high passed 3/5, 6/6, and 4/4. The longer guide condition still
passed all five authoring cases for both models.

## Why It Was Retired

The feature mixed semantic inspection with prompt policy, tutorial examples,
source-excerpt heuristics, and shell workflow. Publishing that composition as
a stable CLI, JSON schema, and SDK surface made experimental agent guidance
part of the language contract. Its request filtering was also too broad to be
a true semantic slice and too shallow to stand alone.

GWT's stable responsibility is executable domain semantics and deterministic
tooling. Agent-specific orchestration can evolve in documentation or a thin
skill by reading source, `gwt inspect --json`, relevant examples, and structured
diagnostics, then running check, format, and validate.

If a future editor, skill, or other tool needs a smaller semantic view, the
appropriate core addition is an agent-neutral inspection projection: AST-backed
source ranges, request-to-behavior dependencies, referenced types, and relevant
scenario locations. It should expose facts rather than prompt prose.

## Preserved Evidence

The exact tasks, raw candidates, repair attempts, run metadata, and deterministic
reports remain under
[`../evaluations/agent-authoring/2026-07-18`](../evaluations/agent-authoring/2026-07-18/README.md).
Those checked-in tasks can still be sent directly through the optional matrix
runner, and every response stream remains re-scorable with the provider-neutral
evaluator.
