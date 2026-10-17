# Native GWT grammar

The [consolidated native draft](spec/native-draft.md) is the main language
reference. This document supplies its complete source productions and context
rules. It describes the **current experimental Rust profile**, alongside
its [execution model](native-execution-model.md) and
[semantic decisions](native-semantics.md). It does not declare a language release
or require eventual parity with Python. The published Python v0.2 surface has
its own [grammar](grammar.md).

The productions describe source forms; the accompanying context and type rules
are also required for a valid program. `block(X)` means a newline followed by
one or more `X` lines indented two additional spaces. `line(X)` ends at the
newline. `{ X }` means repetition, `[ X ]` means optional, and quoted strings
are source tokens. Spaces shown between words are significant separators;
these productions do not promise arbitrary whitespace between every token.

## Layout, names, and literals

Top-level forms begin at column one. Indentation uses two spaces per level,
without tabs or skipped levels. Blank lines and comments do not introduce
blocks. `#` begins a comment outside a double-quoted string. Expressions occupy
one line; parentheses do not provide multiline continuation. UTF-8 text and
LF/CRLF source are supported. Current per-file limits are one MiB, 16,384
nonempty source nodes, and 64 indentation levels.

```ebnf
identifier = (ascii_letter | "_"), { ascii_letter | digit | "_" } ;
path       = identifier, { ".", identifier } ;
number     = digit+, [ ".", digit+ ] ;
boolean    = "true" | "false" ;
string     = json_double_quoted_string ;
literal    = string | boolean | [ "-" ], number ;
label      = nonempty_remaining_line ;
```

Identifiers cannot be `true`, `false`, `not`, `and`, `or`, `is`, `contains`,
`present`, or `absent`. Program, scenario, and request labels may contain spaces;
they are not quoted string literals. Paths have record fields, without indexing.
Numbers have at most 512 decimal digits, with no exponent notation, leading
plus, or omitted digits on either side of the decimal point. Negative values
use unary minus. Strings use JSON escapes. There is no source `null` literal.

## Declarations and types

```ebnf
program     = (declaration | background | scenario | scenario_step)+ ;
declaration = line("PROGRAM", label)
            | line("USE", string)
            | line("TYPE", identifier, "is", type)
            | "RECORD", identifier, block(field)
            | "RECORD", identifier, "is one of", block(kind)
            | behavior | request ;
field       = line(identifier, ":", type)
            | identifier, ":", block(field) ;
kind        = identifier, ":", block(field) ;
type        = "boolean" | "integer" | "decimal" | "number" | "text"
            | identifier
            | "list<", type, ">"
            | "optional<", type, ">"
            | literal, { "|", literal }
            | identifier, "of kind", identifier ;
```

There is at most one entry `PROGRAM` header. Record and kind definitions must
have fields; inline nested records use `field:` with an indented definition.
One-of kinds receive an automatic `kind` field and cannot declare another one.
Types may refer forward to declarations, but recursive types fail. Type names
cannot replace built-in type names, including unsupported `any` and bare `list`.

`number` aliases exact `decimal`. [Literal contracts](native-finite-literals.md)
contain only text, only booleans, or only numbers; singletons are valid. A decimal
spelling selects the decimal base for the whole numeric union. Repeated equal
values fail, including `1 | 1.0`; `true | false` resolves to `boolean`. Union
alternatives may use literal grouping parentheses; singleton declarations use
the unparenthesized form. `Name of kind choice`
selects a declared kind of a named one-of record or alias. It can also appear
inside `optional<...>` or `list<...>`. No `any` or unparameterized list is supported.

