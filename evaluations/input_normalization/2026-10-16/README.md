# Typed contact-input boundary — 2026-10-16

The contact example replaces its four known `any` reads with `RawContactInput`,
including an optional text middle name and a separate domain-state label.
Normalization decisions remain in GWT. The [design note](../../../docs/native-input-boundary-decisions.md)
records stricter acceptance, retained behavior, and remaining engine differences.

`before.gwt` freezes the original example. `cross-engine-final/` is authoritative
for the final source/runtime. Its independent native model checks **94 inputs**:
56 returned profiles, eight behavior assertion failures, and thirty contract
rejections before execution. Both Python source revisions and the native engine
are run, for **282 executions**. All 56 ordinary successful results are preserved;
all eight provided-but-absent cases still fail, without a claim of identical
diagnostics or partial state.

Ten malformed inputs accepted by the old Python source are rejected by the
typed source. The remaining measured engine acceptance difference is an extra
top-level host binding: Python accepts it and native rejects it. Extra fields
inside the typed record are rejected by both. Native boundary failures have
empty state and no execution events; behavior failures retain earlier setup and
normalization state with no successful result.

## Empty-object regression discovered by the boundary check

The initial `cross-engine/` run exposed Python flattening an optional text value
`{}` into absence. The fix preserves explicit empty-object fields during record
validation. `python-runtime-before.json` records the pre-edit hash;
`runtime-before.py` preserves that exact prior module, reconstructed from the
single local fix and verified against the recorded hash. Other existing runtime
changes are preserved.

`empty-object-regression.json` executes the retained module and current module
against the same three independent inputs. Before the fix, optional text `{}`
and an unknown empty field incorrectly pass, while an explicit `any` field
containing `{}` incorrectly fails as missing. Afterward all three follow their
declared contracts. The retained module uses the current unchanged Python
dependencies; this is a targeted module comparison, not a packaged historical
release qualification. Unit tests also cover one-of payloads and ordinary
omitted/null/empty-text cases.

The initial report predates the fix and remains historical. The final report
records the current Python runtime SHA-256 and the existing packaged native
executable SHA-256. All 56 native engine source/build inputs remain unchanged.

## Captured review and verification

`review/` retains sixteen actual Python baseline captures, inputs, selection,
comparison JSON, and an HTML workbench. All captured/old evidence digests match.
The report explicitly classifies ten cases as incompatible with the new input
contract, one as a changed failure, and five as changed paths with preserved
output. There are no unavailable cases or baseline mismatches. These are not
sixteen equivalent successes. No review approval is recorded, and interactive
browser validation remains pending.

The shared source has six scenario executions in each engine. Three new Rust
test groups cover sixteen state/presence inputs, twenty malformed boundaries,
capture/replay of both failure categories, and three policy-fault comparisons:
treating empty text as absent, confusing missing with not-applicable, and hiding
an unknown-state validation error.

All **394 Rust tests** and warning-free Clippy pass on **1.85.0 and 1.96.0**.
All **666 Python tests** pass. All 74 example formatting checks, sixteen top-level
checks, both reference workflows, and the extension check pass; the 92 Python
commands are listed in `reference-checks.json`. Rust formatting and whitespace
checks pass. The documented request returns the expected Grace profile under
both engines; the native numeric count is explicitly serialized as `"0"`.

Reproduce in a new output directory:

```sh
python -m evaluations.input_normalization.qualify --native /path/to/gwt-native --before evaluations/input_normalization/2026-10-16/before.gwt --output /path/to/new-contact-checks
cargo test --locked --test input_normalization
```

These finite checks do not establish arbitrary dynamic-data migration, all nested
record behavior, complete engine equivalence, production readiness, or human
understanding. There are zero human participants and no external pilot.
