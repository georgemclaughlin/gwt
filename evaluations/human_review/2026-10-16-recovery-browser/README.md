# Browser qualification of study recovery — 2026-10-16

This closes the interactive-validation gap recorded in the
[checkpoint recovery qualification](../2026-10-16-recovery/README.md).
**There are zero human participants.** Every response is a synthetic rehearsal;
the automation uses facilitator answers. This establishes apparatus behavior,
not comprehension, defect recognition, or review-time benefit.

## Results

**78 Playwright CLI checks pass** in Chromium 153.0.8010.12, at desktop 1440×1000
and mobile 390×1000. Each rehearsal submits one task, skips one, enters a partial
third response, downloads, reloads, and restores twice before finishing.

- Packet/response identity, profile, submitted/skipped answers, unseen work, and
  partial predictions/selections/Unicode explanations survive recovery.
- Restoration opens paused, hides task source, focuses Resume, and supports
  keyboard resumption. Entering HTML-like text in the explanation does not execute
  it. Restored source text matches the frozen packet exactly.
- Paused active time stays fixed while observed wall time advances. Simulated
  `visibilitychange` events exercise overlap with the explicit Pause button;
  active time resumes only when both reasons end. This does **not** qualify
  operating-system tab scheduling or a person's attention.
- Malformed/incomplete JSON, an oversized file, a checkpoint from another packet,
  and a completed record are refused without starting an imported session. The
  file control resets after rejection and the profile form remains usable.
- Both layouts have no horizontal document overflow. No script errors or external
  requests occur during the checks. The initial loopback navigation requested a
  missing local favicon; its 404 is retained separately and is not a script error.

The initial harness attempted an in-memory file upload using a `Buffer` global
that the CLI sandbox does not expose. The final harness uploads ordinary local
fixture files through the real file input. No application change was needed.

Six retained screenshots were inspected:

| State | Desktop | Mobile |
| --- | --- | --- |
| Restored source | [Source](desktop/restored.png) | [Source](mobile/restored.png) |
| Paused restoration | [Resume control](desktop/paused-restoration.png) | [Resume control](mobile/paused-restoration.png) |
| Completed-file refusal | [Error](desktop/completed-refused.png) | [Error](mobile/completed-refused.png) |

## Scoring the actual browser downloads

The scorer consumes the exported JSON files without editing them. A third planned
packet is deliberately left without a response so missing work stays counted.

| Final rehearsal measure | Count |
| --- | ---: |
| Planned tasks | 12 |
| Submitted tasks | 6 |
| Skipped tasks | 2 |
| Tasks from a missing session | 4 |
| Resumed tasks / sessions | 2 / 2 |
| Recoveries of each interrupted task | 2 |
| Submitted tasks eligible for timing medians | 4 |

The partial score also retains both drafts and both unseen tasks. Final scoring
excludes the two interrupted submissions from timing medians while retaining
their answers and completion status. Recorded times are automation durations and
must not be interpreted as human performance. Manual rationale assessments remain
separate; supplied correct answers do not establish defect recognition.

The twenty focused study/recovery/adjudication tests pass. Requalification of the
unchanged four-domain policy corpus passes **1,305 executions** across ordinary
Python, Python-hosted GWT, and the selected packaged native engine. The native
binary SHA-256 is
`f3c425ef4ff8d00a73f0e92121d61d25a8220febd0820057120bfd4eb2ab298a`.
No runtime, packet template, scorer, or recovery implementation changed.

## Artifacts and reproduction

`prepare-commands.json` and `score-commands.json` retain the actual CLI arguments.
`desktop/`, `mobile/`, and `missing/` contain frozen rehearsal packets and keys;
only the first two have downloaded responses. `partial-report.json` and
`complete-report.json` are scorer outputs. `policy-qualification.json`,
`tests.log`, and `verification.json` retain checks and identities.

Serve this checkpoint on loopback in one terminal:

```sh
python -m http.server 8901 --bind 127.0.0.1 --directory evaluations/human_review/2026-10-16-recovery-browser
```

Run these commands sequentially in another:

```sh
playwright-cli -s=gwt-human-recovery open http://127.0.0.1:8901/desktop/session.html --config evaluations/human_review/2026-10-16-recovery-browser/browser-config.json
playwright-cli -s=gwt-human-recovery run-code --filename evaluations/human_review/2026-10-16-recovery-browser/browser-check.js --json
playwright-cli -s=gwt-human-recovery run-code --filename evaluations/human_review/2026-10-16-recovery-browser/screenshots.js --json
playwright-cli -s=gwt-human-recovery close
```

The browser paths refer to this workspace and the installed Chromium binary.
The CLI result envelope's `result` is JSON text; check `isError`, since process
exit alone does not establish success. Re-running overwrites the synthetic
downloads/screenshots and produces new timing observations. Re-score those new
files before interpreting their reports. Stop the loopback server afterward.

The local test server exposes facilitator fixtures to the automation. A real
participant must receive only their frozen session HTML, as required by the
[study protocol](../../../docs/human-review-study.md). No participant recruitment,
external messages, live model calls, or external pilot occurred. The project goal
still requires actual representative human evidence and broader engineering work.
