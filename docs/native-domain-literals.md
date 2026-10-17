# Domain reason contracts and explicit native literals

The [feature-flag example](../examples/pressure_tests/feature_flag_rollout.gwt)
now names its closed reason vocabulary once and uses it in both its decision
record and helper inputs:

```gwt
TYPE FlagDecisionReason is "new" | "account_disabled" | "kill_switch" | "override_enabled" | "override_disabled" | "rollout_rule_enabled" | "rollout_rule_disabled" | "no_matching_rule" | "invalid_bucket"
```

Its decision field is `reason: FlagDecisionReason`; the enabling and disabling
helpers declare `GIVEN reason is FlagDecisionReason`. The resolved public
request/output shapes remain the same. Previously the helpers accepted any
`text` and then assigned it to the narrower decision field, which native static
checking correctly refused. The adaptation makes the helper's promise match
the values it can actually store, rather than weakening the decision field.

Call sites explicitly quote source constants:

```gwt
disable flag with "kill_switch" into decision
```

In native GWT, an unquoted word in an argument position is a binding reference;
a quoted string is a copied literal value. No unknown name is guessed to be
domain text. This keeps the distinction between a reason chosen by the source
and a value read from state visible to the reader. Quoted values are checked
against the helper's declared domain. The alias does not add a runtime wrapper
or enforce every possible status/reason pairing by itself.

## Preserve the policy while making the contract explicit

The [worked policy note](../examples/pressure_tests/feature-flag-rollout.md)
documents the existing precedence and boundary behavior. The adaptation leaves
that policy intact on the checked closed inputs. It adds scenarios for duplicate
overrides, enabled-rule priority, inclusive cutoff behavior, and decision reuse.

Direct helper callers can observe a deliberate change. An unknown reason used
to enter the Python helper, change `enabled` and `status`, and then fail while
writing the closed reason field. The narrowed contract rejects that call before
those partial writes. The native compiler also rejects a literal outside the
declared vocabulary. Arbitrary helper callers are therefore not transparently
compatible even though the public request's valid-domain results are preserved.

The Python call machinery still has legacy token resolution: quotation alone
does not guarantee native literal semantics. A retained probe supplies an extra
top-level `kill_switch` binding alongside the declared request. Both Python
revisions use that value as the helper reason, while native rejects the extra
binding before execution under its closed input contract. This is outside the
qualification's declared input schema and is not hidden by a whole-engine
equivalence claim. The native literal rule does not redefine Python v0.2.

## Evidence and scope

[Qualification](../evaluations/feature_flags/2026-10-16/README.md) checks 6,272
independently modeled inputs in both Python source revisions and the existing
packaged native engine. It retains the helper partial-state change and the
extra-binding engine difference separately. Eight actual baseline captures,
covering every terminal reason, are verified and compared with the candidate.
Ten embedded scenarios and native fault/replay checks exercise the intended
behavior. No parser, checker, or runtime change is needed for this adaptation.

[Browser qualification](../evaluations/workbench/2026-10-16-adaptations/README.md)
checks the retained report's eight-case unchanged summary and desktop/mobile
presentation. It preserves the distinction between the public-input comparison
and the separately measured helper-boundary change.

This supplies a worked pattern for a helper assigning a closed decision value.
Other examples need their own contract and policy checks; introducing an alias
does not automatically justify narrowing every `text` parameter. It also does
not establish a human-comprehension benefit without actual reviewers.
