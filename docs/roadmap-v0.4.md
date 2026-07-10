# GWT v0.4 Behavior Review Roadmap

Status: core implementation candidate complete; release gates remain open.

Current checkpoint (July 2026): the bounded runtime, frozen dependency-closure
loader, Execution Case profiles, factual explanation, verified scenario
generation, old/new comparison (including failure transitions), and static
local workbench are implemented behind versioned v1 schemas. Wheel and sdist
candidates are buildable without a publish step. Release remains blocked on
reviewed checked-in compatibility fixtures, two external pilots, the owner
name decision, and the owner license/publication decision. The static HTML
workbench displays source locations but does not provide editor navigation;
that remains an integrated-surface follow-up rather than a hidden claim.

This roadmap moves GWT from a stabilized executable-spec module toward a
local-first behavior review workflow. It deliberately does not begin with a
hosted dashboard. The durable product seam must first work as versioned data
and command-line operations that any future UI can faithfully compose.

The current source-language baseline remains the
[`v0.2` specification](spec/v0.2.md). v0.4 is not a broad syntax release.

## Product Decision

The product thesis for this milestone is:

> Executable decision specifications for behavior that is too domain-rich for
> a decision table, too small for a workflow platform, and too important to
> hide in application code.

The differentiated workflow is not a generic trace viewer or visual rule
editor. It turns a concrete execution into durable, reviewable behavior:

```text
captured run -> factual explanation -> expected behavior -> generated scenario -> old/new comparison
```

GWT should make it possible for an engineer and a domain reviewer to answer:

- What happened for this input?
- Which executable behavior and conditions produced it?
- Is that the result we intended?
- Can this case become an ordinary checked `SCENARIO`?
- Which captured cases would change under a proposed program revision?

The primary product object is a source-linked **Execution Case**, not a
dashboard row and not an observability span. The first UI should be a behavior
change workbench over that object. A hosted collaboration product is a possible
later deployment shape, not the premise of v0.4.

## Release Intent

v0.4 should:

- make executions bounded, source-located, deterministic, and attributable to
  the complete program dependency closure
- define a versioned Execution Case format for portable behavior evidence
- replace domain-specific explanation heuristics with generic factual output
- turn a reproducible case into a formatted, reviewable scenario patch
- compare a real case corpus against two actual GWT programs
- expose those primitives in one local behavior-review workbench
- validate the loop with external pilots before investing in hosted workflow
- resolve project identity and make a release installable without contributor
  setup

The implementation order below is a dependency order. A later surface may be
prototyped to test usability, but it must not ship its own evaluator, policy
logic, evidence format, or explanation semantics around an unfinished lower
layer.

## Terminology And Trust Boundary

Use these terms consistently in code, documentation, and UI copy:

| Term | Meaning in v0.4 | What it does not imply |
| --- | --- | --- |
| **Debug session** | Ephemeral developer introspection with breakpoints, stack frames, locals, and potentially full sensitive values | Durable evidence, stable replay, retention, or governance |
| **Operational trace** | An OTLP-compatible projection for latency, errors, and execution events in an observability backend | A canonical or lossless Execution Case; traces may be sampled, dropped, or differently redacted |
| **Execution Case** | A versioned, source-linked record of one invocation and the evidence needed to review or reproduce its behavior | Authenticated actor identity, approval, non-repudiation, legal sufficiency, or tamper-proof storage |
| **Explanation** | A deterministic rendering of facts recorded by execution: evaluated conditions, selected branches, changes, and results | Inferred business intent, an AI-generated causal story, or proof that the behavior was correct |
| **Comparison** | A deterministic old/new evaluation of the same case corpus | Deployment, rollout safety, statistical impact analysis, or approval |
| **Audit system** | A future governance system with identity, authorization, timestamps from a trusted source, retention, integrity controls, approvals, and chain of custody | A label for an Execution Case list or ordinary trace viewer |

