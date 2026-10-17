# USE Import Example

> Historical example/reference. Only entries in the [active catalog](../catalog.json) are qualified for current GWT. Retired host commands can be reproduced from [the pre-retirement tree](https://github.com/georgemclaughlin/gwt/tree/4f403dc51eda5382c6a12c0757cb26deac34012a/examples/use_import).

This example is grouped because the two GWT files are used together.

- `banking_module.gwt` defines reusable banking behavior.
- `use_import.gwt` imports that behavior with `USE "./banking_module.gwt"` and
  runs it against local account state.

Run it with:

```sh
python -m gwtlang run examples/use_import/use_import.gwt --json
```

The imported module contributes behavior definitions. Its scenarios, if any,
would not run as part of the importing program.
