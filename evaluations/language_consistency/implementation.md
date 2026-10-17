# Consistency fixes

Follow-up to the [review](../../docs/language-consistency-review.md).
The original `results.json` remains the pre-fix checkpoint.

Implemented:

- One native vocabulary inventory supplies reserved behavior heads, completion
  primitive types/context, formatter heads, diagnostic suggestions, and lexical
  tooling. Semantic parsing and independent acceptance tests remain separate.
- Website and VS Code use shared contextual lexical rules. All eight primitive
  actions are covered; retired forms are no longer advertised as native syntax.
  Field names and dotted paths take precedence over keyword coloring, lowercase
  type declarations are recognized, and the homepage uses the same highlighting
  path while preserving its selected-branch emphasis.
- Case-sensitive resolution is unchanged. Common unresolved casing mistakes get
  hints with their existing diagnostic codes. Custom `SET` still resolves to its
  own declared behavior, and its argument/type errors keep their own diagnostics.
- `DEPENDING` participates in leading-spacing normalization. Case and the
  accepted `WHERE`/`where` spellings remain unchanged.
- The [authoring convention](../../docs/language-style.md) explains binding,
  mutation, control, `AND`/`and`, naming style, and the limits of formatting/colors.

[Verification evidence](implementation.json) records the final engine identity,
checks, and before/after comparison. The nine saved delivery observations were
replayed with their original engine and compared with the new engine; all were
preserved. Migration approval remains false. The public download/demo were
regenerated as fresh illustrative captures for the current engine, not promoted
as human-approved migrations. Earlier evidence and reviewer decisions were not
rewritten.

Syntax coloring is lexical and does not resolve all names or validate a program.
Casing hints cover common failed resolutions, not every malformed phrase. New
language restrictions and human comprehension claims were not introduced; human
sessions remain pending and external pilots remain deferred.
