# Typed local record checkpoint

The [native constructor](../../../docs/native-local-records.md), `LET name be
RecordType:`, creates a local with visible field values. It reuses the existing
checked initializer and runtime initialization operation. The compiler, scenario
classification, outline, type-use provenance, Python formatter projection, and
documentation support the form. No new runtime value or evidence schema is added.

The preceding goal turn added the allocation workflow and exposed template
plumbing and evidence growth. This turn removes the template plumbing through
a language feature; the evidence-growth problem remains visible.

## Final verification

- [Rust results](final-rust-checks.json): **365 tests** and warning-free Clippy
  pass on **1.85.0** and **1.96.0**, in development mode. Six constructor groups
  cover aliases, nested/optional/one-of records, missing/extra/duplicate/type
  failures, binding and behavior-name disambiguation, copied records, branch and
  loop scope, source-order failures, step/evidence limits, source mapping,
  capture/replay, generated scenarios, and formatting. Editor tests verify
  imported alias, initializer, local, and field provenance. All 1,004 independent
  allocation cases and 11 embedded allocation scenarios still pass.
- [Reference checks](reference-checks.json): **629 Python tests**, **73 example
  formatting checks**, 16 top-level checks, order/tour workflows, extension syntax
  checks, and **five JavaScript tests** pass. Two new formatter groups preserve
  constructor blocks/comments/quoted content and reject malformed field layout.
  Python execution remains unsupported for this native extension.
- [Actual VS Code run](editor-final/extension-host.json): **35 checks** pass,
  including imported constructor aliases and fields in unsaved Unicode/CRLF
  source, an incompatible-field diagnostic, and repair without saving.
- [Final executable](final-executable.json) identifies the frozen Rust 1.96.0
  development binary used for the final editor, migration, review, and resource
  checks. [Engine source hashes](engine-source-hashes.json) and
  [checkpoint hashes](source-hashes.json) record its source inputs and this work.
  No fresh release package, container qualification, or release-mode test matrix
  is claimed in this turn.

## Public outcomes and state changes

The [qualifier](../qualify_local_records.py) migrates **52 actual old allocation
cases** using the retained previous executable. All migrations preserve complete
observations; every migrated case replays. It then captures and replays the
refactored constructor-based source against the independent rational oracle.

[Review totals](review-final/qualification.json) report **zero changed outcomes**,
**52 changed states**, **52 source/evidence changes**, and no unavailable or
baseline-mismatched cases. The only state removal is the request-local `draft`;
the remaining state matches each baseline exactly. The **15 domain rejections**
remain rejected on both sides. All original case hashes remain unchanged and all
proposals are unapproved. [JSON](review-final/review.json) and
[offline HTML](review-final/review.html) retain the review. No new browser or
human review qualification is claimed.

An old returning call ending in a colon is now interpreted as a constructor.
An actual old `produce:` case replays on the previous engine but
[cannot migrate directly](review-final/colon-migration.json), reporting
`candidate_unavailable` with `unknown_type`. Its bytes remain unchanged.
[Renaming on the old engine first](review-final/renamed-migration.json) preserves
the complete observation and produces a verified candidate replay. Ordinary
bindings and calls without the trailing colon retain their previous resolution.

## Remaining limits and retained attempts

[Resource probes](resource-probes/results.json) repeat the previous workflow's
equal-weight cases. Tested inputs with 1/3/8/16 recipients succeed; the tested
32/64-recipient inputs still return `evidence_limit` and no result. The refactor
reduces work and events on the successful probes, but does not solve growth of
collection snapshots or quadratic scanning. These input-specific results do not
establish universal capacity or production performance.

The initial Clippy run requested a simpler equivalent outline condition;
[its log](rust-1.log) remains. The earlier successful `review/` and `editor/`
runs used the executable before that style correction. Final evidence is in
`review-final/` and `editor-final/`, using the final executable. The first editor
unit assertion was corrected to use the existing whole-declaration span for a
type alias. This checkpoint does not claim first-pass authoring success.

The [final checks](final-checks.json) cover documented commands, source/oracle
integrity, precise state comparison, local links, and diff whitespace. The full
goal remains active: broader language and tooling work, resource handling,
production qualification, and demonstrated human comprehension benefits remain.
