# Feature-flag domain contracts — 2026-10-16

The [shared example](../../../examples/pressure_tests/feature_flag_rollout.gwt)
replaces unrestricted helper reason inputs with `FlagDecisionReason`, also used
by the decision field, and quotes domain constants. No native engine change is
made. `before.gwt` freezes the previous source. The resolved public request and
output shapes are preserved; direct helper acceptance/failure timing narrows.

`cross-engine/observations.json` records **6,272 inputs**, each executed under
the old and new Python source and the packaged native engine: **18,816 runs**.
An independent host decision table uses matching sets and ordered override
selection to specify outputs. The matrix crosses four account/kill-switch
combinations, four segments, eight bucket values, seven override arrangements,
and seven rule arrangements. All output values/types match, including every
terminal reason. The declared inputs are closed, valid integer-domain facts;
this is not equivalence for all numeric values, malformed inputs, or budgets.

`cross-engine/helper-boundary.json` executes the same appended direct-helper
request in both Python revisions. For an unrecognized reason, the original
changes `enabled` and `status` before failing at the reason field; the candidate
fails at the helper contract with the decision unchanged. The full errors,
input, source suffix, and partial states are retained. Native tests separately
refuse unknown literal reasons and bare unresolved words.

`extra-binding-observations.json` records an intentionally out-of-schema input.
Both Python revisions still resolve a quoted call token through an extra
top-level binding; native rejects that binding with `unknown_input`, no events,
and no execution. The adaptation does not claim Python quotation now has native
literal semantics. See the [design note](../../../docs/native-domain-literals.md).

`review/` contains eight real Python baseline captures, one for each terminal
reason, their inputs/selection, comparison JSON, and an offline HTML report.
Every baseline evidence digest verifies. All eight comparisons are classified
unchanged, with no output/path differences, failures, mismatches, incompatible,
or unavailable cases. The source/type changes and the separately demonstrated
helper-boundary difference still require review. No approval is recorded;
interactive browser validation remains pending.

Ten embedded scenarios pass in both engines. Three new Rust test groups cover
twelve independently expected request results with capture/replay, all scenarios,
the reused-decision reset fault, four captured incorrect-policy witnesses, and
direct helper acceptance/refusal. The witnesses detect a strict cutoff, matching
either override key instead of both, treating disabled rules as enabled, and
incorrectly refusing bucket zero.

All **401 Rust tests** and Clippy pass on Rust **1.85.0 and 1.96.0**. All **666
Python tests** pass. Required example/reference/extension and formatting checks
are recorded with the source hashes in `verification.json`. The engine's 56
source/build inputs and its retained packaged executable are unchanged. Earlier
package and installed-editor qualification remain applicable; no new deployment,
participant result, or live model comparison is implied.

Reproduce the input matrix in a fresh directory:

```sh
python -m evaluations.feature_flags.qualify --native /path/to/gwt-native --before evaluations/feature_flags/2026-10-16/before.gwt --output /path/to/new-feature-flag-checks
```
