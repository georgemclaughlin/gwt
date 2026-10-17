# Language casing and presentation consistency review

Status: review and recommendations, not a grammar change. Reviewed revision:
`d81235e`, using the Rust engine identified in the accompanying evidence.

## Conclusion

Keep lowercase `set`. Keep the existing mixed-case language, but document its
roles and align the tooling with them. The language has a workable distinction;
our earlier explanation, “uppercase structure, lowercase actions,” was too broad.
Binding, assertion, and control statements also execute, and not every uppercase
statement opens a block.

The recommended distinction is:

- Uppercase introduces declarations, scenario steps, local bindings, assertions,
  control flow, and explicit control markers.
- Lowercase names the eight primitive action verbs, ordinary connecting words,
  expression operators, primitive types, and literal values.
- User-defined names keep their exact spelling. Their casing is an authoring
  convention, not a reliable substitute for parsing their role.

`LET` introduces a local binding; `set` updates an existing location. `RETURN`
ends a returning behavior; `print` records an output value. Keeping those roles
visually different is defensible. It has **not** been demonstrated to improve
human comprehension: human sessions remain pending and external pilots deferred.

Changes are needed, especially to highlighting and documentation. A broad
language rename or automatic case conversion is not justified by this review.

## Scope and evidence

Inspected the current native grammar and consolidated draft, Rust parsing and
name checks, formatter, declaration completion, VS Code TextMate grammar,
website highlighter, and the 28 entries in the active example catalog. The old
Python specification and uncatalogued historical examples are not the current
language contract.

The [reproducible probes](../evaluations/language_consistency/probe.py) and
[recorded results](../evaluations/language_consistency/results.json) contain
26 source programs, execution results, formatter observations, source hashes,
engine identity, example counts, and website token classifications. Thirteen
programs execute successfully and thirteen are rejected. All 26 pass the
source-only formatter unchanged. These are language/tooling observations, not
participant responses or a comprehensive parser conformance suite.

Static editor findings below come from its checked-in TextMate patterns. They
are not a claim that every VS Code theme or tokenizer state was exercised.

## 1. Current vocabulary and recommended convention

| Family | Current spellings | Recommendation |
| --- | --- | --- |
| Module and type declarations | `PROGRAM`, `USE`, `TYPE`, `RECORD` | Retain uppercase |
| Host and example boundaries | `REQUEST`, `OUTPUT`, `BACKGROUND`, `SCENARIO`, `EXAMPLES` | Retain uppercase |
| Behavior/scenario structure | `GIVEN`, `WHEN`, `THEN`, `AND` | Retain uppercase; explain context |
| Binding and return | `LET … be …`, `RETURN` | Retain uppercase; explain binding versus mutation |
| Assertions and intentional no-op | `REQUIRE`, `PASS` | Retain uppercase |
| Selection and iteration | `IF`, `ELSE`, `FOR`, `FIND`, `DECIDE`, `DEPENDING ON` | Retain uppercase, including the complete `DEPENDING ON` phrase |
| Collection filter | `WHERE` or `where` | Prefer `WHERE` in authored examples; retain and document the accepted alias |
| Primitive action verbs | `set`, `add`, `subtract`, `append`, `count`, `sum`, `divide`, `print` | Retain lowercase, highlight all eight consistently |
| Connectors and clause words | `is`, `be`, `to`, `from`, `into`, `in`, `by`, `rounded to`, `places using`, `returns`, `prints`, `fails with`, `the kind is`, `the value is` | Retain exact lowercase phrases in their grammar positions |
| Expression words | `not`, `and`, `or`, `contains`, `is present`, `is absent` | Retain lowercase; do not confuse `and` with step `AND` |
| Primitive/container types | `boolean`, `integer`, `decimal`, `number`, `text`, `list<T>`, `optional<T>` | Retain lowercase; `number` is an alias of decimal |
| Literal values and rounding modes | `true`, `false`; `half_even`, `half_away_from_zero`, `toward_zero`, `floor`, `ceiling` | Retain lowercase; no GWT `null` literal |
| Domain type names | Any permitted identifier, e.g. `Parcel` or `parcel` | Prefer PascalCase as a style convention, not a new parser restriction |
| Bindings, fields, parameters | Permitted identifiers, including some keyword spellings | Prefer snake_case; discourage confusing reserved-word lookalikes through guidance/lint |
| Behavior/request/scenario names | Exact user-defined words/labels | Prefer natural domain phrases; preserve exact spelling |

