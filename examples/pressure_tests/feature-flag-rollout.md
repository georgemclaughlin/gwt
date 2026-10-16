# Feature-flag rollout policy

[`feature_flag_rollout.gwt`](feature_flag_rollout.gwt) exposes `evaluate flag`.
Its policy is deliberately explicit:

1. A bucket outside 0 through 100 needs review, before any other gate.
2. A disabled account blocks the flag before the kill switch is considered.
3. An active kill switch blocks overrides and rollout rules.
4. The first override matching **both** account ID and flag key wins, including
   a disabling override before a later enabling duplicate. Its free-text note
   precedes the fixed decision reason.
5. An enabled rule for the requested segment or `all` qualifies when
   `bucket <= percent`. Enabled qualifying rules take priority over disabled
   fallback rules even when the disabled rule occurs earlier in the list.
6. With no qualifying enabled rule, the first matching disabled rule disables
   the flag regardless of its percent. With no matching fallback, the reason is
   `no_matching_rule`.

The inclusive boundary means bucket zero qualifies for a zero-percent enabled
rule. This is the existing example's policy, preserved and exposed by a scenario;
it is not a claim that a percentage denotes a statistical exposure rate or that
this is the right production rollout policy. Changing the bucket convention
requires an explicit policy revision.

`FlagDecisionReason` shares the decision's closed reason vocabulary with the
helpers. Constants are quoted at call sites for native literal semantics. The
[adaptation note](../../docs/native-domain-literals.md) records the narrower helper
boundary, failure timing, and Python/native interpretation limits. Both engines
run this example; native `number` uses exact decimal boundary rules.

From the repository root:

```sh
python -m gwtlang validate examples/pressure_tests/feature_flag_rollout.gwt --json
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- validate examples/pressure_tests/feature_flag_rollout.gwt
```

The ten scenario executions include first-match override handling, enabled-rule
priority at/above a cutoff, bucket zero, and clearing a prior kill-switch flag
and reason list when reusing the same decision. The
[independent qualification](../../evaluations/feature_flags/2026-10-16/README.md)
varies account gates, segments, bucket boundaries, overrides, and ordered rule
lists. It also detects incorrect cutoff, override matching, enabled filtering,
and reset changes. Local tests do not establish reviewer comprehension or
external adoption.
