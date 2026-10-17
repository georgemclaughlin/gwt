# Exact packing-receipt output

This native example produces a heading, a parcel record, and its quantity as
three captured JSON values. `THEN prints [...]` checks the entire ordered
sequence. A second scenario explicitly expects no output with `THEN prints []`.

The illustrative request requires a positive quantity. Its large integer fixture
tests exact JSON preservation; it does not impose a real shipping policy.

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt -- check examples/native_print_expectations/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- test examples/native_print_expectations/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- run \
  examples/native_print_expectations/rules.gwt --request 'print receipt' \
  --input examples/native_print_expectations/input.json
gwt format examples/native_print_expectations/rules.gwt --check
```

The request has no declared outputs, so its result is `{}`. Its captured output is:

```json
["Packing receipt", {"label": "fragile # café", "quantity": 9007199254740993}, 9007199254740993]
```

Changing the printed quantity to `parcel.quantity + 1` fails the first scenario
with `print_assertion_failed`. Prior output remains visible, and the assertion
event links to the individual print events. Native capture, replay, comparison,
and [scenario generation](../../docs/native-scenarios.md) support this observation.

The expectation array is a literal JSON snapshot, not an expression. Decimal
values use exact strings; nested lists need another array level. The assertion
checks output so far and cannot catch an earlier execution failure. See
[the native semantics](../../docs/native-semantics.md#printed-output-expectations).
Python formatting preserves this syntax, but its runtime/checker does not
support it. [Browser qualification](../../evaluations/native_review/2026-10-16-prints/README.md)
checks the changed receipt, unchanged quiet scenario, and fixed host request.
