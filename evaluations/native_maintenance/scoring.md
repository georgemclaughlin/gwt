# Isolated native maintenance scoring

The scorer evaluates frozen paired tasks against independent expectations. It
accepts recorded responses; it does not call a model or choose model settings.
The separate [experiment runner](experiment.md) manages provider calls and the
public repair loop before invoking full scoring.
Run commands from the repository root with Docker available, an existing local
Python image providing `/usr/local/bin/python`, and a native executable compatible
with that image. The qualified static Linux executable works in the tested image.
Images are never pulled automatically; the selected local image is pinned by ID.

## Prepare and score

First qualify trusted fixtures with the intended native executable:

```sh
python -m evaluations.native_maintenance.study --native /path/to/gwt-native --output /path/to/new-qualification
```

Retain that directory. Task and corpus digests, native executable, and execution
worker must match qualification. Older qualifications without a corpus digest
must be regenerated into a new directory. Hashes detect changes; they do not
authenticate the author or prove an oracle is correct.

Responses are JSONL objects containing `caseId` from `tasks.jsonl`, `attempt`
(positive integer starting at one), `action: "code"`, and full candidate `source`.
Retain every attempt. IDs must be known, attempts contiguous and unique, and
attempt numbers no greater than the configured maximum (default three).
`action: "clarify"` is accepted as a recorded response but fails these code tasks.
Python source must define `decide(state)`; GWT source must retain the task's
request entry. Return the task's decision object, without a scoring wrapper.

```sh
python -m evaluations.native_maintenance.scorer --qualification /path/to/new-qualification --responses /path/to/responses.jsonl --native /path/to/gwt-native --image python:3.12-slim --output /path/to/new-public-feedback --public-only
python -m evaluations.native_maintenance.scorer --qualification /path/to/new-qualification --responses /path/to/responses.jsonl --native /path/to/gwt-native --image python:3.12-slim --output /path/to/new-final-score
python -m unittest tests.test_native_maintenance_scorer tests.test_native_maintenance
```

Every output directory must be new. Public-only mode executes just the latest
attempt and the two public inputs per task. Failed public examples return input,
expected value, and observation; execution failures include bounded stderr when
available. `nextAttempt` identifies an available next attempt, including the
initial attempt for a missing response. It is null after public success or at
the attempt cap. First-pass and recovery metrics are null in this mode because
only the latest public attempt was evaluated.

Freeze all responses after public repairs before running full scoring. Full
scoring executes every recorded attempt over all probes and never schedules a
repair. Do not send full reports, frozen corpus files, or withheld observations
to a model. The experiment runner enforces this ordering; the standalone scorer
does not automate the loop. A public pass can still fail withheld probes.

## Results and execution boundary

Missing tasks stay in the denominator. Reports separate first/final success,
repair recovery, and changed/preserved/public/withheld counts. Invalid, timed-out,
oversized, or incomplete observations fail the selected probes. Exact comparison
distinguishes booleans, numbers, decimal strings, missing fields, and list order.
Expected policy rejection is distinct from an execution error.

Each attempt gets a fresh container with no network, a read-only root, UID/GID
65534, no capabilities, no new privileges, one CPU, 256 MiB memory with no extra
swap, 64 processes, and a 32 MiB temporary filesystem. Only the frozen worker,
native executable, and candidate source are mounted read-only. Request names and
inputs arrive on stdin; expected answers remain in the parent. Repository,
home-directory, and credential mounts are absent.

Default execution timeout is 120 seconds per attempt, configurable with
`--timeout`. Stdout is capped at 16 MiB and stderr at 256 KiB; candidate source
at one MiB and input batches at eight MiB. Cleanup has separate bounded waits,
so recorded duration can exceed the execution timeout. Cleanup errors abort the
run instead of reporting successful removal. An interrupted checkpoint is not a
completed report.

Outputs preserve exact responses, frozen task/corpus/qualification files, image
identity, executable/worker/scorer hashes, commands, bounded streams, per-attempt
observations, and progress. Raw artifacts include withheld expectations and are
for experiment analysis only. Provider latency, tokens, and cost must be retained
separately from real provider records; container duration is not model latency.

This is cooperative maintenance evaluation. Python candidates share the worker
process and could tamper with its protocol; container checks do not establish
resistance to adversarial cheating or all host vulnerabilities. Qualification
uses synthetic responses, with zero live model calls and zero human participants.