This model intentionally describes roles rather than “all keywords are uppercase.”
`set` is still reserved syntax even though it is lowercase. `WHERE` is a control
clause, and `ON` belongs to the fixed `DEPENDING ON` phrase; neither establishes
that arbitrary connecting words may be capitalized.

The catalog contains 116 lines headed by `set`, 25 by `LET`, 33 by `RETURN`,
10 by `DECIDE`, and eight uppercase `WHERE` filter clauses with no lowercase
`where` filter clauses. These counts cover catalog entry files only, not their
import closures, and do not count verbs nested after a leading `WHEN` or `AND`.
They show established usage, not evidence of readability.

## 2. Confirmed findings

### P1 — Website coloring covers the delivery example better than the language

The recently added [site highlighter](../tools/highlight_site.py) has an incomplete
vocabulary. This is a limitation introduced in the highlighting work, not a
language constraint.

- `USE`, `TYPE`, `FIND`, `DEPENDING`, `ON`, and `WHERE` currently fall through to
  the uppercase-word heuristic and are colored as types.
- `set` is colored as an action, but `add`, `subtract`, `append`, `count`, `sum`,
  `divide`, and `print` are not.
- `number` and `optional` are missing from the primitive/container type list;
  `string` and `table` are listed despite not being native built-in type forms.
- `null` receives literal coloring in GWT even though only JSON has that literal.
- `to`, `is`, `into`, and `for` receive the action class alongside `set`, obscuring
  the distinction between a verb and its connectors.
- The heuristic colors uppercase identifiers as types even when they are valid
  bindings or behavior names; lowercase user-defined types receive no such cue.
- The home-page hero has hand-authored spans while other examples use the helper.
  They are separate maintenance paths and can drift.

**Fix:** give GWT, shell, and JSON separate token categories; cover the native
vocabulary; distinguish structural words, action verbs, connectors/operators,
types, literals, names, and comments. Use contextual recognition where needed.
Do not suggest that lexical coloring proves validity. Preserve the hero's
selected-branch emphasis while using the same token classification.

### P1 — Editor coloring retains retired vocabulary and misses native vocabulary

The [TextMate grammar](../vscode-gwt/syntaxes/gwt.tmLanguage.json) still lists
lowercase `find` and `exists` as built-in functions, `any` as a type, and English
comparison phrases such as `greater than`, `less than`, `at least`, and `at most`.
Those are not supported native forms. In contrast, `optional` is absent from
its type pattern, and presence words are not explicitly classified.

The parser deliberately reserves lowercase `find`/`exists` as behavior heads
without implementing them as built-ins. “Reserved” must not be presented as
“callable.” `FIND … ELSE` is the supported control construct.

Type declaration patterns assume a capitalized name even though lowercase type
names are valid. Keyword and built-in patterns match words without their
syntactic context, so a valid field named `WHEN` or a domain phrase containing
an action word can receive misleading coloring. Keyword rules also precede
specialized type-declaration rules; actual TextMate tokenization should be
checked before relying on their capture behavior.

**Fix:** align the default editor grammar with the native profile, add missing
forms, and test real tokenization for declarations, fields, strings, comments,
placeholders, and domain phrases. If historical syntax is ever presented, give
it an explicit legacy mode rather than mixing it into the native surface.

### P1 — Case conversion can change the operation, not just its appearance

Casing is significant in parser dispatch, name resolution, and behavior
signature matching. The probes demonstrate:

