# Native language choices and migration boundaries

These are decisions for the current experimental native profile, not a new
language version or a promise of Python v0.2 compatibility. They complement the
[execution model](native-execution-model.md) and [grammar](native-grammar.md).
The [support and transition contract](native-language-transition.md) defines
current scope and migration responsibilities. A versioned native release and
actual evidence of human understanding remain outstanding. An unsupported form is not automatically a design mistake,
and an available rewrite is not automatically a safe migration.

The [thirty executable probes](../evaluations/native_language/2026-10-16/README.md)
separate source acceptance, runtime results, and Python observations. Their
[current-engine requalification](../evaluations/native_language/2026-10-16-transition/README.md)
retains the original sources and explicitly records the finite-contract changes. The decisions
below use existing substantial examples as well as those focused checks.

## Decisions for this profile

| Area | Decision | Reason and migration responsibility |
| --- | --- | --- |
| Calls producing values | Retain explicit returning behaviors and whole-call `LET`; do not add calls within expressions or directly after `RETURN` | Named intermediate results expose the domain calculation and its execution order. Keep the call in the same conditional scope; it may mutate state or fail. |
| Comparisons | Use symbolic comparisons, boolean operators, and explicit presence/kind predicates; omit parallel English comparison aliases | Keep one expression grammar and visible operator precedence. Domain behavior names and local predicate names carry the readable vocabulary. |
| Public request bindings | Retain root binding names with declared nested records; do not add dotted request input/output bindings | Make the host boundary a visible record contract. Expanding the enclosing contract can narrow accepted sibling fields and change returned shape. |
| Setup tables | Require a declared record type for record tables; omit untyped table inference | The header maps data into a reusable domain contract. Empty lists and later mutations retain a known item type. |
| Standalone existence | Use a named boolean-returning behavior around `FIND ... ELSE` | The found/missing decision is explicit; there is no second native `exists` step. The subscription workflow supplies independent adaptation evidence. |
| Required lookup | Use `FIND ... ELSE`, with an explicit failure exit where absence is an error | Failure and returned snapshot semantics are visible. This does not preserve a legacy mutable destination reference automatically. |
| Optional lookup | Deliberately omit lowercase `find optional`; use `FIND ... ELSE` with an explicit snapshot, retained-selection, or matched-item mutation contract | Absence handling and alias lifetime are separate choices. The stock lookup example qualifies all three contracts; it does not preserve arbitrary Python aliases automatically. |
| Raw host data | Keep closed, typed facts; do not add native `any` | Host representation and domain unknown/missing states are explicit. Dynamic data beyond the worked contact example still needs a concrete representation decision. |
| Broad numeric spelling | Retain `number` as an exact-decimal alias in this experimental profile; prefer `integer` or `decimal` in new contracts | Host floating-point defaults are not domain arithmetic. Fractional boundary values use exact strings; recurring quotients need explicit rounding or another domain representation. The public spelling remains a release-review question. |

These decisions constrain the experimental profile; they do not prohibit revising
it when a substantial workflow or comprehension study demonstrates a better form.

## Calls: preserve conditional execution and mutation

Python accepts a whole behavior invocation after `RETURN`:

```gwt
  RETURN calculate subtotal for order
```

The native form names the result first:

```gwt
  LET subtotal be calculate subtotal for order
  RETURN subtotal
```

The member-pricing example already uses
[named domain calculations](../examples/native_return_values/rules.gwt). The
focused relay probe verifies one call, its mutation, and its returned value.
Moving a call out of an `IF false` branch changes the call count even if the
eventual result assignment stays in that branch. A migration must preserve the
call's condition and relative order, not merely its apparent arithmetic result.
Additional `LET` steps can change evidence and resource use.

Calls nested inside arithmetic, such as `RETURN 1 + bump counter`, are rejected
by both current engines in the probe. They are a possible new feature, not a
Python capability waiting to be ported. The same distinction applies to the
tested `items[0]` expression: neither current engine accepts it.

## Comparisons: one grammar with domain names around it

Use `amount >= limit` for `amount is at least limit`. Use
`not (label contains "blocked")` for the tested negative-membership alias.
The probes cover below/equal/above comparison boundaries and negative membership.
They do not establish a general textual substitution inside strings, comments,
or arbitrary compound conditions. Parse the intended condition and preserve its
grouping. Native conditions must also be boolean; rewriting an alias does not
make Python truthiness a native rule.

The domain sentence should remain in a behavior such as
`eligible <application> for <policy>` or in a local predicate name. Omitting
synonymous operators is a grammar decision, not measured proof that symbols are
more comprehensible to every reviewer.

