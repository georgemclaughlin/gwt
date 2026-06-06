# Checkout Example

This example shows a small checkout workflow split into reusable rules,
scenario coverage, and a host-facing request file.

- `rules.gwt` defines the `Customer`, `Cart`, and `Order` records, the public
  `REQUEST checkout cart`, and the reusable checkout behavior.
- `scenarios.gwt` imports `rules.gwt` with `USE "./rules.gwt"` and runs an
  examples table.
- `request.gwt` supplies input state, invokes `REQUEST checkout cart`, and
  asserts the result in `--input` request mode.
- `request.json` supplies host-facing JSON input for `--json-input` plus
  `--request "checkout cart"`.

Run the scenario examples:

```sh
python -m gwtlang test examples/checkout/scenarios.gwt
```

Run the request against the checkout rules:

```sh
python -m gwtlang run examples/checkout/rules.gwt --input examples/checkout/request.gwt --json
```

Run the JSON request through the public interface:

```sh
python -m gwtlang run examples/checkout/rules.gwt --json-input examples/checkout/request.json --request "checkout cart" --json
```

`request.gwt` does not import `rules.gwt` because request mode pairs the files
at the CLI/API boundary. The program file provides the records and behavior;
the request file provides the starting state, public request call, and
assertions.
