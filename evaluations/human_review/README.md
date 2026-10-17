# Human source-review kit

An offline, source-only GWT/Python comparison across refund, delivery, expense,
and inventory changes. See the [protocol](../../docs/human-review-study.md) for
assignment, participant instructions, scoring, manual rationale assessment, and
interpretation limits.

- `corpus.py`: shared policy descriptions, prediction inputs, facilitator
  answers, and independent policy models/probes.
- `fixtures/`: complete paired source for baseline, correct, and intentionally
  faulty policies. These are study stimuli, not recommended production rules.
- `study.py`: prepare a frozen session and separate answer key; score downloads.
- `adjudication.py`: prepare assessor sheets, retain manual rationale judgments,
  and reconcile explicit resolutions; see the [assessment workflow](adjudication.md).
- `session.html`: offline participant UI with profile, timers, pauses, partial
  exports, checkpoint recovery, skipped tasks, and final export.
- `session-recovery.js`: inline checkpoint validation and observed-segment timing;
  resumed tasks retain answers but are excluded from timing medians.
- `qualify.py`: independent expected-result checks in both GWT engines and Python.
- `check_browser.py`: automated browser rehearsal; all exported data is synthetic.
- `2026-10-16/`: [local qualification](2026-10-16/README.md), with zero participants.
- `2026-10-16-adjudication/`: [synthetic assessment qualification](2026-10-16-adjudication/README.md),
  also with zero participants.
- `qualify_recovery.py`: synthetic checkpoint/clock and scoring interoperability.
- `2026-10-16-recovery/`: [checkpoint recovery checks](2026-10-16-recovery/README.md);
  synthetic clock/protocol and scoring checks.
- `2026-10-16-recovery-browser/`: [interactive recovery qualification](2026-10-16-recovery-browser/README.md);
  78 desktop/mobile browser checks and scoring of actual synthetic downloads.

Prepare a local rehearsal from the repository root:

```sh
python -m evaluations.human_review.study prepare \
  --group 0 --assignment rehearsal-001 --output /tmp/gwt-review-rehearsal-001
```

Open the generated `session.html`. Distribute only that HTML to reviewers, not
the facilitator key. Outputs default to rehearsal and remain separate from
participant observations. No external pilot has been initiated.
