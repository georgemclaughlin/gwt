# GWT v0.1 Grammar

This grammar describes the implemented v0.1 surface. The parser is currently
hand-written, but behavior bodies are parsed into structured statement nodes for
blocks such as `IF`, `FOR`, and `ELSE`.

```ebnf
program        = program_header?, use*, behavior*, background?, scenario* ;
program_header = "PROGRAM" text ;
use            = "USE" string ;

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

behavior       = "WHEN" signature, behavior_block ;
signature      = word+ ;
behavior_block = behavior_statement+ ;

behavior_statement
              = let
              | require
              | if_block
              | for_block
              | return
              | builtin
              | behavior_call
              | and ;

let            = "LET" name "be" expression_or_behavior_call ;
require        = "REQUIRE" condition ;
if_block       = "IF" condition, behavior_block, ("ELSE", behavior_block)? ;
for_block      = "FOR" name "in" expression, behavior_block ;
return         = "RETURN" expression_or_behavior_call ;

builtin        = set | add | subtract | print ;
set            = "set" path "to" expression ;
add            = "add" expression "to" path ;
subtract       = "subtract" expression "from" path ;
print          = "print" expression ;

assignment_or_record
              = path "is" expression
              | path "is", record_block ;

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
```

Indentation is significant:

- Top-level forms start at column 1.
- Behavior block statements are indented by two spaces.
- Nested `IF`, `ELSE`, and `FOR` bodies add two spaces per level.
- Record blocks also add two spaces per level.

CLI request mode runs two parsed programs together: the main program contributes
behavior definitions and optional background setup, while the request program
contributes the scenarios/request steps to execute.
