# Exact Pricing Example

This example shows a small host-facing pricing workflow:

- `integer` for counts
- `decimal` for exact base-10 values
- scalar `DEPENDING ON` for cart mode
- `REQUEST price cart` as the stable host-facing request
- generated Python request/output types and request-specific client method
- Python `compile` once / call many times flow

Run the embedded GWT scenario:

```sh
python -m gwtlang test examples/exact_pricing/rules.gwt
```

Run the fuller Python host example:

```sh
python examples/exact_pricing/host_app.py
```

Regenerate the Python helper module after changing the public records or
request boundary:

```sh
python -m gwtlang types examples/exact_pricing/rules.gwt \
  --language python \
  --output examples/exact_pricing/rules_types.py
```

The Python example validates the rules file, inspects the public request,
executes `price cart` through the generated `ExactPricingClient`, prints the
JSON payload, shows the runtime `Decimal`, rejects accidental JSON float input,
and demonstrates `run_trusted_json()` for already-prevalidated internal state.

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
