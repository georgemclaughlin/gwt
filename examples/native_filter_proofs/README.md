# Prepare counter pickups from a mixed queue

The rule marks a parcel prepared when its route is present, its kind is counter,
it is ready, and it has a nonempty code. It collects eligible codes in queue order
and records the first eligible code. Missing routes, courier routes, unready
pickups, and empty codes are skipped. Existing prepared flags on skipped parcels
remain unchanged. The host handles actual dispatch and persistence.

Both FOR and FIND use their WHERE facts to read counter-specific payload fields
directly. FIND has an explicit empty result in ELSE. The rule does not sort or
deduplicate codes; repeated eligible codes retain their positions.

```sh
cargo run -p gwt-core --bin gwt -- validate examples/native_filter_proofs/rules.gwt
cargo run -p gwt-core --bin gwt -- run examples/native_filter_proofs/rules.gwt --request "prepare pickups" --input examples/native_filter_proofs/request.json
```

The sample returns codes `["B", "A"]`, first code `"B"`, and both parcels marked
prepared. Five embedded scenarios contain 15 top-level expectations. Independent
native tests cover 57 queue combinations and detect 14 changed outcomes when
readiness is removed. Captured requests replay, compare, and generate executable
scenarios.

Python formatting/checking accepts this source, but Python validation fails on
the nested optional route initializer. The example is explicitly assigned to the
native suite. See [filter proofs](../../docs/native-filter-proofs.md) for scope,
live-state selection, mutation protection, and compatibility changes.
