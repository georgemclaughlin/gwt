# Explicit failure-exit qualification — 2026-10-16

The native checker now recognizes a literal-false assertion as an exit for
return completeness and continuation proofs. `program.rs` and `refinement.rs`
share this structural analysis. No expression is evaluated to infer an exit;
runtime assertion execution and its failure categories are unchanged. The
[design note](../../../docs/native-failure-exits.md) explains the authoring need,
scope, and compatibility changes.

## Required inventory inspection

`inventory-before.gwt` retains the original Python example. The current rules
add a named returning inspection helper without changing fulfillment behavior.
The native entry imports these rules and supplies five scenarios: the original
three fulfillment cases, duplicate-match/snapshot inspection, and missing-match
failure. The Python entry remains executable with its existing lookup syntax.
Its checker does not accept native scenario-level LET or failure annotations.

`workflow/inventory-observations.json` records **720 valid integer-domain inputs**
under both Python source revisions and the packaged native engine: **2,160
executions**. An independent host model aggregates demand by SKU and allocates
against its first inventory record; it does not reproduce the GWT per-line loop.
The matrix varies payment/fraud precedence, expedited shipping, stock and demand
boundaries, empty/unrelated/duplicate inventory, duplicate order lines, and
unknown SKUs. All declared fulfillment and inventory outputs match. Numeric
normalization is explicit, including exact fractional shipping fees; other field
types remain checked.

`workflow/legacy-sharing.json` records a separate real Python observation:
writing through a lowercase lookup destination changes the source list item.
The native inspection scenario instead proves a returned snapshot can change
without changing inventory. This is not a universal semantics-preserving rewrite
of legacy lookup destinations. The existing inventory inspections only read them.

## Engine transition and failure evidence

Four new Rust test groups exercise return/failure paths, first match, partial
state/output, no binding on failure, copied records, capture/replay, generated
success/failure scenarios, wrong-predicate detection, structural exclusions,
presence/kind proofs, and guard release on normal return and expected failure.
Fifteen independent native duplicate-stock requests also capture and replay.
Two older negative tests were updated from literal false to `not true` to retain
their conservative-inference checks under the new explicit-exit rule.

`workflow/` retains three engine migration probes from the previous packaged
engine:

- Clearing a newly proven-present value through an alias changes from success
  to `presence_mutation`, retaining the value before the refused write.
- Replacing it with another present value preserves the full observation.
- A now-redundant presence assertion becomes a compilation refusal and remains
  explicitly unavailable for candidate execution.

The changed and preserved candidates replay. Their HTML proposals are saved,
but interactive browser validation remains pending. No proposal is approved.
All **57** retained portfolio cases migrate with complete observations preserved
and replay on the new engine. This finite portfolio is not a universal
compatibility claim. Old cases and the previous executable remain intact.

## Build and verification

All **398 Rust tests** pass on **1.85.0 and 1.96.0**, as does Clippy with warnings
denied. After adding an additional assertion for guard release on failure, the
four new groups were rerun on both toolchains and Clippy was rerun. Formatting
passes. All **666 Python tests** pass, along with 75 example formatting checks,
sixteen top-level checks, two reference workflows, and the extension check.
`reference-checks.json` records the 93 Python commands.

The local static musl release passes the independent Cargo package/host check,
eighteen installed/relocated run/capture/profile/replay profiles, and 288 shared
program executions. `package/qualification.json` records the build, source
fingerprint, artifact hashes, and retained workspace. This build is unpublished;
no production deployment is claimed.
The packaged binary also runs the new five-scenario entry and the complete
720-input comparison above. `example-run.json` records the documented request.

The subsequent `editor-verified/` run passes **40 checks** in installed VS Code
**1.137.0** against this packaged executable. The new check verifies imported
payload hover and definitions after plain/parenthesized literal-false guards;
removing the presence guard or replacing the kind guard with nonliteral failure
clears semantic results and diagnoses the first unsafe access. Restoring the
guards and moving an imported declaration update navigation without saving
either file. Ten JavaScript tests also pass. These are extension-host integration
checks, not visual browser validation or participant observations.

The earlier `editor/` and `editor-final/` attempts are retained failures of test
expectations. Removing the presence guard diagnoses the earlier `contact.kind`
read, not the later payload read. A moved definition's expected position must
use the editor model's normalized text, not the raw CRLF replacement string.
Correcting those expectations required no extension or engine implementation
change. `editor-verified/extension-host.json` is the successful final result.
Browser discovery was retried and still reported no available browser; the
interactive migration reports and study recovery UI remain pending.

Reproduce the workflow with retained old/new executables and a fresh directory:

```sh
python -m evaluations.native_editor.qualify_failure_exits --native /path/to/new/gwt-native --previous-engine /path/to/previous/gwt-native --before evaluations/native_editor/2026-10-16-failure-exits/inventory-before.gwt --output /path/to/new-qualification
```

`engine-source-manifest.json` records the new engine inputs. `verification.json`
binds the checked source and evidence files. Actual human-review evidence and
live native model comparison are still absent; external pilots remain deferred.
