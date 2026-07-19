# DSLs, Semantic Models, And LLMs

GWT treats an LLM as a replaceable collaborator around an executable domain
language. It does not make an LLM, a prompt, or generated host code part of the
runtime semantics.

This model is consistent with the two roles described in Unmesh Joshi's
[DSLs Enable Reliable Use of LLMs](https://martinfowler.com/articles/llm-and-dsls.html),
published on Martin Fowler's site: an LLM can help discover a domain model, and
after that model stabilizes it can serve as a natural-language interface to a
constrained vocabulary.

## The Three Layers

A GWT module has three related layers:

1. The core behavior language supplies deterministic state, contracts, control
   flow, checking, formatting, execution, and evidence.
2. A program supplies the semantic model for one domain through types, records,
   requests, behavior signatures, and invariants.
3. Scenarios supply executable evidence that the domain vocabulary means what
   its authors intend.

The second and third layers are the program-specific DSL. In vendor onboarding,
sentences such as `require document ...`, `score risk signals ...`, and
`classify decision` constrain an author far more effectively than the generic
ability to `set` or `add` values.

This is why GWT should be described precisely: it is an executable
domain-language workbench for defining and running small domain DSLs. It turns
the executable slice of a team's ubiquitous language into a checked program;
it does not generate custom grammars, and a program is not automatically a good
domain model merely because its syntax reads like English.

## Two Phases Of Work

### Discovering the language

Early work is semantic design. Authors identify domain facts, missing states,
behavior boundaries, observable outputs, and scenarios that expose awkward
abstractions. An LLM can propose alternatives and translate examples, but this
is the phase where people must understand and own the design.

Pressure from implementation and realistic scenarios is evidence. If a domain
operation is repeatedly awkward, first ask whether a better behavior signature
or record boundary solves it. New core syntax is the last option.

### Using the language

Once the program vocabulary is stable, a natural-language request should map to
small changes in records, behaviors, requests, and scenarios. The agent can run
the deterministic toolchain and repair its proposal without asking a person to
interpret Python stack traces or generated host code.

The intended loop is:

```text
domain intent
  -> proposed .gwt change
  -> check and structured diagnostics
  -> canonical format
  -> executable scenarios and request invariants
  -> reviewed .gwt source
```

## Source Of Truth

Prompts are transient inputs. Generated types, JSON Schema, OpenAPI, traces,
Execution Cases, comparisons, and workbench pages are projections or evidence.
The checked `.gwt` dependency closure is the durable behavior definition.

This has practical consequences:

- an agent change is incomplete without executable scenario evidence when the
  changed behavior is scenario-testable;
- host code must not reimplement rules that belong in the GWT program;
- inspection and evidence must identify the complete `USE` dependency closure;
- generated scenarios must be checked and replayed before they are accepted;
- explanations report executed facts and must not invent business intent.

## Validator And Repair Contract

An agent needs more than an exit code. JSON diagnostics provide a stable base
code, a repair-specific `subcode`, a source range, and—when known—structured
`expected`, `actual`, `candidates`, and `help` values. Human-readable messages
remain useful, but agents should branch on codes and fields rather than parse
prose.

`gwt inspect --json` supplies the current domain vocabulary. For file-backed
programs it includes both the compatible entry-source `programHash` and a
portable `programIdentity` for the complete dependency closure. A source-only
inspection cannot establish filesystem closure identity and reports
`programIdentity: null`.

`gwt agent-context` packages that semantic vocabulary with selected executable
domain scenarios, two small syntax examples, and the check/format/validate loop.
Its Markdown form is prompt-ready; its versioned JSON form is suitable for a
provider-specific skill or agent runtime. The pack is derived context, while
the checked `.gwt` program remains the durable source of truth. See
[agent-context.md](agent-context.md).

## Semantic Model Boundary

The parser should produce a typed semantic representation that the checker,
runtime, debugger, symbols, tracing, and inspection surfaces share. Consumers
should not independently rediscover whether raw text represents a builtin,
behavior call, or control statement.

Typed leaf statements retain the original source line, semantic kind, command,
token stream, and common expression, binding, and target operands. The checker,
runtime, and symbol index consume that shared parse result instead of
re-tokenizing the same statement. More complex expressions and block forms can
migrate incrementally behind the same boundary. This is an implementation
boundary, not a reason to add syntax or expose a second JSON/YAML rule
representation.

## Constraint Budget

The LLM advantage diminishes as a DSL accumulates equivalent ways to express
the same intent. GWT should therefore preserve a constraint budget:

- prefer domain behaviors over repeated low-level mutation;
- prefer explicit missing and failure cases;
- keep public work behind named requests and typed contracts;
- require realistic scenario pressure before adding syntax;
- improve examples, inspection, and diagnostics before expanding grammar;
- avoid general query, orchestration, networking, persistence, or prompt syntax.

The goal is not to make every valid program easy to generate. It is to keep the
valid programs for a particular domain narrow, reviewable, and deterministically
verifiable.

## What GWT Deliberately Does Not Own

GWT does not need an embedded chat interface or a dependency on a particular
model. External agents can evolve independently while the language contract
stays stable. Product discovery, UX judgment, non-deterministic integration,
deployment, authorization, and broad architecture remain outside the DSL.

The benchmark for LLM support is also behavioral, not aesthetic: can a model
produce a change that parses, checks, formats, validates, and satisfies the
requested scenarios with a small number of repair iterations? The executable
authoring corpus described in [agent-authoring.md](agent-authoring.md) makes
that question measurable.
