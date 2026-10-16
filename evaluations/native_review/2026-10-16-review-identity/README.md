# Capture settings in native review identity — 2026-10-16

Saved review decisions previously omitted the complete case identity and captured
limits. The retained `before/` reproduction uses the previous packaged engine:
five invoice executions have identical full observations, but four use different
step, evidence, text, or call-depth limits. All four changed-budget corpora still
accepted decisions from the default-budget report. These are synthetic test
choices, not human or project approvals.

Native review schema 2 now includes the complete corpus digest and validated
per-case identities and limits. The existing decision hash covers that report,
so changes to any saved case—including budgets, migration provenance, and
unavailable payloads—make earlier choices stale. The HTML case panel exposes
captured limits without claiming the input represents all operating capacity.
The [artifact contract](../../../docs/native-review-decisions.md#artifact-contract)
documents the transition from schema 1 and the need for fresh review choices.

`development/` and authoritative `packaged/` reproduce the same five captures
with the correction. Full execution observations remain identical. Each changed
budget now produces `decisions_stale`; matching choices still assess successfully.
Two new Rust integration groups independently check corpus hashing, budget-only
changes, unavailable payloads, complete embedded report JSON, and metadata
rendering. The CLI test also rechecks a budget change against saved decisions.
All **418 Rust tests** and Clippy pass on **1.85.0 and 1.96.0**.

Following the owner's explicit permission, browser checks use **Playwright CLI
0.1.13** with an isolated installed **Chromium 153.0.8010.12**. The default CLI
Chrome channel was absent; `browser-config.json` selects the installed executable.
A local HTTP server served only this checkpoint because the CLI blocks `file:`
navigation. The session and server were closed after testing.

`browser/qualification.json` records **20 browser checks**: rendered budgets,
actual decision download/restore, stale-decision refusal for all four changed
limits, retention of the current reviewer and notes, no mobile horizontal
overflow, and no browser script errors. The downloaded review JSON equals the
generated report exactly. The actual browser-downloaded choices pass CLI
assessment for their own report and fail with `decisions_stale` for all four
budget revisions. Desktop and mobile screenshots were visually inspected.
`browser-check.js` retains the exact UI rehearsal.

`package/` qualifies the offline Cargo artifact and static executable, independent
Rust host, installed and relocated binaries, eighteen profiles/replays, and 288
concurrent executions. Four packaged unit tests are separate from the full
workspace integration suite. `migration/` verifies **72 unchanged full execution
observations** across the engine transition: the prior 63-case portfolio plus
nine regression cases, including failed boundaries and resource budgets. Every
candidate case replays; no migration approval or corpus replacement was made.

Reproduce the CLI identity check using a new output directory:

```sh
python evaluations/native_review/qualify_review_identity.py \
  --native /path/to/gwt-native --output /path/to/new-identity-checks \
  --expect-binding present
```

Use `--expect-binding missing` only to reproduce the defect against the retained
previous executable. `verification.json` records source/artifact hashes and final
checks. This fixes review fidelity; synthetic reviewer actions do not establish
human comprehension benefit. The full project goal remains incomplete, with
human evidence, live native model comparison, language decisions, and deployment
qualification still open. External pilots remain deferred.
