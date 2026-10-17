# Authoring executable GWT behavior

GWT source is the program. Keep domain rules in `.gwt`; the host owns I/O and
external effects. Use the [language reference](spec/native-draft.md) and
[validated examples](../examples/README.md) for the current engine.

1. Inspect the existing contracts with `gwt inspect rules.gwt`, then read the
   actual bodies and imported sources. Inspection does not replace reading.
2. State intended changed and preserved outcomes, including failure, precedence,
   rounding, missing data, and overlapping conditions.
3. Write scenarios with independent expected outcomes. Use focused behaviors
   over typed state; avoid carrying over Python conventions by default.
4. Run `gwt format rules.gwt --write`, then `gwt validate rules.gwt`. Repair
   diagnostics and repeat. Declaration-only modules can use the explicit
   `--allow-no-scenarios` validation option.
5. Capture baseline requests with `gwt capture`, group them with `gwt corpus`,
   then use `gwt review corpus.json --candidate proposed.gwt --html review.html`.
6. Inspect outcome, state, and evidence changes, including preserved failures
   and unavailable cases. Review intent separately from observed execution.

Generated scenarios reproduce observations; they do not determine desired policy.
Saved decisions bind to the exact fresh comparison. Never manufacture human
approval or relabel a fixture check as a human study or external pilot.

See the [delivery walkthrough](native-review-walkthrough.md) for a complete
worked change and [maintenance evaluation](../evaluations/native_maintenance/README.md)
for experiments. Historical evaluation results remain separate from current runs.
