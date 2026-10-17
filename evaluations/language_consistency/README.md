# Casing consistency review evidence

See [the detailed review](../../docs/language-consistency-review.md).
`results.json` records observations at the source revision and engine identity
inside that file. These are synthetic language probes, not human review results.

Reproduce with the engine used for the reviewed checkout:

```sh
python evaluations/language_consistency/probe.py --gwt target/debug/gwt --output /tmp/gwt-language-consistency.json
```

The script runs temporary programs and source-only formatting without modifying
examples or captured cases. It also inventories the 28 catalog entry files and
samples the website highlighter. Results are observational: future intentional
language/tooling changes may differ. Preserve this checkpoint and write a new
output when comparing an implementation change.

The subsequent [implementation record](implementation.md) and
[verification summary](implementation.json) describe the fixes without replacing
this original checkpoint.
