# Kind proofs in ordinary conditions

Native rules can use a one-of record's payload after a condition proves its kind:

```gwt
IF contact.kind == "email"
  print contact.address
```

This uses ordinary checked equality and existing control flow. It complements
exhaustive `DEPENDING ON` when a policy combines a kind with another condition:

```gwt
IF facts.contact is present and facts.contact.kind == "sms" and facts.contact.opted_in
  set decision.destination to facts.contact.number
```

The expression checker proves each path safe before accepting it. Execution
short-circuits without reading absent records or another kind's fields.

## What a condition establishes

A direct comparison between `path.kind` and a literal text value restricts the
one-of record at `path`. Equality selects that kind; inequality excludes it.
The literal can appear on either side. Negation reverses the truth required by
the proof. A true conjunction retains facts from both sides; a false disjunction
does likewise. These are the same conservative boolean rules used for
[optional presence](native-presence.md).

The right side of `and` sees facts established by the left being true. The right
side of `or` sees facts established by the left being false. `IF` bodies use
true facts, and `ELSE` bodies use false facts. A later `DECIDE` condition and
body know that all earlier conditions were false. The final fallback can thus
use the fields of the remaining kind, or fields shared by all remaining kinds.
Conditions have no effects, so preceding conditions cannot mutate these facts.

Only the selected source path is narrowed. Other aliases retain their declared
contracts. A text variable compared with `path.kind` does not establish a kind,
even if that variable was initialized from a literal. An ordinary record field
named `kind` does not turn its record into a one-of record. No new closed-world
assumption is made about ordinary text fields.

Branch proofs remain local to the expression edge or selected body. Successful
[`REQUIRE` assertions](native-require.md) now retain supported true facts for the
remaining statements of their containing body. [FOR/FIND filters](native-filter-proofs.md)
now retain supported true facts for each selected body. [Early-return guards](native-early-returns.md)
retain common condition facts and the union of kinds on continuing paths.
Arbitrary boolean equivalence and common facts across alternative disjuncts
are not inferred. Impossible comparisons remain ordinary boolean expressions;
an empty possible-kind set does not create an unchecked unreachable body.
Such a body's field accesses still have to pass checking.

## Shared state must preserve the proven set

During a selected body, an alias or ancestor replacement cannot introduce a
kind outside the proven set. Rejection uses `kind_mutation`, before a successful
mutation event or state write. Replacements within that set are allowed. For
example, excluding email from an email/phone/pickup contract can permit a phone
to become a pickup if both kinds provide the field used by the body.

This differs deliberately from a `DEPENDING ON` kind dispatch, which protects
its selected runtime kind even in a fallback covering several kinds. A condition
proves a set; dispatch selects a particular kind. Nested guards enforce their
intersection. Presence and traversal guards also remain active. Returns,
ordinary exits, and failures release only guards introduced by the exited scope.
Returning from a helper does not release its caller's guard. Successful earlier
mutations remain committed after a later failure.

Bare-path shared arguments still require exact types. A proven email value can
call a helper requiring `Contact of kind email`. Passing it to a wider mutable
`Contact` parameter is rejected; a grouped `(contact)` supplies a copy instead.
Returning a refined value through its declared wider contract normalizes the
complete tagged record. The discriminator remains read-only.

## Scenario setup and evidence

An indented initializer for `optional<Record>` or `optional<OneOf>` explicitly
constructs a present value. It follows the same closed field rules and requires
the same literal discriminator as the inner record type. Omitting the optional
field still constructs absence. An indented body for an optional scalar remains
invalid. This makes nested optional input shapes expressible directly in
executable scenarios as well as host JSON.

The compiler retains proof locations in the checked statement representation.
Runtime evidence uses the actual equality, presence, short-circuit, branch,
call, and mutation events; no synthetic successful kind read is invented.
Capture, replay, revision comparison, generated scenarios, and original
Unicode/CRLF spans retain their existing formats.

Editor checking accepts these proofs in unsaved source/imports and diagnoses
invalid payload paths at their source spans. Hover reports the checked expression
type. When the checker proves one kind, definition lookup follows its payload
fields through the original declaration, including nested paths and copies.
If multiple kinds or mixed declaration origins leave the field ambiguous,
lookup returns the known binding instead of guessing. See
[editor navigation](native-editor.md) for source identity and per-example contexts.

## Worked policy and limits

The [contact review example](../examples/native_kind_conditions/README.md) has
seven scenarios and 21 top-level expectations. Independent expectations cover
22 input combinations. Reversing the SMS consent check changes exactly eight
outcomes. Tests also cover alias/ancestor replacement, multi-kind sets, helper
contracts and copies, return/failure cleanup, collection items, limits, source
evidence, replay, and generated scenarios.

Python formatting and checking accept the example, but its runtime rejects
the nested optional payload path. Native execution has independent expectations;
this is not a claim of reference-engine compatibility. The feature does not
establish measured human comprehension or complete native language support.
