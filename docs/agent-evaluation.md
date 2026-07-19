# Evaluating Agent-Authored GWT

GWT's agent benchmark measures whether a model can author, repair, or decline
to guess an executable domain program. It does not compare generated text to a
gold file, and it does not depend on a model provider.

The corpus is `tests/fixtures/agent_authoring/manifest.json`. Its 15 cases cover
five authoring tasks, six repairs, and four intentionally ambiguous requests.
Gold sources and hidden request probes remain in the repository so the scorer
is reproducible, but `prepare` never includes them in model-facing tasks.

## Prepare Blind Tasks

Choose one context variant:

- `source-only` supplies the task plus its starter or broken GWT source;
- `inspect` also supplies the structured inspection payload for that source;
- `guide` adds the canonical agent-authoring guide plus the unrelated hello and
  typed language-tour programs as worked examples. It does not include corpus
  gold sources or hidden probes.

```sh
python -m gwtlang.agent_evaluation prepare \
  tests/fixtures/agent_authoring/manifest.json \
  --variant source-only \
  --output /tmp/gwt-source-only.jsonl

python -m gwtlang.agent_evaluation prepare \
  tests/fixtures/agent_authoring/manifest.json \
  --variant inspect \
  --output /tmp/gwt-inspect.jsonl

python -m gwtlang.agent_evaluation prepare \
  tests/fixtures/agent_authoring/manifest.json \
  --variant guide \
  --output /tmp/gwt-guide.jsonl
```

Each line is an independent task object with a `caseId`, `kind`, task text,
context variant, context, and response contract. Run variants as separate
experiments; do not mix them into one aggregate score.

## Record Attempts

The model harness writes one JSON object per attempt. A code attempt has this
shape:

```json
{"caseId":"repair-domain-behavior-typo","attempt":1,"action":"code","source":"<complete GWT source>"}
```

A clarification response has this shape:

```json
{"caseId":"clarify-decimal-rounding-policy","attempt":1,"action":"clarify","clarifications":["What scale and rounding mode apply?","Are discounts applied before tax?"]}
```

`source` is the complete candidate, not a diff or a fenced Markdown block.
Attempt numbers are positive integers. Preserve failed candidates as earlier
attempts and increment the number after feeding deterministic diagnostics back
to the model. The scorer orders attempts by number and treats the last one as
the final answer.

Alongside the response JSONL, record the provider, exact model/version, sampling
settings, system instructions, date, context variant, and repair policy. Those
facts affect results but do not belong in the executable GWT artifact.

## Score A Run

```sh
python -m gwtlang.agent_evaluation score \
  tests/fixtures/agent_authoring/manifest.json \
  /tmp/gwt-agent-responses.jsonl \
  --output /tmp/gwt-agent-report.json
```

The report includes per-attempt parser, checker, formatter, scenario, semantic,
and clarification outcomes. Its aggregate metrics are:

- `firstPassParseRate`: first attempt is code and parses, over all author/repair
  cases;
- `firstPassCheckRate`: first attempt is code and has no checker errors, over all
  author/repair cases;
- `finalValidationRate`: final code checks, is canonically formatted, and runs
  the required number of scenarios, over all author/repair cases;
- `scenarioSemanticSuccessRate`: final code also satisfies hidden request
  probes, over all author/repair cases;
- `correctClarificationRate`: final clarification covers every required domain
  concept, over clarification cases;
- `repairAttemptedCaseCount`: code cases with more than one recorded attempt;
- `repairRecoveryRate`: attempted repairs whose final code validates and passes
  semantic probes;
- `medianRepairIterations`: median final successful attempt number minus one.

An omitted case counts as unsuccessful in the relevant rate. Parse and checker
rates deliberately exclude clarification cases; clarification rate deliberately
excludes code cases.

## Optional Isolated Codex Runner

`gwtlang.agent_matrix` is a provider-specific capture harness layered outside
the provider-neutral evaluator. It runs each prepared task in a fresh read-only
temporary directory, requests structured output, checkpoints partial results,
and preserves raw stdout/stderr logs in its output directory.

```sh
python -m gwtlang.agent_matrix /tmp/gwt-guide.jsonl \
  --model MODEL_ID --reasoning-effort high \
  --output-dir /tmp/gwt-model-guide --jobs 4

python -m gwtlang.agent_evaluation score \
  tests/fixtures/agent_authoring/manifest.json \
  /tmp/gwt-model-guide/responses.jsonl
```

To run a bounded public repair pass, point a new output directory at the prior
responses:

```sh
python -m gwtlang.agent_matrix /tmp/gwt-guide.jsonl \
  --model MODEL_ID --reasoning-effort high \
  --repair-responses /tmp/gwt-model-guide/responses.jsonl \
  --output-dir /tmp/gwt-model-guide-repair --jobs 4
```

Only public parser, checker, formatter, and scenario-runtime feedback is used.
Format-only failures are normalized deterministically without another model
call. Hidden probes and clarification concepts are never added to repair
prompts. The repair output's `responses.jsonl` contains the prior attempts plus
the new attempts and can be scored directly.

## Interpreting Results

Semantic success is behavioral. A candidate may differ from the gold source if
it passes normal validation, has enough executable scenarios, and produces the
hidden request results. The current probes are a focused regression signal, not
a proof that two arbitrary programs are equivalent.

Clarification scoring is concept-based and intentionally conservative. It
checks whether the response asks about the missing decision; it does not grade
writing style or accept code that silently chooses a policy.

Run model output in an isolated working directory or container. The evaluator
executes candidate GWT and is a deterministic scoring harness, not a security
boundary for untrusted provider output.

The repository test provides the evaluator's deterministic gold baseline:

```sh
python -m unittest tests.test_agent_authoring
```

This proves the corpus, blind preparation, response protocol, gates, hidden
probes, and repair accounting are internally consistent. It is not a claim
about any live model. Live-model results should only be reported when the raw
responses and run metadata have actually been captured.

The first captured live baseline is documented under
[`evaluations/agent-authoring/2026-07-18`](../evaluations/agent-authoring/2026-07-18/README.md).
It also preserves a later retired `agent-context` composition experiment
alongside the three supported context conditions. The exact prepared tasks,
raw responses, and reports remain reproducible historical evidence; the
composition was deliberately removed from the public CLI and current task
preparer. See [agent-context-experiment.md](agent-context-experiment.md).
