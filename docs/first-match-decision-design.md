# First-Matching Decisions

Status: implemented in parser, runtime, checker, formatter, docs, examples, and
VS Code syntax highlighting.

The pressure tests in `examples/pressure_tests/` exposed the same readability
problem across refund eligibility, subscription entitlements, feature-flag
rollouts, and fraud review: GWT is comfortable for request-shaped decision
workflows, but priority rules become deep `IF` / `ELSE` ladders or require
manual "already matched" state.

This proposal adds a narrow behavior-body statement for ordered decisions:

```gwt
DECIDE
  WHEN condition
    behavior
  WHEN another_condition
    behavior
  ELSE
    behavior
```

`DECIDE` evaluates branches from top to bottom, runs the first branch whose
condition is true, and skips the rest. `ELSE` is required so the no-match case
is explicit. If no work should happen, write an `ELSE` block containing `PASS`.

The goal is not to turn GWT into a policy engine or query language. The goal is
to make first-matching behavior read like an executable decision over state.

## Pressure Test Evidence

Fraud review classification currently reads as a nested priority ladder:

```gwt
WHEN classify fraud decision <decision>
  GIVEN decision is FraudDecision
  IF decision.has_severe_signal
    block risk with severe_signal into decision
  ELSE
    IF decision.chargeback_count >= 2
      block risk with repeat_chargebacks into decision
    ELSE
      IF decision.risk_score >= 60
        route risk to review with high_score into decision
      ELSE
        IF decision.unverified_payment and decision.large_order
          route risk to review with unverified_high_value into decision
        ELSE
          IF decision.country_mismatch or decision.has_velocity_signal
            route risk to review with signal_review into decision
          ELSE
            approve risk with low_risk into decision
```

With `DECIDE`, the same behavior keeps the priority visible without nesting:

```gwt
WHEN classify fraud decision <decision>
  GIVEN decision is FraudDecision
  DECIDE
    WHEN decision.has_severe_signal
      block risk with severe_signal into decision
    WHEN decision.chargeback_count >= 2
      block risk with repeat_chargebacks into decision
    WHEN decision.risk_score >= 60
      route risk to review with high_score into decision
    WHEN decision.unverified_payment and decision.large_order
      route risk to review with unverified_high_value into decision
    WHEN decision.country_mismatch or decision.has_velocity_signal
      route risk to review with signal_review into decision
    ELSE
      approve risk with low_risk into decision
```

Subscription entitlement classification shows the same shape:

```gwt
WHEN classify entitlement for <account> into <decision>
  GIVEN account is AccountRequest
  AND decision is EntitlementDecision
  IF decision.matched_override
    set decision.allowed to true
    set decision.status to "allowed"
    set decision.reason to "manual_override"
  ELSE
    IF decision.has_past_due_invoice
      set decision.status to "blocked"
      set decision.reason to "past_due_invoice"
      append "invoice_must_be_paid" to decision.reasons
    ELSE
      IF decision.seat_limit_exceeded
        set decision.status to "blocked"
        set decision.reason to "seat_limit_exceeded"
        append "reduce_users_or_buy_seats" to decision.reasons
      ELSE
        IF decision.required_plan_rank == 99
          set decision.status to "needs_review"
          set decision.reason to "unknown_feature"
          append "feature_catalog_missing" to decision.reasons
        ELSE
          IF decision.plan_rank >= decision.required_plan_rank
            set decision.allowed to true
            set decision.status to "allowed"
            set decision.reason to "feature_in_plan"
          ELSE
            set decision.status to "blocked"
            set decision.reason to "feature_requires_upgrade"
            append "upgrade_plan" to decision.reasons
```

After:

