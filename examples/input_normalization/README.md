# Input normalization with declared facts

This example accepts a known JSON shape and keeps normalization decisions in
GWT. `RawContactInput` declares name, email, the explicit middle-name state,
and an `optional<text>` middle name. It runs in Python and native GWT without
an `any` input.

```text
host JSON -> declared RawContactInput -> GWT behavior -> ContactProfile
```

Omitted and JSON-null middle names both mean absence. The separate
`middle_name_state` distinguishes `provided`, `missing`, and `not_applicable`.
Unknown text labels remain accepted input so GWT can return its existing
`invalid_middle_name_state` validation error.

- `provided` requires present text. Empty text is present and remains accepted;
  an absent value fails an assertion instead of producing a profile.
- `missing` and `not_applicable` produce their named state and an empty output
  middle name, even when the input supplies unused text.
- Empty name/email values produce domain errors in a successful request's
  `profile.status == "invalid"` result. Malformed input types fail contract validation.

The checked-in [request](request.json) supplies a null middle name with the
`missing` state. It returns a normalized Grace profile with empty middle name.

From the repository root:

```sh
python -m gwtlang validate examples/input_normalization/rules.gwt
python -m gwtlang run examples/input_normalization/rules.gwt --json-input examples/input_normalization/request.json --request "normalize contact profile" --json
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- validate examples/input_normalization/rules.gwt
cargo +1.96.0 run --locked -p gwt-core --bin gwt-native -- run examples/input_normalization/rules.gwt --request "normalize contact profile" --input examples/input_normalization/request.json
```

Both validation commands execute six scenarios. Native `error_count` serializes
as an exact decimal string because its declared type remains `number`.

The previous example used `any`. This adaptation deliberately rejects malformed
declared fields before normalization; native also rejects extra top-level host
bindings. The [boundary decision](../../docs/native-input-boundary-decisions.md)
records acceptance changes, the Python empty-object validation fix, captured
review cases, and remaining profile differences. This is a synthetic language
example, not a complete contact-data standard, email validator, or external pilot.
