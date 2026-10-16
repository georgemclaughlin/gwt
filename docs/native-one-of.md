# Native one-of record contracts

The Rust engine supports closed records with named kinds at input/output
boundaries, in source setup, and inside records, lists, and optional values.
`DEPENDING ON` selects a kind branch and makes its payload fields available
within that branch. The checker requires complete kind coverage or a final
`ELSE`.

```gwt
RECORD Contact is one of
  email:
    label: text
    address: text
    note: optional<text>
  phone:
    label: text
    number: text

TYPE Recipient is Contact
```

Each kind must have at least one typed field. Names must be distinct valid GWT
names. `kind` is reserved as the discriminator and cannot be redeclared in a
kind's fields. Recursive contracts remain unsupported, as with ordinary native
records. Ordinary aliases retain the complete one-of contract; an explicit
`of kind` selector restricts an alias to one declared kind.

## Kind-specific contracts

```gwt
TYPE EmailContact is Contact of kind email

WHEN label <contact> as <label>
  GIVEN contact is EmailContact
  AND label is text
  set contact.label to label
  print contact.address
```

`Contact of kind email` is a type expression. Its base must be a named one-of
record or alias and its kind must exist. The result retains the discriminator
and exactly that kind's declared fields; it does not copy a second schema into
the source or erase the tag. Unknown kinds, non-one-of bases, and recursive
aliases are rejected. Selecting the same kind through another alias is allowed.
Selectors may appear directly in contracts or inside containers such as
`list<Contact of kind email>` and `optional<Contact of kind phone>`.

A kind-specific helper can access its fields without another dispatch block.
A `DEPENDING ON` branch or [kind condition](native-kind-conditions.md) proves the
type for callers. A value known only as the
full `Contact` type cannot be passed to an email-only helper, even if its runtime
kind happens to be email. Shared state requires exact structural type equality;
the selected branch type and `EmailContact` agree. Passing a selected value to
a wider mutable parameter remains rejected; `(contact)` passes an independent
copy when the wider contract accepts it. Native source request calls also keep
their exact input/output binding requirements.

JSON requests with selected-kind contracts reject other kinds before executing.
Setup still supplies a literal `kind:` field, even when the type names one kind.
`kind` stays read-only and whole-value assignments must preserve the selected
contract. Active dispatch guards continue to protect against kind changes through
other aliases. Cases, generated scenarios, and host type serialization use the
existing single-kind `OneOf` representation; no case schema changes are needed.

Editor navigation resolves the type's base, selected kind tag, and payload fields
to their declarations, including through aliases and imports. A checked branch
or short-circuit proof selecting one kind also resolves its payload declarations;
several remaining kinds retain an ambiguous binding fallback.
Both formatters preserve selectors. Python's formatter projects these annotations
only during its layout validation, including imported source; it neither rewrites
the formatted annotation nor enables Python execution of this native type form.

The [expression example](../examples/native_kind_contracts/README.md) demonstrates
short helper calls with complete payload contracts and boundary scenarios.

## Closed values

An input selects its shape with a required text `kind`:

```json
{"kind":"email","label":"Accounts","address":"a@example.test"}
```

Only that kind's fields are accepted. Unknown kinds, missing required fields,
wrong field types, and fields belonging to another kind fail validation before
request behavior runs. For example, a phone value cannot carry `address` or
`note`, even if they are null. An omitted email `note` normalizes to absence;
normalization does not add fields from unselected kinds. Unknown kinds cannot
enter the engine as a fallback state.

Nested one-of values share the ordinary input/value depth, node, and byte limits.
Contract validation counts the kinds and their fields against the type budget.
The Rust `Type::OneOf` API uses a map from kind names to their field contracts;
host-built contracts undergo validation too. Exact integer/decimal and strict
boolean rules are unchanged.

## Explicit setup

Native setup uses an ordinary typed record initializer with a quoted kind:

```gwt
GIVEN contact is Recipient
  kind: "email"
  label: "Accounts"
  address: "a@example.test"
```

The literal selects the fields to check before execution. A computed kind is
rejected in an initializer; supplying an entire existing one-of value is allowed.
Nested initializers use the same form. Lists can contain previously initialized
one-of values. Optional fields of the selected kind may be omitted. An indented
initializer for an optional record constructs a present value using these same
closed field and literal-kind rules.

This explicit initializer is a native design choice. Python's existing
`contains a Record of kind name` setup is a different form and is not implemented
by this native checkpoint. Native typed setup tables still require ordinary
record items, not mixed one-of items.