| Source variation | Observed result |
| --- | --- |
| Built-in `set total to 2` | Runs and writes 2 |
| `SET total to 2` or `Set total to 2`, without declarations | `unknown_behavior` |
| A declared behavior `WHEN SET <target> to <value>` | Legal; the probe intentionally writes `value + 100` |
| Calling that declared `SET` with 2 | Writes 102, unlike built-in `set` |
| Declaring lowercase `set` as a behavior | `behavior_name` rejection |
| Declaring lowercase `find` as a behavior | `behavior_name` rejection |
| Declaring `Find value` as a behavior | Legal and callable |

**Fix:** preserve case sensitivity and user-defined names. Do not globally
uppercase/lowercase source. A future style lint may flag confusing case-only
names; a future hard reservation change would require an explicit compatibility
and migration decision.

### P2 — The specification gives exact spellings but lacks a concise casing policy

The [grammar](native-grammar.md) and [draft](spec/native-draft.md) agree on the
spellings examined. They do not explain the overall convention prominently.
Readers currently have to infer why `LET` and `set` differ.

**Fix:** add a short source/casing section to both references, linking to the
same authoring policy. Say explicitly that lowercase action verbs are reserved
syntax, type-name capitalization is a convention, and exact matching matters.
Include `LET` versus `set`, `RETURN` versus `print`, and `AND` versus `and` examples.
Do not claim a historical rationale that is not documented; this review proposes
a clearer rationale for the current design.

### P2 — `WHERE`/`where` is a real, narrowly scoped alias

Both spellings execute in collection headers. Mixed-case `Where` fails. The
parser and both references agree; this is not an implementation/spec mismatch.
The formatter leaves either accepted spelling alone. All eight catalog filter
clauses use `WHERE`.

**Fix:** designate `WHERE` as preferred authoring style while documenting `where`
as accepted. No immediate removal or automatic normalization is necessary.
If formatting later canonicalizes it, recognize the actual collection-header
clause; never replace words inside strings, names, comments, or arbitrary text.

### P2 — Casing mistakes produce valid but unhelpful generic diagnostics

`SET`, `let`, and `return` currently produce `unknown_behavior` in the tested
contexts; `TRUE` produces `unknown_name`; lowercase top-level `when` produces
`unsupported_statement`. Those results are consistent with exact matching, but
they do not guide a person toward the intended spelling.

**Fix:** after ordinary name/signature resolution fails, offer a context-specific
hint such as “The built-in action is spelled `set`.” Never reinterpret source or
warn that a successfully resolved custom `SET` must mean built-in `set`.
Suggestions should preserve existing diagnostic codes where appropriate and
avoid replacing more relevant type or argument errors.

### P2 — Formatting success does not establish language validity

All 26 probes format successfully without changes, including the thirteen that
fail execution checks. This is expected: the [formatter contract](native-formatting.md)
is source/layout-oriented, and its existing tests explicitly preserve unfinished
expressions. It is not a casing linter or semantic validator.

Its prefix normalization table includes `IF`, `FIND`, and `DECIDE` but omits
`DEPENDING`. This is a table-coverage inconsistency worth testing, not evidence
that valid dispatch programs are broken. Internal clause spacing and accepted
aliases are not comprehensively normalized either.

**Fix:** retain the format-then-validate authoring loop. Add representative
formatter coverage for every construct, including dispatch and `AND`-prefixed
steps. Document what normalization promises. Do not add case repair to the
formatter merely to make invalid examples look conventional.

### P2 — `AND` has several meanings that casing alone cannot explain

Inside expressions, lowercase `and` combines booleans. Uppercase `AND` can be a
parameter contract at the start of a behavior; after executable statements it
prefixes a complete statement. In scenarios/requests it repeats the previous
step category. The grammar and draft already document these differences.

**Fix:** teach the contexts together. Prefer plain action lines inside behavior
bodies rather than optional `AND` prefixes; retain `AND` for related contracts
and scenario steps where it makes the prose clearer. This is an authoring
recommendation, not removal of supported syntax.

### P2 — Name style and grammar legality must remain separate

