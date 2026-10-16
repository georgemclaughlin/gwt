# Live paired maintenance trial — October 15, 2026

**Both GWT and Python passed every code task on the first attempt.** This small
trial demonstrates that the model can maintain these rules in either language;
it does not establish a GWT advantage.

| Measure | GWT | Python |
| --- | ---: | ---: |
| Code trials passing all acceptance probes, first attempt | 9/9 | 9/9 |
| Code trials passing all acceptance probes, final attempt | 9/9 | 9/9 |
| Changed outcomes correct | 261/261 | 261/261 |
| Preserved outcomes correct | 747/747 | 747/747 |
| Clarification trials passing | 3/3 | 3/3 |
| Repair calls | 0 | 0 |
| Median code-call elapsed seconds | 24.305 | 13.334 |
| Median code-call CLI-reported tokens used | 21,219 | 19,246 |
| Median serialized code-task size, UTF-8 bytes | 9,752 | 3,001 |

Each arm contains three policy changes repeated three times, plus the same
ambiguous exception request repeated three times. These are **three distinct
code tasks in one domain**, not nine independent domains. Each code trial has
112 probes: two public examples and 110 inputs withheld from the prompt.
The repeated probe totals are 1,008 per language, including 990 withheld checks.
Clarification grading uses lexical concepts; all six responses were also read
and asked about eligibility, precedence, and the returned decision/reason.

## Conditions

- Requested and CLI-reported model: `gpt-6-astra`, reasoning effort `medium`.
- Codex CLI `0.162.1`; default sampling, no explicit seed or temperature.
- Three repeats; maximum two repair rounds using only public-probe feedback.
  Every public probe passed, so no repair calls were made. Recovery rate is
  unmeasured, not 100%.
- Tasks were paired with alternating language order. The first GWT call was
  an infrastructure smoke, retained as trial one. The remaining 23 calls ran
  with two workers. There were no missing responses, timeouts, or discarded
  model attempts.
- Each model call used a fresh temporary directory, read-only execution, and
  instructions to use only the task record without tools. Model calls did not
  receive the withheld probes. The fixtures are public; this is not a claim
  about training-data contamination or adversarial secrecy.
- Generated candidates were scored in Python 3.12 containers with no network,
  no credentials, read-only source mounts, restricted resources, and temporary
  writable storage. Public feedback was computed in the same environment.
- GWT received its authoring guide and a scenario-backed starter; Python
  received a shorter boundary guide and a `decide(state)` starter. GWT prompts
  also request executable scenarios. Elapsed time therefore measures these
  guided workflows, not language efficiency with matched prompts or outputs.

The date is local to America/Chicago; raw run timestamps are October 16 UTC.
The runner and evaluator were uncommitted implementation work on the base
revision recorded in [experiment.json](experiment.json). That file preserves
source digests and the settings chosen before the calls. Exact prepared tasks
are retained so subsequent guide edits cannot change the original context.

CLI token counts are the CLI's reported `tokens used`, not a billing receipt.
Input/output/cache breakdowns and actual cost were unavailable; none are
inferred. Durations include CLI startup and provider latency. This trial does
not measure human review time, error detection, adoption, or harder maintenance.

## Retained evidence

- [Exact task records](tasks.jsonl)
- [Raw GWT responses](gwt-responses.jsonl) and [raw Python responses](python-responses.jsonl)
- [GWT scores](gwt-report.json) and [Python scores](python-report.json)
- [Public repair feedback](public-feedback.json), empty for every task
- [Per-attempt timings, model headers, and reported usage](attempt-metadata.json)
- [Smoke run metadata](smoke-run.json) and [remaining run metadata](remaining-run.json)

Raw CLI logs remain local to the execution environment; their SHA-256 digests
are in the attempt metadata. Complete final responses, including generated
source and clarification questions, are preserved here.

To rescore, use a disposable environment with this checkout and Python 3.11+:

```sh
python -m gwtlang.maintenance_evaluation score \
  evaluations/maintenance/manifest.json \
  evaluations/maintenance/2026-10-15/gwt-responses.jsonl \
  --language gwt --repeats 3 --output /tmp/gwt-maintenance-score.json
python -m gwtlang.maintenance_evaluation score \
  evaluations/maintenance/manifest.json \
  evaluations/maintenance/2026-10-15/python-responses.jsonl \
  --language python --repeats 3 --output /tmp/python-maintenance-score.json
```

## Implication

Keep Python as the baseline. GWT's plausible value is typed executable policy,
captured evidence, and review of behavioral changes. Test that value with harder
changes, unrelated domains, and measured human review; avoid further language
expansion on the strength of this result. External pilots remain pending at
the owner's request because no external workflow or maintainer is available yet.
