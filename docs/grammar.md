# GWT v0.1 Grammar

This grammar describes the implemented v0.1 surface. The normative v0.1
language notes live in [spec/v0.1.md](spec/v0.1.md). The parser is currently
hand-written, but behavior bodies are parsed into structured statement nodes for
blocks such as `IF`, `FOR`, `FIND`, and `ELSE`.

```ebnf
program        = top_level* ;
top_level      = program_header
               | use
               | record
               | program_contract
               | behavior
               | background
               | scenario
               | step
               | examples ;
program_header = "PROGRAM" text ;
use            = "USE" string ;
record         = ("RECORD" | "DTO") name, record_block ;
record_block   = record_field+ ;
record_field   = name ":" type | name ":", record_block ;
type           = primitive_type | name | "list<", type_name, ">" | literal_union ;
primitive_type = "number" | "text" | "boolean" | "list" | "any" ;
type_name      = primitive_type | name ;
literal_union  = literal, "|", literal, ("|", literal)* ;
program_contract
               = request_contract
               | output_contract ;
request_contract
               = "REQUEST" path "is" type ;
output_contract
               = "OUTPUT" path "is" type ;

background     = "BACKGROUND", step* ;
scenario       = "SCENARIO" text, step*, examples? ;
examples       = "EXAMPLES", table ;
table          = table_row, table_row+ ;
table_row      = "|", cell, ("|", cell)*, "|" ;

step           = given | when_call | then | and ;
given          = "GIVEN" assignment_or_record ;
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
              | path "is", record_block
              | path "is" name, record_block
              | path "are", table
              | path "are" name, table ;

condition_or_record
              = condition
              | path "is", record_block ;

condition      = expression
              | expression "is" expression
              | expression "is not" expression
              | expression "is greater than" expression
              | expression "is less than" expression
              | expression "is at least" expression
              | expression "is at most" expression ;

expression     = logical_or ;
logical_or     = logical_and, ("or", logical_and)* ;
logical_and    = equality, ("and", equality)* ;
equality       = comparison, (("==" | "!="), comparison)* ;
comparison     = term, ((">" | "<" | ">=" | "<="), term)* ;
term           = factor, (("+" | "-"), factor)* ;
factor         = unary, (("*" | "/"), unary)* ;
unary          = ("-" | "not"), unary | primary ;
primary        = number | string | boolean | path | list | "(", expression, ")" ;
list           = "[", (expression, (",", expression)*)?, "]" ;
literal        = number | string | boolean ;
```

Indentation is significant:

- Top-level forms start at column 1.
- Behavior block statements are indented by two spaces.
- Nested `IF`, `ELSE`, `FOR`, and `FIND` bodies add two spaces per level.
- Record blocks also add two spaces per level.

CLI request mode runs two parsed programs together: the main program contributes
behavior definitions and optional background setup, while the request program
contributes the scenarios/request steps to execute.

`BACKGROUND` must appear before explicit `SCENARIO` blocks. `EXAMPLES` attaches
to the current scenario. Behavior names cannot use reserved built-in or
behavior-body keywords.