v0.4 may produce **reviewable evidence** and an **evidence timeline**. It should
not label a screen "audit log," claim that a case is tamper-proof, or describe
the workbench as compliance-ready. A content digest can detect accidental
change; without authenticated signing and controlled storage, it does not prove
who produced or preserved an artifact.

## Dependency-Ordered Milestones

### 1. Trustworthy Execution Kernel

The evidence layer cannot be more trustworthy than the runtime that produces
it. Harden the existing parser/checker/runtime path before making captured runs
a product contract.

Work:

- add deterministic semantic execution budgets, including behavior-call depth,
  executed statements, and collection iteration; keep host wall-clock limits as
  a separate safety control
- turn budget exhaustion, recursive behavior, and every expected runtime
  failure into stable, source-located diagnostics instead of raw Python errors
- define program identity over the entry file and every transitively resolved
  GWT dependency, with a documented hashing algorithm, canonical ordering, and
  logical module names
- ensure source references use logical dependency identity plus an accurate
  range, rather than depending only on workstation-specific absolute paths
- record state changes, condition evaluations, branch selections, behavior
  calls, declared outputs, and failures in deterministic execution order
- make value serialization stable for exact numbers, nested records, lists, and
  errors
- preserve parser, runtime, checker, formatter, LSP, and debugger alignment
- document that these controls do not yet make arbitrary remote execution a
  security sandbox

Exit criteria:

- adversarial tests cover recursion, exhausted statement/call/iteration
  budgets, deep nested calls, imports, contract failures, and runtime failures
- each user-actionable failure identifies a GWT source location and contains no
  accidental host stack trace in the stable payload
- changing any file in the loaded dependency closure changes the documented
  program identity, while an unchanged closure produces the same identity
- a successful run and a failed run both emit a complete, monotonically ordered
  evidence stream for every fact required by the next milestone
- the full repository verification gate passes with no new language syntax

### 2. Versioned Execution Case Artifact

Define Execution Case v1 as the canonical interchange object for review,
scenario generation, comparison, and the workbench. OTLP remains an operational
export derived from runtime events; it is not the case storage format.

The format should include:

- an unambiguous artifact kind and artifact schema version
- producer package version, language spec version, runtime/payload versions,
  and capture profile
- program name, request name, entry-module identity, complete dependency
  manifest, hashing algorithm, and dependency-closure digest
- input and initial-state facts when retained, or explicit omission/redaction
  records when they are not
- success, declared output, stable result envelope, or a normalized failure
- evaluated conditions with operands and boolean result, selected branches,
  ordered behavior calls, source ranges, and ordered state changes
- explicit redaction metadata that distinguishes absent, redacted, unavailable,
  and literal `null`-like host values; redaction must never silently substitute
  an ordinary value
- optional capture provenance such as an external correlation ID and observed
  time, clearly marked as unauthenticated unless supplied by a trusted host
- an integrity digest whose threat model is documented

The default artifact does not need to embed proprietary program source, but it
must prove exactly which source dependency closure ran. Replay against a
supplied program must verify that identity. A later portable source bundle may
be added as a separate, explicit capture mode.

Privacy is part of the schema, not a UI afterthought. Full values should be an
opt-in capture policy outside local development. Plain hashes of low-entropy
personal or secret values must not be presented as anonymization; deployments
that need value correlation should use an explicit keyed-digest policy managed
by the host.

Work:

- publish a JSON Schema and typed Python representation for Execution Case v1
- provide one runtime/API construction path and CLI capture path
- validate cases at read and write boundaries
- define canonical serialization and integrity-digest rules
- provide checked-in full-value, redacted, success, contract-failure, and
  runtime-failure fixtures from more than one domain example
- define replay/baseline verification behavior for a case and matching program
- document retention and sensitivity guidance without inventing a hosted data
  policy

Exit criteria:

- all checked-in fixtures validate against the published schema and round-trip
  without semantic loss
- repeated capture of the same program and input produces identical semantic
  evidence after documented provenance fields are excluded
- a dependency change, request mismatch, unsupported artifact version, or
  incomplete redacted case fails explicitly rather than replaying ambiguously
