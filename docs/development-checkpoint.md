# Development checkpoint — October 2026

> Historical Python-era document. Reproduce its commands from [the pre-retirement tree](https://github.com/georgemclaughlin/gwt/tree/4f403dc51eda5382c6a12c0757cb26deac34012a). Current product guidance is in the [language reference](spec/native-draft.md), [upgrade guide](python-retirement.md), and [release checklist](release-checklist.md).

The next investment is evidence about maintenance and adoption. The grammar
remains v0.2; package metadata remains 0.3.0 while v0.4 publication gates are
open. No version bump, publication, or compatibility migration is implied.

The subsequent [project goal](project-goal.md) establishes human understanding
and a deliberately designed Rust foundation as the direction. Native work has
progressed from checked expressions to typed requests and scenarios in a native
language subset; the [goal ledger](project-goal-progress.md)
tracks its separate, incomplete scope and evidence requirements.

## Implemented in this checkpoint

- Paired GWT/Python maintenance preparation and scoring, with repeated trials,
  independent acceptance probes, changed/preserved outcomes, and public repair
  feedback through the existing optional model runner.
- A three-change refund rehearsal that freezes source, captures cases,
  generates observed scenarios, compares revisions, and leaves human review
  observations unfilled.
- A repository authoring skill over existing CLI contracts.
- Workbench case search and grouping by affected output fields, preserving the
  existing priority and collapsed path-only queue. Scenario previews explicitly
  distinguish observed behavior from intended expectations.
- A bounded cache for immutable literal-union type values. Profiling the vendor
  scenario command found 1,545 of 1,887 expression parses came from repeated
  literal-union parsing. The same profiled command after the change made 360
  expression parses. This is a local workload observation, not a cross-platform
  latency claim.
- Cross-layer checks for formatter result preservation, exact-decimal
  capture/scenario replay, and request-value isolation.
- A short README with detailed command examples preserved in
  [the reference](reference.md).

## Measured evidence and remaining work

The [live paired trial](../evaluations/maintenance/2026-10-15/README.md) used
`gpt-6-astra` at medium reasoning effort. GWT and Python each passed 9/9 code
trials on the first attempt and 3/3 clarification trials. Each code trial had
112 acceptance probes. No repairs were needed. Python's median code-call time
was 13.334 seconds versus 24.305 seconds for GWT, with different guide sizes
and output requirements. Exact tasks, responses, scores, and reported usage
are retained. This single-domain result establishes no GWT advantage.

The [browser check](../evaluations/workbench/2026-10-15/README.md) passed search,
combined filters, empty-state handling, selection, and path-only queue checks
on all three refund pages in headless Chromium. Desktop/mobile screenshots
were inspected; no page errors or horizontal overflow at 390px were found.

Next, compare harder changes across unrelated domains and measure human review
effort using [the protocol](maintenance-evaluation.md).

The refund workflow is a local rehearsal. Neither it nor earlier upstream
parity exercises fills the two external-pilot requirements. At least one
workflow still needs an outside maintainer to complete and use the review loop.
The owner confirmed on 2026-10-15 that no external pilot is available yet;
those requirements remain pending.

## Decisions and deferred work

- Owner decisions recorded on 2026-10-15: retain GWT for now and use MIT.
  The root license and package metadata are updated; no rename or publication
  is part of this checkpoint. Third-party attribution remains unchanged.
- Review and freeze compatibility fixtures after actual pilot feedback.
- Keep editor navigation as an explicit integration follow-up: static dossiers
  contain logical source locations, not a verified mapping to a reviewer's
  local checkout. Do not link misleadingly to a different revision.
- Add factual request dependency inspection when an editor/agent workflow
  demonstrates the required slice. Do not restore prompt composition as a
  versioned language API.
- Additional syntax and a hosted product still need maintenance and adoption
  evidence. The owner has since authorized the Rust foundation direction in
  the project goal; its semantic choices are recorded independently of Python
  conveniences in [the native audit](native-semantics.md).

The [release checklist](release-v0.4-checklist.md) remains the publication gate;
the [v0.4 roadmap](roadmap-v0.4.md) remains the broader implementation plan.

## Verified development branch checkpoint — 2026-10-16

The native foundation, editor/host integrations, semantic decisions, maintenance
evaluation tools, and selected evidence are checkpointed together on
`work/native-foundation-checkpoint`. The
[evaluation artifact policy](../evaluations/README.md) explains which generated
records stay local. This is a development backup, not a language release.

An export of the staged files passed 671 Python tests; 431 Rust tests and Clippy
on both Rust 1.85.0 and 1.96.0; current Rust formatting; all example formatting,
top-level checks and the two reference request workflows; 11 extension tests;
10 TypeScript client tests and type checking; and 13 native Node host tests.
Strict Pyright found a missing formatter list annotation, which was corrected;
Pyright and the 17 formatter tests then passed. Staged whitespace checks passed,
with intentional CRLF validation fixtures explicitly preserved in Git attributes.
These local checks do not replace the CI platform matrix.

The [CLI timing comparison](../evaluations/native_performance/2026-10-16-python-cli/README.md)
measures complete process invocations, not isolated interpreter execution.
The next engineering step is a separately labeled Codex CLI transport for the
five-domain model study. ChatGPT login can support that path without an API key;
the existing Responses API transport remains separately unqualified live.
Human sessions and external pilots remain pending by owner choice.
