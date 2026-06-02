# Inventory Allocation Spike

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

The example is intentionally written with the current language only. It shows
that the runtime can express keyed allocation, but the expression is awkward:

```gwt
exists inventory_item in inventory.items WHERE inventory_item.sku == order_item.sku into inventory_match_found
IF inventory_match_found
  find inventory_item in inventory.items WHERE inventory_item.sku == order_item.sku into selected_inventory_item
  reserve_known_item order_item using selected_inventory_item into fulfillment
```

`selected_inventory_item` is a scratch state path that aliases the matched list
record. Mutating `selected_inventory_item.available` updates the record inside
`inventory.items`, which is useful but not obvious from the syntax. The scratch
paths also remain in full debug state, though `OUTPUT` keeps them out of the
stable `result` payload.

This makes the next language-design pressure point concrete: GWT likely needs a
first-class keyed collection update form, rather than relying on `exists`,
`find`, and alias mutation.

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
  --entry "fulfill order from inventory into fulfillment" \
  --json
```

## What This Stresses

- keyed lookup over a typed list of records
- mutation of a matched list record
- duplicate order lines for the same SKU
- unknown-SKU handling
- scratch state created by current lookup/update idioms
- JSON host input using realistic nested records and lists
