# USE Import Example

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
