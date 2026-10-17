# GWT casing and naming

GWT source is case-sensitive. Use the exact spellings in the
[native grammar](native-grammar.md); capitalization is meaningful, not a choice
that the formatter silently repairs. This convention describes the existing
language, not a syntax migration.

## Read the roles

| Role | Convention and examples |
| --- | --- |
| Declarations and scenario steps | Uppercase: `RECORD`, `REQUEST`, `GIVEN`, `WHEN`, `THEN` |
| Local binding, assertions and control | Uppercase: `LET`, `REQUIRE`, `RETURN`, `IF`, `DECIDE`, `FIND`, `PASS` |
| Primitive actions | Lowercase: `set`, `add`, `subtract`, `append`, `count`, `sum`, `divide`, `print` |
| Ordinary connectors and expression words | Lowercase: `is`, `be`, `to`, `into`, `returns`, `and`, `not`, `is present` |
| Primitive/container types and literals | Lowercase: `integer`, `decimal`, `number`, `text`, `boolean`, `list<T>`, `optional<T>`, `true`, `false` |
| Fixed control phrases | `DEPENDING ON`; prefer `WHERE` in `FOR`/`FIND` headers |

Lowercase action verbs are still reserved syntax. “All keywords are uppercase”
is not the rule. `WHERE` and `where` are both accepted in collection headers;
prefer `WHERE` in new examples. `Where` is not an alias. Do not generalize that
exception to other words.

`LET` introduces a local binding; `set` changes an existing checked location:

```gwt
LET fee be 5
set quote.fee to fee
```

`RETURN` exits a returning behavior with a value. `print` records a value in the
execution output and continues. `PASS` marks an intentional no-op. Uppercase
therefore does not mean “opens an indented block.” These are body excerpts; their
bindings, contracts, and enclosing behavior must be supplied by a complete program.

## Names are domain vocabulary

Prefer PascalCase for named domain types (`DeliveryQuote`) and snake_case for
bindings, fields and parameters (`weight_grams`). Use ordinary domain phrases
for behaviors and requests (`quote delivery for <parcel> into <quote>`).
Preserve meaningful domain capitalization in labels where it helps readers.

These are style recommendations, not extra parser restrictions. Lowercase type
names are legal. Some keyword spellings are legal field or binding names, but
names such as `WHEN` or `AND` make source harder to distinguish from syntax and
should usually be avoided.

Behavior signatures match exactly. A user-defined `SET` can be a different
operation from built-in `set`. Never case-fold source or rename domain phrases
as a formatting fix. Lowercase `find` and `exists` remain reserved behavior
heads, but are not callable native built-ins. Use `FIND … ELSE` or a named domain
behavior for lookup/existence logic.

## Keep the two forms of “and” distinct

- Lowercase `and` joins boolean expressions: `ready and funded`.
- Leading behavior contracts can use `AND`: `AND quote is Quote`.
- In scenarios and requests, `AND` continues the preceding step category.
- After executable behavior steps begin, `AND` prefixes a complete statement,
  such as `AND set quote.fee to 5`; it does not repeat an omitted action verb.

Prefer plain action lines inside behavior bodies. Use `AND` for related
contracts and scenario steps when it improves the reading. Structural `ELSE`
and dispatch `WHEN` arms retain their exact forms.

## Formatting, diagnostics and highlighting

Formatting normalizes layout, not case. It preserves the accepted `where` alias,
user names, strings, comments, and source meaning. A successful format operation
can still leave an unresolved or invalid program. Follow it with validation:

```sh
gwt format examples/native_delivery/rules.gwt --check
gwt validate examples/native_delivery/rules.gwt
```

After ordinary resolution fails, common casing mistakes can receive suggestions:
`SET` → `set`, `let` → `LET`, `return` → `RETURN`, `when` → `WHEN`, `TRUE` → `true`,
and infix `AND` → `and`. These are hints, never reinterpretations. A resolved
custom name takes precedence; argument/type errors are not replaced with casing
suggestions. Not every malformed phrase has a casing hint.

Site and editor colors use a shared lexical vocabulary. Colors distinguish
structural words, actions, connectors/operators, declarations, literals, and
comments. They do not prove that a name resolves, an expression type-checks, or
a phrase is valid. Neither colors nor successful formatting replace validation.

## Maintaining this convention

The [spelling inventory](../crates/gwt-core/src/vocabulary.json) records the
native roles, reserved behavior heads, and accepted/preferred filter spellings.
It is shared by reserved-name checks, declaration completion, formatting,
diagnostic suggestions, and presentation tooling. The semantic parser remains
independently implemented and tested.

The [shared lexical rules](../tools/gwt_syntax.py) generate the editor grammar and
color website examples. After changing them, run:

```sh
python tools/gwt_syntax.py
python tools/highlight_site.py docs/index.html docs/getting-started.html docs/installation.html
python tools/build_site.py --gwt target/debug/gwt
```

Run the repository verification commands too. Native vocabulary changes affect
engine source identity; regenerate fresh illustrative site cases with the new
engine and preserve historical captures and decisions. The
[consistency review](language-consistency-review.md) records the original findings;
human comprehension sessions remain pending.
