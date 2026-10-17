# Native language support and transition contract

GWT currently has two explicitly selected implementations. The Python toolchain
implements the [v0.2 specification](spec/v0.2.md). The Rust toolchain's current
contract is consolidated in the [native draft specification](spec/native-draft.md),
with the [experimental native grammar](native-grammar.md) and
[native semantics](native-semantics.md). Shared `.gwt` syntax does not imply
equivalent acceptance, state changes, numbers, or evidence.

This document consolidates the current support boundary and the procedure for
moving a workflow to native GWT. It also specifies the work needed to make a
versioned native language release. It does not assign that release a number,
change the default engine, or publish a package.

## Planned product cutover

The [post-merge product plan](post-merge-product-plan.md) targets one Rust engine
under the public `gwt` command and retirement of the active Python runtime.
That coordinated transition is not implemented yet. The identities below
describe the current checkout; the plan describes the intended merged product.

## Select and identify the implementation

| Surface | Current identity | What it identifies |
| --- | --- | --- |
| Python command | `python -m gwtlang` / installed `gwt` | Existing Python language and artifact workflow |
| Python distribution | `gwtlang` 0.3.0; language v0.2; run payload schema 3 | Separate package, language, and envelope versions |
| Native command | `gwt-native`; `version --json` describes the selected executable | Explicit native execution; no fallback to Python |
| Rust crate | `gwt-core` 0.1.0, `publish = false` | Experimental library package; not language v0.1 |
| Native saved case | Native artifact kind, schema, source and engine identity, frozen limits | Reproducibility of a particular observation; not Python artifact compatibility |

`gwt-native version --json` (also `version`, `--version`, or `-V`) returns a
`gwt.native-version` schema-1 report. It reports the compiled package name and
version, `languageProfile: "gwt-native-experimental"`, `languageVersion: null`,
`status: "experimental"`, and the same engine identity used in captured cases.
The Rust `version_info()` API supplies the same report. Neither path loads or
executes GWT source, and neither depends on the source checkout being present.

The profile is explicitly named but has no assigned language release version.
Its name does not promise unchanged semantics between experimental builds.
Retain the binary digest, source manifest, dependency lock, and build toolchain
alongside this report. A package version alone does not select the semantics of
a saved case. A source digest identifies the frozen
import closure; an engine digest identifies the engine inputs. Neither is a
human approval or authenticated provenance claim.

Select native mode explicitly in the editor and use the same engine for
checking, running, capturing, and reviewing. Python formatting can preserve
some native-only source, but passing that formatter does not establish Python
or native semantic acceptance.

**GWT: Show Engine Information** displays the active editor engine's version
report and selected command without saving or executing the open source. After
changing `gwt.engine`, reload the window; the report describes the engine active
in that window until reload. Older native executables without `version` fail
explicitly instead of reporting inferred identity.

## Supported native language

The grammar and detailed semantics define the accepted forms and their context
rules. The [conformance matrix](native-conformance.md) maps them to evidence.
The following is a support summary, not a second grammar:

| Area | Current contract |
| --- | --- |
| Domain values | Exact bounded integers and finite decimals; booleans and text; aliases; closed records; typed lists; optional values; one-of records and selected-kind contracts; finite text, numeric, and boolean literal contracts |
| State and calls | Explicit typed behaviors and requests; bare-path arguments share locations, grouped values copy; assignment and returns are snapshots; ordered mutation without rollback; typed local construction |
| Decisions | Boolean IF/ELSE, ordered DECIDE, exhaustive/fallback kind or scalar dispatch, explicit REQUIRE, conservative presence/kind proofs |
| Collections | Ordered FOR and first-match FIND with explicit ELSE; filtered traversal, guarded membership, append, count, and sum; snapshot and matched-item mutation contracts remain distinct |
| Calculations | Exact arithmetic and exact finite division; separately specified rounded division; named returning behaviors bound by whole-call LET |
| Host boundary | Declared root request bindings, closed nested records, exact decimal strings, rejected unknown fields, explicit failures and budgets; host owns external effects |
| Executable examples | Independent scenarios, backgrounds, tables, assertions, captured-print assertions, and the documented expected-action failure codes |
| Composition | Explicit USE declaration imports; request entries import their rules; imported scenarios require separate validation |

Finite numeric contracts are supported. A numeric union does not imply inferred
range proofs: arithmetic widens to its base type and a broad value cannot be
silently assigned back to a finite domain. A true-only input contract validates
the supplied value, not the truth of an outside attestation.

## Deliberate omissions and unresolved requirements

The current profile deliberately omits expression-embedded calls, calls directly
after RETURN, dotted public request bindings, inferred untyped record tables,
parallel English comparison aliases, lowercase find/exists steps, and `any`.
The [decision register](native-language-decisions.md) explains the alternatives
and their migration hazards. These are not queued compatibility promises.

Indexed source access is unsupported in both tested implementations. Positional
operations require a concrete policy for ordering, bounds, and mutation before
they can be designed. General dynamic data beyond the worked typed boundary
also needs a real representation requirement. No general automatic,
alias-preserving source translator is supplied.

These boundaries may change when domain needs or comprehension evidence justify
a better language. Preserve the executable behavior-step identity; unsupported
Python conventions alone do not justify new syntax.

