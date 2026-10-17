# Independent regression fixtures

`underwriting.json` contains 1,072 distinct input/expectation pairs, including
exact rational thresholds and precedence cases. `rounded_division.json` contains
630 distinct cases from Python Decimal at precision 1600 across five rounding
policies, signs, midpoint boundaries, and recurring quotients.

Neither corpus contains duplicate cases after excluding case IDs. Keep all of
them: the Rust tests assert the case counts and independently check outcomes;
underwriting tests also require witnesses for deliberately incorrect policies.
Expected values must not be regenerated from the engine under test.

These two JSON files use one complete case per line, preserving their original
array/object schemas, order, numeric strings, and values. This makes case diffs
local without tens of thousands of brace-only lines. To inspect an individual
case with ordinary indentation:

```sh
python -c 'import json; print(json.dumps(json.load(open("crates/gwt-core/tests/fixtures/underwriting.json"))[0], indent=2))'
```

The cleanup changed whitespace only. The original bytes and independent-oracle
provenance remain available at commit
`52f56d34b117f2bccd8e3f70bde4381d3a3d2b8b` and in the dated underwriting and rounded
division evaluation summaries. These are live test fixtures, not archived runs.