- a matching program reproduces the captured declared result and material
  execution evidence, or reports a source-linked divergence
- no consumer in later milestones needs raw tracer internals or OTLP fields

### 3. Generic Factual `explain --json`

Make explanation a deterministic projection of an Execution Case. Direct
`program + input` usage should internally capture the same case shape first so
there is only one explanation path.

Work:

- remove vendor-onboarding field names, thresholds, and prose heuristics from
  the generic explanation implementation
- define a versioned JSON explanation containing request/result summaries,
  selected branches, evaluated predicates with actual operands and results,
  ordered material state changes, behavior/source references, and failures
- distinguish an output-changing fact from a selected branch and from an
  earlier mutation that merely contributed data
- make redacted or unavailable operands explicit and never reconstruct or guess
  hidden values
- build plain-text rendering from the JSON model rather than maintaining a
  separate explanation engine
- retain machine-readable exact values while making text output concise and
  source navigable

A trustworthy first explanation is intentionally factual:

```text
decision.status changed from "new" to "needs_review" at rules.gwt:138

Selected because:
decision.missing_document_count > 0  [1 > 0 = true]
decision.expired_document_count > 0  [1 > 0 = true]
decision.risk_points >= 6             [10 >= 6 = true]
```

Domain narration may later be layered on top through explicit, reviewable
metadata. It must not be inferred from special field names in the runtime.

Exit criteria:

- the JSON contract has a schema and fixtures from at least three unrelated
  examples
- implementation tests prove there are no example- or field-specific prose
  branches in the generic path
- text output is a deterministic rendering of JSON facts and every decisive
  line links to the correct source range
- success, no-op, nested behavior, alternate branch, failure, and redacted
  cases all explain without leaking unavailable values
- the current experimental domain-specific output has a clear migration note

### 4. `scenario-from-run`

Turn a reviewed surprise into durable executable specification coverage. The
initial command should emit a patch or scenario to standard output for human
review; it should not edit a rules file automatically.

Work:

- consume a validated Execution Case and a matching program
- generate deterministic `GIVEN` input setup, the named `REQUEST`, and top-level
  `THEN` assertions over the declared output
- use checker/inspection data for record types and canonical source rendering
  rather than reverse-engineering types from JSON values
- choose a documented assertion default; initially prefer exact declared output
  evidence over an invented notion of a primary `status` field
- attach source/case provenance in a non-semantic form only if the current
  language can preserve it safely
- validate, format, execute, and verify the generated scenario before emitting
  it
- report an actionable refusal when redaction or missing source makes a faithful
  scenario impossible

Exit criteria:

- generated scenarios for scalar, nested-record, list, exact-number, union, and
  empty-collection inputs pass the canonical formatter
- every emitted scenario checks and reproduces the captured declared result
  against the matching program
- generation is deterministic and a format round-trip is idempotent
- fixtures cover vendor onboarding and at least two unrelated programs
- the default output is a reviewable patch/snippet; source mutation requires a
  separate, explicit future decision

### 5. `compare`

Evaluate the same captured inputs against an old and new real GWT program. The
UI and CLI must never reproduce behavior in JavaScript, Python, or handwritten
example-specific policy code.

Work:

- consume a directory or manifest of validated Execution Cases
- verify each captured baseline against the old program before attributing a
  difference to the new program
- check request and contract compatibility, preserving exact-number semantics
- classify declared-output changes, execution-path-only changes, new failures,
  resolved failures, incompatible cases, and baseline mismatches separately
- report old/new output field diffs, selected branches, evaluated predicates,
  and source ranges
- emit deterministic, versioned JSON first and render concise terminal output
  from it
- make partial-corpus failure explicit; never summarize skipped or incompatible
  cases as unchanged

Exit criteria:

- a checked-in corpus demonstrates unchanged results, changed output, same
  output through a changed path, a new error, and a contract incompatibility
- every reported difference is backed by executions of the two supplied GWT
  programs and links to old/new source evidence
- totals reconcile exactly across all classifications, with deterministic case
  and field ordering