## Migrate a Python workflow

1. Preserve the original source, host contract, implementation, representative
   inputs, and observations. State the domain's expected policy independently
   of either runtime, including rejected inputs and partial-state failures.
2. Classify each difference below. Adapt source and host boundaries explicitly;
   do not call a rewrite equivalent merely because it compiles or gives one
   matching result.
3. Check, format, and validate the native program and imported modules. Exercise
   independent request probes and embedded scenarios, including boundary values,
   missing data, repeated calls, alias effects, and applicable resource limits.
4. Compare acceptance, result, state, captured output, failure phase/code, and
   explanation against the intended policy. Record intentional changes and
   noncomparable evidence. Python and native evidence schemas are separate.
5. Capture new native cases and inspect their explanations. Review changed
   policy and host effects before switching a caller to the native engine.
   Keep the previous implementation and observations available for investigation.

| Difference to inspect | Required migration decision and worked evidence |
| --- | --- |
| Truthiness and boolean/numeric equality | Express a boolean predicate; distinguish actual booleans from numbers. See [semantic migration examples](native-semantics.md#migration-examples). |
| Decimal precision, recurring division, dispatch equality | Preserve exact values at the host boundary; choose an explicit rounding policy or domain ratio. See [rounded division](native-rounded-division.md), [ratios](native-exact-ratios.md), and [dispatch](native-value-dispatch.md). |
| Extra fields, missing values, root versus dotted contracts | Project the intended host facts and review newly refused inputs. See [input boundary decisions](native-input-boundary-decisions.md) and [language probes](../evaluations/native_language/2026-10-16-transition/README.md). |
| Return calls and copied/shared arguments | Add explicit result bindings in the original conditional scope; preserve call order, mutations, and failures. See [call decisions](native-language-decisions.md#calls-preserve-conditional-execution-and-mutation). |
| Optional/mandatory lookup and later mutation | Choose snapshot, retained selection, or mutation inside the match. A copied selected record does not preserve a Python alias. See [lookup contracts](../examples/native_lookup/README.md). |
| Flow proofs, new reserved verbs, typed construction | Recheck every branch and behavior declaration; review writes that invalidate a proof and calls affected by newly reserved syntax. See [branch proofs](native-branch-proofs.md), [local records](native-local-records.md), and [rounded division](native-rounded-division.md). |
| Paired request source and implicit dependencies | Put the dependency in USE and select a native scenario or JSON request explicitly. See [request entries](native-request-entries.md). |
| Existing saved cases and review decisions | Retain Python artifacts with their toolchain. Native migrate accepts native cases with a verified previous native engine; it is not a Python artifact importer. |

Each worked adaptation establishes only its documented contract and probe scope.
Passing a collection of examples is not a universal source-equivalence proof.

## Upgrade an existing native workflow

An engine change and a source change are different review operations:

- For an engine change, use [native migration](native-migration.md) or
  [corpus migration](native-corpus-migration.md). The previous explicit executable
  must replay the original case before the candidate runs the same frozen
  source, inputs, target, and limits. Unavailable or incompatible baselines
  cannot count as preserved behavior.
- For a source change, compare the verified native baseline against the
  candidate source on that engine. Use request cases to hold host inputs fixed;
  scenario comparison uses each revision's own setup and expectations.
- If an old source cannot compile on the new engine, the engine-only migration
  cannot bridge it. Adapt source on the old engine first if both engines support
  that form, review it there, then migrate it. Otherwise retain a separate
  before/after qualification against independent expectations and record that
  the automatic migration chain is unavailable. Do not rewrite case identity.

Preserve the originals. Changes to outcomes, partial state, failure details,
evidence, and budget behavior all need an explicit disposition. A migration
proposal starts unapproved; old decisions do not transfer to it. Fresh assessment
must validate saved decisions against the exact proposal before export.

## Versioned native release preparation

Before declaring a native language version:

1. Freeze a reviewed scope consisting of the grammar, semantics, decisions, and
   their conformance mapping. Distinguish normative rules from implementation
   bounds and explicitly deferred features. Resolve any contradictions rather
   than letting a passing parser silently choose the specification.
2. Assign the language identifier separately from crate/package and artifact
   schema versions. Expose that identifier consistently in installed tooling,
   editor selection, documentation, and host metadata; a folder name or crate
   version is insufficient. Identity reporting now exists across library, CLI,
   and editor. Assigning and qualifying a language release version remains
   outstanding; the current report deliberately returns null.
3. Freeze compatibility fixtures and the relevant build/source identities.
   Requalify supported hosts and the migration paths with the final candidate.
   State which platforms and workflows are supported rather than implying
   production readiness from a local package build.
4. Publish the intentional incompatibilities and manual/unavailable migration
   paths. Preserve the existing Python command and payload contract until a
   separately reviewed default/compatibility transition is implemented.
5. Apply the existing [release gates](release-v0.4-checklist.md). External pilots
   and publication remain deferred; preparing this contract does not waive
   either gate or demonstrate human benefit.

The full [project goal](project-goal.md) additionally requires actual human
understanding and review evidence. Internal sessions are pending by owner
choice. Engineering conformance and human benefit remain distinct claims.
