# Explicit failure exits in native behaviors

A required lookup can return the selected value or explicitly fail when it is
missing. It no longer needs a fabricated fallback return solely to satisfy the
native checker:

```gwt
WHEN inventory item for <sku> in <inventory>
  GIVEN sku is text
  AND inventory is InventoryState
  THEN returns InventoryItem
  FIND item in inventory.items WHERE item.sku == sku
    RETURN item
  ELSE
    REQUIRE false
```

This helper is part of the existing
[inventory allocation example](../examples/inventory_allocation_spike/README.md).
Its [native scenario entry](../examples/inventory_allocation_spike/native_scenarios.gwt)
uses `WHEN LET widget_inventory be inventory item for "widget" in inventory` to
inspect allocated stock. The first matching record in input order is returned
as a snapshot. A missing match fails with `assertion_failed`, preserving prior
state changes and output; no caller result binding is installed.

## Deliberate control-flow rule

The structural exit analysis recognizes `RETURN` and a `REQUIRE` whose checked
expression is the literal boolean `false`, including parentheses around that
literal. Complete decisions/dispatch and both `FIND` alternatives can compose
these exits. Every path that can complete normally still requires a compatible
return in a returning behavior. An always-failing behavior can declare a return
contract without producing a value on any execution.

The same analysis determines which branches can reach subsequent steps. For
example, after `IF box.value is absent` with `REQUIRE false` in its body, only
the present path can continue. Supported presence/kind facts from continuing
branches retain the existing alias guards. Failures are exits, not successful
returns: they produce the ordinary assertion diagnostic and evidence, propagate
to the caller, and release only guards owned by scopes being exited.

This is not general constant evaluation. `REQUIRE not true`, `REQUIRE 1 == 2`,
or a boolean variable are not structural exit proofs. Nor are calls to helpers
that always fail, arithmetic that would fail, or loops whose bodies always
exit. A `FOR` may execute zero times. Unreachable source remains checked; when
every branch exits, the checker does not invent facts about the impossible
continuation. No new syntax, runtime failure category, or exception handler is
introduced. Resource failures still retain their own diagnostics.

## Migration requires checking state sharing and guards

The old lowercase Python `find ... into destination` can leave `destination`
sharing the matched record. A native returned record is a value snapshot.
The inventory adaptation preserves the existing scenarios' read-only
inspection, but is not a general rewrite for mutable lookup destinations.
Perform intended mutations inside the existing `FIND ... ELSE` block, where
the selected item aliases the source collection. Moving mutations across that
block can also change traversal-guard lifetimes and needs separate review.

Missing-match diagnostics deliberately differ: legacy mandatory Python lookup
reports that no matching item was found; this explicit source failure reports
`assertion_failed` at its `REQUIRE`. Source locations and execution evidence also
change. Optional lowercase lookup has another important behavior—no match leaves
its destination unchanged—which this returning helper does not reproduce.
That form still needs its own worked adaptation.

Existing native programs may also change when moving engines. A branch that
fails explicitly now contributes no continuation path. A later alias write
that clears a newly proven-present value fails with `presence_mutation` before
the write. Conversely, a now-redundant presence check can fail compilation
because the path has already been refined to its present type. Exact mutable
helper contracts can likewise need review after narrowing. Use captured engine
migration rather than assuming unchanged source implies unchanged behavior.

## Evidence

[Qualification](../evaluations/native_editor/2026-10-16-failure-exits/README.md)
covers first-match selection, missing failures, partial state/output, return
snapshots, generated failure scenarios, proof lifetime, conservative exclusions,
and deliberate engine compatibility changes. An independent inventory model
checks 720 inputs under both Python source revisions and the packaged native
engine. The public native entry has five scenarios, including duplicate-match
inspection, snapshot isolation, and a missing lookup.

From the repository root:

```sh
cargo +1.96.0 run --locked -p gwt-core --bin gwt -- validate examples/inventory_allocation_spike/native_scenarios.gwt
cargo +1.96.0 test --locked --test failure_exits
```

The Python entry retains its existing scenario syntax. The native entry imports
the shared declarations and supplies native actions and failure assertions.
These checks establish concrete behavior, not measured readability or a
universal migration for legacy lookups.
