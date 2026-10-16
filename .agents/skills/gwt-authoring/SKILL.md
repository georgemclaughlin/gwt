---
name: gwt-authoring
description: Author and maintain executable GWT domain rules, validate changes, and review their effect on captured cases. Use for .gwt behavior changes and GWT rule migrations.
---

# GWT authoring and behavior review

GWT source is the executable behavior. Keep domain rules in it; the host owns
I/O and normalization. Work within the existing public request and output
vocabulary unless the task changes that contract.

Read the repository's `docs/agent-authoring.md` and a relevant worked example
before introducing unfamiliar syntax. `examples/language_tour/rules.gwt`
covers syntax; `examples/refund_review/` demonstrates maintenance. Run
`python -m gwtlang inspect path/to/rules.gwt --json` to discover contracts and
behavior signatures, then read the actual behavior bodies and imported modules.
Inspection is an index, not a substitute for those bodies.

For a behavior change:

1. Identify the intended changed outcomes and the outcomes that must remain.
   Resolve missing precedence, rounding, or exception policy before choosing it.
2. Add or update scenarios for boundaries and overlapping conditions. Keep
   independent acceptance inputs or an existing host oracle where available;
   passing self-authored assertions alone does not establish correctness.
3. Run `python -m gwtlang format path/to/rules.gwt`, then
   `python -m gwtlang validate path/to/rules.gwt`. Repair the structured
   diagnostics. Reuse domain behaviors before proposing new grammar.
4. If a case corpus exists, compare the frozen baseline and candidate with
   `python -m gwtlang compare --corpus corpus.json --old baseline.gwt --new candidate.gwt --json`.
   Reconcile every case, including failures, unavailable evidence, and baseline
   mismatches. A mismatch is not evidence of a candidate regression.
5. Produce a review artifact when useful with
   `python -m gwtlang workbench --corpus corpus.json --old baseline.gwt --new candidate.gwt --output review.html`.
   Explain changed outputs separately from path-only changes, and report what
   was actually checked.

`scenario-from-run` reproduces observed behavior. It does not decide the desired
outcome: change its expected assertions only from stated intent. Keep frozen
baseline source and dependencies available for replay. Case and HTML artifacts
may contain full input values; use the task's approved fixtures and destination.

Use `docs/maintenance-evaluation.md` for comparative experiments and
`docs/external-pilot-v0.4.md` for actual outside-user adoption trials. A local
rehearsal or generated report does not count as outside-user evidence.
