# Checkout Example

This example shows a small checkout workflow split into reusable rules,
scenario coverage, and a host-facing request file.

- `rules.gwt` defines the `Customer`, `Cart`, and `Order` records plus the
  checkout behavior.
- `scenarios.gwt` imports `rules.gwt` with `USE "./rules.gwt"` and runs an
  examples table.
- `request.gwt` supplies input state and assertions for `--input` request mode.

Run the scenario examples:

```sh
python -m gwtlang test examples/checkout/scenarios.gwt
```

Run the request against the checkout rules:

```sh
python -m gwtlang run examples/checkout/rules.gwt --input examples/checkout/request.gwt --json
```

`request.gwt` does not import `rules.gwt` because request mode pairs the files
at the CLI/API boundary. The program file provides the records and behavior;
the request file provides the starting state, behavior call, and assertions.