The probes accept a lowercase record type `parcel`, uppercase binding `SET`,
uppercase binding `AND`, and a record field named `WHEN`. Lowercase `and` cannot
be an identifier. The actual namespace rules are more specific than a universal
“keywords cannot be names” statement.

**Fix:** document recommended PascalCase types and snake_case bindings/fields;
keep name resolution authoritative. A lint can discourage uppercase keyword-like
names without falsely claiming that the parser rejects them. Highlighters must
not classify names solely by first-letter case.

### P3 — Completion and vocabulary lists need a shared maintenance contract

Rust declaration completion preserves exact source spelling and uses
case-sensitive prefix matching. It provides declared behavior/request/type
names and primitive types; it is not a full keyword/action snippet provider.
The extension builds parameter placeholders from returned behavior signatures;
there is no separate checked-in snippet catalog in the extension.

Reserved behavior heads are listed separately in the parser and completion code.
Other vocabulary lists exist in the formatter, TextMate grammar, and site helper.
The drift above is a concrete consequence of maintaining related lists separately.

**Fix:** maintain a small machine-readable native vocabulary with token role,
context, accepted spelling, and preferred spelling. Generate presentation lists
or test them against it. Do not generate the semantic parser wholesale from a
coloring list. Keep independent conformance examples so a shared mistaken list
cannot make every test agree with itself. Consider contextual keyword snippets
only after the vocabulary is aligned; preserve exact matching for domain names.

## 3. Alternatives considered

| Direction | Benefit | Cost and risk | Recommendation |
| --- | --- | --- | --- |
| Existing mixed case with explicit role rules | Preserves readable action phrases and current programs; distinguishes binding/control from mutation | Requires a clear taxonomy and consistent tooling | Adopt as the documented convention |
| All language-reserved words uppercase, including `SET` | Easier to state a universal spelling rule | Changes familiar examples; conflicts with legal domain names; connector/operator boundary still needs a decision | Do not adopt without evidence of a comprehension benefit |
| Only outer GWT structure uppercase; all body syntax lowercase | Body could look more sentence-like | Renames `LET`, `RETURN`, `IF`, etc.; lower `find` already has legacy reservations; domain name collisions remain | Too much change for an unproven readability gain |
| Case-insensitive syntax with formatter normalization | More forgiving typing | Can reinterpret legal names and erase distinctions such as custom `SET`; requires a new namespace policy | Reject as an incidental cleanup |

There is no Python or Rust implementation requirement behind any of these
capitalization choices. The decision should serve GWT readers. A source spelling
change also changes source identities and evidence spans even where outcomes
stay equal; it is not free just because the project is experimental.

## 4. Recommended implementation order and acceptance checks

1. **Align presentation without changing syntax.** Correct the site and editor
   vocabulary, distinguish token roles, remove legacy false affordances, and
   unify hero coloring. Check every current construct plus JSON/shell examples,
   exact copied text, HTML escaping, selected-branch styling, mobile layout, and
   offline review case switching. Test actual editor tokenization as well as
   regex/vocabulary inventories.
2. **Publish the casing and naming convention.** Add it to the grammar, draft,
   authoring guide, and contributor guidance. Include the context-dependent
   meanings of `AND`, exact name matching, and the `WHERE` alias. Keep historical
   specs and dated evidence unchanged.
3. **Improve diagnostics and maintenance checks.** Add contextual suggestions
   only after failed resolution; retain legal custom `SET` behavior. Cover every
   statement family in formatter/editor checks. Establish the shared vocabulary
   contract with independent native acceptance/rejection fixtures.
4. **Evaluate any further style restriction separately.** If human review becomes
   available, compare comprehension of otherwise identical policies: explain a
   branch, predict an outcome, distinguish binding from mutation, and safely
   change a threshold. Do not substitute agent answers for participant evidence.

For implementation work, run the applicable repository checks. Engine changes
require Rust formatting, clippy, and tests, plus artifact regeneration and
identity-aware review where needed. Presentation-only fixes should not modify
captured outcomes, review decisions, or language semantics.

This review adds a report and reproducible observations only. None of these
recommended implementation changes has been silently applied.
