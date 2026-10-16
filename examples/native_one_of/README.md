# Contact routing with one-of contracts

This native example describes a contact as either an email address or a phone
number. Each kind has a closed payload: a phone contact cannot carry email
fields. Both kinds share a label. The routing behavior reads the kind and label,
and returns the complete contact for the host to use.

Build and validate from the repository root:

```sh
cargo build --locked -p gwt-core --bin gwt-native
target/debug/gwt-native validate examples/native_one_of/rules.gwt
target/debug/gwt-native test examples/native_one_of/rules.gwt
```

The three scenarios check email routing, phone routing, and changing kind by
replacing the complete contact. They contain eight expectations. Invalid kinds,
missing payload fields, and fields from another kind are covered by the Rust
contract tests in `crates/gwt-core/tests/one_of.rs`.

This example uses the native explicit `kind:` initializer. Python's source
profile uses a different setup form. This foundation example only reads common fields and the discriminator.
The [delivery routing example](../native_kind_dispatch/README.md) demonstrates
exhaustive `DEPENDING ON` branches and kind-specific fields. See
[native one-of semantics](../../docs/native-one-of.md) for the current contract.
