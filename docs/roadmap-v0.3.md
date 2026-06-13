# GWT v0.3 Stabilization Roadmap

Status: proposed direction.

This roadmap treats v0.3 as a stabilization release, not a broad syntax release.
The [v0.2 language surface](spec/v0.2.md) is already implemented around named
`REQUEST` flows, executable scenarios, typed records, generated host types, and
the CLI/API JSON boundary. The next useful milestone is to prove that boundary
under realistic adoption pressure.

## Release Intent

v0.3 should make GWT easier to trust as a small executable-spec module:

- keep named `REQUEST` blocks as the host-facing callable unit
- preserve the stable execution envelope and JSON schema direction
- make `gwt validate` the obvious local and CI gate
- improve diagnostic and editor feedback for ordinary authoring mistakes
- prove adoption through one or more real pilot workflows
- defer new syntax unless pilot examples show repeated, concrete pressure

The release should not try to make GWT a general-purpose language, a policy
decision point, a SQL-like query system, or a host-side scripting extension.

## Work Tracks

### 1. Compatibility And Versioning

Clarify what compatibility means for the language, CLI payloads, generated
types, and host APIs.

Candidate work:

- document the relationship between package versions and language spec versions
- keep JSON schemas additive unless a schema version changes
- keep `gwt version --json` as the machine-readable version surface for tooling
- write migration notes for removed v0.1 boundary forms
- keep `ExecutionResult.as_payload` and CLI JSON output stable

Exit criteria:

- docs clearly distinguish package version, language spec version, payload
  `schemaVersion`, inspect manifest/program hash, and generated type fixture
  diffs
- incompatible payload changes require an explicit version bump or migration
  note
- generated TypeScript/Python host fixtures remain diff-checked in CI

Related docs: [language specifications](spec/README.md),
[JSON schemas](schemas/README.md), and the [host-language client
contract](host-language-clients.md).

### 2. Validation As The Product Gate

Make `gwt validate` the standard answer to "is this rules file ready to run?"

Candidate work:

- keep validation phases source-located and machine-readable
- expand lint only where warnings reinforce documented conventions
- keep public examples formatted and scenario-backed
- add targeted validation tests for imported modules and request-only files
- document which failures should block adoption versus which are advisory

Exit criteria:

- a new adopter can wire one command into CI without learning the internal test
  suite
- lint warnings do not become a dumping ground for subjective style preferences
- scenario evidence remains a strong convention for substantial public examples
- public request invariants remain advisory unless a concrete workflow proves
  they should become required

### 3. Host Integration

Treat the Python API, CLI runner protocol, TypeScript client, and generated host
types as one integration contract.

Candidate work:

- harden examples that compile once, run many requests, and expose diagnostics
- keep TypeScript and Python generated types aligned with `gwt inspect --json`
- document operational guidance for the CLI-backed TypeScript client
- preserve explicit request names when a program exposes multiple workflows
- keep host observation adapters deterministic at the GWT boundary

Exit criteria:

- a host application can validate a file, inspect the manifest, generate types,
  run a named request, and understand failures without reading runtime internals
- examples show both executable-spec mode and embedded-decision mode
- host code does not reimplement durable GWT rules

Related docs: [host language clients](host-language-clients.md) and
[adoption modes](adoption-modes.md).

### 4. Diagnostics, Editor Support, And Debugging

Improve the authoring loop before adding language surface.

Candidate work:

- run a diagnostic UX pass by writing intentionally bad GWT programs
- improve parser/checker/runtime messages with expected and actual details
- keep source ranges accurate for CLI, LSP, and JSON diagnostics
- add editor coverage for any existing syntax that is under-highlighted
- keep debugger executable-line reporting aligned with runtime statements

Exit criteria:

- common mistakes point at the right line and describe the fixable issue
- editor diagnostics match CLI/checker diagnostics closely enough for trust
- debugger stepping remains useful for nested behavior calls and branch blocks

### 5. Pilot Pressure

Use real workflows to decide whether the current language is enough.

Candidate work:

- run at least one pilot using the [pilot evaluation guide](pilot-evaluation.md)
- start with the [release readiness pilot](release-readiness-pilot.md) unless a
  better real workflow is available
- record awkwardness as before/after GWT snippets, not as abstract feature wish
  lists
- classify findings as documentation, diagnostics, host integration, or syntax
  pressure
- keep syntax proposals behind examples that become materially clearer

Exit criteria:

- at least one realistic pilot reaches `gwt validate` plus host execution
- the pilot produces concrete findings, even if the right answer is "no syntax"
- deferred ideas are promoted only with evidence from multiple examples

## Syntax Policy For v0.3

Default answer: no new syntax.

A syntax proposal belongs in v0.3 only if it satisfies all of these:

- a medium-sized realistic example is materially clearer after the change
- the missing or failure case remains explicit
- the feature reads as a behavior step over state
- parser, runtime, checker, formatter, docs, examples, and tests can move
  together
- the design does not drift toward SQL, policy-engine, or general scripting
  vocabulary

Current deferred ideas, such as explicit initialization helpers and first-match
collection, should stay deferred until pilot pressure proves they are worth the
surface area.

Related docs: [deferred language ideas](deferred-language-ideas.md),
[first-matching decisions](first-match-decision-design.md), and
[records with named kinds](variant-match-design.md).

## Suggested Sequence

1. Fix obvious docs drift and make v0.3's stabilization intent visible.
2. Run a diagnostic UX pass and improve the highest-friction messages.
3. Use one real pilot workflow to test the current request/host boundary.
4. Tighten compatibility/versioning notes based on what the pilot needed.
5. Decide whether any deferred syntax has enough evidence for a design note.
6. Cut v0.3 only when docs, examples, generated fixtures, clients, and CI agree.

## Non-Goals

v0.3 should not add:

- implicit record defaults or hidden initialization
- source-level `null` or nullable type syntax
- SQL-like collection operators
- general pattern matching beyond the current one-of record behavior
- a network service before the local runner/client contract is proven
- host callbacks inside ordinary GWT behavior

These may be revisited later only if a concrete workflow demonstrates that a
narrow, behavior-shaped feature is the right answer.
