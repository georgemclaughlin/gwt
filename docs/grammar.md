# GWT v0.2 Grammar

> Historical Python-era document. Reproduce its commands from [the pre-retirement tree](https://github.com/georgemclaughlin/gwt/tree/4f403dc51eda5382c6a12c0757cb26deac34012a). Current product guidance is in the [language reference](spec/native-draft.md), [upgrade guide](python-retirement.md), and [release checklist](release-checklist.md).

This grammar describes the implemented v0.2 surface. The normative v0.2
language notes live in [spec/v0.2.md](spec/v0.2.md). The parser is currently
hand-written, but behavior bodies are parsed into structured statement nodes for
blocks such as `IF`, `FOR`, `FIND`, and `ELSE`.

The experimental Rust engine has a separate [native grammar](native-grammar.md)
with deliberate semantic differences; see [native semantics](native-semantics.md) and
[native conformance](native-conformance.md). This grammar remains the complete
v0.2 surface, not a claim of native coverage.

```ebnf
program        = top_level* ;
top_level      = program_header
               | use
               | type_alias
               | record
               | one_of_record
               | named_request
               | behavior
               | background
               | scenario
               | step
               | examples ;
program_header = "PROGRAM" text ;
use            = "USE" string ;
type_alias     = "TYPE" name "is" type ;
record         = "RECORD" name, record_definition_block ;
record_definition_block
               = record_field+ ;
record_field   = name ":" type | name ":", record_definition_block ;
one_of_record  = "RECORD" name "is one of", one_of_kind+ ;
one_of_kind    = name ":", one_of_field+ ;
one_of_field   = name ":" type ;
type           = primitive_type
               | name
               | "list<", type, ">"
               | "optional<", type, ">"
               | literal_union ;
primitive_type = "number" | "integer" | "decimal" | "text" | "boolean" | "list" | "any" ;
literal_union  = literal, "|", literal, ("|", literal)* ;

named_request  = "REQUEST" text, request_body ;
request_body   = request_statement+ ;
request_statement
               = request_given
               | request_when
               | request_output
               | request_then
               | and ;
request_given  = "GIVEN" path "is" type
               | "GIVEN" assignment_or_record ;
request_when   = "WHEN" command ;
request_output = "OUTPUT" path "is" type ;
request_then   = "THEN" condition_or_record ;

background     = "BACKGROUND", step* ;
scenario       = "SCENARIO" text, step*, examples? ;
examples       = "EXAMPLES", table ;
table          = table_row, table_row+ ;
table_row      = "|", cell, ("|", cell)*, "|" ;

step           = given | request_call | when_call | then | and ;
given          = "GIVEN" assignment_or_record ;
request_call   = "REQUEST" text ;
when_call      = "WHEN" command ;
then           = "THEN" condition_or_record ;
and            = "AND" text ;

behavior       = "WHEN" signature, behavior_contract*, behavior_block ;
signature      = signature_part+ ;
signature_part = word | parameter ;
parameter      = "<", name, ">" ;
behavior_contract
               = contract_input
               | contract_return ;
contract_input = "GIVEN" name "is" type ;
contract_return
               = "THEN returns" type ;
behavior_block = behavior_statement+ ;

behavior_statement
              = let
              | require
              | if_block
              | for_block
              | find_block
              | decide_block
              | depending_block
              | return
              | pass
              | builtin
              | behavior_call
              | and ;

let            = "LET" name "be" expression_or_behavior_call ;
require        = "REQUIRE" condition ;
if_block       = "IF" condition, behavior_block, ("ELSE", behavior_block)? ;
for_block      = "FOR" name "in" expression, ("WHERE" condition)?, behavior_block ;
find_block     = "FIND" name "in" expression "WHERE" condition,
                 behavior_block, "ELSE", behavior_block ;
decide_block   = "DECIDE", decide_branch+, "ELSE", behavior_block ;
decide_branch  = "WHEN" condition, behavior_block ;
depending_block
              = "DEPENDING ON" expression, depending_branch+, ("ELSE", behavior_block)? ;
depending_branch
              = kind_branch | value_branch ;
kind_branch    = "WHEN the kind is" name, behavior_block ;
value_branch   = "WHEN the value is" literal, behavior_block ;
return         = "RETURN" expression_or_behavior_call ;
pass           = "PASS" ;

builtin        = set | add | subtract | append | count | sum | find | exists | print ;
set            = "set" path "to" expression ;
add            = "add" expression "to" path ;
subtract       = "subtract" expression "from" path ;
append         = "append" expression "to" path ;
count          = "count" expression "into" path ;
sum            = "sum" expression "into" path
               | "sum" path "in" expression "into" path ;
find           = "find", ["optional"], name, "in", expression, "where", condition, "into", path ;
exists         = "exists" name "in" expression "where" condition "into" path ;
print          = "print" expression ;

assignment_or_record
              = path "is" expression
              | path "is", record_value_block
              | path "is" name, record_value_block
              | path "contains" ("a" | "an") name "of kind" name, record_value_block
              | path "are", table
              | path "are" name, table ;
record_value_block
              = record_value_field+ ;
record_value_field
              = name ":" expression | name ":", record_value_block ;

condition_or_record
              = condition
              | path "is", record_value_block ;

condition      = expression
              | expression "does not contain" expression
              | expression "is" expression
              | expression "is not" expression
              | expression "is greater than" expression
              | expression "is less than" expression
              | expression "is at least" expression
              | expression "is at most" expression ;

expression     = logical_or ;
logical_or     = logical_and, ("or", logical_and)* ;
logical_and    = negation, ("and", negation)* ;
negation       = "not", negation | equality ;
equality       = comparison, (("==" | "!="), comparison)* ;
comparison     = term, ["is", ("present" | "absent")],
                 ((">" | "<" | ">=" | "<=" | "contains"), term)* ;
term           = factor, (("+" | "-"), factor)* ;
factor         = unary, (("*" | "/"), unary)* ;
unary          = "-", unary | primary ;
primary        = number | string | boolean | path | list | "(", expression, ")" ;
list           = "[", (expression, (",", expression)*)?, "]" ;
literal        = number | string | boolean ;
```

Indentation is significant:

- Top-level forms start at column 1.
- Behavior block statements are indented by two spaces.
- Nested `IF`, `ELSE`, `FOR`, `FIND`, and `DECIDE` bodies add two spaces per
  level.
- Record definition blocks contain `name: type` fields. Record value blocks in
  `GIVEN` and `THEN` setup/assertion forms contain `name: expression` fields.
  Both add two spaces per nested level.
- `DECIDE` branches use `WHEN condition` at the branch indent and require an
  `ELSE` block.
- `DEPENDING ON` branches use `WHEN the kind is name` or
  `WHEN the value is literal` at the branch indent. A block cannot mix kind and
  value branches.

`TYPE Name is Type` declares a named alias for an existing type expression, such
as a literal union or typed list. Type aliases are contracts only; they do not
create runtime values.

`optional<Type>` is a boundary contract for a value that may be omitted or
JSON `null`. Both cases become one absent value at runtime. GWT has no
source-level `null` literal; conditions inspect optional values with
`path is present` and `path is absent`.

`REQUEST path is Type` is no longer a top-level program contract. At the top
level, `REQUEST name` with an indented body declares a public callable request.
Inside a scenario or request file, single-line `REQUEST name` invokes that named
request using the current scenario state.

Inside a named request, `GIVEN path is Type` without an indented body declares
caller-provided input. `GIVEN path is Type` with an indented body creates
request-local setup state and validates it against `Type`. Each named request
must contain at least one `WHEN` call.

CLI `.gwt` request-file mode runs two parsed programs together: the main program
contributes named requests, behavior definitions, and optional background setup,
while the request program contributes scenario setup and `REQUEST` calls to
execute.

`BACKGROUND` must appear before explicit `SCENARIO` blocks. `EXAMPLES` attaches
to the current scenario. Behavior names cannot use reserved built-in or
behavior-body keywords.

The experimental native profile also supports [sequential REQUIRE proofs](native-require.md).
This is a checker/runtime semantic extension over existing statement syntax;
it does not change the Python v0.2 contract. The native profile also carries
supported facts from [FOR/FIND filters](native-filter-proofs.md) into selected bodies.
[Early-return analysis](native-early-returns.md) also retains supported facts on
paths that continue, without adding syntax.
Native [branch-exit joins](native-branch-proofs.md) additionally retain
supported REQUIRE and nested-continuation proofs common to all continuing branches.
Native [explicit failure exits](native-failure-exits.md) recognize literal
`REQUIRE false` in structural return/continuation analysis without adding syntax.

## Experimental native call arguments

This extension describes the Rust engine only; it does not change the Python
v0.2 grammar above. Native signatures determine argument positions, with one
argument token per parameter:

```ebnf
native_argument = path | literal | "-" number | list | "(" expression ")" ;
```

Whitespace splits call tokens only outside double-quoted strings and balanced
parentheses/brackets. A bare path shares state. Literals, list expressions, and
parenthesized expressions copy values; `(state)` explicitly copies a path.
Computed arguments need parentheses even without spaces. Signature literal words
cannot contain `"()[]<>`; complete `<parameter>` placeholders are allowed.
Behavior calls remain statements or whole `LET` right-hand sides, and cannot
appear inside argument expressions. See [native call arguments](native-semantics.md#call-arguments)
for typing, evaluation order, and evidence rules.

## Experimental native printed-output assertions

In scenarios and backgrounds, the Rust engine additionally accepts:

```ebnf
native_print_assertion = ("THEN" | "AND"), "prints", json_array ;
```

`json_array` is a literal serialized output sequence, with exact integer numbers
and JSON strings for decimals. It is not a GWT list expression. Duplicate object
keys and fractional/exponent JSON numbers are rejected. `AND` must continue a
`THEN` step. A binding named `prints` still works in ordinary expressions such as
`THEN prints == true`; the extension requires the array form. See
[native printed-output expectations](native-semantics.md#printed-output-expectations)
for order, scope, limits, and evidence semantics. Python v0.2 does not implement
this assertion.

## Experimental native expected failures

```ebnf
native_failure_assertion = "THEN", "fails with", string ;
```

This scenario/background annotation immediately follows one `WHEN` or `REQUEST`
action and asserts its failure code. The permitted strings are `"assertion_failed"`,
`"division_by_zero"`, and `"nonterminating_decimal"`. Other errors cannot satisfy
it. It cannot introduce new caller bindings or wrap another assertion. The
scenario can continue after a match, preserving earlier state and output. See
[expected action failures](native-semantics.md#expected-action-failures) for scope,
budget behavior, and evidence. Python v0.2 does not implement this form.

## Experimental native typed setup tables

The Rust engine implements the typed `GIVEN path are name` setup form. Its table
production permits a header without data rows:

```ebnf
native_typed_setup = ("GIVEN" | "AND"), path, "are", name, native_setup_table ;
native_setup_table = table_row, { table_row } ;
```

`AND` must continue `GIVEN`. The item name resolves to a record or record alias;
columns are direct field names and cells are ordinary checked expressions.
Unquoted empty cells are invalid. Untyped and scalar-item tables remain outside
the native subset. See [typed setup semantics](native-setup-tables.md) for header
validation, atomic field replacement, bounds, and source evidence.

## Native presence proofs

Native `IF` and `DECIDE` use the existing productions and presence expressions;
no new token is required for [branch-local optional proofs](native-presence.md).
Their checker and runtime carry supported presence facts into selected bodies
and protect those facts against invalidating alias writes.
[Literal kind comparisons](native-kind-conditions.md) use the existing equality
and boolean productions to refine one-of paths in expressions and these bodies.
An indented optional record initializer uses the ordinary record-body production
and explicitly constructs a present value; optional scalars cannot have a body.

## Native one-of contracts

The native engine also recognizes `RECORD Name is one of` declarations. Native
record setup selects a kind with an explicit `kind: "name"` field inside the
ordinary record initializer; the kind must be a literal. This differs from the
Python `contains a ... of kind ...` form. See [native one-of contracts](native-one-of.md)
for field access and alias-safe branch semantics. Native kind dispatch uses
`DEPENDING ON path` with indented `WHEN the kind is name` bodies and an optional
final `ELSE`. All declared kinds must be covered; an unreachable `ELSE` is an
error. Scalar subjects use the same `DEPENDING ON expression` production with
`WHEN the value is literal` branches. Native scalar coverage includes boolean
and text-union values; broader scalar types require a final `ELSE`. Native
numeric labels compare by exact value across integers and decimals, so equal
representations cannot appear as separate cases. See
[native value dispatch](native-value-dispatch.md).

Native type expressions also permit `name "of kind" name`, where the first name
resolves to a one-of record or alias and the second selects one declared kind.
This form can appear as a `TYPE` target or contract annotation, and can be nested
inside `list<...>` or `optional<...>`. It retains the tagged record shape. For
example, `TYPE Email is Contact of kind email` makes payload requirements explicit
in a helper contract. Python formatting preserves this source form; Python
execution does not implement it.

## Native request entries

A native request entry uses the existing `USE`, setup, request-call, and scenario
productions; it introduces no additional grammar. Single-entry CLI selection and
its difference from Python's externally paired input files are documented in
[native request entries](native-request-entries.md).

## Experimental native rounded division

The Rust profile adds this explicit step; it is not part of the Python v0.2
surface:

```ebnf
rounded_division = "divide" expression "by" expression "rounded to"
                   scale "places using" rounding_mode "into" path ;
scale            = digit+ ; (* integer literal 0..512 *)
rounding_mode    = "half_even" | "half_away_from_zero" | "toward_zero"
                 | "floor" | "ceiling" ;
```

It is a behavior-body statement and can follow top-level/request `WHEN`.
Operands must be numeric; the destination must be decimal. The word `divide`
is reserved for this built-in in native behavior definitions. See
[native rounded division](native-rounded-division.md) for arithmetic, evidence,
limits, and migration semantics. Ordinary `/` retains exact-only semantics.

## Experimental native local record construction

```ebnf
local_record = "LET" name "be" type ":", record_value_block? ;
```

This extends native behavior-body statements and request/scenario `WHEN` actions.
The type must resolve to a record, one-of record, or optional record, including
aliases and selected-kind contracts. Fields use the existing record initializer
syntax and checks. An empty body is valid only when no required fields remain.
The trailing colon distinguishes construction from expression/call bindings.
See [typed local records](native-local-records.md), including the migration for
old returning behavior calls whose last token ends with a colon.
