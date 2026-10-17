# Native typed setup tables

The Rust engine supports `GIVEN items are RecordType` in scenarios, backgrounds,
and request-local setup. The record name may be an alias. Table cells use ordinary
checked GWT expressions, and rows create an ordered `list<RecordType>`.

```gwt
RECORD Item
  sku: text
  quantity: integer

GIVEN received is 2
GIVEN items are Item
  | sku      | quantity     |
  | "widget" | received + 1 |
  | "gadget" | 4            |
```

Headers name fields of the resolved record type. Required fields must have
columns; optional columns may be omitted and produce absent values. Unknown or
duplicate headers, unequal row widths, empty cells, and incompatible expressions
are rejected before execution. Quote text, including empty text. Quoted pipes
and hashes stay inside a cell. Nested record/list fields can use previously
bound values or compatible list expressions. Table headers name direct fields,
not dotted paths into a row. Untyped tables and scalar-item tables are not part
of this native feature.

A header with no data rows creates a typed empty list. The complete header
contract is still checked. A new root binding must have a unique name, as with
other native `GIVEN` declarations. To initialize an existing collection field,
name its explicit record path:

```gwt
RECORD Receipt
  lines: list<Item>

GIVEN receipt is Receipt
  lines: []

GIVEN receipt.lines are Item
  | sku      | quantity |
  | "widget" | 3        |
```

The path must already exist, traverse ordinary record fields, and have the same
list item type. Setup replaces that field; it does not append to it or implicitly
create missing parents. Optional-parent narrowing and indexed paths remain
separate language gaps.

## Evaluation and evidence

Cells evaluate in row order and header order using the surrounding setup scope.
Rows do not introduce bindings for later cells or rows. Values are copied into
their records; referencing an existing record does not turn table cells into
mutable aliases of it. Each completed row is normalized against its record
contract and recorded as a `table row` event with its cell-expression dependencies
and original row span. `EXAMPLES` expansion retains the table template and example
cell locations, including UTF-8 and CRLF source.

The collection is assigned only after all rows finish. A bad cell, execution
limit, or evidence limit cannot publish a partially built list. An existing
collection field stays unchanged until its `initialize field` event is recorded
and the replacement is applied. Completed row events can remain as evidence of
work before a later failure; they do not imply that the collection was assigned.
Other earlier state changes are not rolled back.

The compiler permits at most 1024 data rows, 256 columns, and 16384 data cells per
table, within the existing source limits. Runtime value, nesting, step, and
evidence limits also apply; meeting table shape limits alone does not guarantee
execution fits those budgets. Each row consumes a step in addition to its cell
expression work. Both root and field assignments retain the ordinary contract
and mutation guards.

## Example and checks

[The receiving example](../examples/native_setup_tables/rules.gwt) uses a nested
table and a root table through the same public request. Its independent expected
totals are six, four, and zero. The shared example also passes Python v0.2
format/validate; native cell-expression, quote-aware parsing, empty-table,
optional-field, and resource rules are tested against explicit expectations.
Python behavior is not the oracle for these native choices.

```sh
cargo +1.96.0 run --locked -p gwt-core --bin gwt -- validate examples/native_setup_tables/rules.gwt
gwt validate examples/native_setup_tables/rules.gwt
```

`tests/setup_tables.rs` covers values, headers, failures, atomic field replacement,
resource boundaries, source mapping, formatter preservation, capture/replay,
revision comparison, and independent example outcomes. Editor tests cover type
references, cell bindings, field destinations, and collection-item provenance.
Header names themselves are not additional go-to-definition targets.

This adds the collection setup form used by readable request files. Native
[request entries](native-request-entries.md) explicitly import their rules and
run as ordinary GWT source; Python's externally paired request-file form is a
separate invocation convention.
