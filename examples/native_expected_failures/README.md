# Stock rejection as an executable expectation

This example reserves stock only for positive quantities that are available.
It prints `"checking stock"` after the positive-quantity guard, then prints
`"reserved"` only after reducing the stock. Four scenario cases cover a valid
reservation, a shortage, zero quantity, and negative quantity.

```gwt
REQUEST reserve stock
THEN fails with "assertion_failed"
AND stock.available == 2
AND prints ["checking stock"]
```

The failure expectation applies only to that request action. The scenario passes
when the expected rejection occurs and the later assertions match. It does not
roll back changes; the stock assertion proves this rejection left stock intact.

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt -- check examples/native_expected_failures/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- test examples/native_expected_failures/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- run \
  examples/native_expected_failures/rules.gwt --request 'reserve stock' \
  --input examples/native_expected_failures/input.json
gwt format examples/native_expected_failures/rules.gwt --check
```

The host `run` command intentionally exits **1** with `assertion_failed`, unchanged
stock of 2, and captured output `["checking stock"]`. The native `test` command
exits **0** because all four scenario expectations pass. Python formatting works;
Python runtime/checker support for the new assertions is not claimed.

Twenty-five independently specified stock/quantity combinations exercise raw
request outcomes and generated regression scenarios. Removing the stock guard
makes shortage scenarios fail through unexpected success. Moving stock mutation
before rejection fails the generated post-failure input assertion. Neither
change is accepted merely because some error occurred.

See [native failure semantics](../../docs/native-semantics.md#expected-action-failures),
[generation commands](../../docs/native-scenarios.md#generate-an-expected-failure-scenario),
and [browser evidence](../../evaluations/native_review/2026-10-16-failures/README.md).
Only the documented behavior error codes are expectable. Invalid host inputs,
resource limits, and engine errors remain explicit failures, not passing tests.
