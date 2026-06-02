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
  --entry "fulfill order from inventory into fulfillment" \
  --json
```

## What This Stresses

- keyed lookup over a typed list of records
- mutation of a matched list record
- duplicate order lines for the same SKU
- unknown-SKU handling
- explicit missing-case behavior
- JSON host input using realistic nested records and lists
