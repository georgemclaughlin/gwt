# Model experiment orchestration qualification — 2026-10-16

The native maintenance experiment now connects generation, public repair,
response sealing, and full scoring. This checkpoint contains **zero live model
calls and zero human participants**. A synthetic provider supplies known fixture
revisions; candidate execution uses real disposable containers.

## Evidence

`rehearsal-verified/` is the final complete run, including exact synthetic request
and response records, public feedback, container execution records, sealed
responses, source hashes, settings, and final scores. `rehearsal/` retains the
earlier successful run before an additional qualification-copy integrity check.
No earlier artifacts were overwritten.

The experiment runs all thirty tasks in frozen order. Thirty first attempts
produce six public refund failures. Six repairs then recover those failures.
The faulty allocation passes both public examples in every repeat, receives no
repair, and fails 380 withheld probes per trial during final scoring.

| Synthetic outcome | GWT | Python |
| --- | ---: | ---: |
| Trials | 15 | 15 |
| Missing | 0 | 0 |
| First-pass full success | 9 | 9 |
| Final full success | 12 | 12 |
| Repaired trials | 3 | 3 |
| Recovered trials | 3 | 3 |

These are expected harness outcomes, not estimates of model ability. Synthetic
provider records have null usage and timing; the runner does not manufacture
token, price, or latency measurements. The prior live refund study used a
different Codex CLI workflow and cannot supply missing native/API evidence.

The focused tests check public context projection, tool-free request settings,
response validation, round order and sealing, failed-generation attempt caps,
interrupted provider calls, candidate-infrastructure failures, connection cleanup,
and changed qualification copies. Final test counts and independently checked
artifact totals are recorded in `verification.json` and retained test logs:
all 650 Python tests and 21 focused tests pass. Seventy-two container attempts
complete 72 public-input executions and 7,026 full-scoring input executions.
All 36 requests match reconstructed public prompts, all source/response hashes
match, all 56 native engine inputs remain unchanged, and no evaluation containers
remain.

## Remaining boundary

The API adapter has mocked transport checks. No `OPENAI_API_KEY` was configured,
so live transport/model compatibility and actual model results remain unverified.
The [experiment guide](../experiment.md) documents exact commands, limits,
artifacts, interruption handling, and the absence of automatic retries/resume.

No Rust runtime behavior changed. The preceding frozen native executable and
qualified worker are reused. The full project goal remains active, including
representative human comprehension/review evidence and broader adoption work.
