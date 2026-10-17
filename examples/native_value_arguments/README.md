# Pricing with copied arguments

This native example passes a computed subtotal and a literal rate to a named
discount behavior. The behavior can change its local amount without changing
the basket's unit price or quantity. A quoted message containing `#` stays text.

```gwt
LET total be discount (basket.unit_price * basket.quantity) at 0.1
```

Bare paths share state; parentheses explicitly copy a path. The fifth scenario
calls `discount (basket.unit_price) at 0.1` and verifies the original price stays
unchanged. The other four scenarios cover ordinary/member totals, small exact
decimals, and a free item. This illustrative policy requires nonnegative prices
and positive quantities; it does not define rounding or a currency policy.

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt -- check examples/native_value_arguments/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- test examples/native_value_arguments/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- run \
  examples/native_value_arguments/rules.gwt --request 'quote basket' \
  --input examples/native_value_arguments/input.json
gwt format examples/native_value_arguments/rules.gwt --check
```

The request returns `{"quote":{"total":"35.91","note":"member # discount"}}`.
Python's formatter preserves this source, but its runtime/checker does not
support the grouped-call syntax. Use the native engine for execution and checks.

Native tests independently compute 32 pricing results with scaled integers and
exercise capture/replay, a twenty-percent candidate discount, and generated
regression scenarios. The review trail records copied values, their expression
operands, and mutations labeled `amount (value)`. See
[native argument semantics](../../docs/native-semantics.md#call-arguments) and
[browser evidence](../../evaluations/native_review/2026-10-16-arguments/README.md).
These are engineering checks, not a human-comprehension study.
