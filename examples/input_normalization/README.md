# Input Normalization Example

This example shows the recommended v0.1 pattern for JSON payloads that may
contain null values.

GWT does not have a source-level `null` literal. Instead of passing nullable
fields into typed domain records, accept raw host data behind an `any` request
boundary and normalize it into explicit state:

```txt
raw JSON with possible nulls
  -> normalize raw into profile
  -> typed ContactProfile output
```

The JSON request contains a raw nullable field:

```json
{
  "raw": {
    "name": "Grace",
    "email": "grace@example.com",
    "middle_name_state": "missing",
    "middle_name": null
  }
}
```

The GWT behavior does not test for null. It uses the explicit
`middle_name_state` value and writes typed output:

```txt
profile.middle_name_status == "missing"
profile.middle_name == ""
```

## Commands

Static check:

```sh
python -m gwtlang check examples/input_normalization/rules.gwt
```

Run embedded scenario:

```sh
python -m gwtlang test examples/input_normalization/rules.gwt
```

Run with JSON input:

```sh
python -m gwtlang run examples/input_normalization/rules.gwt \
  --json-input examples/input_normalization/request.json \
  --entry "normalize raw into profile" \
  --json
```

## Why This Exists

Typed contracts reject JSON null for fields such as `text`, `number`,
`boolean`, `list`, records, and literal unions. That keeps domain behavior
explicit. Use `any` for raw host data, then normalize missing, unknown, or
not-applicable values into reviewable fields or one-of records.
