# Delivery quotes with a scenario table

This illustrative policy quotes delivery from parcel weight and membership.
Parcels over 5,000 grams require a manual quote, including for members. Otherwise
members pay zero; other customers pay five units up to and including 1,000 grams
and nine units above that boundary. Weights must be positive integers. A manual
quote has a zero fee placeholder; its status tells the host that pricing remains
unresolved.

One `BACKGROUND` initializes the quote for each example. One scenario and ten
`EXAMPLES` rows state the boundary and precedence cases. The runtime checks every
expanded row before execution and gives each row fresh state and execution
budgets. The public request separately initializes its own quote for host calls.

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt-native -- check examples/native_delivery/rules.gwt
cargo run --locked -p gwt-core --bin gwt-native -- test examples/native_delivery/rules.gwt
cargo run --locked -p gwt-core --bin gwt-native -- run \
  examples/native_delivery/rules.gwt --request 'quote delivery' \
  --input examples/native_delivery/input.json
python -m gwtlang format examples/native_delivery/rules.gwt --check
python -m gwtlang validate examples/native_delivery/rules.gwt
```

The supplied request produces `{"quote":{"status":"standard","fee":9}}`.
Both toolchains execute the ten table rows. The native test suite separately
checks 16 host inputs around the boundaries and two invalid weights.

Native evidence starts with the selected example row and its source values.
Literal values substituted from a cell point back to that cell. Expressions
combining a template and substituted values point to the original template
line; their operands retain the more specific locations. Diagnostics identify
the expanded scenario and the offending cell or template location. The original
source remains the source of truth; expanded temporary text is not presented as
if it were a reviewed source file.

See [native scenario semantics](../../docs/native-semantics.md#backgrounds-and-example-tables)
for structure, source substitution, limits, and differences from the Python
toolchain. These tests establish execution behavior, not a measured improvement
in human comprehension.
