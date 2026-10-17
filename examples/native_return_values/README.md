# Pricing with named calculations

This example uses returning behaviors to give calculations domain names:
`calculate subtotal for order`, `discount rate for order`, and
`calculate total for order`. The request still declares its public output;
intermediate calculations use typed values instead of output parameters.

The illustrative policy charges unit price times quantity, with a ten-percent
member discount. Prices must be nonnegative and quantities positive. Arithmetic
is exact; no rounding or currency policy is implied.

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt -- check examples/native_return_values/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- test examples/native_return_values/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- run \
  examples/native_return_values/rules.gwt --request 'quote order' \
  --input examples/native_return_values/input.json
gwt validate examples/native_return_values/rules.gwt
```

The native request returns `{"quote":{"total":"35.91"}}`. Four scenario rows
cover ordinary/member totals, a small exact decimal, and a free item. Native
tests independently compute 32 totals using scaled integers and compare a
candidate with a twenty-percent member discount through capture, replay,
comparison, and generated regression scenarios. This is a language example,
not an external adoption or human-comprehension study.

Returning native behaviors declare `THEN returns Type` and return on every
normal path. `LET` binds the result of a whole behavior call. This example uses
typed state-path arguments; returning a value does not make a behavior pure or prohibit
parameter mutation. See the [native return rules](../../docs/native-semantics.md#returned-behavior-values).
The separate [value-argument example](../native_value_arguments/README.md) shows
native-only copied arguments and grouped calculations.
