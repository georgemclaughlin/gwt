# MiniLang: explicit payload contracts across engines

The MiniLang fixture exercises one-of AST records, dispatch, ordered evaluation,
keyed lookups, mutable runtime state, and domain errors. It is a fixture-driven
executable specification, not a parser or a self-hosted language implementation.

Its original dispatcher established a statement's kind before calling helpers,
but each helper accepted `MiniStatement` and directly accessed fields absent from
other kinds. That implicit relationship did not satisfy native checking: a
helper must establish the shape it uses through its own contract or branches.

The revised dispatcher passes explicit payload fields. For example:

```gwt
DEPENDING ON statement
  WHEN the kind is let_number
    store number statement.number_value as statement.name into runtime
```

The corresponding helper accepts `value is number`, `name is text`, and
`runtime is MiniRuntime`. Other helpers similarly receive a list name or the
operands, threshold, and output text needed by their operation. Mutable runtime
state remains explicit. No native syntax or runtime change was required.

The threshold helper now has a long signature. That is a real readability
tradeoff, and useful pressure on future designs for kind-specific contracts.
Passing a narrowed statement as a mutable generic statement would hide the
contract problem; copying it alone would not establish its kind inside the
helper. This adaptation makes the requirements checkable with today's language.
It does not establish that readers prefer the resulting syntax.

## Shared behavior, explicit source profiles

`examples/minilang_spec/engine.gwt` contains the shared contracts and behavior.
The existing `rules.gwt` imports it and retains Python setup/scenarios. The new
`native_scenarios.gwt` imports the same engine and uses native explicit kind
initializers followed by append steps. Both entries contain two scenarios and
15 expectations. Setup fixtures are separate and must be maintained together;
there is no automatic source translator or separate copy of the domain logic.
Both engines also use the unchanged `request.json` and public request name.

Native `number` means exact decimal, including indexes and counters in this
existing example. Its JSON output therefore uses decimal strings. Python's JSON
numbers and native decimal strings are compared by numeric value only at numeric
leaves defined by the independent oracle. Text, booleans, collection order, record
fields, and errors are compared without coercion. The experiment covers integer
inputs; it does not prove fractional-number equivalence.

## Evidence and preserved behavior

[The qualification](../evaluations/minilang/2026-10-16/README.md) compares the
frozen original Python source, revised Python source, and previously qualified
packaged Rust executable against a separate host model. All 943 probes agree:
720 statement orderings, 125 arithmetic combinations, and additional missing
token/binding/list/statement, duplicate-name, unknown-source, and stale-state
cases. Incorrect inclusive-threshold and triple-map revisions are detected.
Rust tests separately check explicit expected results, replay/explanations,
reused-state clearing, and boundary-change detection.

The five-case Python refactor review has no changed outputs or failures, four
changed execution paths, and one unchanged case. The missing-map case stops
before the changed helpers. A native review detects an incorrect inclusive
comparison only at equality among its five cases. Neither review approves the
deliberately incorrect candidate.

Some existing fixture semantics are intentionally preserved: lexed/parsed flags
reflect the fixture count checks, while errors can independently make the final
status fail. A six-statement fixture may therefore continue evaluation even when
a required kind is missing. Lookups select the first matching name, missing data
produces ordered domain errors, and resetting a reused runtime clears prior
outputs and bindings. This work does not silently redefine those policies.

General source migration, full MiniLang parsing, fractional-number equivalence,
performance, and measured human comprehension remain unproven. The larger
MiniLang 2 VM still needs separate evaluation and adaptation.

## Native kind-contract experiment

The native engine now supports `TYPE ThresholdStatement is MiniStatement of kind
if_add_gt_print`. A helper using that contract can accept the narrowed statement
directly, keeping the call `compare sum statement into runtime`. The selected
contract retains all payload fields and the discriminator. Shared calls require
proof of the kind; generic unrefined statements remain rejected.

[A separate evaluation](../evaluations/native_editor/2026-10-16-kind-contracts/README.md)
compares this form with the explicit-payload engine. Its candidate is a frozen
experiment, not a second maintained domain module. The shared Python/native
engine remains the cross-engine reference fixture. This new type form removes
the mechanical need for a long call, but comparative human comprehension remains
to be measured.
