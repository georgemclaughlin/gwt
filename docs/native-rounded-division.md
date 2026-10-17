# Explicitly rounded division

The experimental native engine supports a behavior step with a source-selected
rounding policy:

```gwt
  divide total by units rounded to 2 places using half_even into price
```

Both operands must be numeric expressions and the existing destination must be
decimal. The scale is a literal integer from 0 through 512. The mode is one of
the five literal names below. Nothing supplies an implicit currency scale or
rounding mode. Use a domain behavior such as `quote <total> across <units> into
<price>` around this arithmetic step so callers read domain intent.

| Mode | Rule |
| --- | --- |
| `half_even` | Nearest multiple of the requested decimal unit; an exact tie selects the even coefficient |
| `half_away_from_zero` | Nearest multiple; an exact tie selects the value farther from zero |
| `toward_zero` | Discard the fractional part at the requested scale |
| `floor` | Toward negative infinity |
| `ceiling` | Toward positive infinity |

At scale two, `10.05 / 2` becomes `5.02` with `half_even` and `5.03` with
`half_away_from_zero`. `-1 / 3` becomes `-0.34` with `floor` and `-0.33` with
`ceiling`. Sign applies to the quotient, so negative denominators follow the
same rules. Zero has no negative sign. Results retain the existing canonical
exact-decimal encoding; scale controls arithmetic, not trailing-zero formatting.

## Execution model

The engine evaluates the numerator and denominator once, left to right, using
ordinary expression semantics. It forms their exact rational quotient and rounds
once to a multiple of `10^-scale`, using integer quotient/remainder arithmetic.
The host floating-point environment and Python decimal context do not participate.
A zero denominator fails with `division_by_zero`. Existing numeric digit limits
still apply; a legal scale does not guarantee that every result fits those limits.

Ordinary `/` remains exact-only. `1 / 3` still fails with
`nonterminating_decimal`. Rounding applies only to the final quotient of this
step: writing `(1 / 3)` as an operand fails before the step can round it.
Use `divide amount by 1 ...` when rounding an already finite amount. No general
rounding function or automatic arithmetic coercion is introduced.

The existing statement and expression budgets apply. On success, an evidence
event named `rounded division` records the literal scale, mode, result, and links
to both evaluated operands. A subsequent ordinary `set` event records the state
change and links to that result. The usual mutation, alias, presence/kind, and
traversal checks apply. A failed calculation or failed evidence recording cannot
write the destination; earlier completed statements retain their normal effects.

Static errors use `rounding_syntax`, `rounding_scale`, `rounding_mode`, or
`rounding_type`. Division by zero can be an expected scenario failure under the
existing failure-expectation rules; resource/numeric limits cannot be treated as
successful domain scenarios. The formatter preserves the step, and native editor
navigation resolves its operand and destination paths.

## Design and compatibility

A separate step keeps loss of precision visible in executable source. In
particular, rounding is not an invisible change to `/`, request normalization,
or the host application's adapter. Scale and mode are deliberately literal so
reviewers can see the selected policy at the arithmetic operation; domains may
choose between explicit steps with existing decisions.

`divide` is now a reserved built-in behavior name. Existing custom behaviors
using that verb must be renamed before adopting this engine. Frozen cases keep
their original source and engine: an unadapted case with that definition becomes
unavailable to the new engine, rather than being silently reinterpreted. Use the
retained prior engine to validate a source rename, then explicitly migrate cases.
Python's reference runtime does not implement this native step. Python formatting
still applies; native-only examples are explicitly registered for native testing.

This closes explicit rounded quotient arithmetic, not every numeric-policy need.
Currency units, allocation remainders, fixed-width display, and business-specific
policy choices remain domain responsibilities. The [quote example](../examples/native_rounded_division/README.md)
illustrates a chosen policy; it is not a universal financial rule or an allocation
algorithm. Multiplying a rounded unit price by a count may differ from the total.

For threshold decisions, a quotient need not always be materialized. The
[underwriting adaptation](native-exact-ratios.md) uses explicit ratio records and
positive-denominator comparisons, keeping recurring decimals out of decision
calculations. It changes the output representation rather than selecting an
arbitrary precision for a decision input.
