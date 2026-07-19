# Agent Authoring Baseline — 2026-07-18

This directory preserves one live Codex CLI matrix over the 15-case GWT agent
corpus. It is an exploratory baseline, not a general model ranking.

## Method

- Codex CLI: `0.144.6`
- models: `gpt-5.6-luna` with low reasoning and `gpt-5.6-sol` with high
  reasoning
- contexts: `source-only`, `inspect`, and `guide`
- samples: one independent call per case and context cell
- concurrency: four calls, except the three-case Sol/guide repair run
- isolation: fresh read-only temporary directory, ephemeral session, ignored
  user configuration and repository rules
- repair policy: at most two public repair rounds; parser/checker diagnostics
  and scenario errors returned to the model; format-only repairs applied by the
  deterministic formatter; hidden probes and clarification concepts withheld

There are 11 code cases (five authoring and six repair) and four clarification
cases. Percentages below use those separate denominators.

| Model | Context | First parse | First check | Final validation | Final semantic | Clarification | Repair recovery |
|---|---|---:|---:|---:|---:|---:|---:|
| Luna/low | source-only | 45.5% | 45.5% | 45.5% | 45.5% | 50% | 33.3% (3/9) |
| Luna/low | inspect | 45.5% | 45.5% | 45.5% | 45.5% | 50% | 0% (0/6) |
| Luna/low | guide | 63.6% | 54.5% | 90.9% | 90.9% | 75% | 100% (5/5) |
| Sol/high | source-only | 36.4% | 27.3% | 45.5% | 45.5% | 75% | 25% (2/8) |
| Sol/high | inspect | 45.5% | 36.4% | 45.5% | 45.5% | 75% | 14.3% (1/7) |
| Sol/high | guide | 81.8% | 72.7% | 100% | 100% | 100% | 100% (3/3) |

The final semantic counts make the context effect especially clear:

| Model | Context | Authoring | Repair | Clarification |
|---|---|---:|---:|---:|
| Luna/low | source-only | 0/5 | 5/6 | 2/4 |
| Luna/low | inspect | 0/5 | 5/6 | 2/4 |
| Luna/low | guide | 5/5 | 5/6 | 3/4 |
| Sol/high | source-only | 0/5 | 5/6 | 3/4 |
| Sol/high | inspect | 0/5 | 5/6 | 3/4 |
| Sol/high | guide | 5/5 | 6/6 | 4/4 |

## What This Run Taught Us

1. The semantic model must include the public vocabulary. An initial discarded
   pilot left request names and input/output binding names only in hidden
   probes. That made valid alternative DSLs fail. The author starters now
   declare those boundaries, and a corpus test enforces the relationship.
2. Inspection helps repair existing GWT but did not teach either model enough
   syntax to author a new behavior. Neither model completed an author case in
   the source-only or inspect conditions.
3. A few unrelated worked examples changed the result materially. The guide
   context enabled both models to complete all five authoring cases after the
   bounded repair loop.
4. Deterministic repair works after the grammar is grounded. Guide-context
   repair recovery was 100% for both models; recovery was weak without worked
   examples.
5. Lexical clarification scoring was initially too narrow. Semantically valid
   phrases such as “rounding rule,” “half-up,” and “tax calculated on the
   discounted price” are now normalized without exposing the hidden concepts
   during generation.

One known baseline caveat remains. The captured
`repair-explicit-missing-case` task asked for an explicit missing branch but did
not explicitly ask for a missing-case scenario, while its acceptance gate
required two scenarios. The current manifest now states that requirement. The
exact pre-correction tasks are retained here so this run remains reproducible;
the caveat accounts for Luna/guide's single remaining code failure.

## Artifacts

- `tasks.*.jsonl` are the exact blind model inputs used for this run.
- `*.responses.jsonl` preserve all raw model candidates and deterministic
  format attempts in scorer order.
- `*.report.json` are the deterministic final score reports.
- `*.first-run.json` and `*.repair-*-run.json` preserve CLI version, requested
  model, effort, task digest, timestamps, durations, and capture status.

Raw CLI progress logs were intentionally excluded. They duplicate task and
candidate content and are not required to reproduce scoring.

Re-score any cell from the repository root, for example:

```sh
python -m gwtlang.agent_evaluation score \
  tests/fixtures/agent_authoring/manifest.json \
  evaluations/agent-authoring/2026-07-18/sol.guide.responses.jsonl
```

Because the clarification rubric and one task were corrected after capture,
the checked-in report is the authoritative score for this dated baseline. A
future rerun should prepare fresh tasks from the current manifest.
