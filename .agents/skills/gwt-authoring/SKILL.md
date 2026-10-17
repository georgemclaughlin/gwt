---
name: gwt-authoring
description: Author and maintain executable GWT domain rules, validate changes, and review their effect on captured cases. Use for .gwt behavior changes and GWT rule migrations.
---

# GWT authoring and behavior review

GWT source is executable behavior. Keep domain rules in it; the host owns I/O.
Read `docs/agent-authoring.md`, `docs/spec/native-draft.md`, and a relevant entry
from `examples/catalog.json` before introducing unfamiliar syntax.

1. Run `gwt inspect rules.gwt` to discover contracts and behavior signatures;
   read the actual bodies and imported sources too.
2. Identify intended changed and preserved outcomes. Resolve precedence,
   rounding, failure, and missing-data policy before choosing behavior.
3. Add scenarios for boundaries and overlaps, with independent expected results.
4. Run `gwt format rules.gwt --write` and `gwt validate rules.gwt`. Repair
   structured diagnostics; reuse domain behaviors before proposing grammar.
5. If a captured corpus exists, run
   `gwt review corpus.json --candidate proposed.gwt --html review.html`.
   Reconcile every case, including failures and unverified baselines. A baseline
   mismatch is not evidence of a candidate regression.
6. Explain changed outcomes separately from changed execution paths. Generated
   scenarios capture observations; they do not decide intended outcomes.

Preserve source and engine identities, original cases, and recorded decisions.
Use only approved fixtures and destinations for review artifacts. Human sessions
and external pilots remain pending unless actual participants provide evidence.
