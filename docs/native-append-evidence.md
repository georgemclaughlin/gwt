# Append evidence without repeated list snapshots

The native `append` step now records an `append item` event. Its value contains
the resolved target path, the source spelling of that path, the inserted item's
zero-based index, and the normalized inserted value:

```json
{
  "path": "result.values",
  "sourcePath": "result.values",
  "index": 2,
  "item": "shipment-C"
}
```

The index equals the list's length before this append. Existing items remain
unchanged. The event retains its source span, sequence number, and operand event
reference. The item uses the destination contract: for example, appending integer
`1` to a decimal list records the inserted decimal as `"1"`. An absent optional
item is represented by an explicit `"item": null`.

The runtime verifies that the new list consists of the old prefix plus exactly
one item. All ordinary type, value-size, active-traversal, presence, and kind
mutation checks still apply. It records the event before installing the new
list. If that event exceeds the evidence budget, the append does not happen.
A later failure can retain already completed appends; this is not transaction
rollback.

## Why the representation changed

Previously, every append stored complete `before` and `after` lists. Repeatedly
building a list therefore duplicated growing prefixes. Recording the individual
insertions describes the same changes with evidence size proportional to the
number and size of inserted items, apart from index/sequence digit growth and
path/source metadata.

For the tested collector with 64 labels of 200 characters each, complete event
bytes fall from **930,561 to 112,182**, about **88%**, with the same 266 events,
state, and result. A 128-label input previously refused by the default evidence
limit now succeeds using **222,823 event bytes**. No limit was raised and no
evaluated step or inserted item was omitted. These measurements sum the compact
UTF-8 JSON bytes of individual events, matching the budget's accounting; they
exclude the surrounding run/case envelope and array separators.

These are evidence-size results, not a claim of linear runtime complexity.
Value copying and normalization remain, and other events can still snapshot
whole collections. The allocation workflow's repeated remainder scans still
exceed the default evidence budget on the tested 32/64-recipient cases.

## Reading and consuming the evidence

The explanation and offline review page describe the appended item and position,
and keep the event visible in the default decision trail. They do not claim
that this event contains a complete before/after snapshot. Given a known starting
list, append-only deltas reconstruct its final value in order. Mixed mutations
also require their own recorded changes; an isolated append event does not
reconstruct the previous list by itself.

Consumers should branch on `operation`. The older `append` operation has full
`before`/`after` values; `append item` has `path`, `sourcePath`, `index`, and
`item`. Other mutation operations retain their before/after representation.
The event envelope and case schema version are unchanged; the distinct operation
name identifies the new payload shape. The explanation API validates that shape.

The engine source identity changes, so historical cases require explicit engine
migration. Across 52 retained allocation cases, 36 migrations report changed
evidence and 16 preserve complete observations; all preserve public outcomes and
state. Original bytes remain unchanged and candidates replay. A run formerly
stopped by the evidence budget may now continue and produce a result, so migration
must also expose resource-related outcome changes. Proposals remain unapproved.

## Verification and scope

[The checkpoint](../evaluations/native_editor/2026-10-16-evidence-growth/README.md)
contains measurements, migrations, exact-boundary tests, alias and normalization
checks, replay, reconstruction, and HTML escaping/default-visibility checks.
Browser selection reported no available browser, so new visual or interactive
browser validation remains pending. This change does not establish human review
benefit or production capacity.

```sh
cargo test --locked --test append_evidence
python evaluations/native_editor/qualify_append_evidence.py --native /path/to/new/gwt-native --previous-engine /path/to/previous/gwt-native --output /tmp/gwt-append-evidence
```

The qualifier requires a new output directory and the previous engine that owns
the retained local-record allocation cases.
