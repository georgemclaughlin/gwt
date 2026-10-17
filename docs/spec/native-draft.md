# GWT language — consolidated draft

Status: **experimental draft**, consolidated 2026-10-16. Profile:
`gwt-native-experimental`; language release version: **unassigned**.

This is the main language reference for the Rust implementation. It consolidates
the implemented choices into one contract for authors and reviewers. It does not
introduce syntax, change execution, or freeze compatibility. The Python
[v0.2 specification](v0.2.md) is retained as a historical contract for the retired
implementation. The crate version is not a language version.

Sections 1–10 describe the current language requirements. Section 11 identifies
implementation bounds; section 12 separates tooling evidence from language
meaning. The linked [grammar](../native-grammar.md) supplies the complete EBNF
and lexical/context details. Feature notes provide worked cases and design
history; the [conformance map](#13-conformance-and-open-decisions) connects this
draft to executable checks. A disagreement between this draft, the grammar, or
the implementation is a defect to resolve explicitly, not permission to silently
change the language. Release review and human-benefit evidence remain open.

For a first practical pass, follow the
[read, change, explain, review walkthrough](../native-review-walkthrough.md).

## 1. Program model

A GWT program describes behavior over typed domain state. It consists of type
and behavior declarations, named host requests, and executable scenarios.
The host supplies facts, selects a request, and performs any external effects.
GWT execution itself does not perform networking or persistence. `print` captures
a value in the execution observation.

The engine loads the source closure and checks all included declarations,
behavior bodies, initializers, entry scenarios, and branches before execution.
An invalid unselected branch still prevents execution. Imported examples are
excluded as specified in section 10. There is no dynamic name lookup or expression
reparsing at execution time.

Each direct host request and each scenario begins with fresh engine-owned state,
budgets, output, and evidence. A compiled program owns its source snapshot;
subsequent edits to files or a caller-supplied source bundle do not change it.
The library interprets checked GWT; this profile does not generate Rust programs.

## 2. Source and declarations

Source spellings and user-defined names match case-sensitively. Uppercase marks
structure, binding, assertions, and control; the primitive action verbs such as
`set` remain lowercase. Type-name capitalization is a style convention, not a
parser requirement. `WHERE` is the preferred collection-filter spelling; `where`
is also accepted. See [casing and naming](../language-style.md) for `LET` versus
`set`, `RETURN` versus `print`, and `AND` versus expression `and`.

Source is UTF-8, with LF or CRLF line endings. Top-level forms start at column
one. Blocks indent by two spaces; tabs and skipped indentation levels fail.
Blank lines and `#` comments outside double-quoted strings do not create blocks.
Expressions occupy one line. Strings use JSON double quoting and escapes.

Identifiers use ASCII letters or underscore followed by letters, digits, or
underscore. `true`, `false`, `not`, `and`, `or`, `is`, `contains`, `present`, and
`absent` cannot be identifiers. Paths use dot-separated fields, without indexes.
Program, request, and scenario labels can contain spaces and are not quoted.

| Declaration | Meaning |
| --- | --- |
| `PROGRAM delivery quote` | Optional entry name; at most one entry header |
| `USE "policy.gwt"` | Import declarations from a source module |
| `TYPE Status is "standard" \| "manual"` | Name a type or finite scalar domain |
| `RECORD Parcel` with field lines | Define a closed record shape |
| `RECORD Delivery is one of` with named kind blocks | Define a closed set of tagged record shapes |
| `WHEN quote <parcel> into <decision>` with contracts/body | Declare a behavior signature |
| `REQUEST quote delivery` with an indented body | Declare a host-callable entry |
| `SCENARIO ...` followed by unindented steps | Declare an executable example |

Ordinary records and each one-of kind have fields. `field:` with nested field
declarations defines an inline record. Forward type references are allowed;
recursive type definitions and duplicate type names fail. Built-in type names
cannot be redefined, including unsupported `any` and bare `list`.

Types, request names, and behavior signatures have separate collision checks.
Duplicate requests and overlapping behavior signatures fail across imports.
A type, request, and zero-argument behavior may share a spelling.

## 3. Values and contracts

| Type | Meaning and host JSON representation |
| --- | --- |
| `boolean` | `true` or `false`; distinct from numbers |
| `integer` | Exact whole number, encoded as a JSON integer token |
| `decimal` | Exact finite base-ten value; input uses decimal text or an integer JSON token; output uses canonical decimal text |
| `number` | Alias of native `decimal`, not an approximate or dynamically numeric type |
| `text` | Text encoded as a JSON string |
| `list<T>` | Ordered homogeneous list |
| Ordinary record | Closed object with its declared fields |
| One-of record | Closed object with `kind` plus that kind's payload |
| `Name of kind choice` | Selected kind of a named one-of type or alias |
| `optional<T>` | A present `T` or one absent value |
| Scalar literals separated by `\|` | Closed finite domain of one scalar category |

Contracts validate the entire host input object, including values an eventual
short circuit does not read. Extra fields, including nested ones, fail. Missing
required values fail. Omitted optional values and JSON null normalize to absence;
false, zero, and empty text are present. There is no ordinary source `null`
literal. Represent distinct meanings such as unknown and not applicable with
explicit domain alternatives.

One-of records receive an automatic `kind` field; authors cannot redeclare it.
An initializer selects a shape with `kind: "choice"` and supplies only that
shape's payload. Payload access must be valid for the statically known kind(s).

Finite domains contain only text, only numbers, or only booleans. Singletons
are valid. An all-integer domain has integer representation; any decimal spelling
selects decimal representation for the domain. Equal alternatives are duplicates:
`1 | 1.0` fails. `true | false` resolves to ordinary boolean. Parenthesized
alternatives are accepted within unions; singleton declarations use the plain
literal. Arithmetic expressions and type references are not union alternatives.

Allowed literals and compatible finite subsets can be assigned to finite
contracts. Integer values can widen to decimal at compatible value boundaries.
A broad integer does not become a finite-domain value merely because its current
value is a member; copying it does not prove membership. Arithmetic and boolean
operations produce their ordinary base types. Neither constant folding nor
equality guards infer a finite domain or numeric range.

Records and lists have structural types. Ordinary construction, assignment,
`LET`, and returned values copy values; they do not create aliases. Required
initializer fields must be supplied, optional ones may be omitted, and unknown
or duplicate fields fail. Initializer expressions run in supplied source order;
an incomplete constructor does not install a partial binding.

## 4. Expressions and exact arithmetic

Expressions contain literals, state paths, lists, grouping, and the operators
below. They cannot call behaviors or perform assignment. Number source literals
have digits on both sides of an optional decimal point, no exponent notation or
leading plus; negative numbers use unary minus. `[1, 2,]` is accepted.

| Binding, loose to tight | Operators |
| --- | --- |
| 1 | `or` |
| 3 | `and` |
| 5 | `==`, `!=` |
| 7 | `<`, `>`, `<=`, `>=`, `contains`, postfix `is present` / `is absent` |
| 9 | `+`, `-` |
| 11 | `*`, `/` |

Binary operators associate left. Prefix `not` takes comparisons but stops before
`and`/`or`; prefix minus binds before binary operators. Thus
`not 1 == 2 and true` means `(not (1 == 2)) and true`. Comparison chains are
ordinary binary operations, not Python-style chained comparisons.

Operands and list elements evaluate left to right. `and` and `or` require
booleans and short-circuit. Conditions never use truthiness. Skipped expressions
are checked statically but have no evaluated value.

Integer addition, subtraction, multiplication and negation produce integers.
Mixed integer/decimal arithmetic produces decimal. `/` produces an exact finite
decimal or fails: zero divisors give `division_by_zero`; a recurring result such
as `1 / 3` gives `nonterminating_decimal`. There is no implicit rounding.
Decimal output normalizes insignificant fractional zeros and signed zero;
display scale is separate from value.

Numeric equality compares exact integer/decimal values. Booleans never compare
as numbers. Text and boolean equality require compatible types. Lists compare
in order; records compare corresponding fields structurally, with exact numeric
comparison at leaves. Incompatible shapes/types fail checking. Comparison stops
at the first difference. Ordering operators require numbers. Text addition
concatenates text; `contains` supports text substrings and scalar membership in
typed lists, without key membership or implicit conversion.

List elements require a common checked type; integers may widen to decimals.
An empty list needs a known item type from context, such as a typed destination,
a nested list's other items, or the other comparison operand. `LET items be []`
without context fails; `[] == [1]` is a typed, false comparison.

## 5. Behaviors, bindings, and calls

Every `<parameter>` in a behavior signature has exactly one leading
`GIVEN parameter is Type` or `AND parameter is Type` contract. An optional
`THEN returns Type` follows parameter contracts and precedes executable steps.
A behavior has at least one executable step, possibly `PASS`, and may have no
parameters. Signatures match literal words exactly and cannot overlap.

The first signature word cannot be a parameter or a built-in/body keyword:
`set add subtract append count sum divide find exists print LET RETURN PASS
REQUIRE IF ELSE FOR FIND DECIDE DEPENDING`. Signature words cannot contain
argument delimiters `<>"()[]` except as complete parameter placeholders.

Calls replace signature parameters with arguments, separated at whitespace
outside strings and balanced grouping/list brackets. Computed arguments require
parentheses even without spaces. Quoted paths remain text, not state references.

| Argument/binding form | State relationship |
| --- | --- |
| Bare path argument, `adjust order.total` | Shared mutable location; exact structural parameter contract required |
| Parenthesized path, `adjust (order.total)` | Copied value, with compatible boundary normalization |
| Literal, list, or grouped calculation | Copied value, evaluated before callee entry |
| `LET`, assignment, constructed or returned record/list | Value snapshot |
| Traversal item from a state path | Alias to that actual item |
| Traversal item from a computed collection | Temporary value |

Passing one location twice creates aliases; writes are visible through both.
Copied arguments evaluate left to right before the callee body. An argument
failure prevents body entry but does not erase prior caller mutations/evidence.
Locals belong to their containing call or block; branch/item locals do not escape.

`LET name be expression` creates an inferred binding. A whole returning call
may be its right-hand side. Expression resolution has precedence when a name
could also match a zero-argument behavior. `LET name be RecordType:` constructs
a typed local record with fields below it; the colon is required. An omitted
constructor body is valid only when all fields can be omitted.

`RETURN expression` requires a return contract and exits the current behavior,
including enclosing branches/loops. Returned values normalize to that contract.
A statement call may discard a returned value; a `LET` call requires one.
Calls cannot be embedded in expressions or directly after `RETURN`; bind first.

Every syntactic path to normal completion must return. A literal `REQUIRE false`
is an explicit failure exit. Complete branch alternatives can establish an exit;
a possibly empty `FOR` cannot. This does not prove termination or infer arbitrary
constant/helper failures. All included return statements are checked, including
unreachable ones. A return contract does not imply purity or rollback.

Within a behavior, leading `AND` lines are parameter contracts. After executable
steps begin, `AND` prefixes a complete statement: `AND set total to 0`, not
`AND total to 0`. Structural `ELSE` and dispatch `WHEN` retain their exact forms.

## 6. Steps, decisions, and collection traversal

| Step | Requirement and effect |
| --- | --- |
| `set path to expression` | Replace an existing checked location with a compatible value |
| `add expression to path` / `subtract expression from path` | Update an unrestricted numeric destination |
| `append expression to path` | Append one compatible item to a typed list |
| `count expression into path` | Write list length to an unrestricted integer/decimal destination |
| `sum expression into path` | Sum a numeric list in order; empty sum is zero |
| `sum item.field in expression into path` | Sum a numeric field path over record items; no arbitrary mapping expression |
| `divide x by y rounded to 2 places using half_even into path` | Round an exact quotient with explicit literal scale/mode into an ordinary decimal destination |
| `print expression` | Append a serialized value to captured output |
| `REQUIRE expression` | Require true; otherwise fail with `assertion_failed` |
| `PASS` | Explicit no-op |

Rounded division supports `half_even`, `half_away_from_zero`, `toward_zero`,
`floor`, and `ceiling`; scale is a literal integer from 0 through 512. A zero
divisor still fails. `add`, `subtract`, `count`, `sum`, and `divide` cannot target
finite domains because they cannot guarantee membership. `set` and `append`
retain the destination's contract. A sum writes its destination only after all
contributions succeed; earlier statements remain committed if summing fails.

| Block | Selection and scope |
| --- | --- |
| `IF condition` / optional `ELSE` | Run the chosen nonempty body |
| `DECIDE` with `WHEN condition` arms and final `ELSE` | Test in order; execute the first true arm, otherwise fallback |
| `DEPENDING ON path`, `WHEN the kind is choice` | Select a kind of a one-of state path |
| `DEPENDING ON expression`, `WHEN the value is literal` | Evaluate once and select an exact scalar value |
| `FOR item in collection` with optional `WHERE predicate` | Visit in order and execute selected bodies |
| `FIND item in collection WHERE predicate` with required `ELSE` | Execute for the first match, otherwise the missing body |

Conditions and filters require booleans. `where` is also accepted in collection
headers. Dispatch kinds and values cannot mix. Duplicate cases and an unreachable
fallback fail. Finite domains can be covered explicitly; unrestricted numeric
and text domains require a fallback. Exact numeric equality makes `1` and `1.0`
duplicate dispatch labels. There is no fallthrough.

Traversal over a state path aliases actual items. Membership is fixed while the
traversal is active, but each visit reads current state: earlier bodies can update
later items' fields. Replacing/appending to the active collection or replacing an
ancestor fails with `collection_mutation` before the write. Guards follow aliases
through nested calls. Item writes remain allowed if they preserve contracts and
active proofs. Computed collections use copied items.

`FIND` does not evaluate later predicates after a match. Its item is unavailable
outside the selected body, including in `ELSE`. A missing `FIND` releases its own
traversal guard before its fallback; enclosing guards still apply. Returning or
copying a found record produces a snapshot, not a lasting selected-item alias.

## 7. Presence, kinds, and continuing paths

Optional operations require proof that the value is present; variant-specific
fields require a compatible known kind. Supported presence/kind facts propagate
through short-circuit expressions, selected `IF`/`DECIDE` branches, dispatch,
successful `REQUIRE` steps, and selected collection filters. Later `DECIDE`
conditions retain facts from earlier conditions being false.

Only facts common to every continuing branch survive after a branching statement.
Branches that structurally return or fail contribute no continuation. An `IF`
without `ELSE` has an empty false alternative. `FIND` joins its selected and
missing bodies; the missing body has no false-filter fact because the collection
may be empty. `FOR` establishes no new facts afterward. Local names and helper
assertions do not establish facts about an outer caller path. `THEN` adds no
proofs. There is no general theorem proving or inferred numeric range.

Presence joins require the same outer binding path. Within a branch, kind
restrictions intersect; continuing alternatives join by union. Fields invalid
under the joined parent type do not escape. When every alternative exits, later
source is still checked without inventing impossible-state facts.

Runtime guards protect relied-upon paths and ancestors against alias writes that
would clear presence or introduce an excluded kind. Such writes fail before
mutation. Branch guards end at their scope; joined proofs persist through the
containing body. Return/failure releases only exited scopes' guards. Declared
request outputs and return contracts do not change because of local refinement.

## 8. Requests and setup

A `REQUEST` has an indented body. Uninitialized typed `GIVEN` roots declare host
inputs. Initialized `GIVEN` roots are local setup, not extra host inputs. Input
and setup declarations precede actions. At least one `WHEN` precedes the
`OUTPUT`/`THEN` phase. Outputs and assertions may interleave in source, but runtime
output validation always precedes postconditions.

Direct host request execution proceeds as follows:

1. Validate and normalize the entire closed host-input record.
2. Execute request-local setup in source order.
3. Execute actions in source order, sharing state and budgets.
4. Validate all declared root outputs against their unchanged declared types.
5. Evaluate request `THEN` postconditions.
6. Publish a successful result containing only declared outputs.

This native input timing differs from Python v0.2's setup/contract ordering.
Successful native `state` also includes initialized inputs and request locals.
A failed request has no successful result. Request output declarations name
existing root bindings with exactly the declared type; dotted host contracts
are not supported.

Request actions are single statements or typed local construction, not block
control flow. Put decisions and traversal in named behaviors. Requests cannot
call other requests, expect failures, or assert print snapshots. `RETURN` belongs
only to returning behaviors. A scenario may invoke `REQUEST name`: it supplies
inputs from existing scenario state, shares those locations, and publishes new
output bindings only after success. Failed calls can still mutate shared inputs.

Setup supports `GIVEN name is expression`, typed record initializers, and typed
record tables (`GIVEN items are Item` with a table). Ordinary setup introduces a
root, not an assignment to a dotted field. A typed table can introduce a root
list or replace an existing list field. It requires an ordinary record item type
and direct-field headers; cells are nonempty expressions, with required fields
supplied. A header without data rows creates an empty list. There is no anonymous
record expression or untyped table form.

Table cells evaluate in row/header order using the surrounding scope; rows do
not introduce bindings for later cells. The target list is installed only after
all rows succeed. Replacing a field requires an existing ordinary-record path
with the same list item type; it neither creates missing parents nor appends.
Earlier row evidence may remain after a failure without a partial list assignment.

Input recognition is contextual. `GIVEN status is "ready"` initializes text;
it does not declare a singleton host input. Declare `TYPE Ready is "ready"`
and use `GIVEN status is Ready` for that contract.

## 9. Scenarios and expectations

`GIVEN`, `WHEN`, `REQUEST`, and `THEN` execute in scenario source order. `AND`
continues the preceding category; request bodies additionally support continuing
`OUTPUT`. Continuation is invalid without a preceding category. Top-level action
steps form an implicit `Main` scenario, which cannot mix with explicit scenarios.
Scenario names must be unique; each has at least one executable step.

One optional nonempty `BACKGROUND` precedes explicit scenarios and runs before
each with fresh state, sharing that scenario's budgets. Its assertions run at
their written position, not after the scenario. `AND` continuation resets at
scenario boundaries. Backgrounds are not host-request setup.

A scenario may end with one `EXAMPLES` table, with unique identifier headers and
at least one data row of matching-width nonempty cells. Cell text substitutes
once for `<header>` in that scenario, including inside quoted template text;
inserted text is not recursively substituted. Use complete quoted strings in
cells for text values. Backgrounds and declarations are not templates. Every row
is checked before execution, with names `scenario name example N` (one-based).
Each row gets fresh state/budgets; an execution failure does not suppress the
other rows. Source locations retain the original template/cell mapping.

`THEN expression` requires a true boolean at that point. Two additional forms
belong only to scenarios/backgrounds:

- `THEN prints [...]` compares the complete output so far with a JSON snapshot,
  not a GWT list expression. It neither consumes output nor constrains later
  prints. Types, order and exact values matter. Decimal outputs are JSON strings;
  fractional/exponent JSON number tokens fail. JSON null is allowed here.
- `THEN fails with "code"` annotates the immediately preceding action, including
  a scenario `REQUEST`. Allowed codes are `assertion_failed`, `division_by_zero`,
  and `nonterminating_decimal`. `AND` cannot replace this immediate annotation.
  Matching failure permits subsequent steps; unexpected success or a different
  supported code yields `failure_assertion_failed`. Unsupported errors propagate.

Failure expectations cannot catch setup, resource, safety-guard, or arbitrary
engine errors. Earlier mutations/output remain. A failed action introduces no
new usable binding. A passing rejection scenario does not mean the underlying
request succeeded; add state/output assertions for consequences that matter.

## 10. Modules, failures, and observations

`USE` imports declarations once per reachable module, without a namespace.
Dependencies are visited in source order; cycles fail. Imported program names do
not replace the entry name. Imported scenarios, implicit steps, and backgrounds
are excluded from entry execution and semantic checking. Their layout, import
placement, background placement, and table structure are still checked. Validate
their examples by running those modules separately.

Logical source paths are canonical, relative and slash-separated. Imports may
use `.`/`..` only within the selected root; absolute paths, escaping the root,
backslashes, colons, control characters, empty path components and symlinks below
the root are refused. The default root is the entry's parent; an explicit import
root supports sibling modules. In-memory bundles must contain exactly the
reachable closure. Filesystem loading is not an atomic snapshot against concurrent
edits; compile/freeze a reviewed closure before use.

Runtime failure stops the current execution unless a supported scenario failure
expectation handles that action. There is **no rollback**. A write validates its
replacement and reserves its mutation evidence before committing. Prior committed
state, captured output, and evidence remain visible after later failure. Hosts
must distinguish this partial observation from a successful domain result.

Observations retain actual operations and their source locations, operand links,
selected/skipped branches, calls, returns, assertions, and mutations. Skipped
source has no fabricated value. Most writes show before/after values; append
shows the inserted item and index. This explains execution, not policy intent
or counterfactual causation. Source spans use UTF-8 byte offsets and human line/
column locations; editor UTF-16 conversion is a tooling responsibility.

Exact source identity includes reachable file paths, bytes, comments and line
endings. It is not a signature. Native run/case/review envelopes have their own
schemas, separate from the retired Python payload contract. See
[case identity and replay](../native-cases.md) for the artifact encoding.

## 11. Current implementation bounds

These are explicit experimental operating/structural bounds, not business rules
or a promise of unlimited precision, memory safety against hostile hosts, or
wall-clock isolation. Resource refusals are not catchable domain rejections.
Relevant default bounds include:

| Resource | Current bound |
| --- | --- |
| Numeric literal/result | 512 base-ten digits |
| Source expression | 65,536 UTF-8 bytes; depth 64; 4,096 nodes |
| Type contract | Depth 64; 4,096 nodes |
| Normalized input or constructed value | Depth 64; 16,384 values; one MiB JSON |
| Source module / closure | One / four MiB; at most 256 modules; import depth 64 |
| Source nodes / indentation | 16,384 nodes; 64 indentation levels |
| Bindings per scope | 4,096 |
| Program execution | Default 100,000 shared statement/expression steps |
| Standalone expression execution | Default 4,096 steps |
| Evidence / concatenated text | Default one MiB each |
| Calls and nested bodies | Shared execution nesting ceiling 64 |
| Expanded scenarios | 1,024 scenarios; 65,536 nodes; four MiB expanded text/names/values |

Collection visits, sum contributions, membership scans, and visited structural
comparison elements consume steps. `count` uses the known length without a scan.
Normalization/allocation/serialization are structurally bounded but are not fully
charged as execution steps. Run, test, validate and profile may use budgets above
or below defaults, without raising hard structural/depth ceilings. Capture
accepts only budgets at or below defaults; replay and review retain those frozen
budgets and accept no override. See
[operating limits](../native-execution-limits.md) for configuration details.

## 12. Validation and review contract

`check` establishes static acceptance. `format --check` checks canonical layout.
`test` executes entry scenarios and fails if there are none. `validate` combines
checking, formatting and scenario gates; declaration-only modules require an
explicit no-scenarios allowance. A passing command does not establish adequate
coverage or correct policy intent.

Capture freezes source, target, inputs, limits, engine identity and observation.
Replay verifies that full observation. Request-case comparison holds host input
fixed; scenario-case comparison uses each revision's own setup and assertions.
A same-named reordered example row can therefore represent different data.

Review retains every case, including unavailable evidence and baseline mismatches.
`complete` means comparison coverage, not approval. Outcome, state, evidence and
source change flags describe different properties. An unchanged result can still
have changed execution evidence. A reproduced domain failure remains a failure.
Review decisions are explicit records bound to the exact report, separate from
execution. Pending records must not be reported as human approval.

The [walkthrough](../native-review-walkthrough.md) demonstrates this distinction.
Engine upgrades require the separate [migration workflow](../native-migration.md);
they cannot silently rewrite the identity of saved cases.

## 13. Conformance and open decisions

Test paths below are relative to [`crates/gwt-core/tests`](../../crates/gwt-core/tests).
They are executable evidence for the requirements, not claims of exhaustive proof.

| Draft requirements | Main conformance suites |
| --- | --- |
| 1–2: source, checking and declarations | `programs.rs`, `bundles.rs`, `language_choices.rs` |
| 3: contracts and closed inputs | `conformance.rs`, `one_of.rs`, `kind_contracts.rs`, `finite_literals.rs`, `input_diagnostics.rs` |
| 4: expressions and arithmetic | `conformance.rs`, `collections.rs`, `rounded_division.rs` |
| 5: calls, locals and returns | `arguments.rs`, `returns.rs`, `local_records.rs`, `failure_exits.rs` |
| 6: decisions and traversal | `depending.rs`, `value_dispatch.rs`, `collections.rs`, `lookup_contracts.rs` |
| 7: proof scope and mutation guards | `presence.rs`, `kind_conditions.rs`, `require_proofs.rs`, `filter_proofs.rs`, `branch_proofs.rs`, `early_returns.rs` |
| 8–9: requests and scenarios | `programs.rs`, `entry_files.rs`, `setup_tables.rs`, `scenarios.rs`, `failure_expectations.rs`, `print_expectations.rs` |
| 10–11: source, failure, evidence and limits | `bundles.rs`, `cases.rs`, `append_evidence.rs`, `cli_limits.rs`, `conformance.rs` |
| 12: validation and review | `validation.rs`, `validation_evidence.rs`, `review.rs`, `review_decisions.rs`, `corpus_regressions.rs`, `migration.rs` |

The [full matrix](../native-conformance.md) adds host/editor evidence and known
limitations. Deliberately absent forms include `any`, open record contracts,
untyped lists/tables, dotted host request contracts, indexing, calls within
expressions, English comparison aliases, and lowercase `find`/`exists` built-ins.
Use explicit `FIND ... ELSE`, typed facts, symbolic comparisons and named
behaviors where they express the domain; this is not an automatic migration
recipe for every Python program.

Before a versioned native release, review and freeze this scope, resolve any
contradictions, choose a language identifier independently of package/schema
versions, qualify compatibility fixtures and supported hosts, and publish the
intentional migration boundaries. The [transition contract](../native-language-transition.md)
and [release gates](../release-v0.4-checklist.md) still apply. Human understanding
and review benefit remain unproven; human sessions and external pilots are
pending by owner choice. Documentation consolidation does not close those gates.
