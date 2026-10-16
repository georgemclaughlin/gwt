# Native maintenance model experiment

`experiment.py` connects the frozen five-domain task corpus, tool-free model
requests, public repairs, and the isolated native/Python scorer. The complete
workflow has been rehearsed with synthetic provider replies and real containers.
The Responses API transport has mocked contract tests but has **not yet been
qualified with a live API call**. No API key was configured during preparation.

## Run

Select an exact model available to your API account and its supported reasoning
effort. The runner makes no model substitution. Configure `OPENAI_API_KEY` in the
calling process without placing it in command arguments, source, or artifacts.
Use a previously qualified native executable and an existing local Docker image
as described in [scoring](scoring.md).

```sh
python -m evaluations.native_maintenance.experiment --qualification /path/to/qualification --native /path/to/gwt-native --image python:3.12-slim --model MODEL_ID --reasoning-effort medium --maximum-attempts 3 --maximum-output-tokens 16000 --output /path/to/new-experiment
python -m unittest tests.test_native_maintenance_experiment
```

The output directory must be new. The frozen corpus contains thirty tasks:
five domains, two languages, and three repeats. The runner follows frozen task
order in each round, alternating language order within pairs. Default settings
permit at most ninety provider requests. Calls are sequential. The output-token
cap and attempt cap bound requested work; they are not a dollar budget or a
prediction of actual usage. An unsupported model/setting or transport failure
stops the run rather than silently selecting another model or retrying.

## Model and scoring boundaries

Every request contains only an explicit projection of the public task: intent,
baseline source, guide, request name, public examples, and output contract. Repair
requests add the preceding normalized response and public feedback. Requests use
`tools: []`, `tool_choice: "none"`, structured JSON output, and `store: false`.
No shell, file, search, or external tool is exposed or dispatched. Each call is
independent; no provider conversation ID carries earlier tasks or hidden context.

The adapter follows official OpenAI documentation for
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
and [Responses text generation](https://developers.openai.com/api/docs/guides/text).
Schema conformance does not prove correctness: refusals, incomplete messages,
unexpected output types, duplicate JSON fields, and invalid response shapes are
recorded as unsuccessful generation attempts. They consume the attempt budget
and receive response-format feedback. Their raw provider response remains intact;
the scorer receives an explicitly annotated empty-source failure placeholder.

Public execution uses only the two public inputs for that task. A public pass
ends that task's repair loop. A failure may trigger the next attempt up to the
cap. After all public rounds, the runner seals the response file by digest and
only then executes full scoring. There are no provider calls after the seal;
withheld outcomes cannot trigger another repair. Successful public feedback
does not establish withheld correctness.

Generated code executes in the scorer's bounded containers, separately from the
credential-bearing API process. The API key is never passed to candidate execution
or written into request artifacts. Python candidate evaluation remains cooperative,
with the protocol limitations documented in the scoring guide.

## Evidence and interrupted runs

The run retains frozen task/corpus/qualification files, code hashes, model and
reasoning settings, execution-image identity, every exact API request and raw
transport response, normalized candidate attempts, public feedback, per-attempt
execution observations, and a final report. Each completed call records the
provider's response/request IDs, returned model, reported usage, duration, and
prompt UTF-8 byte count. Missing usage stays missing. No prices or token counts
are inferred, and API call time is kept separate from candidate execution time.

`run.json` records a pending request before sending it. Responses are recorded
before candidate execution, and JSON/checkpoint replacements are atomic. This
supports inspection after interruption; it is not a guarantee against storage
loss. A timeout, HTTP failure, or execution-infrastructure failure stops the run
and preserves partial evidence. The provider transport bounds response size at
twenty MiB and uses a configurable socket timeout (default 300 seconds), which
is an I/O timeout, not a strict whole-request wall-clock deadline.

There is no automatic resume or transport retry. An interrupted request may
already have reached the provider and incurred usage. Inspect `pendingCall` and
its retained transport artifact before deciding what to do. Do not restart a
complete experiment to conceal failed or missing trials. Existing response files
can be scored independently using the isolated scorer; missing tasks remain in
its denominator. Partial experiments must be reported as partial.

`report.json` is authoritative only with `run.json` status `complete` and matching
recorded hashes. A source change during execution invalidates the run. An
interrupted full-scoring phase retains the sealed responses and execution files
but does not establish a completed experiment.

## Qualification

```sh
python -m evaluations.native_maintenance.qualify_experiment --qualification /path/to/qualification --native /path/to/gwt-native --image python:3.12-slim --output /path/to/new-rehearsal
```

This uses a clearly labeled synthetic provider, not model calls. Refund starts
with unchanged source and repairs once; allocation deliberately passes public
examples while retaining a withheld bug. Other domains use correct references.
See the [retained rehearsal](2026-10-16-experiment/README.md). Live provider
qualification, actual model maintenance results, and human-review benefit remain
separate evidence requirements.
