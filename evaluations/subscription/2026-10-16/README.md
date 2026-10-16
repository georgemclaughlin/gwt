# Standalone existence adaptation — 2026-10-16

The subscription pressure test now expresses its standalone past-due question
as a named boolean behavior using the existing `FIND ... ELSE` and `RETURN`
forms. This supports the [native design decision](../../../docs/native-existence-decisions.md)
to use that primitive rather than add a parallel `exists` statement. No parser,
checker, runtime, or evidence schema changed.

`before.gwt` freezes the original example. The public request's resolved input
and output shapes are preserved. The plan-rank helper deliberately narrows from
arbitrary text to the account's named free/pro/enterprise union. In
`helper-contract.json`, the same appended caller supplying `legacy` succeeds
with rank three before adaptation and fails the helper contract afterward.
The appended source is retained so this boundary can be reproduced.

## Independent policy checks

`cross-engine/observations.json` retains **3,276 inputs** crossing:

- three plans and four feature classes, including unknown;
- zero/equal/over-limit seat usage;
- thirteen ordered invoice lists: empty, each single status, every status pair;
- seven override arrangements, including unrelated entries and active/inactive
  duplicate ordering.

The oracle uses a host precedence table and status-set membership. It is not
derived from GWT observations. Both Python revisions and the retained packaged
native executable match every expected decision: **9,828 executions**. The native
input account remains unchanged in normalized state for every case. Exact boolean,
text, and list results are retained; native rank values are explicitly expected
as decimal strings. These are valid integer-domain checks, not broad numeric or
failure equivalence.

Reproduce from the repository root with a new output directory:

```sh
python -m evaluations.subscription.qualify --native /path/to/gwt-native --before evaluations/subscription/2026-10-16/before.gwt --output /path/to/new-subscription-checks
```

The checked native executable is the retained static release whose SHA-256 is
`0008ff9638d89f930b25a28faeae8765a1b0f4368193f966324296d9a12c4c6f`.
All 56 qualified engine source/build inputs remain unchanged.

## Scenarios, faults, and review

Both toolchains pass thirteen embedded scenario executions, adding invoice
status-versus-age, duplicate override precedence, and repeated-decision checks.
The new Rust `subscription.rs` suite verifies thirteen presence combinations
with capture/replay, all scenarios, and four captured incorrect-policy witnesses:
true on no match, using age instead of status, skipping inactive matching
overrides, and treating seat equality as excessive. Removing the seat reset also
fails the reuse scenario. The first status-fault witness contained both a paid
and a past-due invoice, so both predicates returned true; it was corrected to a
single past-due invoice with zero age, which distinguishes the intended rules.

`review/` contains ten actual Python baseline captures, input files, selected
expected decisions, comparison JSON, and a source-backed HTML workbench. All ten
baseline observations verify; none changes output or failure, all ten change
execution path, and none is unavailable. These include each decision reason,
combined blockers with an override, first-inactive duplicate overrides, later
past-due status, and a void invoice. Browser interaction/visual validation is
pending; no approval or human-review finding is claimed.

All **391 Rust tests** and warning-free Clippy pass on **1.85.0 and 1.96.0**.
All **664 Python tests** pass, including example formatting/checking/execution.
Rust formatting and `git diff --check` pass. Logs are retained here.

The added helper changes call/return evidence and resource costs. Finite output
agreement does not prove equivalence for every budget or helper caller. No new
packaging, production, performance, model, or human-comprehension claim follows.
External pilots remain deferred; the full project goal remains incomplete.
