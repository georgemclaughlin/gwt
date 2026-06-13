# GWT JSON Schemas

These schemas describe the stable JSON payloads emitted by the CLI and public
API helpers:

- `diagnostic.schema.json` for checker, parser, formatter, runtime, and lint
  diagnostics.
- `execution.schema.json` for `gwt run --json` and `gwt test --json`.
- `check.schema.json` for `gwt check --json`.
- `inspect.schema.json` for `gwt inspect --json`.
- `validation.schema.json` for `gwt validate --json`.
- `version.schema.json` for `gwt version --json`.

Schemas are additive contracts. New optional fields may be added as tooling
evolves; incompatible shape changes should bump the payload `schemaVersion`.