- the JSON comparison contract has a schema and the text report is derived from
  it
- baseline drift and redaction limitations cannot be mistaken for a policy
  change

### 6. Local Behavior-Review Workbench

Build one focused local UI over the completed command/data contracts. A VS Code
panel or a loopback-only `gwt studio` are both acceptable delivery shapes; pick
the smallest option that supports realistic review.

The primary screen should answer “what changes under this draft?” and show:

- corpus totals and explicit incompatible/skipped counts
- cases whose declared output changed
- old/new field values and selected conditions
- source-linked factual evidence
- a reviewed action to generate a scenario patch

Work:

- load or capture Execution Cases without a database requirement
- render explanation and comparison JSON without adding UI-only semantics
- open exact GWT source ranges in the editor when available
- generate scenario patches through the same core implementation as the CLI
- keep data local by default and make any listening address or file write
  explicit
- test the complete workflow against real repository examples

Exit criteria:

- a user can capture/load a case, understand the factual result, compare a
  draft, and produce a verified scenario patch from one local entry point
- the workbench contains no alternate evaluator, domain-specific explanation,
  or handwritten policy reimplementation
- displayed counts and facts match CLI JSON fixtures exactly
- the application works without accounts, cloud persistence, deployment
  control, or a hosted service
- usability review confirms the behavior-change screen is the primary workflow,
  not an inbox or generic trace dashboard

### 7. External Pilots

Use the completed local loop to test whether the product is valuable outside
its examples. Pilot builds must be reproducibly installable, even if broad
public distribution and branding wait for the final milestone.

Work:

- recruit at least two unrelated decision/behavior workflows, with at least one
  maintained primarily by someone outside the project
- package a versioned wheel/source distribution and editor or workbench artifact
  that does not require a repository checkout
- ask each pilot to capture a real or safely synthetic surprising case, explain
  it, review the intended outcome, generate a scenario, and compare a change
- record task completion, incorrect or misleading evidence, redaction friction,
  unusable scenario output, and source-language pressure
- separate product/workflow findings from syntax proposals; require concrete
  before/after examples for the latter
- ask whether collaboration, shared retention, or approvals are repeated needs
  rather than assuming a hosted product

Exit criteria:

- both pilots complete the full case-to-scenario-to-comparison loop with their
  own programs and leave a durable scenario in source control
- no pilot relies on example-specific code or manual reconstruction of a result
- all trust, privacy, and misleading-explanation findings are resolved or
  explicitly block the v0.4 release
- findings identify the next product constraint with evidence, even if the
  result is “remain local and add no syntax”
- hosted work is proposed only if multiple pilots need the same collaboration
  or governance capability

### 8. Project Identity And Distribution

Resolve the `GWT` name collision before investing in a hosted brand, and make
the validated product available through normal release channels. Name research
may happen in parallel, but rebranding should not distract from the dependency
chain above.

Work:

- make an explicit keep/rename decision using searchability, package and editor
  identifiers, domain availability, trademark risk, and pilot recognition
- if renamed, publish a migration matrix for the project name, Python
  distribution/import package, CLI, VS Code extension ID, language ID, file
  extension, environment variables, schema identifiers, docs URLs, and trace
  attribute namespace
- prefer compatibility aliases and redirects over rewriting stored Execution
  Cases or breaking source files solely for branding
- publish signed/tagged source artifacts, Python wheels, checksums, release
  notes, and an editor/workbench installation path
- validate clean-machine install, upgrade, uninstall, and version reporting
- document support boundaries for the experimental language, local workbench,
  artifact schemas, and any pre-1.0 API

Exit criteria:

- the keep/rename decision and its rationale are public; a rename includes a
  tested migration guide and deprecation window
- a new evaluator can install a pinned release, run the examples, open the
  workbench, and validate its version without contributor setup
- GitHub Releases and the chosen package/editor channels contain matching,
  traceable artifacts
- stored v1 Execution Cases remain readable across any branding change
- release notes identify every schema/API incompatibility and its upgrade path

## Versioning, Migration, And Release Discipline

