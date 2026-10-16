# Make the lookup contract visible

This native example uses the stock-item vocabulary from
[reservation](../native_reservation/README.md) to distinguish three operations.
They share first-match lookup, but have different contracts for absence and
mutation. These are illustrative stock-count policies, not a change to the
existing reservation or inventory-allocation request.

| Request | Found | Missing | Inventory mutation |
| --- | --- | --- | --- |
| `preview stock count` | Return a snapshot with the proposed count | Return an absent selected item | None |
| `record stock count` | Set the first matching item's count and report `matched: true` | Report `matched: false` | First matched item only |
| `retain stock selection` | Replace the prior selection with a snapshot | Preserve the prior selection, including absence | None |

Both count requests reject a negative proposed count before changing inventory.
Duplicate SKUs are deliberately first-match operations; no uniqueness constraint
is invented. The later duplicate remains unchanged. Hosts own persistence and
decide when a preview becomes a recorded count.

The returning helper creates `Selection:` with its optional field omitted,
fills it when an item exists, and returns it. That is the current native way to
construct an absent optional field. Bare `null` is not a general native expression;
JSON null is accepted at optional host boundaries. The preview guards presence
before changing its copied selection. Assertions similarly guard optional field
access within the same boolean expression.

The record request performs its write inside `FIND`, where `item` refers to the
matched inventory element. Replacing that with `LET selected be item` followed
by a write to `selected` edits a copy and leaves inventory unchanged. The retained
selection request uses `ELSE PASS` intentionally: it does not clear stale state.

## Validate and inspect

```sh
gwt-native inspect examples/native_lookup/rules.gwt
gwt-native validate examples/native_lookup/rules.gwt
python -m gwtlang format examples/native_lookup/rules.gwt --check
```

The seven embedded scenarios assert snapshots, absence, retained state, missing
items, empty inventory, and duplicate first-match behavior. This is native source:
Python's formatter supports its syntax, but Python execution does not supply the
same local-constructor or record-copy semantics.

For host execution, `preview stock count` and `record stock count` accept:

```json
{"inventory":{"items":[{"sku":"widget","available":5},{"sku":"widget","available":9}]},"reading":{"sku":"widget","available":2}}
```

Save that JSON in `input.json`, then run:

```sh
gwt-native run examples/native_lookup/rules.gwt --request "preview stock count" --input input.json
gwt-native run examples/native_lookup/rules.gwt --request "record stock count" --input input.json
```

The preview leaves stock at `[5, 9]` and selects a proposed count of 2. Recording
changes stock to `[2, 9]`. `retain stock selection` instead accepts `inventory`,
`query: {"sku": "..."}`, and `selection: {"item": ...}`; omitted/null optional
items represent an absent previous selection.

## Migration evidence

[Qualification](../../evaluations/native_language/2026-10-16-lookup/README.md)
checks 150 independent request expectations and a nine-case review of the faulty
copied-record rewrite. The corrected write changes three captured outcomes;
missing/unaffected cases and the expected negative-count failure remain visible.
That baseline is a deliberate fault fixture, not a historical production program.

The native profile deliberately uses `FIND … ELSE` for these operations instead
of adding lowercase `find optional`. A Python lookup that leaves a shared record
in a destination is not equivalent to a native snapshot. Choose the intended
operation and review its consequences; do not apply a spelling-only migration.
See the [decision register](../../docs/native-language-decisions.md).
