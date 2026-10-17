# Stock reservation with native collection steps

This example processes order lines in source order against available inventory.
Each line uses the first inventory item with a matching SKU. If that item has
enough stock for the entire line, the behavior reserves the quantity and reduces
availability. Otherwise it records the SKU as a shortage. Missing SKUs are
recorded separately. Duplicate order lines see the inventory left by earlier
lines; duplicate inventory SKUs are not combined or searched for a better match.

All stock quantities must be nonnegative and every requested quantity positive.
The behavior validates those facts before allocating anything. An empty order
is valid. The result contains the reservation summary and updated inventory;
the caller's supplied JSON is unchanged.

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt -- check examples/native_reservation/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- test examples/native_reservation/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- run \
  examples/native_reservation/rules.gwt --request 'reserve order' \
  --input examples/native_reservation/input.json
```

The supplied request asks for nine units across three lines. It reserves three
widgets, reports a gadget shortage and an unknown SKU, and leaves four units
across the inventory. The three embedded scenarios cover this mixed outcome,
empty collections, and exact stock exhaustion.

The source uses the shared syntax and also validates with the Python toolchain:

```sh
gwt format examples/native_reservation/rules.gwt --check
gwt validate examples/native_reservation/rules.gwt
```

Native [collection semantics](../../docs/native-semantics.md#lists-iteration-and-collection-steps)
define mutable item aliases, fixed membership during traversal, exact sums,
and execution budgets independently of Python. This example exercises the
implemented native subset; it does not establish full v0.2 compatibility.

`crates/gwt-core/tests/collections.rs` checks 36 independent stock/quantity
combinations, repeated lines, rejection before allocation, and review of a
deliberately changed exact-stock boundary. Captured review evidence includes
each visited item, predicate result, inventory change, and sum contribution.
