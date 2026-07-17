# GWT JSON Schemas

These schemas describe the stable JSON payloads emitted by the CLI and public
API helpers:

See [`../execution-cases.md`](../execution-cases.md) for the Execution Case
identity, replay, integrity, and sensitivity contract.

- `diagnostic.schema.json` for checker, parser, formatter, runtime, and lint
  diagnostics.
- `execution.schema.json` for `gwt run --json` and `gwt test --json`.
- `execution-case.schema.json` for the versioned artifact emitted by
  `gwt capture` and, for compatibility, `gwt explain --json`.
- `comparison.schema.json` for `gwt compare --json`.
- `case-corpus.schema.json` for a versioned, labeled selection of Execution Cases.
- `serve-qualification.schema.json` for `gwt qualify-serve --json` operator evidence.
- `check.schema.json` for `gwt check --json`.
- `inspect.schema.json` for `gwt inspect --json`.
- `validation.schema.json` for `gwt validate --json`.
- `version.schema.json` for `gwt version --json`.

`gwt capture PROGRAM --json-input FILE --request NAME` is the explicit
Execution Case v1 capture path. It prints canonical pretty JSON to stdout unless
`--output CASE.json` is provided; `FILE` may be `-` to read the input object
from stdin. Version 1 records an explicit capture policy, semantic execution
limits, completed or opted-in failed outcomes, and either full values or the
`omit-values` profile selected with `--omit-values`. `--record-failures`
returns a normalized failed case for GWT parse/runtime errors after program
identity is available. `gwt explain --json` emits the same payload as a
compatibility and convenience path. Readers verify the artifact's canonical
content digest; see the linked Execution Case contract for availability-state
semantics and its deliberately limited threat model.

The optional `factProvenance` array stores sorted host-supplied source notes for
validated request input paths. It is descriptive, unauthenticated metadata and
is omitted when the `omit-values` profile is used.

Schemas are additive contracts. New optional fields may be added as tooling
evolves; incompatible shape changes should bump the payload `schemaVersion`.
Distribution candidates also install the Execution Case, Case Corpus,
Comparison, and Serve Qualification v1 schemas under `share/gwtlang/schemas`
in the Python environment so offline consumers do not require a repository
checkout.
