# v0.4 Artifact Compatibility Fixtures

These files freeze representative Execution Case v1 and Comparison v1
payloads for reader and schema compatibility tests. They use fictional library
hold and shipping quote data only.

- `library-completed.execution-case.json`: full-value completed capture
- `library-available.execution-case.json`: second completed comparison case
- `library-omitted.execution-case.json`: completed omit-values capture
- `shipping-contract-failure.execution-case.json`: full-value recorded REQUEST
  contract failure
- `shipping-runtime-failure.execution-case.json`: full-value recorded runtime
  requirement failure
- `library-change.comparison.json`: deterministic old/new comparison with one
  output-changed and one unchanged case

The artifacts retain their original capture IDs and timestamps because those
fields are part of the canonical integrity digest. Tests verify integrity,
Python loading, published schemas, profile coverage, and reconciled comparison
totals. Regenerate deliberately when a versioned contract changes; do not
silently rewrite historical fixtures.