Imports introduce no module namespace. Types, request names, and behavior
signatures have separate collision rules: duplicate type names, duplicate
request names, and overlapping behavior signatures fail across the loaded
declarations. A type, request, and zero-argument behavior can share a spelling.
`USE` is module-level and loads declarations, excluding imported scenarios from
execution and semantic checking. See [import rules](native-semantics.md#imports-and-exact-source-identity)
for path, layout, identity, and boundary checks.

## Behaviors and calls

```ebnf
behavior   = "WHEN", signature,
             block({ parameter_contract }, [ return_contract ], body) ;
signature  = signature_word, { signature_word | "<", identifier, ">" } ;
parameter_contract = line(("GIVEN" | "AND"), identifier, "is", type) ;
return_contract    = line("THEN returns", type) ;
call       = signature_with_each_parameter_replaced_by_one_argument ;
argument   = path | literal | list_expression | "(", expression, ")" ;
```

Every signature parameter needs exactly one leading contract. Parameter
contracts precede the optional return contract; executable steps follow them.
Behaviors must contain an executable step and may have no parameters.
Signature words are whitespace-separated, cannot contain `<>"()[]`, and match
call words exactly. The first word cannot be a parameter or any of:

```text
set add subtract append count sum divide find exists print
LET RETURN PASS REQUIRE IF ELSE FOR FIND DECIDE DEPENDING
```

Calls split at whitespace outside double quotes and balanced parentheses/list
brackets. A computed argument requires parentheses even without internal spaces.
Bare paths share mutable state; literals, lists, and grouped expressions copy
values. `(account)` explicitly copies that record. Calls occur as whole steps
or the whole right-hand side of `LET`, never inside expressions. `RETURN` takes
an expression; bind a returning call with `LET` before returning its result.
Returning behaviors must return a compatible value on every normal path.
An explicit literal `REQUIRE false` is a
[failure exit](native-failure-exits.md), not a normal path requiring a return.

At the start of a behavior, `AND` is parsed as a parameter contract. After
executable steps begin, `AND` prefixes a complete statement; it does not repeat
the preceding operation. Write `AND set total to 0`, not `AND total to 0`.
Structural branch markers (`ELSE` and dispatch `WHEN` arms) retain their exact
forms and do not accept this prefix.

## Behavior statements

```ebnf
body       = statement, { statement } ;
statement  = [ "AND" ], (simple | local_record | if | for | find
                         | decide | depending) ;
simple     = line("LET", identifier, "be", (expression | call))
           | line("RETURN", expression)
           | line("REQUIRE", expression)
           | line("PASS") | line(call) | builtin ;
local_record = "LET", identifier, "be", type, ":", [ block(value_field) ] ;
if         = "IF", expression, block(statement),
             [ "ELSE", block(statement) ] ;
for        = "FOR", identifier, "in", expression,
             [ where, expression ], block(statement) ;
find       = "FIND", identifier, "in", expression, where, expression,
             block(statement), "ELSE", block(statement) ;
where      = "WHERE" | "where" ;
decide     = "DECIDE", block(decision_arm+, fallback) ;
decision_arm = "WHEN", expression, block(statement) ;
fallback   = "ELSE", block(statement) ;
depending  = "DEPENDING ON", path, block(kind_arm+, [ fallback ])
           | "DEPENDING ON", expression, block(value_arm+, [ fallback ]) ;
kind_arm   = "WHEN the kind is", identifier, block(statement) ;
value_arm  = "WHEN the value is", literal, block(statement) ;
```

Conditions require booleans. `FIND` selects the first matching item and requires
an explicit missing branch. `DECIDE` selects its first true condition and
requires a final `ELSE`. Kind dispatch requires an explicit one-of state path;
scalar dispatch takes an expression. Kind and value arms cannot mix. Dispatch
must cover its domain, with a final `ELSE` when needed; duplicate cases and an
unreachable fallback fail. Finite boolean, text, and numeric domains can be covered
explicitly, while unrestricted scalar domains require `ELSE`.

Typed local construction requires the trailing colon and a record-compatible
type. An omitted body is valid only if all fields can be omitted. One-of
construction still requires an explicit quoted kind. Branch and collection
bodies are nonempty; use `PASS` for an intentional empty action. Local bindings,
flow proofs, returns, and alias guards also obey the
[execution-model rules](native-execution-model.md).

```ebnf
builtin    = line("set", path, "to", expression)
           | line("add", expression, "to", path)
           | line("subtract", expression, "from", path)
           | line("append", expression, "to", path)
           | line("count", expression, "into", path)
           | line("sum", expression, "into", path)
           | line("sum", projected_path, "in", expression, "into", path)
           | line("print", expression)
           | line("divide", expression, "by", expression, "rounded to",
                  scale, "places using", rounding_mode, "into", path) ;
projected_path = identifier, ".", identifier, { ".", identifier } ;
scale      = digit+ ;
rounding_mode = "half_even" | "half_away_from_zero" | "toward_zero"
              | "floor" | "ceiling" ;
```

Projected sum introduces its first path component as an item binding, such as
`sum item.price in items into total`; it does not take an arbitrary mapping
expression. Aggregate sources must be lists and their destination types must
fit the operation. Rounded division requires a literal scale from 0 through
512, a literal mode, numeric operands, and a decimal destination. Lowercase
`find` and `exists` are not built-ins in this profile; see the
[named existence adaptation](native-existence-decisions.md).

## Setup, requests, and scenarios

```ebnf
setup       = line(identifier, "is", expression)
            | identifier, "is", type, block(value_field)
            | path, "are", type, block(table_row) ;
value_field = line(identifier, ":", expression)
            | identifier, ":", [ block(value_field) ] ;
input       = line(identifier, "is", input_type) ;
request     = "REQUEST", label, block(request_step+) ;
request_step = "GIVEN", (input | setup)
             | "WHEN", action
             | line("OUTPUT", identifier, "is", type)
             | line("THEN", expression)
             | "AND", continued_request_step ;
action      = simple | local_record ;
scenario_step = "GIVEN", setup
              | "WHEN", action
              | line("REQUEST", label)
              | line("THEN", expression)
              | line("THEN prints", json_array)
              | line("THEN fails with", string)
              | "AND", continued_scenario_step ;
background  = line("BACKGROUND"), scenario_step+ ;
scenario    = line("SCENARIO", label), scenario_step*, [ examples ] ;
examples    = "EXAMPLES", block(table_row, table_row+) ;
table_row   = line("|", cell, { "|", cell }, "|") ;
```

`BACKGROUND`, `SCENARIO`, and their steps all start at column one. Their setup
initializers and tables have indented children. A request declaration instead
has an indented body. Top-level `WHEN` with a body declares a behavior, except
`WHEN LET ... be Type:`, which remains an action with a record initializer.
The remaining top-level steps form an implicit `Main` scenario;
implicit steps cannot mix with explicit scenarios. One nonempty background may
precede explicit scenarios; it requires at least one scenario. Scenario names
are unique. `EXAMPLES` follows all steps of its scenario and has at least one
data row. Cells substitute `<header>` placeholders; see
[scenario expansion](native-scenarios.md) for quotation and source mapping.

In a request, setup and input declarations precede execution. At least one
`WHEN` must precede the `OUTPUT`/`THEN` phase. Output declarations and assertions
may interleave in source, but all outputs validate before postconditions run.
Outputs name existing root bindings with exactly their declared types. Requests
do not contain request calls, print snapshots, or expected-failure assertions.
Their actions can be single-line statements or typed local construction, not
indented control-flow blocks. `RETURN` is only valid inside returning behaviors.

Input recognition is contextual: `input_type` is a named type, primitive,
`list<...>`, `optional<...>`, or a selected kind of a named type. With no body,
`GIVEN status is "ready"` creates a text value, not a singleton input contract.
Declare `TYPE Ready is "ready"` and use `GIVEN status is Ready` for that contract.
Scenarios require initialized values; they cannot declare host inputs.

Ordinary `GIVEN name is ...` introduces a root binding. It does not assign to an
existing dotted field. Typed tables can create a root list or replace an existing
list field. Their item type must resolve to an ordinary record, their header
names direct fields, and a header without data rows creates an empty list.
This differs from `EXAMPLES`, which needs data. Table cells are nonempty source
expressions; quote empty text. Pipes inside quoted strings remain within a cell.
See [typed setup tables](native-setup-tables.md) for shape and evaluation rules.

Record initializers supply declared fields using expressions or nested record
bodies. Required fields must be supplied; omitted optional fields become absent.
One-of initializers select their shape with `kind: "choice"`. There are no
anonymous record expressions or untyped record/table setup forms.

In scenarios and requests, `AND` repeats the preceding step category, including
`GIVEN`, `WHEN`, `THEN`, or request `OUTPUT`. It is invalid without a preceding
category. `THEN prints [...]` uses a JSON output snapshot, not a list expression;
decimal values are JSON strings and fractional/exponent JSON numbers fail.
`THEN fails with "code"` immediately follows one action and accepts only
`assertion_failed`, `division_by_zero`, or `nonterminating_decimal`. `AND` cannot
substitute for that immediate failure annotation. See
[failure expectations](native-semantics.md#expected-action-failures).

## Expressions and binding strength

```ebnf
primary    = number | string | boolean | path | list_expression
           | "(", expression, ")" ;
list_expression = "[", [ expression, { ",", expression }, [ "," ] ], "]" ;
expression = primary
           | "not", expression | "-", expression
           | expression, binary_operator, expression
           | expression, "is", ("present" | "absent") ;
binary_operator = "or" | "and" | "==" | "!=" | "<" | ">" | "<=" | ">="
                | "contains" | "+" | "-" | "*" | "/" ;
```

This expression production deliberately leaves grouping to the following
binding rules, matching the Pratt parser rather than implying that all
operators bind equally. Larger binding strength binds more tightly.

| Operator | Binding strength | Grouping |
| --- | --- | --- |
| `or` | 1 | Left associative |
| `and` | 3 | Left associative |
| `==`, `!=` | 5 | Left associative |
| `<`, `>`, `<=`, `>=`, `contains` | 7 | Left associative |
| `is present`, `is absent` | 7 | Postfix |
| `+`, `-` | 9 | Left associative |
| `*`, `/` | 11 | Left associative |
| Prefix `not` | Operand minimum 5 | Includes comparisons, excludes `and`/`or` |
| Prefix `-` | Operand minimum 13 | Binds before binary operators |

Parsing an expression at minimum strength `m` first consumes a primary or
prefix. It then consumes each postfix whose strength is at least `m`, or each
binary operator with strength `p >= m` and a right operand parsed at `p + 1`.
Grouped expressions and list items restart at minimum zero. Prefix operands use
the minima above. Type checking still applies: presence requires an optional
value, boolean operations require booleans, and comparison chains are ordinary
left-associated binary operations, not Python-style chained comparisons.

For example, `not 1 == 2 and true` groups as `(not (1 == 2)) and true`.
`10 - 3 - 2` yields `5`; `[1, 2,]` is an accepted list expression. Use symbolic
comparison operators; English aliases such as `is at least` are not supported.
For arithmetic, short-circuit proofs, and resource bounds, consult
[expression semantics](native-semantics.md#implemented-expression-rules).

## Validate source against this profile

From the repository root:

```sh
cargo +1.96.0 run --locked -p gwt-core --bin gwt -- validate examples/native_return_values/rules.gwt
cargo +1.96.0 run --locked -p gwt-core --bin gwt -- validate examples/native_setup_tables/rules.gwt
cargo +1.96.0 run --locked -p gwt-core --bin gwt -- validate examples/native_value_dispatch/rules.gwt
```

The implementation references for this audit are
[`program_source.rs`](../crates/gwt-core/src/program_source.rs) (layout and words),
[`program.rs`](../crates/gwt-core/src/program.rs) (declarations and statements),
[`scenario_source.rs`](../crates/gwt-core/src/scenario_source.rs) (sections/tables),
[`depending.rs`](../crates/gwt-core/src/depending.rs) (dispatch), and
[`expression.rs`](../crates/gwt-core/src/expression.rs) (expression parsing).
The [conformance matrix](native-conformance.md) tracks implementation evidence;
grammar documentation alone does not establish conformance or human readability.
