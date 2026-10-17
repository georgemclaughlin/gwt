# Human source-review study

This protocol tests whether people can understand a proposed GWT rule change
and assess it correctly compared with ordinary Python. The local kit is in
[`evaluations/human_review/`](../evaluations/human_review/README.md).
**No participant study has been run.** Automated checks and browser rehearsals
qualify the apparatus; they do not demonstrate a human benefit.

On 2026-10-16, the owner explicitly chose to keep internal human sessions
pending. Do not recruit or count synthetic sessions as participation. External
pilots also remain deferred; available engineering work may continue.

This is a source-only comparison. It does not evaluate the explanation
workbench, authoring productivity, runtime performance, or production adoption.
Those require separate experiments. The [project goal](project-goal.md) remains
broader than this study, and [external pilots](external-pilot-v0.4.md) remain
pending the user's choice of workflow and participating maintainer.

## Questions and measures

The primary questions are whether reviewers can predict the implementation's
behavior and distinguish a correct change from a faulty one. Record:

- Two predictions of the proposed implementation's actual output per task.
  Each question includes an explicit uncertainty option.
- An approve / request changes / unsure recommendation.
- A written explanation, including a suspected mistake and concrete input when
  possible, and confidence on a 1–5 scale.
- Active task time and wall time, task completion or skipping, role, prior
  familiarity with each language, and previous exposure to the exact tasks.

Correct rejection is a decision measure, **not proof of defect recognition**.
Manually assess explanations against the facilitator rubric before reporting
mistakes detected. Report correct approvals, false rejections, missed defects,
uncertain judgments, and missing work separately. Faster but incorrect review
does not establish benefit. Self-reported confidence is not correctness.

Time starts when a task is displayed and includes reading the source, policy,
language guide, and questions, and entering answers. It excludes the initial
profile and instructions. Explicit pauses hide the task. Hidden-tab intervals
are excluded from active time. Both kinds of pause remain in wall time and
overlapping pauses count only once. Keep timing and completion results together;
the median time of only completed tasks can favor a condition with more skips.
These are browser observations, not authenticated attention measurements.

New packets support explicit recovery from a downloaded partial record. A
resumed task retains its saved active/wall durations and adds newly observed
segments. The interval between checkpoint export and restoration is unknown;
it is not added to either duration. The task's `resumeCount` increases and the
scorer marks its timing interrupted. Such tasks remain in answer/completion
denominators but are excluded from submitted-task timing medians. Report the
timing-eligible denominator and resumed task/session counts alongside medians.
Later uninterrupted tasks remain eligible; `sessionResumed` also permits a
predeclared sensitivity analysis excluding the entire resumed session.

## Task design

Each task contains an existing policy, a requested change, a common input/output
schema, complete existing and proposed source, a short language guide, and the
same two prediction inputs and answer options in both languages. Source is
plain text in both conditions. There are no execution traces, syntax
highlighting, generated explanations, or candidate-specific correctness hints.

| Domain | Requested change | Fault in the faulty candidate |
| --- | --- | --- |
| Refund | Extend the defective-goods deadline from 30 through 45 days | Uses 44 as the inclusive deadline |
| Delivery | Raise the free base-delivery threshold from 100 to 120 | Removes the express surcharge when base delivery is free |
| Expenses | Review any over-limit line, including nonreimbursable lines | Also adds nonreimbursable lines to the reimbursable total |
| Inventory | Allow partial reservation when stock is insufficient | Subtracts the requested amount from remaining stock, even on a shortfall |

The correct candidates implement the requested change and preserve other
rules. The faulty candidates are valid executable programs whose policy is
wrong. Each domain has an independent host model, boundary and interaction
probes, and a baseline. The first prediction distinguishes the correct and
faulty candidates; the second tests other behavior. This question selection can
cue a relevant boundary, so results apply to guided review with supplied inputs,
not unaided discovery of arbitrary defects.

Inputs are valid, nonnegative integer-domain facts with exact booleans and
declared fields. This study does not test malformed inputs, rounding, or
contract enforcement. GWT exposes its record/request declarations; Python uses
an ordinary dictionary-in/dictionary-out function and the shared schema. Neither
arm is padded to match line count. Preserve and report the exact source and
guide sizes, because source volume and prior familiarity can affect reading
time. The small synthetic tasks are not representative deployment evidence.

