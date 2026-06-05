# Exact Pricing Example

This example shows a small host-facing pricing workflow:

- `integer` for counts
- `decimal` for exact base-10 values
- scalar `DEPENDING ON` for cart mode
- `EXPORT price_cart_v1 as price cart` as the stable host entry name
- Python `compile` once / call many times flow

Run the embedded GWT scenario:

```sh
python -m gwtlang test examples/exact_pricing/rules.gwt
```

Run the fuller Python host example:

```sh
python examples/exact_pricing/host_app.py
```

The Python example validates the rules file, inspects the public export,
executes `price_cart_v1`, prints the JSON payload, shows the runtime
`Decimal`, rejects accidental JSON float input, and demonstrates
`call_trusted_json()` for already-prevalidated internal state.

For host JSON boundaries, send decimals as strings:

```json
{
  "cart": {
    "mode": "reserve",
    "quantity": 2,
    "unit_price": "12.30",
    "total": "0.00",
    "status": "pending"
  }
}
```
