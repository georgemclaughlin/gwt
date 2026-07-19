# Authoring GWT With Agents

This guide defines the supported agent workflow. Natural language can propose
intent, but the checked and scenario-backed `.gwt` program is the source of
truth.

## Gather The Domain Context

Start with the target source and its concise machine-readable vocabulary:

```sh
python -m gwtlang inspect path/to/rules.gwt --json
```

The manifest identifies records, type aliases, one-of records, named requests,
behavior signatures and contracts, scenarios, direct imports, diagnostics, and
the complete file-backed program identity. Read the relevant scenarios as
worked examples; they express semantic expectations that a manifest cannot.

For a new program, use the smallest relevant examples rather than the entire
repository. Usually that means `examples/hello.gwt`,
`examples/language_tour/rules.gwt`, and one example close to the target domain.

## Separate Discovery From Generation

If names, record boundaries, missing states, or precedence rules are unclear,
stop treating the task as mechanical generation. Propose alternatives and add
pressure-test scenarios before selecting the abstraction.

Once the domain vocabulary is settled, keep the proposed change within it.
Prefer an existing behavior sentence over expanding the same intent into
generic `set`, `add`, or collection machinery.

## Generate And Repair

Use this loop after each small edit:

```sh
python -m gwtlang check path/to/rules.gwt --json --lint
python -m gwtlang format path/to/rules.gwt
python -m gwtlang validate path/to/rules.gwt --json --lint
```

Interpret diagnostics in this order:

1. Use `code` for the stable diagnostic family.
2. Use `subcode` for the repair-specific condition.
3. Use the source `range` to constrain the edit.
4. Use `expected`, `actual`, `candidates`, and `help` when present.
5. Re-run the complete loop; do not assume a syntactic repair preserved intent.

`validate` checks semantics, canonical formatting, and executable scenarios.
Do not skip scenario execution in the final pass merely because `check`
succeeds.

## Required Shape Of A Behavior Change

A substantial change should normally contain:

- domain-shaped records or aliases for new facts;
- explicit behavior signatures for new operations;
- a named request contract change when the host boundary changes;
- request invariants for properties that must hold on every call;
- scenarios covering the normal, boundary, missing, and precedence cases;
- documentation when language semantics or public examples change.

If the intended outcome cannot be expressed as observable state and assertions,
the request is still underspecified. Ask for the missing decision rather than
encoding an arbitrary assumption in executable rules.

## Acceptance Criteria

An agent-authored change is acceptable when:

- the complete dependency closure is the one that was inspected and reviewed;
- the program parses and has no checker errors;
- canonical formatting is stable;
- embedded scenarios and request invariants pass;
- the scenarios demonstrate the requested behavior rather than merely execute;
- host projections remain generated from GWT contracts;
- no durable rule exists only in a prompt, transcript, fixture explanation, or
  generated client.

## Evaluation Corpus

The model-independent corpus lives in
`tests/fixtures/agent_authoring/manifest.json`. It contains three case classes:

- `author`: natural-language intent paired with a valid gold GWT artifact;
- `repair`: a broken candidate, required diagnostic subcodes, and a repaired
  artifact that must validate;
- `clarify`: intent that lacks a domain decision and therefore requires explicit
  clarification rather than code generation.

Run its executable contract with:

```sh
python -m unittest tests.test_agent_authoring
```

Prepare blind, provider-neutral tasks and score an external model run with:

```sh
python -m gwtlang.agent_evaluation prepare \
  tests/fixtures/agent_authoring/manifest.json \
  --variant inspect --output /tmp/gwt-agent-tasks.jsonl

# Send each task through the model harness of your choice, preserving every
# attempt in the response JSONL described in agent-evaluation.md.

python -m gwtlang.agent_evaluation score \
  tests/fixtures/agent_authoring/manifest.json \
  /tmp/gwt-agent-responses.jsonl --output /tmp/gwt-agent-report.json
```

See [agent-evaluation.md](agent-evaluation.md) for context variants, the JSONL
response contract, metric denominators, repair-loop guidance, and interpretation
limits.

When evaluating a model, preserve the task text, model/version, supplied
context, raw candidate, repair iterations, and final result outside the runtime
artifact. Report at least:

- first-pass parse rate;
- first-pass checker rate;
- final validation rate;
- median repair iterations;
- scenario-semantic success rate;
- correct clarification rate.

The gold source is not a text-match target. A different candidate succeeds when
it stays within the intended domain vocabulary and passes the behavioral gates.

## Prompt Template

Prompts are replaceable inputs, but a compact template can keep the interaction
focused:

```text
Using the inspected GWT records, requests, behavior signatures, and scenarios,
implement this domain behavior: <intent>.

Keep the change in executable GWT. Add or update scenarios for normal,
boundary, missing, and precedence cases. Do not put domain rules in host code.
Run check, format, and validate, repairing structured diagnostics. If a domain
decision is missing, identify it instead of choosing one silently.
```

Do not commit this prompt as the normative specification. Commit the resulting
reviewed GWT behavior and evidence.