## Field access and replacement

Without narrowing, code may read `contact.kind` and fields with exactly the same
type in every kind, such as `contact.label`. Those common fields may be updated.
A field like `contact.address` is unavailable on the full contract, including
inside `IF contact.kind == "email"`. Use `DEPENDING ON` for explicit kind
narrowing. The checker reports `one_of_field` for unproven payload access.

`kind` cannot be assigned independently or passed as a shared mutable argument.
Pass `(contact.kind)` to copy its value into a behavior. To change a kind, replace
the complete one-of value with another value of the same contract. Validation
and evidence recording precede publication of the replacement. The new value
contains only its active payload; prior-kind fields do not survive the write.

The contact-routing example selects a channel and copies a common label. It
retains the kind-specific address/number in the output for the host. It does not
claim to demonstrate access to kind-specific payloads in behavior:

```sh
target/debug/gwt-native validate examples/native_one_of/rules.gwt
target/debug/gwt-native test examples/native_one_of/rules.gwt
```

## Evidence and tooling

Cases capture and replay exact tagged inputs and normalized outputs. Generated
scenarios emit the complete one-of declaration and explicit active-kind setup,
including nested/list/optional values. Formatting preserves the declaration and
initialization forms. Source spans use the existing module/UTF-8 rules.

Editor type references follow aliases, and payload field declarations have their
own source locations. A common field can have several declarations; navigation
currently falls back to the root binding instead of arbitrarily choosing one
kind's field. Explicit selected-kind annotations and checked proofs selecting
one kind resolve its unique payload declarations. Nested paths, copied payloads,
and collection items preserve their original declaration identities; equal
structural types do not merge them. See [editor navigation](native-editor.md).

`tests/one_of.rs` covers valid/invalid boundaries, explicit and nested setup,
common fields, discriminator protection, complete replacement under step limits,
generated scenarios, replay, and host type/value budgets. `tests/editor_types.rs`
covers declaration provenance. The three public routing scenarios contain eight
expectations. `tests/depending.rs` adds exhaustive branches, alias guards, nested subjects,
returns, failure cleanup, resource bounds, and expanded Unicode/CRLF evidence.
[Scalar-value dispatch](native-value-dispatch.md) is qualified separately.
[Kind conditions](native-kind-conditions.md) also narrow ordinary `IF`/`DECIDE`
bodies and short-circuit expressions. Broader domain pressure tests remain open.

## Exhaustive kind branches

```gwt
DEPENDING ON contact
  WHEN the kind is email
    print contact.address
  WHEN the kind is phone
    print contact.number
```

The subject must be an explicit path to a nonoptional one-of value. Nested record
paths and collection item bindings work. The subject is evaluated once. Each
branch names a declared kind exactly once; unknown/repeated kinds are errors.
Cover all kinds, or finish with `ELSE` for the remaining kinds. An unreachable
`ELSE` after complete coverage is rejected. Every branch needs a body, which can
be `PASS`. Scalar subjects instead use [`WHEN the value is` branches](native-value-dispatch.md).

Inside a kind branch, the selected path has only that kind's fields. `ELSE`
retains only the remaining kinds, exposing fields common to that remainder.
Branch-local bindings and refinements do not escape. Nested dispatch can refine
further. The discriminator remains read-only. Exhaustive branches count toward a
behavior's return guarantee only when every reachable branch returns.

Payload fields may be read and updated. A narrowed value can be copied or returned
into its full declared contract. This also works for containing records and
collections. Shared mutable behavior arguments still require exact matching types:
use `(contact)` to pass a narrowed contact as a copy to a behavior expecting the
full contact type. A local copy retains its narrower type, so it cannot silently
be passed as mutable state to a wider contract.

Other parameters can alias the same storage without the checker knowing that
fact. During a selected branch, the runtime protects the subject's actual kind.
A write through any alias, including replacement of a containing record, must
preserve that kind. A violating write fails with `kind_mutation` before publishing
state or a mutation event. Same-kind replacement and payload edits are allowed.
Guards nest and are removed on normal completion, return, or failure, including a
failure caught by a scenario expectation. Earlier completed writes are retained;
this is not transactional rollback of the branch.

Each kind comparison records a `kind branch` event linked to the subject read,
with the actual kind, candidate kind, and selected flag. Comparison work charges
steps and evidence against the normal limits. Explanations and the default review
trail show these decisions. The [delivery routing example](../examples/native_kind_dispatch/README.md)
uses three distinct payloads and six scenario expectations.