## Request roots: model the enclosing contract deliberately

A Python request can declare only `bundle.customer is Customer` and return that
nested path. The native alternative declares `bundle is Bundle`, where `Bundle`
contains a `customer: Customer` field. Both probes return the same nested result
for the minimal input. This compares the declared result, not print encoding or
execution evidence, which differ between engines. With an extra `bundle.note`, the original Python request
accepts the otherwise undeclared sibling, while the new closed record rejects it
before execution. Include a sibling in the contract only if it is an intended
fact; do not silently discard it to claim compatibility.

Returning the complete root can also expose more fields than returning one nested
path. Another option is separate root input/output names and an explicit host
adapter. That changes the public shape and must be reviewed. Use the native
[contract inspection](native-inspection.md) report to compare actual boundaries.

This audit found and corrected a Python bug: validation flattened nested objects
past declared record-valued fields and then reported the parent field missing.
Validation now preserves declared field boundaries and checks their nested types
recursively, including optional records, aliases, active variant payloads, and
list items. Legacy dotted field declarations still flatten their structural
prefixes; unknown fields and explicit empty objects remain visible. This repairs
the existing record model rather than introducing a new native compatibility rule.

## Tables: retain item contracts

Change an untyped table to a named `RECORD` and `GIVEN items are Item` with explicit
field types. The focused example preserves its rows and exact total. The existing
[receiving workflow](native-setup-tables.md) exercises empty lists, optional
columns, source-mapped cells, and typed field destinations more substantially.

This is not universally an inference-only edit: adding a contract can reject
heterogeneous rows, formerly accepted fields, or later assignments. Choose the
record from domain intent and include failing and empty cases. Native tables do
not create undeclared enclosing records merely because a destination is dotted.

## Collection and finite-domain choices

| Form | Current treatment | What remains unresolved |
| --- | --- | --- |
| Numeric literal unions | Supported as closed integer or exact-decimal domains | [Finite contracts](native-finite-literals.md) provide boundary validation, checked assignments, and exhaustive dispatch. Arithmetic widens to the numeric base; unrestricted values are not silently narrowed. |
| Boolean literal unions | Singleton contracts are supported; `true | false` resolves to `boolean` | Boolean values remain separate from numbers. A declared true input does not verify an external attestation. |
| Indexed source access | Unsupported in the tested expression form in both engines | Positional access, negative offsets, bounds failure, mutation, and ordering need a worked requirement. A business-key lookup is not a substitute when position is the domain fact. |

The optional-lookup probes expose a specific trap. With no match, both the old
step and `FIND ... ELSE PASS` retain the previous selection. With a match, Python
keeps a shared record reference; a later write through the selection mutates the
list item. Native `set selected to item` copies the record, so that later write
does not mutate the list. Even the rewritten block still shares in Python.
Changing the spelling therefore does not make the engines equivalent. Put an
intended item mutation inside the native `FIND` body; use a snapshot when that is
the intended contract. The [stock lookup example](../examples/native_lookup/README.md)
now supplies executable contracts for a preview with explicit absence, a retained
selection, and first-match inventory mutation. Its 150 independently expected
requests and nine-case fault review justify keeping these contracts explicit in
the current profile instead of introducing a parallel optional lookup statement.

The source inventory found no public example using lowercase `find optional`;
the retained runtime test and language-choice probes remain evidence of its Python
semantics. This does not prove that outside programs do not use it. There is no
general automatic migration: a destination used after lookup may refer to a list
item in Python, and a later missing lookup can retain that alias. Move an intended
mutation into the matching block, or model stable item identity explicitly when
the later action needs to locate it again. A repeated key lookup is equivalent
only if uniqueness, ordering, and intervening mutation justify that assumption.
Native snapshots must not be advertised as persistent mutable references.

The historical broad-integer rewrite probe passes static checking for `3`, then
fails its explicit assertion. A literal-union contract would have a different
checking/boundary promise. The audit keeps this distinction visible rather than
calling runtime validation a substitute for every finite type. The current native
profile now supplies actual finite contracts; its new qualification preserves
the original captures and records the changed acceptance separately.

## What this establishes

The probes and existing workflows justify specific current-profile choices and
identify migration hazards. They do not prove whole-language completeness,
arbitrary source equivalence, human preference, or production readiness. The
[feature matrix](native-conformance.md) and [goal ledger](project-goal-progress.md)
retain the remaining language, release, adoption, and comparative-evidence work.