Keep these version surfaces independent and visible:

| Surface | Purpose | v0.4 rule |
| --- | --- | --- |
| Package/tool version | Distribution of runtime, CLI, and workbench | Advances for shipped tooling; does not imply new syntax |
| Language spec version | Source syntax and semantics | Remains `v0.2` unless an intentional language change updates implementation, tests, grammar, guide, and spec together |
| Existing payload `schemaVersion` | Stable run/check/inspect/validate envelopes | Preserve `ExecutionResult.as_payload`; additive changes only unless the version is explicitly bumped |
| Execution Case schema version | Portable captured evidence | Version independently by artifact kind; reject unsupported incompatible versions with an upgrade message |
| Explanation/comparison schema versions | Derived tool contracts | Version independently and keep text renderers downstream of JSON |

Compatibility rules:

- do not overload the existing execution envelope with an Execution Case trace;
  keep the stable host result small and make capture explicit
- additive optional fields may retain a schema version; removal, meaning change,
  or required-field change needs a version bump and migration note
- keep readers for checked-in prior-version fixtures, or provide a deterministic
  offline upgrade command; never mutate archived evidence silently
- identify experimental commands and schemas as such until their v1 fixtures,
  validation, and compatibility tests satisfy the milestone exit criteria
- retain the existing OTLP projection and debugger protocol unless a documented
  compatibility change is necessary; neither is the canonical evidence API
- replacing the current domain-specific `explain` behavior is an expected
  experimental break, but it still requires release notes and before/after
  examples
- a project rename must preserve old artifact kind/schema identifiers through
  aliases or resolvers; presentation branding is not permission to rewrite
  historical evidence

Suggested release sequence:

1. v0.4 development snapshots: kernel and artifact fixtures, explicitly
   unstable.
2. v0.4 alpha: case capture plus generic explain, used only with non-sensitive
   or safely redacted data.
3. v0.4 beta: scenario generation, comparison, and the local workbench with
   frozen candidate schemas.
4. v0.4 release candidate: external pilot findings resolved, compatibility
   fixtures frozen, clean-machine packages produced.
5. v0.4 release: identity decision complete, public artifacts published, full
   verification and migration documentation green.

## Overall v0.4 Exit Gate

v0.4 is ready only when:

- every milestone above meets its exit criteria in dependency order
- a complete program dependency closure and semantic execution budget are part
  of every captured case
- case capture, explain, scenario generation, comparison, and UI all use the
  same runtime evidence and versioned schemas
- generated scenarios reproduce their captured results and substantial public
  examples remain formatter-clean and scenario-backed
- comparison evaluates old/new GWT sources directly and accounts for every case
- full-value and redacted data paths have tested, documented behavior
- at least two external pilots complete the workflow
- package, schema, migration, and identity decisions are represented in release
  notes
- the standard repository verification commands and `git diff --check` pass

## Explicit Non-Goals

v0.4 will not build:

- a multi-tenant hosted service, account system, review inbox, or notification
  service
- a generic audit/compliance console or a claim of legally sufficient evidence
- a replacement for Jaeger or another general observability trace viewer
- a drag-and-drop or visual rule-authoring environment
- a BRMS with deployment, release approval, rollback, or policy distribution
- an AI narrator that guesses business reasons from field names
- a second evaluator in browser JavaScript or host application code
- automatic mutation or publication of `.gwt` source from captured data
- a remote untrusted-code execution service or claim that runtime budgets are a
  security sandbox
- new language syntax without repeated pilot evidence and the full
  parser/runtime/checker/formatter/spec process
- implicit collection queries, SQL-like operations, or general policy-engine
  vocabulary

## Decision After v0.4

Only after external pilots should the project choose among:

- continuing as a strong local developer/domain-author tool
- adding a small shared case repository for collaboration
- building authenticated governance features such as approvals and retention
- pursuing a broader hosted behavior-review product

The hosted path is justified only by repeated needs for shared state,
authenticated history, controlled retention, or cross-team review. A polished
dashboard alone is not product validation.
