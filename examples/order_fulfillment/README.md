# Order Fulfillment Example

This folder shows a state-transition workflow: an order is authorized, allocated
against inventory, classified as ready/partial/backordered/held, and assigned
shipping details.

- `rules.gwt` contains reusable fulfillment behavior and embedded regression
  scenarios.
- `request.gwt` is a production-style request with no inline assertions.
- `request_with_assertions.gwt` is the same request with `THEN` assertions.
- `request.json` is the same production request as JSON state for host
  integrations.

The rules declare a host-facing interface with `REQUEST order`,
`REQUEST inventory`, `REQUEST fulfillment`, and `OUTPUT fulfillment` /
`OUTPUT inventory`. JSON/API runs return a stable envelope whose `result`
contains only the declared outputs while the full `state` remains available to
tests and debuggers.

The order lines use a GWT data table:

```gwt
GIVEN order.items are OrderItem
  | sku      | quantity |
  | "widget" | 1        |
  | "gadget" | 2        |
```

Each row becomes an `OrderItem` record, so behavior can loop over
`order.items` and read `item.sku` or `item.quantity` with checker-visible
field types. Inventory is still modeled with explicit fields, which keeps the
example inside the current language while showing where future lookup/filter
operations would help.

Fulfillment status and reason fields use literal-union contracts, so unexpected
state labels are rejected. Unknown SKUs are counted and produce a held decision
with reason `"unknown_sku"` instead of being silently ignored.

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

Run like a JSON-speaking host application would:

```sh
python -m gwtlang run examples/order_fulfillment/rules.gwt \
  --json-input examples/order_fulfillment/request.json \
  --entry "fulfill order from inventory into fulfillment" \
  --json
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
- typed table rows and list iteration for requested unit totals
- literal-union workflow state
- explicit unknown-SKU handling
- nested behavior calls and return values
- app-style request execution versus embedded regression scenarios

`gwt check` validates the file statically, but does not execute the scenarios.
`gwt test` runs the embedded `SCENARIO` / `EXAMPLES` table. `gwt run --input`
is the production-style path a host app would use to compute JSON output.
