# Local human-review kit qualification — 2026-10-16

**Zero human participants.** This directory contains automated fixture checks,
synthetic browser sessions, and scorer checks. It establishes that the kit can
collect and preserve review observations; it provides no human comprehension,
productivity, or adoption evidence.

## Verified results

- `fixture-qualification.json`: **1,305 executions** matched independent policy
  expectations. The 137 general inputs and eight prediction inputs run against
  three source revisions in Python-hosted GWT, ordinary Python, and native GWT.
  The general probes include boundary values, receipt/defect interactions,
  express surcharges, empty/single/ordered-pair expense collections, and stock
  shortfalls. Every domain includes changed and preserved policy outcomes and
  probes that expose its seeded defect.
- Native executable SHA-256:
  `b70d8bd3caaae1819dd488537f7351546f874a8ffbcf1b43cf7aaac17b4a1e1d`.
  This is the previously qualified Rust 1.96.0 installed package at
  `/tmp/gwt-package-host-r4xiuq1n/installed/bin/gwt-native`; its package evidence is
  in [`native_editor/2026-10-16-kind-contracts`](../../native_editor/2026-10-16-kind-contracts/README.md).
- All 12 GWT fixture files pass the Python canonical formatter check and static
  checker. No production language semantics changed for this study.
- `browser/report.json`: offline Chromium **153.0.8010.12**, at **1440px** and
  **390px** widths. Required profile/answer fields, exact proposed source,
  partial/final downloads, a skipped task, pause hiding/timing, and overlapping
  simulated visibility events passed. No script errors, external requests, or
  document horizontal overflow were observed. Visibility events were simulated
  by the test; actual OS tab suspension was not qualified.
- Four screenshots (`browser/task-*.png`, `browser/complete-*.png`) were visually
  inspected. The source comparison is side by side on desktop and stacked on
  mobile; completion keeps the download action visible.
- `rehearsal-score.json`: eight planned tasks, seven submitted, one skipped;
  14 correct submitted predictions and seven correct submitted recommendations.
  The test supplied answers from the facilitator key. All observations remain
  in the rehearsal section and all rationale assessments remain pending.
  Automated task durations are not human review times.
- `partial-and-missing-score.json`: one filled draft, three unseen tasks, and
  four tasks in a missing session remain in the eight-task denominator, with
  no submitted correctness credit and no invented durations.
- `python-tests.log`: **621 tests passed**, including six new study tests
  covering balanced position/language/validity/adjacency, public/private packet
  separation, safe script embedding, prediction keys, missing data, rehearsal
  segregation, duplicates, identity mismatches, impossible task sequences, and
  invalid timings. `git diff --check` also passed.

## Artifacts and reproduction

The [`desktop/session.html`](desktop/session.html) and
[`mobile/session.html`](mobile/session.html) are runnable rehearsal pages. Their
adjacent `packet.json` files freeze public material; adjacent facilitator keys
are for qualification and scoring, never participant distribution. The browser
directory retains downloaded intermediate, partial, paused, and complete JSON
snapshots. Only the selected complete snapshots enter the main rehearsal score.

From the repository root, the relevant commands were:

```sh
python -m evaluations.human_review.study prepare \
  --group 0 --assignment rehearsal-desktop --output NEW_CHECKPOINT/desktop
python -m evaluations.human_review.study prepare \
  --group 7 --assignment rehearsal-mobile --output NEW_CHECKPOINT/mobile
python -m evaluations.human_review.qualify \
  --native /path/to/gwt-native --output NEW_CHECKPOINT/fixture-qualification.json
python evaluations/human_review/check_browser.py NEW_CHECKPOINT
python -m evaluations.human_review.study score \
  --keys NEW_CHECKPOINT/desktop/facilitator-key.json NEW_CHECKPOINT/mobile/facilitator-key.json \
  --responses NEW_CHECKPOINT/browser/complete-1440.json NEW_CHECKPOINT/browser/complete-390.json \
  --output NEW_CHECKPOINT/rehearsal-score.json
python -m unittest discover
git diff --check
```

`NEW_CHECKPOINT` means a fresh directory. Browser execution used the existing
`mcr.microsoft.com/playwright/python:v1.63.0-noble` image with `--network none`,
mounted repository, and the existing Playwright Python dependencies. The
container had no configured external browser session. These are local browser
checks, not a deployed or externally hosted study.

`source-hashes.json` records the final kit, fixture, test, and documentation
hashes. The fixture report's own source inventory was captured before the
browser helper and final documentation were added; its fixture and semantic
oracle hashes still match. The final inventory covers those later additions.

Actual participant observations, a frozen enrollment/analysis plan, manual
rationale adjudication, and broader representative workflows remain pending.
See the [protocol](../../../docs/human-review-study.md). No outside maintainer
was contacted and no external pilot was initiated.
