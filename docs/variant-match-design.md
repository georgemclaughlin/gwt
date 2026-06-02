# Records With Named Kinds

MiniLang exposed a real modeling problem in GWT: kind-shaped data previously
had to be encoded as one wide record with a literal `kind` field and
placeholder fields for every possible kind.

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

GWT now supports records with named kinds. The source should read like:

- a statement is one of these kinds
- the front end contains a statement of this kind
- depending on the statement, do the behavior for that kind

## Syntax

The declaration uses the existing `RECORD` idea and says that the record is one
of several named kinds:

```gwt
RECORD MiniStatement is one of
  let_number:
    index: number
    name: text
    number_value: number
  fn_add:
    index: number
    name: text
  if_add_gt_print:
    index: number
    left_name: text
    right_name: text
    threshold: number
    then_text: text
    else_text: text
  let_number_list:
    index: number
    name: text
  print_map_double:
    index: number
    list_name: text
```

Setup adds one concrete kind to a list:

```gwt
GIVEN front_end.statements is []

GIVEN front_end.statements contains a MiniStatement of kind let_number
  index: 1
  name: "x"
  number_value: 10

GIVEN front_end.statements contains a MiniStatement of kind print_map_double
  index: 6
  list_name: "nums"
```

The stored value is a record with an automatic `kind` field plus the active
kind's fields:

```json
{ "kind": "let_number", "index": 1, "name": "x", "number_value": 10 }
```

In GWT setup, `kind` is added automatically. In JSON input, include the same
`kind` field shown in the stored value.

Behavior branches read as a step over the current value:

```gwt
DEPENDING ON statement
  WHEN the kind is let_number
    store_number statement into runtime
  WHEN the kind is fn_add
    set runtime.add_defined to true
  WHEN the kind is if_add_gt_print
    evaluate_add_threshold statement into runtime
  WHEN the kind is let_number_list
    store_number_list statement using front_end into runtime
  WHEN the kind is print_map_double
    evaluate_map_double statement into runtime
  ELSE
    append "unknown_statement" to runtime.errors
```

Inside `DEPENDING ON statement`, `WHEN the kind is let_number` means
`statement.kind` is `let_number`. GWT then knows that `statement` has the
fields for `let_number`. Fields are read with ordinary dot paths, such as
`statement.name` and `statement.number_value`.

## Readability Bar

This feature should be understandable to someone reviewing the behavior, not
only to someone implementing the parser. A product manager should be able to
read the MiniLang example and understand that each statement has one active
kind. An engineer should be able to see which fields exist for each kind and
which behavior runs for that kind.

Prefer this:

```gwt
DEPENDING ON statement
  WHEN the kind is let_number
    store_number statement into runtime
```

over lower-level checks spread through the behavior:

```gwt
IF statement.kind == "let_number"
  store_number statement into runtime
```

## Guardrails

- These are records with named kinds; avoid beginner-facing
  algebraic-data-type terms.
- `DEPENDING ON` belongs inside behavior bodies.
- Branch labels are `WHEN the kind is ...`, which names the active kind of the
  `DEPENDING ON` value.
- No destructuring.
- No nested patterns.
- No guards; use existing `IF` inside a branch.
- Require `ELSE` unless all known kinds are covered.
- Unknown runtime kinds produce a clear runtime error or enter `ELSE`.
- A one-of value may only carry fields for its active kind.

## Anti-Goals

Avoid importing a full ML/Rust-style pattern matching system:

- no constructor syntax beyond records, setup blocks, tables, and JSON
- no branch form inside expressions
- no implicit field binding
- no general-purpose pattern language
- no broad algebraic data type terminology in beginner-facing docs

The design should continue to read as executable behavior over domain state,
not as a general programming-language feature.
