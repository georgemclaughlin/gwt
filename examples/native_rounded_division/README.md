# Quoted unit price

This illustrative policy divides a total by a positive unit count and quotes a
unit price at two decimal places, using `half_even`. Eight scenarios cover
recurring quotients, both midpoint directions, negative totals, exact division,
zero totals, and an invalid unit count.

```sh
cargo run -p gwt-core --bin gwt -- validate examples/native_rounded_division/rules.gwt
cargo run -p gwt-core --bin gwt -- run examples/native_rounded_division/rules.gwt --request "quote unit price" --input examples/native_rounded_division/request.json
```

The request produces `{"price":"0.33"}`. The policy is visible in the domain
behavior body. Changing it to `half_away_from_zero` deliberately changes some
midpoint results; tests and captured-case review expose those changes.

This quotes a unit price, not a distribution of the total. It does not promise
that rounded price multiplied by units equals the original total. Currency and
business-specific rounding requirements must be chosen explicitly for a real
workflow. See [native rounding semantics](../../docs/native-rounded-division.md).
