# Native language-choice audit — 2026-10-16

The [decision register](../../../docs/native-language-decisions.md) distinguishes
current-profile choices, actual Python migration differences, and unresolved
language work. `crates/gwt-core/tests/fixtures/language_choices.json` contains
thirty source probes with explicit native acceptance/diagnostic expectations and
independent state/result expectations. The Rust `language_choices` test executes
the accepted programs and checks those expectations.

`final/observations.json` is the authoritative completed comparison against the
retained packaged native engine and both Python runtime revisions. It includes
source, separate static-check results, complete native execution payloads, and
Python results or errors. Seventeen native programs compile; fifteen execute
successfully and two deliberately fail at a contract/assertion boundary. Thirteen
native sources are refused with the expected static diagnostics. Python checking
accepts 28 sources, while 26 execute successfully. Checking alone is not treated
as evidence of execution.

Key observations:

- A whole Python call after `RETURN` becomes native `LET result be call` followed
  by `RETURN result`, retaining the tested call count, mutation, and result.
  General arithmetic-embedded calls and `items[0]` expressions are rejected by
  both current engines; they are not existing Python features to port.
- Hoisting a call out of an unselected branch increments its state counter even
  though the assignment remains conditional. Staging is not a free reordering.
- Symbolic comparisons preserve the tested below/equal/above boundaries, and
  explicit negated membership preserves the tested text condition.
- A root record preserves the minimal nested request's result, but rejects an
  extra sibling the original dotted input contract accepts. The public contract
  is deliberately broader in scope and narrower in accepted unknown fields.
- A typed table preserves the checked rows and exact total. An integer plus an
  assertion permits an invalid code through static checking, then fails in the
  behavior; it does not replace a finite static type contract.
- Missing optional lookup retains the previous selection in the tested old and
  explicit-block forms. On a match, both Python forms share the selected record
  with the list; native assignment copies it. A later selection mutation leaves
  the native list unchanged. The source rewrite alone does not establish parity.

The audit also found a Python nested-record validation bug. The previous runtime
flattened through declared record fields, falsely reporting their parent field
missing. `runtime-before.py` is the exact retained module, with SHA-256 recorded
in the final qualification. The new validator stops flattening at declared field
boundaries and delegates to each field's type. Four regression groups cover
aliases, normalized optional children, present-empty optional records, absent
values, nested unknown fields, variants inside lists, dotted declarations, and
explicit `any` objects. This repairs existing contracts; it adds no native syntax.

The final comparison executes both Python modules. Exactly two probe observations
change: the valid root-record request now succeeds, and its extra-sibling case
reports the actual unknown field instead of a spurious missing parent. Other
record shapes are covered by the four focused regression groups rather than being
claimed as thirty-probe before/after observations.

`initial/` retains the original audit, including the old-runtime failures and one
incorrect native diagnostic expectation (`unknown_field` instead of the actual
boundary code `unknown_input`). `verified/` records the first corrected-runtime
run; `final/` adds pinned static diagnostic expectations and exact old-module
execution. Initial Rust test compilation and Clippy failures are retained; the
test's JSON string comparison and optional-value predicate were corrected.

All **410 Rust tests** pass on **1.85.0 and 1.96.0**, with Clippy and final focused
checks on both toolchains. All **670 Python tests** pass. Required repository
checks, source identities, and the unchanged native engine/package identity are
recorded in `verification.json`. No new package, release, participant result,
live model comparison, or review approval is implied.

Reproduce in a fresh output directory:

```sh
cargo +1.96.0 test --locked -p gwt-core --test language_choices
python -m evaluations.native_language.qualify_choices --native /path/to/gwt-native --previous-runtime evaluations/native_language/2026-10-16/runtime-before.py --output /path/to/new-language-audit
```

`--previous-runtime` executes the supplied trusted Python module; omit it to check
only the current runtime. The comparison refuses an existing output directory.
