# Downloaded checkpoint recovery — 2026-10-16

New human-review packets support loading a downloaded partial record into the
same offline session page. Restoration checks packet/source/assignment identity,
profile, sequential task statuses, answers, and timing before replacing state.
The original response ID and completed/skipped answers remain intact. The current
draft opens paused; no task resumes counting active time until Resume is selected.
There is no autosave or recovery of work after the chosen download.

The packet now binds response schema version 2. Each task records `resumeCount`;
unseen tasks must have zero. Old version 1 packets/downloads still score under
their original identity but cannot be resumed. Completed records cannot reopen.
Choosing the latest snapshot and retaining earlier files remains a facilitator
procedure, not an authenticated guarantee enforced by this offline page.

## Timing and scoring

Recovered drafts retain saved durations and add newly observed segments. The
unknown interruption is not assigned invented active or wall time. Resumed tasks
remain in answer/completion denominators but are excluded from timing medians.
Reports expose resumed tasks/sessions, timing-eligible submissions, raw durations,
and `sessionResumed` for analysis of the whole session's interruption. Correct
answers remain distinct from manual recognition judgments.

## Verified evidence

- All **664 Python tests**, including six new recovery groups, pass. The twenty
  focused study/recovery/adjudication tests also pass. Logs are retained here.
- The actual inline JavaScript recovery/clock module is exercised in Node. Checks
  cover identity and frozen-answer preservation, repeated recovery, paused/active
  segments, fresh-task timers, 26 invalid records rejected by both JavaScript and
  Python, completed-record refusal, legacy records, and timing denominators.
- Generated inline scripts parse, and no external script or browser storage is
  introduced. These checks do not substitute for browser interaction/layout tests.
- `rehearsal/` records five actual prepare/score/assessment CLI commands and two
  JavaScript restorations. Eight planned synthetic tasks remain accounted for:
  three submitted, one skipped, and four from a missing session. One submitted
  task has two recoveries and remains outside the two timing-eligible submissions.
  Its 2,000 active ms and 4,500 observed wall ms include only the scripted segments.
- The original study policy corpus/fixtures and native engine inputs remain
  unchanged; the independent policy-execution qualification is not rerun here.

Reproduce in a new directory:

```sh
python -m unittest tests.test_human_recovery tests.test_human_review tests.test_human_adjudication
python -m evaluations.human_review.qualify_recovery --output /path/to/new-recovery-rehearsal
```

## Pending browser validation

The Browser runtime returned “No browser is available”; documented discovery
returned an empty list. No browser check or screenshot is claimed for this change.
The retained earlier browser qualification predates recovery support. Before a
participant session, validate the generated page interactively on desktop/mobile:

1. Start a rehearsal, submit one task, skip another, enter a partial explanation,
   and download. Reload and restore that file; check frozen answers, current form
   values, paused state, and source visibility.
2. Download while paused, wait, and download again. Active time must stay fixed;
   observed wall time must advance. Resume and repeat explicit/hidden-tab pauses.
3. Finish and score the result. Check identity, increased recovery count, timing
   exclusion, preserved missing/skipped work, and refusal to reopen the final file.
4. Try a different packet, malformed/incomplete JSON, and a file over one MiB.
   Each must leave the setup usable with an error and no imported state.
5. Check keyboard/file selection, readable mobile layout, exact source rendering,
   and absence of external requests.

All observations here are synthetic. There are zero human participants, zero
live model calls, and no external pilot. The full project goal remains incomplete.
