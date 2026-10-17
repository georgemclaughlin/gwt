# Delivery response with scalar dispatch

This native example chooses an action from a delivery status, assigns retry
delays of 5 and 15 for attempts one and two, and otherwise requests manual
review. A separate exhaustive boolean decision controls the notice. Every
request requires a positive attempt number.

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt -- validate examples/native_value_dispatch/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- run examples/native_value_dispatch/rules.gwt --request "review delivery" --input examples/native_value_dispatch/request.json
gwt format examples/native_value_dispatch/rules.gwt --check
```

The request returns `{"decision":{"action":"retry","delay":15,"notice":"retry"}}`.
Six embedded example rows contain 18 top-level expectations, in addition to the
positive-attempt requirement checked on each run. Native tests independently
check 30 status/attempt/notice combinations and two invalid attempts. A candidate
that changes the second delay to 25 affects exactly the two second-attempt retry
probes and is visible through captured-case comparison.

This is a native-profile example: complete boolean dispatch does not need an
`ELSE`. Python's formatter preserves the source, but its current checker requires
an `ELSE` for the plain boolean subject. Native numeric labels also use exact
value equality across integers and decimals. See
[native scalar dispatch](../../docs/native-value-dispatch.md) for semantic
choices, coverage rules, and migration implications.