```gwt
WHEN classify entitlement for <account> into <decision>
  GIVEN account is AccountRequest
  AND decision is EntitlementDecision
  DECIDE
    WHEN decision.matched_override
      set decision.allowed to true
      set decision.status to "allowed"
      set decision.reason to "manual_override"
    WHEN decision.has_past_due_invoice
      set decision.status to "blocked"
      set decision.reason to "past_due_invoice"
      append "invoice_must_be_paid" to decision.reasons
    WHEN decision.seat_limit_exceeded
      set decision.status to "blocked"
      set decision.reason to "seat_limit_exceeded"
      append "reduce_users_or_buy_seats" to decision.reasons
    WHEN decision.required_plan_rank == 99
      set decision.status to "needs_review"
      set decision.reason to "unknown_feature"
      append "feature_catalog_missing" to decision.reasons
    WHEN decision.plan_rank >= decision.required_plan_rank
      set decision.allowed to true
      set decision.status to "allowed"
      set decision.reason to "feature_in_plan"
    ELSE
      set decision.status to "blocked"
      set decision.reason to "feature_requires_upgrade"
      append "upgrade_plan" to decision.reasons
```

Feature-flag rollout showed a related first-match collection problem. Current
GWT can express the behavior, but it needs explicit guard state:

```gwt
WHEN apply rollout rules for <request> into <decision>
  GIVEN request is FlagRequest
  AND decision is FlagDecision
  FOR rule in request.rollout_rules WHERE rule.enabled == true
    IF decision.matched_rule == false
      LET applies be segment matches rule for request
      IF applies and request.bucket <= rule.percent
        set decision.matched_rule to true
        enable flag with rollout_rule_enabled into decision
  IF decision.matched_rule == false
    FOR rule in request.rollout_rules WHERE rule.enabled == false
      IF decision.matched_rule == false
        LET applies be segment matches rule for request
        IF applies
          set decision.matched_rule to true
          disable flag with rollout_rule_disabled into decision
  IF decision.matched_rule == false
    disable flag with no_matching_rule into decision
```

`DECIDE` does not directly add loop control, but it improves the final
first-match fallback once facts have been collected:

```gwt
WHEN classify rollout result <decision>
  GIVEN decision is FlagDecision
  DECIDE
    WHEN decision.matched_enabled_rule
      enable flag with rollout_rule_enabled into decision
    WHEN decision.matched_disabled_rule
      disable flag with rollout_rule_disabled into decision
    ELSE
      disable flag with no_matching_rule into decision
```

If first-match collection remains awkward after `DECIDE`, consider a separate
follow-up around reusable predicates in `FIND` conditions or a narrow
`FIND FIRST` spelling. Do not bundle that into this proposal.

## Comparison With DEPENDING ON

`DEPENDING ON` and `DECIDE` should stay separate because they answer different
branching questions.

Use `DEPENDING ON` when the behavior dispatches on one known value or one
record kind:

```gwt
DEPENDING ON statement
  WHEN the kind is let_number
    store_number statement into runtime
  WHEN the kind is print_text
    emit_text statement into runtime
  ELSE
    append "unknown_statement" to runtime.errors
```

That reads as: look at this value, then run the behavior for its case.

Use `DECIDE` when the behavior chooses the first matching outcome from ordered
conditions:

```gwt
DECIDE
  WHEN decision.has_severe_signal
    block risk with severe_signal into decision
  WHEN decision.chargeback_count >= 2
    block risk with repeat_chargebacks into decision
  WHEN decision.risk_score >= 60
    route risk to review with high_score into decision
  ELSE
    approve risk with low_risk into decision
```

That reads as: evaluate these conditions in order, then run the first matching
outcome.

Extending `DEPENDING ON` to arbitrary conditions would be possible, but it
would blur its current meaning. `DEPENDING ON` should remain value/kind
dispatch. `DECIDE` should handle priority policy decisions.

## Syntax

Add `DECIDE` as a behavior-body statement.

```ebnf
behavior_statement
              = let
              | require
              | if_block
              | decide_block
              | for_block
              | find_block
              | depending_block
              | return
              | pass
              | builtin
              | behavior_call
              | and ;

decide_block  = "DECIDE", decide_branch+, "ELSE", behavior_block ;
decide_branch = "WHEN", condition, behavior_block ;
```