The study sources are isolated fixtures, including intentionally wrong policies,
not production examples. They omit embedded scenarios in both conditions to
avoid providing answer-key feedback through one language's test syntax. The
independent qualification runner executes baseline, correct, and faulty source
against their respective expected behavior, including every prediction input.
Passing the faulty variant's qualification establishes the intended defect is
present; it does not endorse that policy.

## Assignment and participant protocol

Before collecting observations, freeze the corpus, protocol, packets, and
analysis plan. Record the intended participant population, number of enrolled
sessions, recruitment method, allocation seed, exclusion rules, and stopping
rule. Do not choose a sample size by watching whether GWT appears to win.
This kit does not perform recruitment or contact anyone.

There are 16 assignment groups: four balanced domain orders, two language
orders, and two candidate-validity orders. Across a complete block, each domain
occurs at every position with each language/validity combination exactly once.
Every ordered pair of adjacent domains appears equally often. Each reviewer
sees each domain once, two tasks per language, and two candidates of each
validity. Do not disclose that validity distribution to participants.

Randomize the order of groups within each planned block using a recorded seed.
Use balanced blocks within important role/familiarity strata when feasible;
otherwise report imbalance. A block of 16 is an allocation unit, not evidence
of adequate statistical power. Do not show the same reviewer both languages or
both candidate variants of a domain and treat the results as independent.
Do not replace withdrawals invisibly to restore balance.

Use an opaque assignment ID, not a name or email address. Keep any consent and
identity administration outside this repository and out of answer files. The
profile records broad role, language familiarity (none, read a little, written
some, regular use), and whether the participant has seen these exact tasks.
Developers testing their own fixtures belong in rehearsal records.

Give a participant only `session.html`, never the facilitator key or task corpus.
Explain that participation can stop at any time, that the page does not send
data automatically, and how to return the downloaded record. Ask participants
to use source only, without running the programs, AI, or outside assistance.
Use the same instruction and assistance policy for both languages. Record any
deviation, interruption, accessibility accommodation, or facilitator help;
do not silently discard it. If think-aloud feedback is desired, use a separate
untimed session or declare that condition before collecting timing data.

## Prepare a session

From the repository root, choose a new output directory:

```sh
python -m evaluations.human_review.study prepare \
  --group 0 --assignment rehearsal-001 \
  --output /tmp/gwt-review-rehearsal-001
```

Open `/tmp/gwt-review-rehearsal-001/session.html` in a local browser. No server,
network connection, or package installation is required to use the page.
The preparation tool defaults to `rehearsal`; an actually planned participant
session uses `--purpose participant` and its own opaque assignment ID. Preparing
a participant packet is not evidence that a person participated.

The directory contains:

- `session.html`: self-contained participant page and public packet.
- `packet.json`: exact public context, source, source digests, assignment, and
  question options. Option order is deterministic per assignment and shuffled.
- `facilitator-key.json`: frozen packet plus prediction answers, recommendation
  answers, and rationale rubrics. Keep this separate from participant materials.

Advance only after answering or explicitly skipping a task. Earlier tasks
cannot be revised in the running page. Download a partial record before stopping.
To recover, reopen the **same frozen session HTML** and select that download
under “Continue from a downloaded partial record.” The page verifies the packet,
assignment, source digests, profile, task order, answers, and timing fields before
restoring anything. Completed records and records from other packets are refused.
It restores the original response ID, profile, submitted/skipped tasks, and current
draft, then opens paused. Select Resume when ready to continue.

Only work present in that download is recovered. There is no autosave, analytics,
or upload service. Keep all snapshots and tell the facilitator about the
interruption. An older checkpoint can predate later work; the page cannot prove
which download is newest or authenticate unedited answers. Submitted/skipped
tasks stored in the selected checkpoint remain frozen. The final download keeps
unseen/skipped work and recovery counts visible.

New packets bind `responseSchemaVersion: 2` into their packet identity; version 2
responses require a `resumeCount` for every task. Existing frozen version 1
packets/downloads remain scoreable, but do not support recovery. Do not regenerate
an old study packet and assume it has the same protocol or identity. Freeze and
report the recovery procedure before collecting new observations.

The public repository contains the answers. This is a cooperative study with
packet withholding, not a secret benchmark or an adversarial assessment.
The browser exports self-reported purpose and profile data; checksums bind the
packet's contents but do not authenticate a participant, time, or answer.

## Score observations

Preserve raw downloads unchanged. Select one explicit snapshot per assignment;
the scorer rejects duplicates rather than silently selecting the best attempt.
If both a partial and final record exist, keep both in the archive, score the
final one, and record that choice. Do not pool different task revisions under
one study label.

