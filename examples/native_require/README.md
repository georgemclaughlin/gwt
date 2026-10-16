# Prepare a bank transfer with sequential requirements

This native example prepares a transfer only when the amount is positive and
its method is a present, verified bank account with a nonempty reference. The
host supplies normalized facts and performs any actual banking operations.

The behavior uses sequential `REQUIRE` steps. Presence makes the method usable;
the kind requirement makes its bank payload usable. The remaining checks precede
all output mutation. Missing, cash, unverified, empty-reference, zero-amount, and
negative-amount cases stop with `assertion_failed`.

```sh
cargo run -p gwt-core --bin gwt-native -- validate examples/native_require/rules.gwt
cargo run -p gwt-core --bin gwt-native -- run examples/native_require/rules.gwt --request "prepare transfer" --input examples/native_require/request.json
```

The request returns account `bank-reference-1` and amount `100`. Seven embedded
scenarios contain 14 top-level expectations, including six expected failures.
The native suite checks 24 independent inputs and detects two newly accepted
inputs when verification is removed. It also captures, replays, compares, and
generates executable scenarios from the success and failure observations.

Python formatting preserves this source. Python validation rejects its native
`THEN fails with` expectations; it is explicitly assigned to the native example
suite. See [REQUIRE semantics](../../docs/native-require.md) for scope, mutation
protection, and deliberate compatibility changes.