Indentation:

- `DECIDE` appears at behavior statement indentation.
- Each `WHEN` branch is indented two spaces under `DECIDE`.
- Each branch body is indented two spaces under its branch.
- `ELSE` is aligned with the branch `WHEN` lines.

Example:

```gwt
DECIDE
  WHEN decision.status == "blocked"
    PASS
  WHEN decision.risk_score >= 60
    route risk to review with high_score into decision
  ELSE
    approve risk with low_risk into decision
```

`WHEN` inside `DECIDE` is a branch label, not a behavior definition and not a
scenario `WHEN` step.

## Semantics

At runtime:

1. Evaluate branch conditions from top to bottom.
2. Execute the behavior block for the first condition that evaluates to true.
3. Skip all remaining branches.
4. If no condition is true, execute the required `ELSE` block.

Only one branch body executes. Branch conditions use the existing condition
grammar. Branch bodies use existing behavior statements.

`DECIDE` does not introduce fallthrough, priority numbers, rule names,
implicit scoring, implicit mutation, or table-driven execution.

## Checker Rules

The checker should:

- reject `DECIDE` outside behavior bodies
- require at least one `WHEN` branch
- require `ELSE`
- type-check every branch condition with existing condition rules
- type-check every branch body with existing behavior statement rules
- include `DECIDE` in behavior-body reserved words so behavior names cannot use
  it as a signature word

Potential diagnostic:

```text
DECIDE requires an ELSE block; use an ELSE block containing PASS when no default action is needed
```

## Formatter Rules

The formatter should:

- normalize `DECIDE`, branch `WHEN`, and `ELSE` keyword casing
- preserve branch order
- indent branch bodies exactly like `IF`, `FIND`, and `DEPENDING ON`
- validate the formatted output before writing, same as existing formatting

## Runtime And AST Changes

Implementation should mirror the existing structured block statements:

- Add a `DecideBlock` AST node with ordered branches and an else body.
- Reuse existing condition parsing and behavior-block execution.
- Execute only the first matching branch.
- Surface runtime errors with the branch line that failed where possible.

The debugger and inspection APIs do not need a public contract change for the
MVP. A later debugger enhancement could expose the selected branch.

## Guardrails

- Keep `DECIDE` inside behavior bodies only.
- Require explicit `ELSE`.
- Do not add rule tables, priority numbers, or SQL-like filtering.
- Do not make `DECIDE` an expression.
- Do not introduce implicit return values.
- Do not allow fallthrough.
- Do not combine this with collection search changes in the same feature.

## Alternatives Considered

### Keep Nested IF / ELSE

This requires no syntax, but four pressure tests reached the same readability
problem. The deeper the domain priority list, the less reviewable the behavior
becomes.

### Add ELSE IF

`ELSE IF` would reduce indentation, but it still frames the behavior as a
low-level control-flow chain. `DECIDE` better names the domain operation:
choose the first matching outcome.

### Extend DEPENDING ON

`DEPENDING ON` already means dispatch by one value or one record kind. Reusing
it for arbitrary ordered conditions would blur that meaning.

### Add RULES

`RULES` is tempting, but it points toward a general policy engine. GWT should
stay focused on executable behavior over state, not become an OPA-like policy
language.

## Adoption Plan

1. Implement parser, AST, runtime, checker, formatter, and syntax highlighting.
2. Add runtime and checker tests for selected branch, skipped branches, required
   else, nested use, and invalid locations.
3. Convert one pressure-test classifier to `DECIDE`.
4. Add a focused public example only if the syntax proves clearer after the
   pressure-test conversion.
5. Update `docs/grammar.md`, `docs/spec/v0.2.md`, `docs/language.md`, and
   relevant README/example text if the feature is accepted.

The acceptance bar is simple: the converted example should read more like an
ordered domain decision and less like control-flow plumbing.
