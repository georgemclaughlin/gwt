# Inventory Allocation Spike

> Historical example/reference. Only entries in the [active catalog](../catalog.json) are qualified for current GWT. Retired host commands can be reproduced from [the pre-retirement tree](https://github.com/georgemclaughlin/gwt/tree/4f403dc51eda5382c6a12c0757cb26deac34012a/examples/inventory_allocation_spike).

This example pressure-tests GWT against a more realistic inventory shape than
`examples/order_fulfillment`.

Instead of one field per SKU, inventory is modeled as a list:

```json
{
  "inventory": {
    "items": [
      { "sku": "widget", "available": 5, "reserved": 0 },
      { "sku": "gadget", "available": 1, "reserved": 0 }
    ]
  }
}
```

The example uses the first-class matched-record block that came out of this
pressure test:

```gwt
FIND inventory_item in inventory.items WHERE inventory_item.sku == order_item.sku
  reserve_known_item order_item using inventory_item into fulfillment
ELSE
  add 1 to fulfillment.unknown_sku_count
```

`inventory_item` is a local binding for the first matching list record. Mutating
`inventory_item.available` updates the record inside `inventory.items`, and the
required `ELSE` block keeps the unknown-SKU path explicit.

## Commands

Static check only:

```sh
python -m gwtlang check examples/inventory_allocation_spike/rules.gwt
```

Run embedded scenarios:

```sh
python -m gwtlang test examples/inventory_allocation_spike/rules.gwt
```

Run with production-style JSON input:

```sh
python -m gwtlang run examples/inventory_allocation_spike/rules.gwt \
  --json-input examples/inventory_allocation_spike/request.json \
  --request "fulfill order" \
  --json
```

## What This Stresses

- keyed lookup over a typed list of records
- mutation of a matched list record
- duplicate order lines for the same SKU
- unknown-SKU handling
- explicit missing-case behavior
- JSON host input using realistic nested records and lists

## Native required-lookup inspection

The Rust entry imports these same rules and uses a returning domain helper to
inspect allocated inventory:

```sh
cargo +1.96.0 run --locked -p gwt-core --bin gwt -- validate examples/inventory_allocation_spike/native_scenarios.gwt
cargo +1.96.0 run --locked -p gwt-core --bin gwt -- run examples/inventory_allocation_spike/native_scenarios.gwt --request "fulfill order" --input examples/inventory_allocation_spike/request.json
```

`inventory item for <sku> in <inventory>` returns a snapshot of the first match
or explicitly fails with `REQUIRE false`. The native entry includes the three
existing fulfillment scenarios plus duplicate-match/snapshot inspection and
missing-match failure. Python retains its original scenario entry because its
checker does not support scenario-level `WHEN LET` or native failure assertions.

Returning a record does not retain the legacy lowercase lookup's mutable alias.
Use `FIND ... ELSE` for mutations of selected inventory; the new helper is for
inspection. See [failure exits and migration](../../docs/native-failure-exits.md)
for error, sharing, and guard differences. The public fulfillment policy and
request/output contracts are unchanged.