```sh
python -m evaluations.human_review.study score \
  --keys /tmp/gwt-review-rehearsal-001/facilitator-key.json \
  --responses /tmp/rehearsal-001-complete.json \
  --output /tmp/gwt-review-rehearsal-001-report.json
```

Supply **all enrolled assignment keys**, including sessions without a returned
record. Exclude spare prepared packets that were never assigned, and retain
the enrollment/allocation log explaining the planned denominator. Omit
`--responses` to report a completely missing session; do not invent timing or
empty completed answers. `--keys` and `--responses` each accept multiple paths.

The scorer validates packet identity, assignment identity, source digests,
question choices, sequential task statuses, completion flags, finite
nonnegative durations, active time no greater than wall time, and unique
assignments/responses. It separates rehearsals from participant observations.
All planned tasks remain in denominators. Draft/skipped answers are retained,
but only submitted answers receive correctness credit. Explicit uncertainty
receives no correctness credit and remains visible in raw observations.

The report contains descriptive counts and uninterrupted submitted-task time medians by
language, plus task-level domain, validity, order, profile, confidence, times,
answers, and rubrics for stratified analysis. It deliberately makes no claim of
superiority or statistical significance. Review attrition, familiarity,
exposure, task difficulty, position, and candidate validity before interpreting
an aggregate difference. Treat repeated tasks from one person as related
observations in any subsequent uncertainty analysis.

For manual rationale assessment, keep an adjudication table keyed by packet ID
and task ID. Record assessor, assessment, evidence excerpt, and rationale:

- `recognized_defect`: identifies the seeded erroneous rule and its consequence
  or a valid counterexample. A generic “looks wrong” rejection does not qualify.
- `missed_defect`: accepts a faulty candidate or offers no correct explanation
  of its defect. Retain unsupported rejections as distinct decision outcomes.
- `supported_approval`: a correct candidate is approved with reasoning about
  both the requested change and preserved rules.
- `unsupported_or_incorrect`: reasoning does not support the recommendation.
- `uncertain` or `unavailable`: insufficient evidence or missing response.

Where possible, have two assessors review explanations without seeing aggregate
language results, then record disagreements and resolutions. Avoid claiming
assessors are language-blind when the explanation quotes source syntax.
The original automated scorer leaves every rationale assessment pending; do not
rename its correct-decision count to “defects detected.” The separate
[manual assessment workflow](../evaluations/human_review/adjudication.md) now
prepares identity-bound assessor sheets and reconciles them against the raw keys
and responses. Declare the full assessor roster, retain missing sheets and
unfinished ratings, and preserve disagreements until explicitly resolved.
Final categories require all planned ratings and agreement from at least two
assessors, or an explicit resolution of their disagreement. A single rating
stays provisional. The resulting counts are labeled assessor-judged recognition,
not automatic proof of defect detection. Archive the sheets and resolutions with
any eventual participant report. No actual assessments by participants or human
assessors are claimed by the synthetic qualification.

## Qualification and interpretation boundary

```sh
python -m unittest tests.test_human_review
python -m evaluations.human_review.qualify \
  --native /path/to/gwt \
  --output /tmp/gwt-human-review-fixture-checks.json
```

The fixture check evaluates 137 policy probes plus eight prediction inputs per
revision, for three revisions under Python-hosted GWT, ordinary Python, and
native GWT: 1,305 executions. Numeric native outputs are compared by value only
at integer leaves; strings, booleans, object keys, and shapes remain exact.
Browser checks separately cover complete and partial downloads, required
answers, skips, explicit pause timing, simulated visibility-event overlap,
source rendering, mobile layout, and absence of external requests.

The [local qualification](../evaluations/human_review/2026-10-16/README.md)
contains only synthetic records. The later
[checkpoint-recovery checks](../evaluations/human_review/2026-10-16-recovery/README.md)
exercise recovery, clocks, scoring, and legacy compatibility without a browser;
the subsequent [browser qualification](../evaluations/human_review/2026-10-16-recovery-browser/README.md)
passes 78 actual browser checks, including repeated desktop/mobile restoration,
invalid-file refusal, preserved answers, paused timing, and scorer interoperability
with the downloaded records. Visibility events are simulated; this does not
measure operating-system tab scheduling or attention. The current engines also
pass all 1,305 policy-fixture executions. Actual representative participant observations,
manual rationale adjudication, and measured benefit remain missing. Even a
successful study on these four short tasks would require broader workflows and
deployment evidence before closing the project goal.
