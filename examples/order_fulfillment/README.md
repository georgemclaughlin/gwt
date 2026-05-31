# Order Fulfillment Example

This folder shows a state-transition workflow: an order is authorized, allocated
against inventory, classified as ready/partial/backordered/held, and assigned
shipping details.

- `rules.gwt` contains reusable fulfillment behavior and embedded regression
  scenarios.
- `request.gwt` is a production-style request with no expected output.
- `request_with_assertions.gwt` is the same request with `THEN` assertions.

The order lines use a GWT data table:

```gwt
GIVEN order.items are
  | sku      | quantity |
  | "widget" | 1        |
  | "gadget" | 2        |
```

Each row becomes a record, so behavior can loop over `order.items` and read
`item.sku` or `item.quantity`. Inventory is still modeled with explicit fields,
which keeps the example inside the current language while showing where future
lookup/filter operations would help.

## Commands

Static check only:

```sh
python -m gwtlang check examples/order_fulfillment/rules.gwt
```

Run embedded tests:

```sh
python -m gwtlang test examples/order_fulfillment/rules.gwt
```

Run like an application would:

```sh
python -m gwtlang run examples/order_fulfillment/rules.gwt --input examples/order_fulfillment/request.gwt --json
```

Run the request and assert expected output:

```sh
python -m gwtlang run examples/order_fulfillment/rules.gwt --input examples/order_fulfillment/request_with_assertions.gwt --json
```

## What This Stresses

- multi-step state transitions
- payment and fraud gates before allocation
- inventory mutation
- partial fulfillment and backorders
- list iteration for requested unit totals
- nested behavior calls and return values
- app-style request execution versus embedded regression scenarios

`gwt check` validates the file statically, but does not execute the scenarios.
`gwt test` runs the embedded `SCENARIO` / `EXAMPLES` table. `gwt run --input`
is the production-style path a host app would use to compute JSON output.
