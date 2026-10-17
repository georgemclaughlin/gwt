# Delivery routing by destination kind

Email, SMS, and collection in person each require a different destination field.
The executable rule handles every declared kind explicitly and copies its payload
into the route. Adding another kind requires updating this exhaustive decision.

From the repository root:

```sh
cargo build --locked -p gwt-core --bin gwt
target/debug/gwt validate examples/native_kind_dispatch/rules.gwt
target/debug/gwt test examples/native_kind_dispatch/rules.gwt
```

Three scenarios contain six expectations for the channel and destination. Rust
tests also supply independent host inputs for all three kinds and verify exact
outputs, capture/replay, and branch evidence.

This example uses native `kind:` setup. Inside `DEPENDING ON`, fields belonging
to the selected kind become available. The runtime prevents a shared alias from
changing that kind while the branch uses it. See
[native one-of semantics](../../docs/native-one-of.md) for exhaustive checking,
fallback branches, mutation rules, and remaining language gaps.
