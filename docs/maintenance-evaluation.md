# Paired maintenance evaluation

This experiment asks whether GWT improves maintenance over ordinary Python.
It extends the authoring benchmark without changing its historical results or
the language contract. The initial corpus is deliberately small: three
successive refund-rule changes and one underspecified goodwill exception.
The [October 15 live trial](../evaluations/maintenance/2026-10-15/README.md)
found first-pass success on all nine code trials per language and all three
clarification trials per language. This is a small guided-use result, not
evidence of GWT superiority. Deterministic harness checks are reported separately.

The subsequent [native maintenance corpus](../evaluations/native_maintenance/README.md)
prepares five domains, including a larger exact-allocation change, for Rust GWT
and Python. Its 6,828 reference executions qualify fixtures and independent
expectations; no live model results are claimed. Its separate
[isolated scorer](../evaluations/native_maintenance/scoring.md) now supports
bounded native/Python execution and public-only repair feedback, qualified with
synthetic responses and actual container checks. The
[native experiment runner](../evaluations/native_maintenance/experiment.md) now
connects public repairs to tool-free API requests; live provider qualification
and the native model comparison remain pending. The older worker described below
uses Python GWT and must not score the native allocation task.

## Comparable tasks

`evaluations/maintenance/manifest.json` supplies paired GWT/Python starters,
identical task intent, public boundary examples, and independent expected
results. Each code task has 112 acceptance inputs covering seven age boundaries
and every combination of four boolean facts. Every probe is labeled either
`changed` or `preserved` relative to the starter. Reasons count as outputs.

The two public examples per task are included in the acceptance set; the
remaining 110 inputs are withheld during preparation. Sources and fixtures are
public for reproducibility, so run model tasks away from the checkout.
"Held out" describes the prompt boundary, not secrecy or training contamination.

Python returns the same JSON decision object from `decide(state)`. Both arms
are scored on independent outputs. GWT checking happens before execution;
formatting and agent-authored test counts are not comparative score gates.
GWT gets the existing authoring guide; Python gets a short boundary guide.
This is a practical guided-use comparison, not equal prompt-token allocation.
Record context size and cost separately.

## Prepare and score

Run each language independently, with at least three repeats:

```sh
python -m gwtlang.maintenance_evaluation prepare \
  evaluations/maintenance/manifest.json --language gwt --repeats 3 \
  --output /tmp/gwt-maintenance-tasks.jsonl
python -m gwtlang.maintenance_evaluation prepare \
  evaluations/maintenance/manifest.json --language python --repeats 3 \
  --output /tmp/python-maintenance-tasks.jsonl
```

Each task has a unique `caseId`, a shared `pairId`, and a trial number. Record
attempts using the existing response protocol:

```json
{"caseId":"damage-precedence-python-1","attempt":1,"action":"code","source":"<complete source>","clarifications":[]}
```

The optional `gwtlang.agent_matrix` runner accepts both languages and returns
only public example feedback on repair. Its model/version, effort, task digest,
durations, and raw-response records remain applicable. Use the same model,
effort, repair allowance, and execution policy for both arms. Alternate or
randomize language order to reduce temporal bias.

```sh
python -m gwtlang.agent_matrix /tmp/gwt-maintenance-tasks.jsonl \
  --model MODEL_ID --output-dir /tmp/gwt-maintenance-model
python -m gwtlang.agent_matrix /tmp/python-maintenance-tasks.jsonl \
  --model MODEL_ID --output-dir /tmp/python-maintenance-model
python -m gwtlang.maintenance_evaluation score \
  evaluations/maintenance/manifest.json \
  /tmp/python-maintenance-model/responses.jsonl \
  --language python --repeats 3 --output /tmp/python-maintenance-report.json
```

Prepare fresh tasks for each experiment. Preserve failed attempts; numbering
starts at one and remains contiguous. Missing tasks count as failures.
Unknown case IDs, duplicate attempts, and skipped attempt numbers are rejected.
Reports record task and manifest digests. Retain prepared tasks and the exact
repository revision so later guide edits cannot be mistaken for the original
experiment context.

Candidates execute in temporary subprocesses with a timeout. This does not
restrict filesystem or network permissions. Score untrusted Python/model output
inside a disposable container without credentials. Expected outputs are not
sent to the worker; the parent scores returned values. The harness evaluates
cooperative authoring, not adversarial code.

## Interpret results

Report first-pass and final all-probe success, changed/preserved probe counts,
repair recovery, successful repair iterations, and clarification outcomes.
Missing runs remain in the denominator. Public repair success does not imply
held-out correctness. Clarification grading uses declared lexical concepts;
manually inspect disagreements rather than claiming semantic proof.

Collect latency, token usage, and cost from actual provider records; the scorer
does not guess them. Include raw per-trial outcomes alongside aggregate rates.
Add unrelated domains and larger changes before generalizing from this corpus.

For review time, use the [refund rehearsal](../examples/refund_review/README.md).
Counterbalance GWT-workbench and Python-source/test conditions across reviewers;
do not show one reviewer both versions of the same task in sequence and call
the times independent. Include wrong and correct candidates, record detected
and missed mistakes, and state expected results before viewing execution traces.

The separate [human source-review protocol](human-review-study.md) now provides
an offline participant kit across four domains, balanced GWT/Python assignments,
correct and faulty candidates, prediction questions, timing, and raw answer
capture. It tests source comprehension without workbench assistance. Its local
qualification contains only synthetic rehearsals; participant evidence is still
missing.

## Deterministic baseline

```sh
python -m unittest tests.test_maintenance_evaluation tests.test_semantic_invariants
```

The reference GWT and Python candidates pass all 336 code-task probes each.
Unchanged starters preserve existing behavior but fail the requested changes.
Tests cover omitted/invalid attempts, repairs, timeouts, noisy output,
boolean-vs-number equality, and public-example overfitting. These are evaluator
checks, not live-model results.
