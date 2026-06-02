# Variant And Match Design Note

This is a design note, not implemented syntax.

MiniLang exposed a real modeling problem in GWT: variant-shaped data currently
has to be encoded as one wide record with a literal `kind` field and placeholder
fields for every possible case.

```gwt
RECORD MiniStatement
  kind: "let_number" | "fn_add" | "if_add_gt_print" | "let_number_list" | "print_map_double"
  name: text
  left_name: text
  right_name: text
  number_value: number
  threshold: number
  then_text: text
  else_text: text
  list_name: text
```

That works, but it makes executable specs carry irrelevant empty strings, zero
values, and manual dispatch:

```gwt
IF statement.kind == "let_number"
  store_number statement into runtime
IF statement.kind == "fn_add"
  set runtime.add_defined to true
```

The next substantial language feature to consider is a narrow, record-like
variant model plus behavior-body matching.

## Goals

- Make executable specs model tagged domain cases without placeholder fields.
- Keep the shape close to records, contracts, and behavior steps.
- Preserve explicit failure or missing-case handling.
- Improve MiniLang-style AST specs without turning GWT into a general-purpose
  implementation language.

## Sketch

```gwt
VARIANT MiniStatement
  let_number:
    name: text
    number_value: number
  fn_add:
    name: text
  if_add_gt_print:
    left_name: text
    right_name: text
    threshold: number
    then_text: text
    else_text: text
  let_number_list:
    name: text
  print_map_double:
    list_name: text
```

Behavior matching should be statement-oriented:

```gwt
MATCH statement
  WHEN let_number
    store_number statement into runtime
  WHEN fn_add
    set runtime.add_defined to true
  WHEN if_add_gt_print
    evaluate_add_threshold statement into runtime
  WHEN let_number_list
    store_number_list statement using front_end into runtime
  WHEN print_map_double
    evaluate_map_double statement into runtime
  ELSE
    append "unknown_statement" to runtime.errors
```

Inside a `WHEN let_number` branch, the checker should know that `statement`
has `let_number` fields. Variant fields should be read with ordinary dot paths,
such as `statement.name` and `statement.number_value`.

## Constraints

- `MATCH` is a behavior-body statement, not an expression.
- No destructuring in the first design.
- No nested patterns.
- No guards; use existing `IF` inside a branch.
- Require `ELSE` unless all known variants are covered.
- Unknown variant values should produce a clear runtime error or enter `ELSE`.
- Formatter, checker, docs, examples, and VS Code syntax must land with any
  implementation.

## Anti-Goals

Avoid importing a full ML/Rust-style pattern matching system:

- no constructor syntax beyond records/tables/JSON
- no expression-level `match`
- no exhaustiveness theorem as the primary user-facing feature
- no implicit field binding
- no broad algebraic data type terminology in beginner-facing docs

## Open Questions

- How should typed tables construct variant rows without placeholder fields?
- Should JSON represent variants as `{ "kind": "...", ... }` or with a nested
  tagged object shape?
- Should `OUTPUT` validation reject fields that do not belong to the active
  variant?
- Can `MATCH` reuse `WHEN` for branch labels without confusing behavior
  declarations?
- Is `VARIANT` the right keyword, or would `RECORD ... CASES` better fit GWT?
