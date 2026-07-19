# Agent Domain-Language Context

`gwt agent-context` turns a checked GWT program into a compact, deterministic
context pack for coding agents. It carries the executable slice of the
program's ubiquitous language without making a prompt, model, or agent
configuration the source of truth.

```sh
python -m gwtlang agent-context path/to/rules.gwt
python -m gwtlang agent-context path/to/rules.gwt \
  --request "review vendor" --scenario-limit 2
python -m gwtlang agent-context path/to/rules.gwt --json
```

The default Markdown is ready to place in an agent conversation. `--json`
emits the provider-neutral version-1 contract described by
[`schemas/agent-context.schema.json`](schemas/agent-context.schema.json). Use
`--output FILE` to write either form atomically.

## What The Pack Contains

The pack is generated from the same parsed semantic model as inspection,
checking, and execution. It includes:

- domain nouns and states as canonical `TYPE`, `RECORD`, and one-of record
  declarations;
- public request names with input and output contracts;
- domain behavior signatures with their contracts;
- a complete scenario index and up to two embedded executable scenarios;
- two small, unrelated worked syntax examples;
- the structured check, format, and validate workflow;
- parser or checker diagnostics when the source does not yet check;
- the portable dependency-closure identity for file-backed programs.

The two generic examples are intentional. The first captured model matrix found
that inspection alone helped repair existing GWT but did not teach either model
enough syntax to author any of five new behaviors. Adding two small worked
examples changed both models from `0/5` to `5/5` authoring success after repair.
The context pack turns that result into a repeatable product surface rather
than relying on a carefully assembled prompt.

The provider-neutral evaluation harness exposes an `agent-context` context
variant so the exact generated Markdown can be compared with `source-only`,
raw `inspect`, and the longer `guide` condition. See
[agent-evaluation.md](agent-evaluation.md).

## Request Scoping

Pass `--request NAME` to embed only scenarios that directly invoke that public
request. All types, requests, behavior signatures, and the full scenario index
remain present because a request can depend on reusable domain vocabulary.
`--scenario-limit 0` omits scenario source while retaining the index.

Request scoping is deliberately conservative. It does not guess a transitive
semantic dependency graph from names or hide apparently unrelated domain
types. If no embedded scenario directly invokes the selected request, the pack
says so instead of substituting an unrelated example.

## How Skills Fit

A Codex, Claude, or other agent skill can call `gwt agent-context --json` and
place the result into its own provider-specific workflow. The skill should be a
thin adapter: it should not copy the program's records, behaviors, scenarios,
or durable rules into skill instructions. Regenerating the context from the
checked program prevents that knowledge from drifting.

This separation also keeps GWT usable without a skill. Editors, CI systems,
local scripts, and future agent runtimes can consume the same JSON contract.
The Python API exposes `build_agent_context_file`,
`build_agent_context_source`, and `GwtClient.agent_context()`.

## Trust And Review Boundary

The pack may contain domain names, type shapes, scenario values, source paths,
and behavior contracts. Treat it with the same sharing and retention policy as
the source program. It is not a sanitization or access-control boundary.

The generated Markdown and JSON are context artifacts, not normative specs.
Review and commit the resulting `.gwt` change and its executable scenarios.
Do not commit a model transcript as a substitute for the program, and do not
accept a change merely because it parses. Final acceptance still requires
canonical formatting, checking, and scenario validation.
