# Five-domain Codex CLI maintenance comparison — 2026-10-16

This experiment uses native GWT and Python across refund, delivery, expenses,
inventory, and allocation policies. The protocol schedules three trials per
language per domain (30 total), with up to three attempts driven only by public
feedback. The larger allocation policy exercises exact arithmetic, fallback,
eligibility, ordering, and conservation. Human participants: **zero**.

## Results

All 30 trials completed, with no missing calls or repairs. Both languages passed
all public and withheld cases on their first attempts: **15/15 GWT and 15/15
Python**, or 3/3 per domain per language. Full scoring executed 6,828 inputs;
the public round executed another 60. The preliminary probe is excluded.

| Recorded measure | GWT | Python |
| --- | ---: | ---: |
| First-pass full success | 15/15 | 15/15 |
| Final full success | 15/15 | 15/15 |
| Median CLI call duration | 6.915 s | 6.116 s |
| Reported input tokens, all 15 calls | 156,190 | 151,693 |
| Reported output tokens, all 15 calls | 4,802 | 3,146 |
| Median public prompt size, UTF-8 bytes | 3,886 | 2,439 |

Call duration includes CLI startup and model generation, not candidate execution;
it is unrelated to the Python/Rust runtime benchmark. Built-in CLI context and
caching affect usage. These totals are not a price estimate or matched-context
comparison. Three repeats of five tasks do not establish general model superiority.

This is evidence that the selected model can maintain these native GWT policies
from their supplied guide. It shows **no success-rate advantage over Python** and
no human-comprehension or adoption benefit. There is no reason to expand syntax
just to chase a benchmark lead. The next product question remains whether people
can inspect intent, predict outcomes, and review changes more reliably.

The artifact audit in `verification.json` reconstructed every public request,
verified the sealed responses and frozen inputs, recomputed score partitions
from retained observations, and found zero tool events or changed runner sources.
All 678 Python tests pass, including seven new CLI transport tests; the 16 focused
transport/orchestrator tests pass. No native runtime behavior changed in this step.

## Protocol and artifacts

- Requested model: `gpt-6-astra`, medium reasoning effort, Codex CLI `0.163.0`.
- Fresh ephemeral sessions using the existing login; no API key extraction.
- Frozen native binary SHA-256:
  `22803923302696abe60e382fce16dc4b1cb841ea597505b7692e50b7a8df1696`.
- Python candidates and native requests execute in the same bounded Docker
  image, `sha256:b4acd70b6f4ca3e8fa68f11d4bc6831d141744654e62286f862b3c8ca7bd0467`.
- `fixtures/` contains the new 6,828-execution trusted-fixture qualification;
  1,138 distinct inputs per revision and three source revisions per language.
- `probe/` retains the preliminary structured-output transport check. It is
  separate from maintenance scores and usage.
- `live/` retains frozen tasks/corpus, requests, raw CLI events, normalized
  responses, public feedback, execution observations, response seal and report.

The [transport guide](../experiment.md) records restrictions and limitations.
CLI built-in context is present; this is not the Responses API protocol.
Accepted event streams must have no tool activity. The returned model is not
independently attested by CLI events. Usage is reported, not inferred. There is
no qualified CLI output-token cap; each process has a 300-second deadline.
Withheld results cannot trigger repairs. Repeats are not independent new tasks.
This is guided use with unequal language guides and source sizes.

## Reproduction

Use new output directories and a native executable matching the qualification:

```sh
python -m evaluations.native_maintenance.study --native /path/to/gwt-native --output /path/to/new-fixtures
python -m evaluations.native_maintenance.experiment --provider codex-cli --qualification /path/to/new-fixtures --native /path/to/gwt-native --image python:3.12-slim --model gpt-6-astra --reasoning-effort medium --maximum-attempts 3 --provider-socket-timeout 300 --output /path/to/new-live-run
python -m evaluations.native_maintenance.verify_codex_run /path/to/new-live-run --output /path/to/new-audit.json
```

The verifier makes no model calls and executes no candidate code. It reconstructs
public prompts, checks original events against normalized responses and usage,
verifies the seal and frozen input hashes, and recomputes score partitions from
retained observations. This checks artifact consistency, not independent policy
correctness or human comprehension.
