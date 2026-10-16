# Manual assessment of review explanations

`adjudication.py` records assessors' judgments about written explanations and
reconciles disagreements. It does not use a model to grade people, infer defect
recognition from an approve/reject choice, or establish that an assessor's
interpretation is correct. No participant observations have been collected.

The workflow reads the same frozen keys and selected raw responses used by
`study.py score`. It recomputes and validates the original observations, then
binds judgments to those exact keys, rubrics, and response snapshots. Original
decision, prediction, timing, and attrition summaries remain unchanged.

## Prepare independent assessor sheets

Declare an opaque assessor roster before assessment. Retain the assignment log
outside the report, including any planned independent assessment or later joint
discussion. Use the same full roster, enrolled keys, and selected response
snapshots in every command, including absent sessions and missing assessors.

```sh
python -m evaluations.human_review.adjudication prepare --keys /path/to/key.json --responses /path/to/response.json --assessors reviewer-a reviewer-b --assessor reviewer-a --output /path/to/reviewer-a-blank.json
python -m evaluations.human_review.adjudication prepare --keys /path/to/key.json --responses /path/to/response.json --assessors reviewer-a reviewer-b --assessor reviewer-b --output /path/to/reviewer-b-blank.json
```

The key/response arguments accept multiple files; omit `--responses` when no
records were returned. These are **facilitator materials**, containing correct
and faulty source identities and rubrics. Never distribute them with participant
packets. The sheets show policy, requested change, original/proposed source,
recorded recommendation and explanation, and the applicable rubric. They omit
aggregate results, correctness scores, confidence, and timing to reduce unrelated
cues. Source language remains visible; this is not language-blind assessment.

Copy each blank sheet to a new filled filename. Edit only these fields in each
row; keep all rows and their order:

| Field | What to enter |
| --- | --- |
| `assessment` | One of the categories below, or `null` while pending |
| `evidenceQuote` | An exact excerpt from the participant's recorded explanation |
| `reason` | Why that excerpt and the rubric support the assessment |

Use these categories consistently:

- `recognized_defect`: a submitted explanation identifies the seeded faulty
  rule and its consequence or a valid counterexample. Available only for faulty
  candidates. Recognition and recommendation remain separate: someone can
  describe a defect yet still recommend approval; retain that inconsistency.
- `missed_defect`: a submitted explanation fails to identify the seeded defect,
  including an unsupported rejection. Available only for faulty candidates.
- `supported_approval`: a submitted approval of a correct candidate explains
  both the requested change and preservation of the other rules.
- `unsupported_or_incorrect`: the submitted reasoning does not support its
  recommendation. Applicable to either candidate validity.
- `uncertain`: a submitted explanation cannot be assessed confidently. Explain
  the uncertainty; a quote is optional.
- `unavailable`: there is no submitted explanation, including missing, unseen,
  draft, or skipped work. Retained draft text cannot receive recognition credit.

Every completed judgment needs a written reason. Except for `uncertain` and
`unavailable`, it also needs a nonblank exact quote. `unavailable` must have an
empty quote. Pending rows keep `assessment: null` and empty quote/reason strings.
Checks ensure a quote occurs in the recorded explanation; they do not determine
whether it supports the chosen category. Review that interpretation manually.

## Reconcile and resolve disagreements

```sh
python -m evaluations.human_review.adjudication reconcile --keys /path/to/key.json --responses /path/to/response.json --assessors reviewer-a reviewer-b --assessments /path/to/reviewer-a-filled.json /path/to/reviewer-b-filled.json --output /path/to/initial-adjudication.json
```

The report distinguishes `pending`, `single_assessor`, `consensus`, and
`needs_resolution`. Final consensus requires at least two ratings, all planned
assessors' ratings present, and agreement on the category. Two agreeing ratings
do not hide a missing third assessor or override a dissenting third rating.
An assessor sheet that has not arrived remains explicitly missing; omit its
file, not its roster ID. A single completed rating stays provisional and receives
no final recognition credit. An entirely missing submission may reach consensus
on `unavailable`, which remains distinct from a recognized or missed defect.

For disagreements, prepare a separate resolution sheet:

```sh
python -m evaluations.human_review.adjudication prepare-resolution --keys /path/to/key.json --responses /path/to/response.json --assessors reviewer-a reviewer-b --assessments /path/to/reviewer-a-filled.json /path/to/reviewer-b-filled.json --resolver adjudicator --output /path/to/resolution-blank.json
```

This contains only disagreements after all planned ratings are present, with
every original judgment, quote, and reason intact. Save a filled copy, editing
the same three fields to record the resolution. A resolution may retain
`uncertain`; it need not force recognition or approval. The resolver may be one
of the assessors or another person; record the agreed procedure in the protocol.

```sh
python -m evaluations.human_review.adjudication reconcile --keys /path/to/key.json --responses /path/to/response.json --assessors reviewer-a reviewer-b --assessments /path/to/reviewer-a-filled.json /path/to/reviewer-b-filled.json --resolution /path/to/resolution-filled.json --output /path/to/final-adjudication.json
```

Completed resolutions have status `resolved`. Blank resolution rows remain
`needs_resolution`. Prior opinions remain in the report; there is no majority
vote or implicit overwrite. Changing an assessor sheet, including its reasoning,
invalidates an earlier resolution and requires a new explicit snapshot.

## Interpret and archive

`rationaleReview.summaries` separates rehearsal/participant observations and GWT/
Python conditions. It retains planned/submitted task and faulty-task counts,
review-status counts, final categories, `assessorJudgedRecognizedDefects`, and
`assessorJudgedSupportedApprovals`. Missing, provisional, and unresolved work
receive no final recognition credit and remain visible. These descriptive counts
do not establish significance, superiority, or a causal language effect.

Keep raw response downloads, keys, assessor assignment log, blank and filled
sheets, resolution snapshots, and reports. Output files must be new; commands
refuse to overwrite earlier artifacts. Duplicate assessor snapshots, edited
context, invented quotes, unplanned assessors, mismatched rosters, and changed
response/rubric identities are rejected. Changed response timing or profile also
creates a new evidence snapshot; do not reuse prior sheets silently.

Checksums and opaque IDs are integrity references, not authentication. They do
not prove distinct people, independent assessment, actual participation, or
accurate semantic judgment. The study protocol must establish those facts.

## Local qualification

```sh
python -m unittest tests.test_human_adjudication tests.test_human_review
python -m evaluations.human_review.qualify_adjudication --output /path/to/new-adjudication-rehearsal
```

The [retained rehearsal](2026-10-16-adjudication/README.md) uses synthetic answers,
assessors, and resolutions only. It establishes the recording/reconciliation
workflow, not human-review benefit. Participant page content and timing behavior
are unchanged.
