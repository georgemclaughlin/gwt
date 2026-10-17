# Branch-specific field navigation checkpoint

Native editor navigation now follows a kind-refined payload to its actual field
declaration. The checker retains possible kind names at each prefix of a checked
read or mutable path. Navigation combines those facts with the binding's original
type declaration; equal structural types and matching field names cannot choose
a target. These metadata additions do not change source syntax or execution
rules. See [native editor navigation](../../../docs/native-editor.md).

Supported paths include `IF`/`DECIDE` and exhaustive kind branches, short-circuit
conditions, aliases, optional ancestors, nested one-of records, mutation targets,
copied records and payloads, collection items, and expanded examples. Root-name
selections still navigate to bindings. A field with several possible kind
declarations, or a value inferred from mixed declaration origins, retains a
binding fallback. Grouped/substituted spans without an exact source component
also retain the existing fallback.

## Tests and installed editor

- Rust **1.85.0** and **1.96.0** each pass **301** workspace tests (297 integration
  and four unit tests) and Clippy with warnings denied. Logs are
  `rust-*-tests.log` and `rust-*-clippy.log`.
- `editor_types.rs` now has **18** tests. Six added groups cover branch reads,
  writes and copied payloads; short-circuit and exhaustive-dispatch origins;
  narrowed collection items and copied one-of values; distinct records with
  equal shapes and ambiguous kind sets; per-example contexts; and multiple
  nested one-of prefixes. The prior condition-hover test now requires the
  selected field declaration rather than the earlier binding fallback.
- Actual VS Code **1.137.0** passes **26** checks with the installed package
  (`editor-installed/extension-host.json`). The existing optional/kind check
  now requires the imported email payload declaration. A new check changes a
  condition from email to phone while both payloads have `address: text`, and
  verifies the target moves to the phone declaration. It then moves the unsaved
  imported declarations with a Unicode/CRLF prefix and verifies the new range.
  Neither file is written to disk. The existing wrong-kind diagnostic and
  stale/invalid-edit checks still pass.
- All **621 Python tests** pass. Formatting passes for all **68** examples;
  top-level Python example checks, fulfillment/tour request workflows, extension
  syntax and five JavaScript tests, Rust formatting, and whitespace checks pass.
  `final-checks.json` records the final commands, including the documented editor
  protocol example and exact field queries for the worked contact policy's
  email, SMS, and pickup payloads.

## Package and unchanged observations

The Rust 1.96.0 package passes independent source/dependency checks, **18** host
observations, **288** concurrent executions, and **18** relocated replays. It
also verifies an explicit transition from the previous installed engine. The
new installed executable is `/tmp/gwt-package-host-4geqibtc/installed/bin/gwt-native`,
SHA-256 `e46378539d8dc88a5412ed3ea9cb574225462a75661a1abfd759dd9da07b20a0`.
Its engine source identity is
`sha256:638369358550c066f4cfe8375adfbca193702c05e47f68ba265b6d3d8fa9caaa`.
`package-source-verification.json` compares all **48** archived implementation
and build inputs with the current workspace.

`qualify_branch_navigation.py` compares **16 complete execution observations**
through the explicit migration protocol: eight previously captured contact
requests, the prior alias-guard failure, and seven scenarios captured with the
previous executable. That executable first reproduces every baseline observation;
the new engine then recaptures the frozen source and input. All results are
`observation_preserved`, including state, output, diagnostic, events, and steps.
The source cases remain byte-for-byte unchanged. Raw cases, migration proposals,
binary hashes, and command results are retained in `observations/`.

The engine source identity changes because implementation inputs changed.
Observation equality does not bypass that identity boundary or automatically
approve a migration. No saved review decisions or accepted corpus were changed.
This is preservation evidence for the tested cases, not proof for every program.

No review-page renderer changed in this checkpoint; the actual editor and
execution-preservation checks are the relevant new UI/behavior evidence. The
earlier review browser qualification is not presented as a new run.

## Remaining objective

This improves navigation while a person reads or edits kind-dependent rules.
It does not demonstrate a human comprehension benefit. Ambiguous-field multiple
targets, error-tolerant navigation, completion/debugging, broader language and
deployment work, and actual comparative human evidence remain open. No external
pilot or publication occurred. `source-hashes.json` identifies the checkpoint's
implementation, tests, documentation, and qualification tools.
