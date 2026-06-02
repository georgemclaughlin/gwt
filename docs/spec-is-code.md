# Spec Is Code

GWT is built around one product thesis: for deterministic domain behavior, the
durable specification should be the executable artifact.

Spec-driven tools can make prompts, plans, and requirements much better. They
can organize context, preserve decisions, and guide agents through safer
implementation workflows. But if the spec remains Markdown that an agent
interprets into separate code, the final behavior still depends on a semantic
handoff.

GWT tries to remove that handoff for the rules and workflow layer.

## The Handoff Problem

In a prompt-centered spec workflow, a typical path is:

```text
intent -> Markdown spec -> agent interpretation -> host code -> tests
```

Each arrow can change meaning. The spec can be clear to one reviewer and still
be implemented differently by another agent or developer. Tests can catch some
drift, but the specification and implementation remain separate artifacts.

In GWT, the intended path is:

```text
intent -> executable GWT -> runtime result
```

Natural language can still help discover and describe intent. The difference is
that normative behavior becomes the `.gwt` program:

- `GIVEN` creates concrete state.
- `WHEN` defines and invokes executable behavior.
- `THEN` checks observable outcomes.
- `RECORD`, `REQUEST`, and `OUTPUT` define runtime contracts.
- The checker, formatter, runtime, CLI, LSP, and debugger all operate on the
  same source.

## What Becomes Unambiguous

GWT does not make every product question unambiguous. Humans still need to
decide what matters, which domain concepts to name, where boundaries belong,
and which tradeoffs are acceptable.

GWT can make deterministic behavior unambiguous once it is expressed:

- whether a request satisfies its contract
- which behavior runs for a given state
- how state changes after each step
- which outputs a host application receives
- which scenarios pass or fail
- which missing or failure cases are explicit

If a requirement cannot be expressed as state, behavior, contracts, and
assertions, it is still underspecified for GWT's runtime purposes.

## What GWT Should Own

GWT is a good fit for:

- business rules
- deterministic workflows
- request/response decision programs
- validation and normalization
- state transitions
- executable examples and regression scenarios
- domain contracts that host applications call through JSON/API boundaries

GWT should not try to own every part of software development. Product vision,
UX taste, broad architecture, deployment strategy, and non-deterministic
integrations can still live in surrounding docs and host systems. Those systems
can call GWT, but durable domain behavior should remain visible in GWT source.

## Working With Agents

Agents are useful collaborators for GWT, but they should improve the executable
spec instead of bypassing it.

A good agent-generated change should usually include:

- updated `.gwt` behavior
- updated or new executable scenarios
- record, request, or output contract changes when the interface changes
- docs updates when language semantics or examples change

This keeps the agent from being the hidden interpreter of the spec. The final
artifact is still parseable, checkable, executable GWT.
