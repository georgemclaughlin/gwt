# Project goal: implementation and evidence ledger

The full objective is [project-goal.md](project-goal.md). **It is not achieved.**
This ledger tracks authoritative evidence and missing work without substituting
a partial native implementation for the requested language and review workflow.

**Completion is blocked on evidence prerequisites as of 2026-10-16.** Internal
human sessions remain pending and external pilots deferred by owner choice.
The prepared live model experiment also requires API access; its provider
preflight currently refuses to start without `OPENAI_API_KEY`. Installed Codex
CLI access is a different evaluation route, not a completed or qualified run of
that experiment. The [completion checkpoint](../evaluations/goal_audit/2026-10-16/completion-checkpoint.md)
records the current evidence and what would allow work to resume.

## Product cutover update

The Rust engine is now the only active implementation and installs `gwt`.
Python runtime/distribution and editor launch/debug paths are retired. The
[upgrade guide](python-retirement.md) records the historical reference and
existing-installation conflicts. The [cutover evidence](../evaluations/product_cutover/README.md)
qualifies packaging, installed examples, editor integration, and the generated site.
The [consistency follow-up](../evaluations/language_consistency/implementation.md)
aligns language guidance, editor/site syntax coloring, and casing diagnostics;
437 Rust tests pass on each supported toolchain, and all nine saved delivery
observations are preserved across the engine update.
Package and language release versions have not been advanced. Integration status
is tracked in [PR #2](https://github.com/georgemclaughlin/gwt/pull/2).
Publication, human sessions, and external pilots remain pending; the historical
ledger below records earlier checkpoints and should not be read as current engine
selection.

## Objective audit

Audited on 2026-10-16 against the current native engine and retained evidence.
The owner has explicitly left **internal human sessions pending** and **external
pilots deferred**. These decisions do not pause available engineering work.
See the [dated evidence audit](../evaluations/goal_audit/2026-10-16/README.md).

| Objective | Evidence in the current tree | Remaining proof or implementation |
| --- | --- | --- |
| Human understanding | Executable examples, source-backed review workbench, and a qualified offline source-review kit across four domains | Actual comprehension, error detection, and review-time measurements with representative participants; sessions are pending by owner choice |
| Independent semantics | Documented execution model, exact numbers, explicit state/aliasing, typed boundaries, failure/resource rules, finite scalar contracts, and deliberate language choices | [Support and migration contract](native-language-transition.md) is consolidated; CLI/library/editor profile identity is implemented; assigning a language release, freezing its scope, and final migration qualification remain |
| Rust foundation | Parser, checker, execution, independent conformance, scenarios, imports, source identity, capture/replay/comparison, and bounded evidence; 437 Rust tests at the latest identity checkpoint | Resolve remaining scope questions against concrete workflows; unsupported Python forms are not automatically features to port |
| Complete behavioral review | Source-backed offline comparison, saved decisions, fresh assessment, regression scopes, generated scenarios, engine-transition review, and qualified source adaptations | Representative human review and broader migration policy validation; browser automation verifies mechanics rather than comprehension |
| Practical adoption | Qualified Rust library/CLI packaging, GNU/static Linux bundles, Node host, native VS Code integration, and offline WASM execution in Chromium, Firefox, and Linux WebKit | Deployment/support decisions and representative integration evidence; additional platforms and editor conveniences need concrete demand |
| Demonstrated value | Small live refund maintenance comparison tied; five-domain maintenance apparatus and four-domain human-study fixtures now requalified on the current engine; separate runtime measurements | Larger live model experiment, actual human-benefit evidence, and representative adoption; no superiority claim follows from fixture checks |

## Completion-criterion audit

| Criterion from the goal | Status | Evidence required to close it |
| --- | --- | --- |
| Documented, intentional execution model | Documented for the experimental native profile | Deliberate version/support transition and consolidated migration expectations |
| Implementation passes independent conformance tests | Demonstrated for the documented profile | Close the final scope/support contract and maintain feature-to-evidence coverage; this is not full Python v0.2 compatibility |
| Explanations accurately reflect execution | Mechanically qualified for covered behavior | Continue independent execution/evidence checks as scope changes; confirm representative reviewers can use the explanations correctly |
| Representative users review meaningful changes with demonstrated benefit | Missing; sessions deferred by owner | Actual comparative participant observations, mistakes detected/missed, task times, and limitations |

Passing engineering checks does not close the last criterion. Conversely, an
optional platform, editor feature, or possible syntax extension is not a new
completion gate merely because it could be built. The release checklist has
separate external-pilot and publication gates, which remain in effect.

## Completed foundation work

- Added a Cargo workspace and an unpublished `gwt-core` library with an
  experimental `gwt` expression command.
- Parsed expressions once and checked their types before execution; resolved
  input bindings to slots while preserving source paths for evidence.
- Defined strict booleans, exact integer/decimal operations, closed input
  contracts, optional guards, short-circuit behavior, and explicit limits.
- Added 37 independent expression fixtures and integration checks for source
  spans, evidence dependencies, skipped operands, failures, repeated execution,
  nested presence guards, malformed syntax, and resource limits.
- Added full-file parsing and checking for records, aliases, text unions,
  typed behavior signatures, root request contracts, setup, `set`, `LET`,
  `IF`/`DECIDE`, assertions, captured output, and scenarios.
- Ran the existing refund programs against all 336 independent acceptance
  probes. Executed 20 embedded scenarios across four refund stages, support
  ticket triage, invoice pricing, and hello-world without invoking Python.
- Verified mutable parameter aliasing, local scope, nested record arguments,
  exact invoice totals, request failures, selected/skipped branches, source
  spans, shared execution budgets, and evidence-before-write behavior.
- Added transitive declaration imports and portable frozen source bundles.
  Native CLI runs now identify their exact source closure. Independent tests
  cover fingerprint encoding, shared dependencies, cycles, path and resource
  limits, imported diagnostics, relocation, and immunity to later source edits.
- Added immutable native execution cases binding source, input, limits, engine
  source identity, and the full observed execution. Replay detects forged
  observations even with valid checksums. Comparison only executes candidates
  after verifying the baseline, and separates source/outcome/state/evidence
  changes. All 336 independent refund probes pass through serialized case
  replay and comparison with expected changed/preserved classifications.
- Added native corpus reconciliation and offline HTML review with case search,
  filters, exact-value JSON download, source excerpts, decision trails, and
  operand links. Corrupt/incompatible cases and baseline mismatches stay in the
  report and cannot count as compared. All 336 refund probes have reviewed
  native explanations; this is test coverage, not human approval.

- Added typed list literals, structural equality, mutable collection traversal,
  first-match search with explicit missing handling, and exact collection totals.
  Independent tests cover live item values, scalar and record aliases, rejected
  shape changes, scope/type errors, bounded construction, and metered traversal.
  The stock-reservation example has three executable scenarios and 36 independent
  stock/quantity cases, plus repeated-SKU and invalid-input checks. Its captured
  decisions replay and compare with source-backed collection explanations.

- Added shared backgrounds and source-mapped example tables. Every row is
  checked before execution; each run gets fresh state and budgets. Original
  table cells and template lines remain the sources for evidence and errors.
  Independent tests cover layout, row failures, imports, expansion limits,
  CLI row counts, and delivery-quote boundaries.

The fixtures now include complete programs in refund review, invoice pricing,
support triage, stock reservation, and delivery quotes. They do not constitute multi-domain maintenance experiments
or adoption evidence. [The feature matrix](native-conformance.md) separates
implemented support from remaining language and product work.

## Remaining work and evidence

1. Complete the release preparation described in the
   [support and transition contract](native-language-transition.md). Current
   scope, migration responsibilities, and CLI/library/editor profile identity
   are implemented. Assigning a native language release version, freezing its
   scope, making a supported-host commitment, and qualifying the final candidate
   remain outstanding. No publication is implied.
2. Run the prepared five-domain live model experiment when provider access and
   the model configuration are available. Retain the small refund tie as a
   separate result; synthetic provider rehearsals are not live model evidence.
3. Keep human source-review sessions pending as requested. When resumed, freeze
   the participant and analysis plan before collecting responses. A source-only
   study cannot establish the workbench's benefit; that requires its own tasks.
4. Keep external pilots deferred. Production deployment and additional host or
   editor work should follow a concrete workflow and support requirement.

Finite numeric/boolean contracts, explicit calls, nested request representation,
lookup alternatives, branch refinements, exact rounding, browser execution, and
fresh-process measurements now have recorded implementation or design evidence.
They are not untouched milestones. Arbitrary indexing, general dynamic data,
additional target platforms, completion, and debugging remain possible work;
none should be added solely to reproduce Python conventions.

## Verification

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked -- -D warnings
cargo test --workspace --locked
```

The current native checks prove the documented subset only. Repository
Python/example/editor verification remains governed by [AGENTS.md](../AGENTS.md).

The first expression checkpoint passed 13 Rust integration tests and the
existing 611 Python tests. The program checkpoint expands native coverage to
30 integration tests, including the 37-expression fixture table, 336 refund
probes, 20 embedded scenarios, negative cases, and CLI checks. Verification
commands above run those assertions. The imports/source-identity checkpoint
adds 10 integration tests, bringing the native total to 40. These include
positive depth/module-count boundaries and filesystem failure diagnostics.
The native-case checkpoint adds 11 integration tests, bringing the total to 51,
including all 336 refund revision comparisons and CLI failure/replay semantics.
Independent Python hashing reproduced the case and engine fingerprints, and an
invoice case captured on Rust 1.96.0 replayed on both 1.96.0 and 1.85.0.
The corpus-review checkpoint adds nine tests, bringing the native total to 60.
Browser checks exercised 343 selectable cases, filters, operand links, injection
escaping, exact-integer download, and 390px layout; see the
[dated evidence](../evaluations/native_review/2026-10-16/README.md).
Tests and Clippy passed on Rust 1.85.0 and 1.96.0; formatting passed on 1.96.0.
Native check/test/run commands passed for
the documented refund and invoice examples, and Python `validate` passed for
the new invoice fixture. CI contains the Rust checks; a hosted CI run has not
been claimed.

The collection checkpoint brings the native total to 70 integration tests.
Tests and Clippy pass on Rust 1.85.0 and 1.96.0. This adds language and review
coverage; it does not close the human-benefit or deployment criteria.
The reservation example passes Python format/validate and native check/test/run.
Browser qualification now covers 380 cases across five pages, including 37
reservation inputs and five independently expected boundary changes; see the
[collection evidence](../evaluations/native_review/2026-10-16-collections/README.md).

The scenario checkpoint brings the native total to 81 integration tests.
Tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes on 1.96.0.
The delivery example passes native check/test/run and Python format/validate
with ten scenario rows. Independent host expectations cover 16 boundary/member
combinations and two invalid weights. Source-backed explanations validate each
expanded row without inventing a generated file in the source snapshot.
At that checkpoint, native case capture targeted named requests; scenario
capture/generation and human review evidence were still unfinished.

The generated-scenario checkpoint adds ten tests, bringing the native total to
91. Verified successful request cases produce frozen runnable source bundles
with assertions over every declared output. At that checkpoint, generation refused mismatches,
failed observations, captured print output, and output-free requests; it checks
and runs the generated scenario before returning. All 336 independent refund
revision probes have the expected changed/preserved classifications when run as
generated scenarios. Typed values, mutated inputs, imports/source locations,
export behavior, and limits are covered. Tests and Clippy pass on Rust 1.85.0
and 1.96.0; formatting passes on 1.96.0. See
[native regression scenarios](native-scenarios.md) for scope and reproduction.

The saved-decision checkpoint adds seven native tests, bringing the total to 98.
Reviewer choices and notes can be saved/restored in an offline page and checked
against a freshly regenerated report with `assess-review`. Choices start pending,
cover every case, and cannot accept unverified comparisons. Report identity
binds exact source, engine, input, evidence, labels, and case order. This is a
portable record with a self-reported reviewer, not authenticated approval or an
append-only audit history. See [saved review decisions](native-review-decisions.md).

Tests and Clippy pass on both Rust 1.85.0 and 1.96.0; formatting passes on
1.96.0. Browser checks cover all 380 cases, saved-decision round trips, rejection
of stale/malformed imports, note escaping, and exact-number downloads. The
browser-produced files pass fresh CLI assessment with the expected synthetic
rejection/pending counts. See the [dated decision evidence](../evaluations/native_review/2026-10-16-decisions/README.md).
Authentication and immutable history remain optional integration concerns;
these engineering checks do not supply the missing human-benefit evidence.

The expression-read checkpoint removes eager copies of unrelated bindings and
parent records during native expression evaluation. Paths are resolved when
reached, including optional guards and short-circuiting. Three unit tests cover
read order/source spans, skipped reads, and budget-before-read behavior; the
98 integration tests continue to pass. Tests and Clippy pass on Rust 1.85.0 and
1.96.0; formatting passes on 1.96.0.

A reproducible development harness separates in-memory compilation, repeated
request execution with full evidence, and response serialization. Two measured
before/after pairs preserve all 189 normal/budget observations exactly. The
4,000-item unused-payload workloads improve by 2.2–2.6×; smaller measurements
are noisy and do not establish a general speedup. See the
[dated report](../evaluations/native_performance/2026-10-16/README.md) for raw
samples, source/build provenance, independent expected outputs, and the exact
runtime patch. All nine benchmark sources pass Python format/validate checks.
Cold start, isolated evidence-construction cost, memory/concurrency, packaging,
host/editor qualification, and the human-benefit criterion remain unfinished.

The scenario-capture checkpoint adds selected scenario execution and native
schema 2 scenario cases while preserving the schema 1 request-case shape.
Backgrounds, expanded example rows, printed output, execution failures, partial
state, and budgets replay exactly. Baseline mismatch prevents candidate execution.
Scenario comparisons select the same name in each revision and explicitly use
that revision's own setup and assertions; request cases preserve host input.
Mixed corpora retain both target types in review/search and saved decisions.

Seven integration tests bring native coverage to 105 integration tests plus
three unit tests (108 total). Tests and Clippy pass on Rust 1.85.0 and 1.96.0;
formatting passes on 1.96.0. A mixed 13-case browser review independently expects
four outcome changes and three candidate failures. Browser checks cover scenario
labels/search, exact printed integers, report download, decision save/restore,
and 390px layout. Downloaded decisions pass fresh CLI assessment with one
synthetic rejection and 12 pending choices. See
[scenario review qualification](../evaluations/native_review/2026-10-16-scenarios/README.md).
Source-level expected-failure/print assertions and generation, engine migration,
the remaining language/deployment work, and human-benefit evidence remain open.

The returning-behavior checkpoint adds explicit `THEN returns Type` contracts,
checked `RETURN` expressions, and whole-call `LET` bindings. Native checking
requires a return on every normal path. Return values are snapshots; arguments
retain state-alias semantics. Early returns propagate through branches and
collections, stop at the callee, and release only the callee's traversal guards.
Recorded returns link their expression, behavior completion, and caller binding.

The member-pricing example passes Python format/validate and native check/test/run
with four scenario rows. Eleven native tests add 32 independent exact-price
probes, revision comparisons, and generated scenario checks, plus typed values,
early exits, aliasing/snapshots, evidence limits, static errors, and recursion.
Runtime dispatch was separated after a full-suite test exposed excessive stack
use at the nesting limit. Tests now cover both the hard limit and deep successful
calls with nested return expressions. All 189 prior development-workload
observations, including budget failures, remain byte-identical.

Native coverage is now 116 integration tests plus three unit tests (119 total).
Tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes on 1.96.0.
Browser qualification covers return visibility, operand links, and saved choices
for three independently checked pricing cases; see
[return-value review evidence](../evaluations/native_review/2026-10-16-returns/README.md).
At that checkpoint, value/expression arguments, remaining language forms, source-level failure/print
expectations, engine migration, deployment qualification, and human-benefit
evidence remain unfinished.

The value-argument checkpoint adds copied literals, lists, and grouped expressions
alongside existing shared state paths. `(state)` explicitly copies a path;
quoted strings remain text. Shared arguments require exact mutable contracts,
while copied values permit ordinary assignment normalization. Arguments evaluate
left to right before entering the callee. Source-linked argument events and
local-copy mutation labels make that distinction visible in review.

Ten native tests cover record/list snapshots, unchanged alias behavior, numeric
widening, quoted text, source mapping, traversal guards, pre-entry failures,
evidence limits, and successful/bounded recursion. Thirty-two independent price
probes pass capture/replay, candidate comparison, and generated regression
scenarios. The example passes native check/test/run with five scenarios; its
grouped-call syntax passes Python formatting but is native-only for checking
and execution. Eleven Python formatter tests pass.

Native coverage is now 126 integration tests plus three unit tests (129 total).
Tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes on 1.96.0.
All 189 earlier development-workload observations still match exactly; no new
performance claim is made. Browser checks verify copied argument visibility,
source/operand links, saved choices, and mobile layout for three independently
specified pricing cases. Fresh CLI assessment reproduces one synthetic rejection
and two pending choices. See [value-argument evidence](../evaluations/native_review/2026-10-16-arguments/README.md).

At that checkpoint, calls embedded in expressions, remaining language forms, source-level failure/print
expectations, engine migration, deployment qualification, and actual human-benefit
evidence remain unfinished. The external pilot remains pending as requested.

The printed-output checkpoint adds native scenario/background `THEN prints [...]`
assertions over the complete ordered JSON output so far. Missing, extra,
reordered, or changed values fail without erasing observed output. The literal
has explicit size/depth/integer rules and rejects duplicate object keys.
Source-backed evidence records expected/actual values and links prior print events.

Generated scenarios now assert every declared output and the full print sequence,
including empty output. Successful requests without declared outputs are supported.
Generated artifact schema 2 records this stronger assertion scope; schema 1
source remains executable. Expected-failure generation still requires explicit
scoping of the failing action and remains unfinished.

Eight tests bring coverage to 134 integration tests plus three unit tests (137
total). Tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes on
1.96.0. Twelve Python formatter tests pass; Python runtime/checker support is not
claimed for the native assertion. The receipt example passes native check/test/run.
The generator and browser verify three independent observations: a changed receipt
scenario fails, the quiet scenario stays successful, and a fixed host request
retains its successful execution while its printed quantity changes. Exact-number
download, operand links, mobile layout, and saved choices pass; fresh CLI
assessment returns one synthetic rejection and two pending choices. See
[printed-output review evidence](../evaluations/native_review/2026-10-16-prints/README.md).

At that checkpoint, the full goal remained incomplete: expected-failure scenarios/generation, engine
migration, remaining language forms, deployment qualification, and comparative
human evidence are still open. No external pilot has been started.

The expected-failure checkpoint adds `THEN fails with "code"` immediately after
one scenario/background action. Supported assertion and arithmetic failures let
the scenario continue, preserving prior mutations and output. Setup/earlier
failures cannot satisfy the annotation. Unsupported boundary, safety, engine,
and resource errors propagate unchanged. Newly introduced caller bindings are
unavailable after an expected failure. Evidence retains the complete observed
diagnostic and links its original source alongside the expectation.

Generated artifact schema 3 supports verified behavior failures. It asserts the
failure code, every input's post-failure state, and the complete print sequence;
generation also independently checks the original diagnostic before returning.
Future source assertions do not lock message text or source position. Failed
request-local state and unpublished outputs are not exposed as caller bindings.
Unsupported failure codes remain eligible for exact replay/comparison, rather
than being relabeled as passing source tests.

Twelve native tests add 25 independently specified stock/quantity combinations,
generated revisions, wrong-error/unexpected-success cases, partial-state checks,
scope and binding failures, traversal cleanup, evidence/step/depth bounds,
successful deep recursion, and source-mapped example rows. Native coverage is
146 integration tests plus three unit tests (149 total); tests and Clippy pass
on Rust 1.85.0 and 1.96.0. Rust formatting and 13 Python formatter tests pass.
The stock example passes native check/test with four scenarios, while its raw
shortage request intentionally fails. CLI export executes supported failed-case
regressions and refuses unsupported boundary failures without creating output.

Four independently specified browser cases distinguish expected-rejection
scenarios from raw rejected requests. Removing the stock guard causes the shortage
scenario to fail through unexpected success, while the same raw request starts
succeeding with incorrect negative stock. Valid and nonpositive-quantity cases
retain their expected outcomes. Source/error visibility, operand links, mobile
layout, and saved choices pass; fresh CLI assessment reproduces one synthetic
rejection and three pending choices. See
[expected-failure review evidence](../evaluations/native_review/2026-10-16-failures/README.md).

At that checkpoint, the full goal remained active. Engine migration, remaining language forms,
boundary/resource authoring, deployment qualification, and comparative human
evidence remain unfinished. The external pilot remains pending as requested.

The engine-transition checkpoint adds explicit `migrate` proposals. The CLI
copies and runs an operator-selected trusted previous executable against a frozen
copy of the exact case. A full verified replay is required before current-engine
recapture. Source, target, raw input, and limits remain fixed. Normal replay still
refuses engine mismatch. A wrong executable, forged observation, timeout, or
excessive process output cannot produce a candidate.

Proposals retain both cases, previous replay, executable SHA-256, differences,
and an integrity digest. Migrated cases use schema 3 with immediate-parent
provenance; ordinary captures retain schemas 1/2. Changed observations are explicit,
unavailable candidates retain diagnostics, and `approved` is always false. The
library's I/O-free preparation API requires a trusted caller to obtain the previous
engine response; consistency checking does not authenticate a supplied transcript.

Eight tests bring coverage to 154 integration tests plus three unit tests (157
total). Tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes.
Executable qualification covers 18 transitions over requests, scenarios, failures,
large printed integers, deleted import files, and zero-step budgets. A deliberately
altered qualification engine changes an assertion message: two raw failure
outcomes change, while a passing expected-failure scenario has only evidence
changes. Both previous executables reject forged observations. All produced
candidates replay on the current engine, and supported migrated request cases
generate scenarios successfully. See [migration qualification](../evaluations/native_migration/2026-10-16/README.md).

These are unapproved JSON proposals, not a completed migration review product.
Dedicated migration presentation, saved migration decisions, verified corpus
promotion, and source adaptation across engines remain open. No live corpus was
modified. Remaining language/deployment work and comparative human evidence still
prevent full-goal completion; the external pilot remains pending.

The migration-review checkpoint adds an offline before/after page over a freshly
verified engine transition. It separates outcome/state/evidence differences,
retains exact JSON values, exposes recorded source/operand links, and keeps old
observations readable without compiling old source through the new engine.
Saved choices bind to the complete proposal. Non-pending choices require a
self-reported reviewer and note; unavailable candidates cannot be accepted.

`assess-migration` and `export-migration` rerun the explicit previous executable
and recapture on the current engine before using a saved choice. A changed
proposal invalidates the decision. Only explicit matching acceptance can export
one new case, preserving exact observations and parent provenance. Existing
files are refused. Assessment/export receipts retain decision/proposal/case
identities. This completes a single-case migration review/export path, not bulk
corpus promotion or authenticated approval.

Five tests bring native coverage to 159 integration tests plus three unit tests
(162 total). Tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes.
Eighteen real-engine transitions pass offline Chromium checks for exact downloads,
saved choice round trips, stale/malformed/duplicate/oversized refusal, source
navigation, mobile layout, and no external requests. Fresh CLI assessment matches
one synthetic acceptance, one rejection, one needs-information choice, and fifteen
pending choices. The accepted fixture exports and replays; stale choices and
existing-file overwrites are refused. See [migration review evidence](../evaluations/native_migration/2026-10-16-review/README.md).

The full goal remains active. Bulk corpus promotion, source adaptation, remaining
language forms, boundary/resource authoring, deployment qualification, and
comparative human-benefit evidence remain unfinished. No live corpus was changed,
and the external pilot remains pending as requested.

The whole-corpus migration checkpoint adds explicit engine maps and complete
reconciliation of mixed previous/current engines. Every entry keeps its ID,
label, and order. Current-engine cases must replay exactly and are retained
unchanged; old cases require selected executable replay before recapture.
Missing mappings, corrupted cases, baseline mismatches, and unavailable candidates
remain visible and prevent complete export.

The offline page provides per-case notes/choices, search and status filters,
source/operand evidence, exact report download, and decision save/load. Choices
bind to the full report, including corpus membership and metadata. Fresh
assessment/export reexecutes verification for every entry. Export requires
explicit acceptance of every verified case and creates one separate new corpus;
it cannot silently omit unresolved entries or overwrite the original. Receipts
retain original/new corpus, report, and decision identities.

Six tests bring native coverage to 165 integration tests plus three unit tests
(168 total). Tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes.
Real-executable qualification reconciles a nineteen-entry complete corpus and a
twenty-one-entry incomplete corpus with eleven unavailable entries. Independent
Python hashes verify report/corpus identities. Browser checks cover all forty
entries, exact numbers, saved decisions, invalid/stale coverage, unavailable
acceptance, local operand targets, and mobile layout. A synthetic fully accepted
corpus exports and all nineteen cases replay. Incomplete export, relabeled-case
acceptance, and existing-file overwrite are refused. See [whole-corpus migration
evidence](../evaluations/native_migration/2026-10-16-corpus/README.md).

The full objective is still not achieved. Source adaptation across engines,
remaining language forms and semantic decisions, boundary/resource authoring,
native deployment qualification, and comparative human-benefit evidence remain
unfinished. No live corpus was approved or modified. The external pilot remains
pending as requested.

The packaging/embedding checkpoint found and fixed an actual distribution
failure: Cargo package verification could not find the build script's workspace
ancestor manifest/lockfile. The crate now has self-contained package metadata,
pinned direct dependencies, an included dependency baseline and MIT license,
and a runnable Rust embedding example. Repository-wide integration/performance
harnesses remain in the repository and continue running in CI.

Engine source fingerprint v2 uses package-local source/assets, build script,
actual manifest, and dependency baseline. Cargo manifest normalization deliberately
separates workspace and packaged engine identities; relocation of an unchanged
package preserves identity. Existing cases retain their original profile/schema
and use explicit engine migration. The digest does not identify a host's actual
resolved dependency graph, compiler, target, flags, or executable; qualification
records those relevant build details separately.

Both Rust toolchains verify the Cargo artifact outside the workspace, install the
CLI into a temporary prefix, and compile an unrelated Rust host. The host's
resolved target-specific dependency versions/features match the package baseline.
Fourteen independent request expectations cover exact values and boundary/policy
failures. Two reduced-budget cases and two scenarios bring the recorded total to
eighteen; full observations match CLI replay, and default-budget cases match
CLI run/capture. Four threads share one compiled program for 288 exact repeated
observations. Relocated builds replay all eighteen cases. A retained previous
engine verifies a transition to the package with unchanged observation.

Two tests bring native coverage to 167 integration tests plus three unit tests
(170 total). Tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes.
The local package/host qualification passes on both toolchains on x86_64 Linux.
CI now includes it, without claiming an unobserved remote CI result. Exact
unpublished Cargo artifacts, host observations, lockfiles/graphs, executable hashes,
and migration evidence are retained in the [packaging checkpoint](../evaluations/native_packaging/2026-10-16/README.md).

The full goal remains active. Source adaptation, remaining language semantics
and forms, boundary/resource authoring, production and broader host/target
qualification, editor integration, and comparative human-benefit evidence remain
unfinished. No package was published, and the external pilot remains pending.

The native-editor checkpoint adds a bounded stdin snapshot protocol and an
explicit VS Code Rust mode. It checks unsaved file-backed source and imports
without saving or executing scenarios, retains exact error text, maps UTF-8
spans to UTF-16 editor ranges, and discards obsolete results. Explicit checks
wait through invalidation by edits or save watchers. Native test/run commands
use saved source and preserve exact numeric text in the output channel.

Actual extension-host testing found and fixed an invalidated-check race and a
shutdown disposal error. Default Python-mode testing also found and fixed a
language-client configuration that appended an unsupported `--stdio` argument.
Python remains the default and does not run implicitly in native mode.

Six tests bring native coverage to 173 integration tests plus three unit tests
(176 total). Both supported Rust toolchains pass tests and Clippy; formatting,
five JavaScript tests, and nine Python LSP/service tests pass. VS Code 1.137.0
passes seven native checks with both workspace and packaged executables, and
default Python diagnostics/correction/hover pass. Both toolchains requalify the
unpublished Cargo package, separate host observations, concurrency, and relocated
replay. See the [editor evidence](../evaluations/native_editor/2026-10-16/README.md)
and [native editor setup/protocol](native-editor.md).

The full objective remains incomplete. Native hover, completion, navigation,
formatting, and debugging are still open, along with remaining language forms,
source adaptation, boundary/resource authoring, broader production deployment,
and comparative human-benefit evidence. Native Validate currently means static
checking, not scenario execution or formatting validation. No package was
published or external pilot started.

The semantic-navigation checkpoint adds native hover and go-to-definition using
compiled behavior/request target IDs and binding slots. It retains declaration
types for header hover and follows locals, parameters, returning calls, loops,
projections, request outputs, and expected-failure actions to their actual
binding sites. Same-named branch and behavior locals remain distinct. Unsaved
imports and UTF-8/UTF-16 positions use the checked source snapshot.

Invalid source returns no semantic results; edits or cancellation discard
in-flight navigation. Hover renders source as untrusted text. Table-expanded
contexts stay visible with a 64-result limit; labels and type descriptions are
bounded. Field paths deliberately navigate to their root binding. Type-reference
and individual record-field navigation remain unfinished.

Six tests bring native coverage to 179 integration tests plus three unit tests
(182 total). Tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting and five
JavaScript tests pass. The actual VS Code host verifies unsaved imported return
contracts, local definitions, Unicode cursor mapping, and refusal of stale
definitions after invalid edits, alongside the seven prior native checks.
Rust 1.96.0 packaging/host qualification passes with unchanged independent
expectations. See the [navigation evidence](../evaluations/native_editor/2026-10-16-navigation/README.md).

The full objective remains incomplete. Broader native editor coverage, language
semantics and forms, source adaptation, boundary/resource authoring, production
qualification, and comparative human review evidence remain open. This is
functional navigation evidence, not proof that users understand GWT changes
better. The external pilot remains pending.

The type/field-navigation checkpoint retains compiler-recorded annotation
locations and each expanded scenario's annotation range. Named references in
aliases, fields, contracts, and nested containers navigate to the declared type.
Field access follows the declared origin through aliases, nested records,
copied locals, returning calls, request outputs, loops, and projections. Equal
record shapes do not create false declaration matches. Root tokens still point
to their bindings; inferred mixed lists without one declared origin explicitly
fall back to that binding. Runtime structural compatibility remains unchanged.

Six new tests bring native coverage to 185 integration tests plus three unit
tests (188 total). Both Rust toolchains pass the workspace tests and Clippy;
formatting and the JavaScript checks pass. Eleven actual VS Code checks cover
the previous authoring flow plus imported type/field targets and invalidation
after an unsaved imported field edit. The Rust 1.96.0 Cargo artifact is separately
qualified with the independent host expectations and exercised in VS Code.
See [type/field evidence](../evaluations/native_editor/2026-10-16-type-navigation/README.md).

The full goal remains incomplete: native completion, formatting, debugging,
error-tolerant navigation, remaining language semantics/forms, source adaptation,
boundary/resource authoring, broader production qualification, and comparative
human understanding/review evidence are still open. This checkpoint establishes
declaration-link correctness on the tested cases, not a measured human benefit.
The external pilot remains pending; no package was published.

The native-formatting checkpoint adds a Rust source-only formatter and explicit
file preview/check/write commands. It preserves expression/literal spelling,
call grouping, statement order, and quote-aware table values while normalizing
layout. Uniform LF/CRLF is retained. It validates layout before and after
formatting, permits request fragments with external DTOs, and does not resolve
imports, type-check expressions, or execute source. Output growth, physical line
count, and table width have explicit limits.

VS Code formats unsaved and untitled buffers with undo/redo support, without
saving. Version/digest checks discard stale edits. File write mode validates
before creating a temporary replacement, preserves permissions, and checks
source bytes again before rename. Invalid source, symlink file entries, and
changed read-only files are refused; concurrency protection is best effort.

Eight tests bring native coverage to 193 integration tests plus three unit tests
(196 total). Both toolchains pass the workspace suite and Clippy; formatting and
JavaScript checks pass. Tests cover exact independent values, quoted pipes/hashes,
grouped arguments, failure order, five native workflow comparisons, CRLF spans,
resource refusal, and CLI effects/permissions. All six native example files
already pass native format checking. Fourteen actual VS Code checks pass with
workspace and packaged executables, including formatting, undo/redo, stale
responses, invalid-layout refusal, and untitled buffers. Rust 1.96.0 packaging
and the independent host qualification pass. See [formatting evidence](../evaluations/native_editor/2026-10-16-format/README.md)
and [native formatting rules](native-formatting.md).

The full objective remains incomplete. Native completion and debugging,
error-tolerant navigation, remaining language decisions/forms, source adaptation,
boundary/resource authoring, production qualification, and comparative human
understanding/review evidence remain open. At that checkpoint, native Validate
still used static checking, separate from formatting and scenario execution. No external pilot
was started or package published.

The combined-validation checkpoint adds `gwt validate` and typed library
APIs over one captured import closure. Reports distinguish loading, static
checking, formatting, and scenario execution, with explicit failed, skipped, and
unexercised states. Zero scenarios fail by default; an explicit declaration-only
exception preserves the `notExercised` status. Formatting failures do not stop
scenarios, and scenario failures do not stop later scenarios. Compact results
release execution traces between scenarios; full traces remain available through
run/test. Reports record the compiled source identity and per-execution budgets.

VS Code Validate now saves dirty open GWT files and invokes the complete native
workflow. Check retains unsaved static checking. Integration exposed and fixed
a formatter issue that incorrectly counted module imports as implicit scenario
steps before explicit scenarios.

Seven tests bring native coverage to 200 integration tests plus three unit tests
(203 total). Both Rust toolchains pass the workspace suite and Clippy; formatting
and JavaScript checks pass. All six native example files pass validation across
28 scenarios. Sixteen actual editor checks pass with workspace and packaged
executables. Rust 1.96.0 package/host qualification passes, including 18 independent
observations, 288 concurrent executions, and 18 relocated replays. See
[validation rules](native-validation.md) and the
[checkpoint evidence](../evaluations/native_editor/2026-10-16-validation/README.md).

The full objective remains incomplete. Completion/debugging, error-tolerant
navigation, remaining language decisions/forms, source adaptation,
boundary/resource authoring, broader production qualification, and comparative
human understanding/review evidence remain open. Passing scenarios do not
establish assertion coverage or a measured human benefit. The external pilot
remains pending; no package was published.

The validation-evidence checkpoint exposes what each embedded scenario checked.
The compiler retains the indices of scenario/background THEN expectations,
including AND continuations and expanded rows, separately from behavior
requirements, request postconditions, and WHEN assertions. Validation records
each expectation's source span, kind, outcome, and scenario-local event ID.
Missing results are explicitly `notObserved`: they can reflect interrupted
evaluation or exhausted budgets as well as an earlier failure.

A declaration inventory counts recorded behavior/request entries and distinct
scenarios entering each declaration, including imports and nested/repeated calls.
These are entry observations, not claims of successful completion or branch
coverage. Warnings identify scenarios without expectations, expectations without
recorded results, and declarations without recorded entries. They leave the
language and validation exit policy unchanged. VS Code distinguishes successful
validation with evidence gaps through a warning notification and output details.

Eight new tests bring native coverage to 208 integration tests plus three unit
tests (211 total). Both toolchains pass the suite and Clippy; formatting and
JavaScript checks pass. Six examples pass across 28 scenarios and 68 recorded
expectations. The delivery example correctly reveals that its embedded scenarios
call the behavior without entering its request; independent host tests exercise
that request separately. Seventeen actual editor checks pass with workspace and
packaged executables. Rust 1.96.0 package/host qualification passes. See the
[evidence checkpoint](../evaluations/native_editor/2026-10-16-validation-evidence/README.md)
and [validation report contract](native-validation.md).

The full goal remains incomplete. This inventory supplies factual review context;
it does not assess assertion quality, branch/input coverage, or human comprehension.
Remaining language decisions/forms, source adaptation, boundary/resource
authoring, editor capabilities, production qualification, and comparative human
review evidence remain open. No external pilot was started or package published.


The offline-validation-view checkpoint adds an immutable validation document
pairing the report with its captured source, plus `validate --html NEW_REPORT.html`.
Reviewers can inspect each gate, search/filter scenarios, see expectation results
and evidence gaps, inspect recorded call entries, and open highlighted captured
source. UTF-8/CRLF spans and example template locations are preserved. Exact
report/source JSON downloads are available; a load failure cannot invent source
or exercised scenarios. Output creation refuses existing paths. Rendering does
not reload files or execute source, and escaped serialization is bounded to
64 MiB. The report contains summaries rather than full execution traces or
approval controls.

Six integration tests and one serialization unit test bring the native total to
218 (214 integration and four unit tests). Both toolchains pass tests and Clippy;
formatting, JavaScript syntax, and whitespace checks pass. Seven report fixtures
pass nine browser interaction groups at desktop and 390px widths, offline with
no script errors or network requests. Visual inspection led to stacked mobile
declaration rows and clearer warning text. The independently installed Rust
1.96.0 Cargo artifact generates reports that pass the same browser checks;
package/host qualification also passes. See the
[qualification and delivery report](../evaluations/native_validation/2026-10-16/README.md).

The full goal remains incomplete. This adds a reviewable presentation of actual
checks and their limits; it does not demonstrate better human comprehension or
review outcomes. Remaining language decisions/forms, source adaptation,
boundary/resource authoring, editor capabilities, broader deployment
qualification, and comparative human evidence remain open. The external pilot
remains pending, and no package or site was published.

The typed-setup-table checkpoint adds readable record collections through
`GIVEN items are Record` and explicit existing record fields. Aliases, checked
expression cells, omitted optional columns, and header-only empty tables have
documented semantics. Every row is checked and normalized, with source-linked
cell dependencies; assignment occurs only after the complete list succeeds.
Row, step, value, and evidence failures cannot publish a partial collection.
The formatter, expanded-example source maps, editor navigation, explanations,
and default review trail understand the new initialization forms.

Nine table tests and one editor provenance test bring the native total to 228
(224 integration and four unit tests). Both toolchains pass tests and Clippy.
Seven native examples pass across 31 scenarios and 71 expectations. The receiving
example also passes Python validation. Eighteen actual VS Code checks pass with
workspace and packaged executables; package/host qualification passes. Packaged
capture/replay and comparison verify totals 6, 4, and 0, and isolate a deliberate
changed quantity to one failed scenario with total 7. Its review page passes
desktop/mobile checks for visible row/assignment evidence and operand navigation.
See [table semantics](native-setup-tables.md) and the
[checkpoint evidence and review](../evaluations/native_editor/2026-10-16-setup-tables/README.md).

The full goal remains incomplete. Typed tables supply a prerequisite used by
the existing language-tour and order-fulfillment request files; separate native
GWT request-file execution is the next host-boundary gap, not part of this
checkpoint. Remaining language forms, source adaptation, boundary/resource
authoring, editor capabilities, deployment qualification, and comparative human
evidence remain open. No external pilot was started or package published.

The readable-request-entry checkpoint makes a sole source entry directly
runnable and capturable, with the same selection API available to Rust hosts.
Entries explicitly import rules through `USE`; their setup, public calls, and
expectations use the existing checked scenario model. This deliberately keeps
the dependency visible instead of reproducing Python's externally paired
request-file convention. Zero or multiple scenarios require explicit selection;
imported scenarios do not execute. Exact source bundles and the existing scenario
case format support frozen replay and review without source rewriting. The entry
result is its full state; explicit JSON requests retain declared-output results.

Six integration tests bring the native total to 234 (230 integration, four unit).
Both Rust toolchains pass tests and Clippy. Nine examples validate across 37
scenarios and 131 expectations. The order-fulfillment entry also validates in
Python and matches independently expected fulfillment/inventory values. Nineteen
actual VS Code checks pass with workspace and packaged executables, including
direct entry execution after saving imported rule edits. Package/host qualification
passes. Packaged capture/replay and comparison preserve input source while
detecting an expedited fee change from 19.5 to 20.5 through the existing expectation.
See [request entry semantics](native-request-entries.md) and the
[qualification and review artifacts](../evaluations/native_editor/2026-10-16-request-entries/README.md).

The full goal remains incomplete. Readable native request execution is now
available through explicit source dependencies. The language tour still requires
unsupported lowercase collection operations; one-of records, other documented
language decisions/forms, source adaptation, boundary/resource authoring, editor
capabilities, broader deployment, and comparative human evidence remain open.
The external pilot remains pending; no package or site was published.

The first-match source-adaptation checkpoint revises the language tour to use
one existing `FIND ... ELSE` step. It preserves the public expense request and
output contracts while exposing matched/missing handling and clearing reused
decision state. The tour now has eight embedded scenarios with 72 expectations,
plus a direct native request entry with nine expectations. No language or engine
implementation change was needed.

Original Python, revised Python, and the previously qualified packaged Rust
engine match independent expectations on 436 integer-domain probes. Incorrect
inclusive-limit and non-reimbursable handling mutations are detected on 100 and
140 probes respectively. Nine captured Python cases reconcile with no output or
failure changes and nine changed execution paths. Their review passes offline
desktop/mobile case-selection, filter, and search checks. Three native tests add
explicit expected decisions, reused-state fault detection, source explanations,
replay, and a boundary comparison. Both Rust toolchains pass all 237 tests and
Clippy; all 614 Python tests pass. The Python example runner now explicitly
assigns the three deliberately incompatible native examples to their existing
Rust suites instead of attempting Python execution. All example formatting and
shared-example Python coverage remain required.

This is one verified manual source adaptation, documented with its conditions
and limits in [native-source-adaptation.md](native-source-adaptation.md) and the
[qualification and refactor review](../evaluations/language_tour/2026-10-16/README.md).
It does not establish general migration correctness, numeric equivalence outside
the tested domain, faster execution, or measured human readability. Legacy
collection forms remain a separate design decision; the tour no longer depends
on them. One-of records, other remaining language forms, broader source
adaptation, boundary/resource authoring, editor capabilities, deployment, and
comparative human evidence keep the full goal incomplete. No external pilot or
publication was performed.

The one-of contract checkpoint adds closed tagged records to native input/output
contracts, explicit source setup, and nested/list/optional values. Only the
selected kind's fields are admitted. Common fields with identical types remain
accessible; the discriminator cannot be independently mutated or shared as a
mutable argument. Whole-value replacement preserves a complete valid payload.
Capture/replay, generated scenarios, formatting, and editor type references
support these contracts.

Seven contract tests and one editor provenance test bring the native total to
245 (241 integration, four unit). Both Rust toolchains pass tests and Clippy;
all 614 Python tests pass. Twenty actual editor checks pass with the workspace
and final packaged executables. Package qualification passes independent identity
and dependency checks, 18 host observations, 288 concurrent executions, and 18
relocated replays. The three contact scenarios have eight passing expectations.
Packaged runs reject an extraneous payload field before execution, replay both
kinds, and detect a deliberately changed email route while retaining the phone
outcome. See [one-of contract semantics](native-one-of.md), the
[contact example](../examples/native_one_of/README.md), and
[checkpoint evidence](../evaluations/native_editor/2026-10-16-one-of-contracts/README.md).

The full goal remains incomplete. This is the one-of value foundation;
kind-specific field access, exhaustive `DEPENDING ON` branches, and alias-safe
narrowing still need implementation. Those are the next language work, followed
by broader domain pressure tests. Other remaining language decisions, source
adaptation, boundary/resource authoring, editor capabilities, deployment, and
comparative human evidence remain open. No external pilot or publication occurred.

The exhaustive-kind-dispatch checkpoint adds native `DEPENDING ON path` with
scoped payload narrowing. Every declared kind must have a branch or be covered
by a final `ELSE`; unknown, repeated, missing, and unreachable branches receive
diagnostics. Nested paths and collection item bindings work, and exhaustive
branches participate in return checking. The runtime guards the active subject's
kind across shared aliases and containing-record replacements, while permitting
payload edits and same-kind replacement. Guards release on completion, return,
and caught failure. Branch evidence records the actual and candidate kind and
links to a single subject evaluation.

Eleven new tests bring the native total to 256 (252 integration, four unit).
Both Rust toolchains pass tests and Clippy; all 614 Python tests pass. Twenty-one
actual editor checks pass with workspace and packaged executables. Package
qualification verifies independent identity/dependency checks, 18 host
observations, 288 concurrent executions, and 18 relocated replays. Three new
delivery scenarios contain six expectations. The packaged executable routes and
replays email, SMS, and pickup inputs and isolates a deliberately changed email
destination. Desktop/mobile browser checks verify visible kind decisions and
operand navigation. See [kind semantics](native-one-of.md), the
[delivery example](../examples/native_kind_dispatch/README.md), and the
[verification record](../evaluations/native_editor/2026-10-16-kind-dispatch/README.md).

The full project goal remains incomplete. Exhaustive kind dispatch and scoped
payload access now work; scalar-value dispatch, `IF` narrowing, branch-specific
field navigation, and broader domain pressure tests remain. Other language
decisions, source adaptation, boundary/resource authoring, editor capabilities,
deployment qualification, and comparative human evidence also remain open. No
external pilot or publication occurred.

The shared-MiniLang checkpoint exercises kind dispatch in a larger ordered AST
workflow. Its dispatcher now passes explicit payload fields into typed helpers,
removing their implicit assumptions about generic one-of statements. Both engines
use one `engine.gwt`; Python and native entries retain their supported setup
syntax and each provide two scenarios with 15 expectations. Public request and
output contracts are preserved. This is a source adaptation with no engine change.

Original Python, revised Python, and the qualified packaged Rust engine match an
independent host model on 943 integer-domain probes, including all 720 statement
orderings and 125 arithmetic combinations. Inclusive-threshold and triple-map
faults are detected seven and 126 times respectively in their 126-probe mutation
set. Five captured Python cases show no output/failure changes, four path changes,
and one unchanged case. Five native captures replay; an intentional boundary
revision changes only the equality case. Both review pages pass desktop/mobile
interaction checks. Three native regression tests bring the total to 259 on both
toolchains, with Clippy passing; all 614 Python tests pass. The reused packaged
binary and all 47 implementation/build inputs match their prior qualification.
See [the source adaptation](native-minilang-adaptation.md) and
[its probes and review artifacts](../evaluations/minilang/2026-10-16/README.md).

The full goal remains incomplete. Separate setup fixtures require coordinated
maintenance, and the long threshold-helper signature motivates further design
work on kind-specific contracts; no human readability benefit is claimed.
Fractional-number equivalence, general source migration, the larger MiniLang 2
workflow, remaining language decisions, boundary/resource authoring, editor
capabilities, deployment qualification, and comparative human evidence remain
open. No external pilot or publication occurred.

The kind-specific-contract checkpoint adds type expressions such as
`TYPE ThresholdStatement is MiniStatement of kind if_add_gt_print`. Helpers can
state their payload requirements and accept a proven narrowed value directly.
The tag and payload remain intact, shared state keeps exact type requirements,
and existing dispatch guards protect specialized helpers from kind-changing
writes through other aliases. Selected contracts also work at request boundaries
and in containers. Editor navigation resolves their base, kind tag, and payload
fields through aliases and imports. Python formatting preserves the native form
without enabling it in Python execution.

Five contract tests and one editor test bring native coverage to 265 tests on
each toolchain, with Clippy passing; all 615 Python tests pass. Twenty-two actual
editor checks pass with workspace and packaged executables. Package qualification
passes independent identity/dependency checks, 18 host observations, 288 concurrent
executions, and 18 relocated replays. The new expression example validates five
scenarios and ten expectations. A packaged email-only request rejects another
kind before execution.

The larger MiniLang experiment replaces explicit scalar payload calls with named
kind contracts. Both native revisions match the independent oracle and each other
on all 943 probes, including all 720 statement orderings. Both scenario entries
pass 15 expectations; five captured cases replay and compare with unchanged
outcomes/state. Its threshold call becomes `compare sum statement into runtime`.
The candidate is a frozen experiment; the shared engine remains the cross-engine
reference fixture. See [kind contracts](native-one-of.md#kind-specific-contracts),
the [expression example](../examples/native_kind_contracts/README.md), and the
[verification and MiniLang review](../evaluations/native_editor/2026-10-16-kind-contracts/README.md).

The full goal remains incomplete. This addresses the mechanical need for long
payload calls; it does not prove a human readability gain. Scalar-value dispatch,
`IF` narrowing, general branch-field provenance, broader workflows, other language
decisions, boundary/resource authoring, editor capabilities, deployment, and
comparative human evidence remain open. No external pilot or publication occurred.

## Human source-review study kit (2026-10-16)

Added a local operational prerequisite for the human-understanding objective:
[`evaluations/human_review/`](../evaluations/human_review/README.md) and the
[study protocol](human-review-study.md). The previous turn only reconfirmed the
goal document's location and made no implementation progress; this turn adds
review tasks, collection/scoring tools, and executable qualification evidence.

The kit contains complete matched GWT/Python baseline, correct, and faulty
sources across refund, delivery, expenses, and inventory. Sixteen balanced
assignment groups vary domain order, language, and candidate validity without
showing one reviewer the same domain twice. Public packets withhold answer keys;
source and question identities are frozen. The offline page captures profile,
actual-output predictions, recommendations, explanations, confidence, wall and
active times, skips, partial work, and completed downloads. Explicit pauses
hide the task, and hidden-tab time is excluded from active time.

The scorer rejects mismatched identities, invalid timing/status sequences, and
duplicate snapshots. Missing enrolled sessions remain in planned denominators;
rehearsal data is separated from participant observations. Correct decisions do
not become claims of defect recognition: rationale assessment remains manual.
The protocol records allocation, source-only assistance conditions, prior
exposure/familiarity, attrition, interpretation limits, and the separate scope
of later workbench and adoption studies.

[Qualification evidence](../evaluations/human_review/2026-10-16/README.md):
1,305 executions across independent integer-domain expectations and all three
engines matched. All 12 GWT fixtures passed formatter/checker checks. Offline
Chromium 153 desktop/mobile rehearsals passed required fields, exact source
rendering, partial/final export, skipping, explicit pause timing, and simulated
visibility overlap, without external requests or script errors. Four captured
screenshots were inspected. All 621 Python tests passed, including six new
study tests; `git diff --check` passed. No runtime implementation changed.

**There were zero human participants.** Automated scores and times demonstrate
the apparatus, not GWT's comparative value. Representative users, a frozen
actual study enrollment/analysis plan, manual adjudication, and broader
workflow/deployment evidence remain missing. No external pilot was initiated.
The full project goal remains active and incomplete.

## Scalar-value dispatch and explicit Run reliability (2026-10-16)

The previous goal turn made concrete progress by building and qualifying the
human-review kit. This turn advances intentional native semantics and executable
behavior: [`DEPENDING ON` scalar cases](native-value-dispatch.md) now accept
literal text, boolean, and exact numeric labels, with finite boolean/text-union
coverage or an explicit fallback. Subject expressions evaluate once; branch-body
mutation does not dispatch again or narrow a mutable path's contract. Numeric
matching deliberately follows native `==`, so representation differences such
as `1` versus `1.0` do not become implicit domain categories. Duplicate equal
values and impossible branches are rejected before execution. Migration guidance
explains how to model a meaningful category explicitly rather than inheriting
Python's type-sensitive dispatch convention.

The parser/checker/runtime, return analysis, source remapping, editor navigation,
explanations, and default review trail support the new statement. The focused
[delivery-response example](../examples/native_value_dispatch/README.md) has six
scenario rows and 18 top-level expectations. Independent tests cover 30 valid
policy combinations, two invalid attempts, exact numeric boundaries, coverage,
scopes/returns, aliases, collection guards, budgets, replay, revision comparison,
generated scenarios, and original Unicode/CRLF source evidence. An older
kind-return negative test was also repaired after inspection found reversed
source/file arguments. The semantic overview's stale statement that one-of
records were unsupported was corrected.

[Checkpoint evidence](../evaluations/native_editor/2026-10-16-value-dispatch/README.md):
274 native tests pass on both Rust 1.85.0 and 1.96.0 with clean Clippy; all 621
Python tests pass. Example formatting/checking, reference request workflows,
Rust formatting, extension syntax/five unit tests, and whitespace checks pass.
The new package passes 18 independent host observations, 288 concurrent
executions, and 18 relocated replays. Six packaged delivery cases verify and
compare; changing the second retry delay affects exactly two outcomes, with no
baseline mismatch, unavailable case, or candidate failure. Offline desktop/mobile
browser checks and two inspected screenshots confirm visible scalar decisions,
case filtering, and operand navigation.

Actual VS Code qualification exposed a save-watcher race in explicit Run's
preflight check. The adapter now keeps that check separate from cancellable
background diagnostics while retaining source-digest validation. A delayed
executable exercises saving and preflight together; the final installed-engine
editor run passes all 23 checks. The failed first installed attempt and diagnosis
are retained in the checkpoint rather than reported as success.

This does not establish human readability gains or complete language/deployment
support. The full objective remains active; real participant evidence and the
other audited gaps still require work. No outside maintainer was contacted and
no release or external pilot was initiated.

## Optional presence in behavior branches (2026-10-16)

The immediately preceding goal turn only reconfirmed the goal document and was
no progress toward its implementation. This continuation inspected the pending
presence implementation and its test/package/editor evidence, completed visual
inspection, verified all 48 archived implementation/build inputs against the
workspace, and finished the checkpoint record. The implementation extends native
presence proofs from short-circuit expressions into `IF` and `DECIDE` bodies;
later `DECIDE` conditions can rely on earlier absence checks having failed.
People can handle missing policy or receipt data explicitly, then read the
present records without additional extraction conventions.

The checker narrows only the guarded source path. Runtime guards prevent aliases
or ancestor replacement from invalidating a live proof, while allowing another
present value. Exact shared contracts remain enforced; copied/returned records
can cross their original optional boundary. Scope cleanup covers return and
failure as well as normal exit. Zero, false, and empty text are present values.
See [presence semantics](native-presence.md) and the
[reimbursement example](../examples/native_presence/README.md).

[Checkpoint evidence](../evaluations/native_editor/2026-10-16-presence/README.md):
285 Rust tests pass on each of 1.85.0 and 1.96.0, with clean Clippy. Ten presence
test groups include 80 independent policy combinations, two invalid inputs,
alias protection, copies/returns, nested scopes, budgets, Unicode/CRLF evidence,
replay, and generated scenarios. The example has six scenarios and 18 top-level
expectations; its boundary mutant changes nine probe outcomes. All 621 Python
tests and 24 installed-engine VS Code checks pass. Package qualification passes
18 host observations, 288 concurrent executions, and 18 relocated replays.
Eight packaged policy cases verify; the boundary revision changes exactly two
of these cases. A separate forbidden alias write is captured and replayed.
Offline desktop/mobile browser checks and inspected screenshots confirm visible
presence decisions, correct filtering, and operand navigation.

Python accepts the example's formatting and static checks but fails its nested
optional record execution. That reference limitation and the initially failing
JSON smoke check are retained. The Python smoke loop now uses the existing
native-only example registry; both affected native JSON request fixtures have
direct Rust expected-output tests. Passing native checks do not imply Python
execution compatibility.

The full goal remains incomplete. Broader flow refinement, remaining intentional
language decisions, editor and deployment work, and comparative human evidence
remain open. Local UI and engine evidence does not prove a readability benefit.
No external pilot, participant recruitment, or publication occurred.

## Kind proofs in ordinary conditions (2026-10-16)

The previous goal turn made concrete progress by completing the presence
verification record. This turn extends deliberate semantics so a rule can
combine a kind with a domain condition, for example
`contact.kind == "sms" and contact.opted_in`, and safely read that payload.
[Kind proofs](native-kind-conditions.md) apply to short-circuit expressions,
`IF`/`ELSE`, and ordered `DECIDE` branches. The compiler retains conservative
sets of possible kinds; runtime guards prevent aliases and ancestor replacement
from invalidating them. Multi-kind proofs permit replacements within the proven
set, while exhaustive kind dispatch retains its selected-kind protection.
Existing presence, traversal, shared-contract, return, and failure rules compose
with these proofs.

The [contact policy](../examples/native_kind_conditions/README.md) handles
missing contact data, email confirmation, SMS consent, and pickup permission.
Writing its seven scenarios exposed a source-setup gap: nested optional record
initializers were rejected despite equivalent JSON input being valid. An explicit
record body now constructs a present value under the inner closed contract;
optional scalars still reject such bodies. No new grammar tokens were added.

[Checkpoint evidence](../evaluations/native_editor/2026-10-16-kind-conditions/README.md):
295 Rust tests pass on each toolchain with clean Clippy; all 621 Python tests
pass. Nine new test groups cover 22 independent contact inputs, seven scenarios
with 21 expectations, alias/ancestor protection, multi-kind replacements,
copies/helpers, collection items, returns/failures, budgets, Unicode/CRLF evidence,
replay, and generated scenarios. Reversing consent changes exactly eight probe
outcomes. Package qualification passes 18 host observations, 288 concurrent
executions, and 18 relocated replays. Eight packaged policy cases verify, and
the consent revision changes exactly three of them. A forbidden alias write is
captured/replayed. Offline desktop/mobile checks and inspected screenshots pass
case selection, filtering, condition evidence, and operand navigation.

All 25 installed-engine VS Code checks pass after correcting a test assertion
to decode the editor's escaped hover text; the failed first run is retained.
Kind-refined payload hover has the checked type, but field declaration provenance
still falls back to the known binding. The test explicitly verifies that limit.
Python formatting/checking accept the contact example, but Python execution
rejects its nested optional payload; that reference limitation is recorded.

The goal remains incomplete. This makes a common domain-rule form executable
and reviewable, but supplies no participant evidence of better understanding.
Broader flow refinement, field provenance, remaining language decisions, editor
capabilities, deployment qualification, and comparative human evidence still
require work. No external pilot or publication occurred.

## Field navigation through checked kind proofs (2026-10-16)

The previous goal turn made concrete progress by implementing and qualifying
kind conditions. This turn closes the unique-field navigation gap it exposed:
the editor now follows a kind-refined read or mutation path to the corresponding
payload declaration. Checked kind alternatives are retained at each path prefix
and combined with the original declaration identity, including aliases, optional
ancestors, nested one-of records, copies, and collection items. Structural type
equality does not merge declaration targets. Expanded scenarios keep separate
kind facts and contexts at their shared template location.

When several possible kinds or mixed declaration origins leave a field ambiguous,
the editor retains the known binding fallback. Root-name selections still point
to their bindings. This is source declaration provenance, not runtime value
history, and it does not add syntax or change execution rules.

[Checkpoint evidence](../evaluations/native_editor/2026-10-16-branch-navigation/README.md):
301 Rust tests pass on each toolchain with clean Clippy; all 621 Python tests
pass. Eighteen type/navigation tests include six new branch/nesting/copy/ambiguity/
example groups. All 26 installed-engine VS Code checks pass, including switching
between equal-shaped email/phone payload declarations and moving unsaved imported
definitions across Unicode/CRLF source. Package qualification passes 18 host
observations, 288 concurrent executions, 18 relocated replays, and an explicit
previous-engine transition. All 48 archived implementation/build inputs match
the workspace. Sixteen full captured observations—nine requests including a
guard failure, plus seven scenarios—are identical between the previous and new
engines. Original cases remain unchanged; migration proposals were not approved.

The full project goal remains active. This supplies a concrete reading/editing
capability and tested preservation of execution for the captured cases, but no
participant evidence of improved understanding. Remaining work includes broader
flow semantics, ambiguous navigation and invalid-edit support, completion and
debugging, deployment qualification, and comparative human evaluation. No external
pilot, participant recruitment, release, or publication occurred.

## Release binaries and deployment boundaries (2026-10-16)

The preceding goal turn made concrete progress on branch-specific navigation.
This turn advances adoption/deployment and separately measured performance:
the package harness now qualifies both development and release profiles, and
release qualification produces a standalone local GNU/Linux binary bundle.
The bundle includes its license, example, manifest, and archive checksum;
extraction checks all file identities and paths before writing and refuses
overwrites. The executable runs the example and all captured host cases with an
empty command path. Rust or Python installation is unnecessary for those
executable operations.

[Release evidence](../evaluations/native_packaging/2026-10-16-release/README.md):
301 native tests pass in release mode on both 1.85.0 and 1.96.0. Each release
package passes 18 independent host observations, 288 concurrent executions,
18 relocated source-build replays, and 18 extracted-binary replays. Both release
toolchains preserve all 18 complete development host records/cases. All three
source archives match the workspace's 48 implementation/build inputs. All 627
Python tests pass, including six archive-verification groups. The extracted
release executable passes 26 actual editor checks. CI is configured for both
toolchains and profiles; no hosted run or publication is claimed.

Both binaries pass the example and all 18 replays in GLIBC 2.39 and 2.41
containers. A GLIBC 2.36 container fails at the loader because the current build
requires `GLIBC_2.39`; this is retained as an incompatibility. Image identities,
loader diagnostics, and executable dependencies are recorded. Containers use
the host kernel. Older GLIBC, musl/Alpine, other targets, and production rollout
remain unqualified; a target triple is not proof of portability.

Separate fresh-process measurements compare development and release binaries
on invoice, contact, and fulfillment workloads, preserving every full observation.
Two alternating-order passes per workload contain 30 samples per profile; peak
RSS uses separate invocations. Release medians span about 0.8–3.6 ms, versus
1.8–12.8 ms for development builds on this shared host. Those timings include
loading, checking, execution, complete evidence, and JSON output. They do not
isolate startup, clear filesystem caches, establish throughput, compare
languages, or measure human benefit. Raw timings, memory readings, source/input
snapshots, independent expectations, and observation identities are retained.

The full goal remains active. These local artifacts and compatibility findings
advance deployment without claiming general production readiness. Broader
language/tooling decisions, target/host qualification, and actual comparative
human evidence still require work. No external pilot was initiated.

## Static Linux deployment qualification (2026-10-16)

The preceding goal turn confirmed the existing goal document but made no
implementation progress. This turn revalidated the known GNU release loader
failure and addressed that deployment gap with a separately qualified static
musl build. The project goal and its completion criteria remain unchanged.

The package harness now carries an explicit target through source verification,
tests, embedding, installed CLI, consumer dependency/feature checks, and relocated
builds. Musl builds use the selected compiler's bundled linker by default.
Release bundling verifies actual ELF linkage; both resulting executables have
no interpreter, required shared libraries, or GLIBC version symbols. Build
identities retain target settings independently from engine source identity.
CI is configured for release musl qualification on both supported toolchains;
no hosted run is claimed.

[Static deployment evidence](../evaluations/native_packaging/2026-10-16-static/README.md):
301 native release tests and warning-free Clippy pass on each Rust version.
Each package passes three library tests, two embedded scenarios, 18 host
observations, 288 shared-program executions, 18 relocated replays, and 18
extracted-binary replays. All 18 full host records equal the previous GNU release,
including budget failures and execution evidence. Both static binaries pass
Alpine (musl 1.2.5) and GLIBC 2.36, 2.39, and 2.41 containers with no networking,
a read-only filesystem, and empty PATH. The GNU regression still records the
GLIBC 2.36 loader failure. All 627 Python tests, five extension unit tests, and
26 actual editor checks pass. All three source archives match the workspace's
48 implementation/build inputs.

This removes the observed shared-library obstacle for the tested static builds.
Containers share the host's Linux 7.2.4 kernel: older kernels, other architectures,
Windows/macOS, production rollout, and comparative human benefit remain
unverified. No public release, external pilot, or participant recruitment occurred.
The full goal remains active.

## Sequential REQUIRE proofs (2026-10-16)

The preceding goal turn made concrete progress on static Linux deployment.
This turn advances intentional semantics and the readable behavior workflow:
successful REQUIRE steps establish supported optional-presence and one-of-kind
facts for the remaining steps in their containing body. Existing boolean proof
rules are reused; no new grammar was added. Ordinary THEN expectations do not
introduce new facts. Branches, loops, calls, and caught failures retain their
lexical checking boundaries.

Runtime guards protect the proven state addresses against invalidating aliases
and ancestor writes. Values can still change within the proven set. Normal exit,
return, and failure remove only the body's own proofs. Focused tests found an
output-boundary mismatch caused by narrowing request state; retaining the
original declared binding type fixes it without widening OUTPUT contracts.
Editor payload navigation and hover retain the selected declaration after
sequential assertions, including copied values and unsaved imported types.

[Qualification evidence](../evaluations/native_editor/2026-10-16-require/README.md):
310 native tests and warning-free Clippy pass on both Rust versions; the full
310-test static musl release suite also passes on both. Eight new
semantic test groups cover 24 independently expected transfer inputs, seven
scenarios with 14 expectations, alias/ancestor mutation, scope cleanup, exact
contracts, source mapping, budgets, replay, and generated scenarios. Removing
bank verification changes exactly two corpus outcomes; the review retains all
24 cases, including 20 remaining candidate assertion failures. A nineteenth
editor type/navigation test and the 27-check actual VS Code run cover sequential
proofs. All 627 Python tests, example formatting, top-level checks, reference
workflows, and five extension unit tests pass.

The static release package passes its library/host checks, 288 concurrent calls,
relocated/binary replays, and Alpine/GLIBC 2.36 runtime checks. All 48 archived
implementation/build inputs match the workspace. Eighteen full invoice
observations are preserved, with an explicit prior-engine transition. A separate
retained migration records the intentional change from successful alias clearing
to presence_mutation after REQUIRE; the prior case is unchanged and the candidate
replays exactly. That proposal is unapproved. Source compatibility is not inferred
from the preserved invoice corpus.

The full goal remains active. Assertions now support more direct validation
steps, but this is not comparative human evidence. Proofs after early-return
conditions or collection filters, remaining native forms, broader tooling and
production qualification, and actual participant evidence remain open. No public
release or external pilot was initiated.

## Collection filter proofs (2026-10-16)

The preceding goal turn made concrete progress on sequential REQUIRE proofs.
This turn extends those intentional semantics to FOR/FIND filters: a true
WHERE condition refines the selected body using supported presence/kind facts.
Guards protect actual item or surrounding-state addresses until that body exits.
They release per iteration, return, and failure without releasing outer guards.
Skipped bodies and FIND fallbacks gain no filter facts. Predicates continue to
read live state; ordinary boolean truth is not frozen by a type proof.

[Qualification evidence](../evaluations/native_editor/2026-10-16-filter-proofs/README.md):
319 native tests pass on both Rust versions in development and static musl
release modes, with warning-free Clippy on both. Eight new semantic groups cover
57 independently expected ordered pickup queues, five scenarios with 15
expectations, optional scalar/items/fields, alias and ancestor writes, allowed
kind sets, helper contracts, external proofs, live state, cleanup, returns,
caught failures, source evidence, replay, generated scenarios, and step budgets.
Removing readiness changes exactly 14 review outcomes; all 57 cases reconcile
without unavailable entries or baseline mismatches. Twenty editor type/navigation
tests and 28 actual VS Code checks include optional item payloads, copies,
FOR/FIND definitions, and exact unsaved-filter diagnostics. All 627 Python tests,
example formatting, top-level checks, reference workflows, and five extension
unit tests pass.

The static package passes its host/concurrency/relocation checks and Alpine/GLIBC
2.36 runtime replays. Its 48 source/build inputs match the workspace, and 18
complete invoice observations match the previous engine. A separate old/new
migration records the deliberate incompatibility: a filter-proven value can no
longer be cleared through a wider traversal alias while its selected body runs.
The old case is unchanged, the new failure replays exactly, and the proposal is
unapproved. An initial temporary-filesystem quota failure was retained and
resolved by rerunning in new main-filesystem scratch directories after the
failed processes terminated; existing artifacts were preserved.

The full goal remains active. This supports more direct collection behavior
steps without introducing query pipelines, but it does not prove better human
understanding. Early-return proof flow, remaining native forms, broader tooling,
production qualification, and actual participant evidence remain open. No
external pilot or public release occurred.

## Early-return continuations and source adaptation (2026-10-16)

The preceding goal turn made concrete progress on collection filter proofs.
This turn supports more direct returning behavior: IF/DECIDE retain common
condition facts on paths that can continue, kind dispatch joins surviving kinds,
and FIND with a returning fallback can retain outer filter facts. Only definite
structural returns remove a path. Branch-local facts and item bindings keep
their scope; joins of arbitrary facts produced inside bodies are not inferred.
Runtime continuation guards preserve the resulting state facts against aliases
until the containing scope exits. No grammar or public evidence schema changed.

[Qualification evidence](../evaluations/native_editor/2026-10-16-early-returns/README.md):
328 native tests pass on both Rust versions in development and static musl
release modes, with warning-free Clippy. Eight new semantic groups cover 20
independent exchange inputs, eight scenarios, single/multiple continuing paths,
kind unions, optional ancestors, unsafe inference, aliases, return/failure/loop
cleanup, caller guards, source evidence, replay/generation, and execution budgets.
The boundary mutation changes exactly one reviewed outcome. The 21st editor
navigation test and 29 actual VS Code checks cover payload definitions/copies
and unsaved return-to-PASS edits. All 627 Python tests, example formatting,
top-level checks, reference workflows, and five extension unit tests pass.

Twenty cases from an equivalent older nested-ELSE source run on the retained
previous executable and migrate with full observation preservation. Comparing
those migrated cases with the guard-clause source preserves all outcomes and
state, while retaining changed source/evidence. No case is unavailable or
mismatched. This is a concrete source adaptation across actual engines, not a
human review study or approval. A separate migration records a deliberate
incompatibility: alias clearing after an absence-return guard now fails with
presence_mutation. Prior cases remain unchanged and the candidate failure
replays exactly; migration/refactor proposals remain unapproved.

The qualified static package passes host/concurrency/relocation checks and
Alpine/GLIBC 2.36 replays. All 48 archived source/build inputs match the workspace,
and all 18 complete invoice observations match the previous engine. Main-filesystem
scratch space avoided the prior temporary-filesystem quota issue.

The full goal remains active. This advances readable rule structure, independent
semantics, and source-adaptation evidence, without claiming measured comprehension
benefits. Remaining language/tooling decisions, broader source migration and
production qualification, and actual participant evidence remain open. No
external pilot or public release occurred.

## Local source outline (2026-10-16)

The preceding recovery turn produced evidence that the crash preserved the
checkpointed source and completed verification. Continuing the adoption and
human-understanding objectives, native VS Code mode now exposes a local Outline
and Go to Symbol in Editor view of declarations, record fields, domain behaviors,
requests, backgrounds, scenarios, and example tables. It uses the Rust layout
parser, keeps domain names and exact source ranges, and supports unsaved and
untitled documents. Missing imports, type errors, and incomplete expressions do
not erase the surrounding structure. Invalid layout returns no guessed outline.
This is a source index, not a claim that the program is semantically valid.

[Qualification](../evaluations/native_editor/2026-10-16-outline/README.md):
333 native tests and warning-free Clippy pass on Rust 1.85.0 and 1.96.0.
Five new test groups cover hierarchical/exact Unicode/CRLF ranges, flat scenario
sections, interleaved declarations, unavailable imports and invalid bodies,
empty documents, layout/resource refusal, and bounded CLI snapshots. All 627
Python tests, 71 example formatting checks, top-level checks, reference workflows,
and five JavaScript tests pass. The installed VS Code host passes 31 checks,
including actual stale-outline rejection and unsaved/untitled navigation.

Eighteen cases from the retained previous static executable migrate through the
new development executable with complete observations preserved; original case
bytes are unchanged and proposals remain unapproved. This checkpoint qualifies
the development executable and editor, not a new static release package. The
first editor run exposed a test that reused VS Code's symbol cache; the corrected
test waits for a new delayed process before editing and passes. Both runs are
retained. No syntax, execution semantics, or public run payload changed.

The full goal remains active. This improves local navigation while fixing a
rule, but does not establish human comprehension or review-time benefits.
Completion/debugging, broader error-tolerant semantic navigation, remaining
language decisions, deployment qualification, and actual participant evidence
remain open. No external pilot or publication occurred.

## Static type-error explanations (2026-10-16)

The previous goal turn made concrete progress on the native source outline.
This turn improves the information available while repairing a rule: selected
static errors use bounded GWT-style type descriptions, assignments/operators/
conditions/collections show the received and required types, optional-record
paths identify the missing presence proof, and shared-state argument errors
show both contracts. Copy advice appears only when a copy is type compatible
and explains the resulting isolation from the original state. One-of diagnostic
descriptions include payload fields; hover retains its compact kind summary.
Error codes, spans, grammar, accepted programs, and execution semantics remain
unchanged; diagnostic message text changes. Other categories retain existing
messages, including host-input validation.

[Qualification evidence](../evaluations/native_editor/2026-10-16-type-diagnostics/README.md):
338 native tests and warning-free Clippy pass on both Rust versions. Five new
groups cover operator/assignment/condition/collection errors, optional read/write
paths, truthful repair advice, copy isolation, variant payload differences, and
bounded Unicode descriptions. Four actual old/new source comparisons preserve
codes and spans and accept the repaired sources. The installed editor passes
33 checks, including imported optional fields and unsaved corrections. All
627 Python tests, 71 example formatting checks, reference checks/workflows, and
five JavaScript tests pass. Eighteen retained cases migrate from the prior static
engine with complete observations preserved and original bytes unchanged;
proposals remain unapproved. The new executable is qualified in development
mode, without a new static-package or production claim.

The full goal remains active. This improves diagnostic content and demonstrates
that the tested advice applies, but does not prove a human comprehension benefit.
Remaining diagnostic/tooling work, language and deployment decisions, and actual
participant evidence remain open. No external pilot or publication occurred.

## Host-input contract explanations (2026-10-16)

The previous goal turn completed static type-error explanations. This turn
extends readable contract feedback to normalization: expected GWT types and
actual JSON kinds, missing required types, nested field/item locations,
exact-decimal encoding guidance, and missing/nontext/unknown one-of tags.
Unknown field and tag names are escaped and bounded. Input acceptance,
first-error ordering, diagnostic codes/spans, and request execution semantics
are unchanged. The same normalizer serves internal value checks. Message text
is part of a captured observation, so its changes are explicitly reviewed.

[Qualification](../evaluations/native_editor/2026-10-16-input-diagnostics/README.md):
343 native tests and warning-free Clippy pass on both Rust versions. Five new
boundary groups cover JSON categories, exact encoding, nested lists/optionals,
missing values, no execution/state installation on rejected inputs, kind tags,
and bounded Unicode descriptions. Fifteen actual old/new cases preserve all
non-message observation fields: eleven failures change wording and four cases
are fully unchanged. Every migration candidate replays, originals remain
unchanged, and all proposals remain unapproved. Separately, 18 invoice cases
have 13 fully identical observations and five message-only changes.

The static musl release package passes its independent Rust host, 288 concurrent
calls, relocation and binary-only replay checks; all 52 archive inputs match
the workspace. Alpine/GLIBC 2.36 checks pass with their documented isolation and
shared-kernel limits. The actual editor passes all 33 existing checks against
the package. All 627 Python tests, 71 example formatting checks, reference
checks/workflows, and five JavaScript tests pass. The initial invalid TYPE test
fixture and the corrected successful RECORD run are both retained.

The full goal remains active. This improves host integration feedback without
claiming measured human comprehension. Remaining language/tooling and production
qualification work and actual participant evidence stay open. No external pilot
or public release occurred.

## Checked native contract inspection (2026-10-16)

The preceding goal turn made concrete progress on host-input diagnostics and
message-aware case migration. Native authoring now has contract discovery through
`gwt inspect` and the borrowed Rust `program.inspect()` API. Both use the
checked program, exposing resolved named types, caller inputs versus local setup,
required input names, declared outputs, behavior parameters/returns, expanded
entry scenarios, original source locations, and the frozen source identity.
Inspection executes no rules and makes no assertion-passing claim. The bounded
JSON conversion returns an explicit error above eight MiB without dropping or
abbreviating contracts. Existing execution and case payloads are unchanged.

[Qualification](../evaluations/native_editor/2026-10-16-inspection/README.md):
349 native tests and warning-free Clippy pass on Rust 1.85.0 and 1.96.0. Six new
groups cover exact host inputs, local setup exclusion, optional omission and
declared types after refinement, aliases/kind contracts/imported locations,
frozen source identity, failing but unexecuted scenarios, example rows and
expectation counts, 60-level types, oversized-report refusal, and CLI failures.
Three representative examples produce reports matching the checked identities
and entry names. All 627 Python tests, 71 example formatting checks, reference
checks/workflows, and five JavaScript tests pass.

The packaged independent Rust host verifies inspection against expected invoice
contracts. Installed and relocated CLIs return identical reports. The static
musl package passes the existing host/concurrency/replay checks; all 53 archived
source/build inputs match the workspace. Alpine and GLIBC 2.36 container
inspection matches the host report, and their scenario/execution/replay checks
pass. All 33 existing editor checks pass against the package. All 18 invoice
execution observations equal the preceding engine's observations; an explicit
prior-case engine transition also preserves its complete observation.

The full goal remains active. This closes a native discovery gap in the authoring
and integration workflow, while broader tooling, intentional language coverage,
production qualification, and actual comparative human evidence remain open.
No external pilot or public release occurred.

## Explicit rounded division (2026-10-16)

The preceding goal turn completed checked native contract inspection. This turn
addresses an arithmetic-policy gap: a native division step requires an explicit
literal decimal scale, one of five named rounding modes, numeric operands, and
a decimal destination. It rounds the exact rational quotient once; ordinary `/`
retains exact-only behavior. Source-mapped evidence records the selected policy
and result before mutation. The formatter, checker, editor navigation, grammar,
language/spec notes, and an eight-scenario quoted-price example are aligned.
The example chooses half-even rounding explicitly and does not claim to allocate
a total without a remainder or establish a universal business policy.

[Qualification](../evaluations/native_editor/2026-10-16-rounded-division/README.md):
356 native tests and warning-free Clippy pass on both Rust versions. Seven new
groups include 630 independent Python-decimal probes and cover static refusals,
signs/ties/recurring values, aliases/copies/traversal, limits and no-write failures,
source evidence, capture/replay/generation, and formatting. Fifty-four actual
captured inputs compare two rounding policies: four outcomes/states change,
nine zero-unit rejections remain failures on both sides, and no case is missing
or mismatched. JSON/HTML review artifacts retain source and evidence differences;
there is no new browser qualification or human-approval claim.

The new built-in reserves `divide`. An actual prior custom behavior with that
name replays on its previous executable but cannot compile on the new engine;
migration reports `candidate_unavailable`, preserving the original. Renaming
that helper with the old engine before migration yields full observation
preservation and verified candidate replay. These proposals remain unapproved.
The qualifier's initial exit-code expectation was corrected to recognize the
explicit unavailable-candidate failure; all runs are retained.

The static package passes host/concurrency/inspection/relocation/binary replay
checks and Alpine/GLIBC 2.36 checks within their documented scope. All 54 archive
inputs match the tree and all 18 previous invoice observations are unchanged.
The actual editor passes 34 checks, including rounded-division field navigation;
a pre-existing positive definition check now retries empty responses under a
stable document version with a deadline. All 627 Python tests, 72 example
formatting checks, reference checks/workflows, and five JavaScript tests pass.
Python validation of this explicitly native-only example remains unsupported.

The full goal remains active. Explicit rounded arithmetic is now expressible,
while broader domain numeric needs, remaining language/tooling work, production
qualification, and actual human evidence remain open. No external pilot or
public release occurred.

## Weighted allocation pressure test (2026-10-16)

The preceding recovery turn verified the saved rounded-division checkpoint.
This turn exercises that feature in a larger policy using existing language:
whole-cent budget validation, eligibility, proportional base shares, largest
remainders, input-order ties, and total conservation. The public request accepts
only domain inputs; result construction and policy remain in GWT. Eleven
scenarios include the deliberate consequence that a larger total can reduce an
individual share under this allocation policy.

[Qualification](../evaluations/native_editor/2026-10-16-weighted-allocation/README.md):
1,004 independent rational-quota/sort cases match complete native results or
expected rejections. A plausible faulty selection condition changes 12 of 52
captured inputs, exactly as the independent oracle predicts. Fifteen invalid
inputs remain rejected; no baseline mismatches or unavailable cases occur.
All 104 captures replay and baseline bytes remain unchanged. Scenario validation
also rejects the faulty revision. The review remains unapproved, with no new
browser or actual-human evidence claimed.

This example exposes two concrete areas for further work: local typed record
construction currently needs template plumbing, and repeated scanning plus
growing-state evidence limits scale. Default-limit probes succeed for the tested
1/3/8/16-recipient inputs and refuse the tested 32/64-recipient inputs with
`evidence_limit` and no result. These are input-specific results, not a universal
capacity threshold; partial state can remain after failure.

All 358 native tests and warning-free Clippy pass on Rust 1.85.0 and 1.96.0.
All 627 Python tests, 73 example formatting checks, reference workflows, and five
JavaScript tests pass. The retained release executable was used for capture and
review; its 54 source/build inputs still match the tree. There is no engine
semantic change or new release/package/editor qualification in this turn.
The full goal remains active, including deliberate language design, practical
resource handling, production qualification, and demonstrated human benefit.

## Typed local records (2026-10-16)

The preceding allocation pressure test exposed template arguments needed only
to construct result records. Native `LET name be RecordType:` now constructs
typed locals with explicit fields, reusing existing initializer checks, copied
values, source-order evaluation, and atomic binding installation. It works in
behavior bodies and after request/scenario WHEN. The colon distinguishes it from
ordinary expression/call bindings. Required/optional/nested/one-of contracts,
formatter projection, source mapping, inspection, and editor navigation align.
The allocation example constructs each share locally and no longer passes a
request-local draft through its behavior signatures.

[Qualification](../evaluations/native_editor/2026-10-16-local-records/README.md):
365 native tests and warning-free Clippy pass on Rust 1.85.0 and 1.96.0, including
six constructor groups and imported editor provenance. All 1,004 independent
allocation cases and 11 embedded scenarios still pass. Fifty-two actual old
cases migrate with complete observation preservation, then review against the
refactor with zero changed public outcomes. All 52 states change solely by
removing `draft`; 15 invalid inputs remain rejected. Captures replay, original
bytes remain unchanged, and the review is unapproved.

The colon introduces an explicit compatibility edge for old returning calls
ending in `:`. A retained old case replays on its prior engine but cannot migrate
directly. Renaming that behavior on the old engine before migration preserves
its complete observation; candidate replay verifies. No migration is silently
accepted or historical case rewritten.

All 629 Python tests, 73 example formatting checks, reference workflows, and five
JavaScript tests pass. The actual editor passes 35 checks against the frozen
final development executable. Initial lint and intermediate qualification results
are retained; no new release package or container qualification is claimed.
The tested 32/64-recipient allocations still exceed the default evidence budget.
The full goal remains active: this reduces concrete authoring plumbing without
claiming measured human benefit or closing resource, language, and deployment gaps.

## Append evidence growth (2026-10-16)

The preceding turn removed template plumbing with typed local records. Profiling
the remaining allocation limit separated event metadata and repeated scans from
growing append snapshots. Native append evidence now records an `append item`
delta with the exact inserted value, index, resolved/source paths, source span,
and operand dependency. The runtime verifies the unchanged prefix and records
the event before mutation. Other mutation events retain before/after values;
historical `append` events remain distinguishable by their operation name.

[Qualification](../evaluations/native_editor/2026-10-16-evidence-growth/README.md):
a 64-label collector's complete event bytes fall from 930,561 to 112,182, about
88%, with identical state/result and 266 events on both engines. A 128-label
input that formerly hit the default evidence limit now succeeds in 222,823
event bytes. No limit was raised. All 52 existing allocation outcomes and states
are preserved across explicit engine migration: 36 change evidence and 16 retain
complete observations. Originals remain unchanged and candidates replay; all
proposals remain unapproved. The tested 32/64-recipient allocations still exhaust
the evidence budget because other growth costs remain.

All 370 native tests and warning-free Clippy pass on Rust 1.85.0 and 1.96.0.
Five new groups cover delta reconstruction, aliases, normalization/optional items,
exact budget boundaries, append-event growth, explanation validation, replay,
and HTML visibility/escaping. All 629 Python tests, 73 example formatting checks,
reference workflows, and five JavaScript tests pass. Browser selection reported
no available browser, so visual/interactive review validation remains pending;
only static HTML checks are claimed. No new release package, container, or actual
editor-host qualification occurred. The full goal remains active, including
broader resource handling and demonstrated human benefit.

## Execution evidence profiling (2026-10-16)

The interrupted profiling work is recovered and qualified. Native `profile`
executes one request or scenario with its ordinary limits and reports exact
retained event bytes, value/metadata contributions, and operation/source-span
groups. Execution diagnostics and partial accounting remain visible on failure;
no refused event is counted and no larger budget is silently selected. Complete
profile input/output bounds are explicit. Rust hosts have matching request and
scenario APIs. The [guide](native-profiling.md) distinguishes evidence accounting
from time/memory measurements and from behavioral review.

[Qualification](../evaluations/native_editor/2026-10-16-profiling/README.md):
376 native tests and warning-free Clippy pass on Rust 1.85.0 and 1.96.0. Twenty-two
workload profiles match independent byte accounting, both groupings, and repeated
report ordering. All 57 actual retained cases migrate with complete observation
preservation; originals remain unchanged, candidates replay, and proposals are
unapproved. A fresh static musl release passes an independent packaged host,
installed/relocated CLI profile comparison, and local Alpine/Debian container
checks. The package qualification now derives its unit-test count from actual
output instead of retaining an outdated constant.

All 629 Python tests, 73 example formatting checks, 16 top-level checks, both
reference workflows, and five JavaScript tests pass. The documented profile
command succeeds, and all 55 source/build inputs match the qualified package.

The tested 16-recipient allocation records 816,194 bytes, about 77% event metadata,
with repeated collection scans prominent. The 32/64-recipient inputs still fail
at the evidence limit. This supplies actionable evidence for further resource
work without claiming an optimization, universal capacity threshold, or measured
human benefit. No new browser/editor interaction or external pilot occurred.
The full project goal remains active.

## Explicit CLI operating budgets (2026-10-16)

Profiling exposed a workflow gap: Rust hosts could select budgets, but the CLI
always used defaults. Native run/profile/capture/test/validate now accept a strict,
complete `--limits FILE.json`. Settings are read once before loading/executing
source, reused consistently, and recorded in profiles, tests, validation, and
cases. Replay/comparison retain frozen limits. Hard runtime bounds and the
existing default-profile ceiling on captured cases are unchanged. Resource
exhaustion remains an execution failure. No language syntax was added.

[Qualification](../evaluations/native_editor/2026-10-16-cli-limits/README.md):
382 native tests and warning-free Clippy pass on both supported Rust versions.
All 18 independent packaged-host profiles now match installed and relocated
CLI output, including zero-step/evidence cases. All 57 preceding retained cases
migrate with complete observation preservation; originals remain unchanged and
candidates replay without approving proposals.

A copied allocation candidate repeats a valid assertion. Both revisions pass
their eleven embedded scenarios and preserve complete outputs/state under default
limits. A representative eight-recipient request succeeds on the baseline but
hits the selected 256-KiB evidence budget on the candidate. Capture/replay and
review retain this failed outcome, illustrating why operating budgets and
representative request cases matter alongside scenarios. A zero-step validation
also records failure for all eleven scenarios rather than accepting resource
exhaustion as an intended rejection.

The adjacent allocation limit file and [guide](native-execution-limits.md) make
the workflow reproducible. Resource-expectation syntax, broader boundary authoring,
larger-input efficiency, production qualification, and measured human benefit
remain open. No external pilot or new interactive review evidence is claimed.

## Editor budget consistency and profiling (2026-10-16)

The explicit CLI operating-budget workflow now reaches VS Code. Native
`gwt.native.limitsFile` selects the same complete settings for Run, Profile, Test,
and Validate. Dirty selected limit buffers are saved before execution; relative
paths use the active workspace folder or file parent, independently of import
roots. Failed saves stop execution and missing/malformed settings do not fall
back to defaults. Static checking/navigation remain independent, including when
the setting itself has an invalid type.

The new Profile Execution Evidence command shares Run's entry/target selection
and preserves exact CLI stdout in the output channel. Stderr-only configuration
failures now retain a bounded command diagnostic rather than being described as
invalid JSON. Python mode refuses native profiling without switching engines.

[Qualification](../evaluations/native_editor/2026-10-16-editor-limits/README.md):
38 native and two Python checks pass in the installed VS Code extension host;
ten JavaScript tests cover the adapter/process boundaries, including request
selection and cancelled saves. Final qualification verifies source and executable
hashes remain unchanged during the run. All 56 engine inputs still match the
preceding packaged native engine; no runtime semantics or captured-case identity
changed. Existing process time/output bounds remain in force.

This closes an editor/terminal consistency gap without establishing human
comprehension benefit. Resource authoring, larger-workload costs, broader language
and deployment work, and representative user evidence remain open. The full goal
is still active; external pilots remain deferred at the owner's request.

## Broader maintenance experiment preparation (2026-10-16)

The earlier live trial covered small changes in one refund domain. A separate
[native maintenance corpus](../evaluations/native_maintenance/README.md) now
prepares paired GWT/Python tasks across refund, delivery, expenses, inventory,
and a larger exact-allocation policy. The allocation change introduces equal
effective weights only when all eligible weights are zero, while preserving
weighted cases, rejection rules, ordering, output shape, and metadata semantics.
This is an isolated research fixture, not a change to the public example policy.

[Qualification](../evaluations/native_maintenance/2026-10-16/README.md): both
languages' baseline, correct, and faulty references agree across 6,828 executions
over 1,138 distinct inputs per revision. Correct references pass all probes;
baselines preserve 952 outcomes and fail the 186 requested changes. The allocation
task contributes 998 inputs, including 158 changed and 840 preserved outcomes.
Its deliberate faulty candidate passes both public examples but fails 380 withheld
probes. Independent expected outcomes remain outside the execution worker.

Thirty paired task records are frozen with source, guide, public probes, trial
order, and source/executable hashes. Four new unit groups and the full 633-test
Python suite pass. Native engine code is unchanged and the preceding static
release is used. The corpus explicitly distinguishes exact values, policy
rejections, execution errors, and missing observations.

There were zero live model calls and zero participants. This qualifies experiment
materials; it does not demonstrate maintenance superiority or human benefit.
A native-aware isolated candidate scorer and repair loop are still needed before
live trials: the old worker executes Python GWT and cannot score the native
allocation syntax. The full project goal remains active, including deliberate
semantics, broader deployment, and representative human review evidence.

## Isolated native maintenance scoring (2026-10-16)

The five-domain corpus now has a native-aware container scorer and public-only
feedback command. Each attempt receives only candidate source, a frozen worker
and native executable, and selected inputs in a bounded disposable container.
Expected answers remain outside execution. Full scoring preserves missing trials,
every recorded attempt, strict outcome distinctions, and first/final and repair
metrics. Public feedback evaluates only the latest attempt and public examples;
full scoring never schedules repairs. Provider integration remains unfinished.

[Qualification](../evaluations/native_maintenance/2026-10-16-isolated/README.md)
retains twelve actual container checks, including 1,996 allocation executions,
timeouts, stream limits, malformed outputs, and verified cleanup. A cleanup race
found in the first run was corrected and requalified. Synthetic responses prove
missing trials remain visible, a refund repair recovers, and a candidate passing
public allocation examples can fail 380 withheld probes. All 641 Python tests
pass; twelve focused tests cover the final scorer changes. Native engine semantics
are unchanged. Crash recovery confirmed completed logs and reports survived.

There were zero new live model calls and zero human participants. This completes
the isolated scoring component, not the model comparison or proof of human
benefit. The full goal remains active; external pilots remain deferred.

## Native model experiment orchestration (2026-10-16)

The native scorer now has a [model experiment runner](../evaluations/native_maintenance/experiment.md).
It supplies only explicit public task context to tool-free Responses API requests,
records exact provider input/output and reported usage, and runs repairs in frozen
task order. Public success stops repairs. All responses are sealed before any
withheld execution, and no provider call occurs after that seal. Provider and
execution-infrastructure failures stop the experiment without automatic retries;
pending request intent and completed responses remain available after interruption.

[Qualification](../evaluations/native_maintenance/2026-10-16-experiment/README.md)
uses thirty paired trials, thirty-six synthetic provider responses, and actual
container execution. Six refund repairs recover; allocation's public pass does
not trigger repair despite 380 withheld failures per trial. Unit checks cover
context boundaries, ordering, schema/refusal failures, attempt caps, interrupted
calls, resource cleanup, and qualification-copy integrity. All 650 Python tests
and 21 focused tests pass. The rehearsal completes 72 container attempts and
7,098 input executions; reconstructed public requests and recorded hashes match.
All 56 native engine inputs remain unchanged.

No API key was configured, so the transport is only mock-tested and live
model/API qualification remains pending. There were zero live model calls and
zero human participants. This advances the experiment workflow without claiming
model performance or demonstrated human benefit. The full goal remains active.

## Manual assessment of human-review explanations (2026-10-16)

The [human-review kit](human-review-study.md) now has a facilitator workflow for
recording rationale judgments separately from prediction and approval accuracy.
Sheets bind exact response snapshots, source/context, and rubrics. A declared
assessor roster keeps missing sheets visible. Final consensus requires all planned
ratings and at least two agreeing assessors; disagreements retain their original
opinions and require a separately bound resolution. Exact quote validation checks
provenance, not whether an assessor's interpretation is right. Recognition counts
are explicitly assessor-judged and do not replace the original decision metrics.

The [synthetic CLI rehearsal](../evaluations/human_review/2026-10-16-adjudication/README.md)
retains twelve planned tasks, five submitted answers, seven unavailable
explanations, one disagreement, and its explicit resolution to uncertainty. It
also proves that a missing assessor yields no final recognition credit. No human
participants or actual human assessor judgments were collected, and no model
was called. All 658 Python tests and fourteen focused tests pass. This closes a recording/analysis gap without supplying human-benefit
evidence.

Browser selection and discovery still report no available browser, so the
pending append-evidence visual check remains open. Participant UI, policy
fixtures, native runtime, and source semantics are unchanged. The full project
goal remains active; live model qualification and representative human evidence
remain pending.

## Common facts after branch bodies (2026-10-16)

Native continuation analysis now joins supported proofs made inside continuing
branches, including successful REQUIRE steps and nested guard clauses. Authors
can retain route-specific checks in their branches and read a commonly proven
payload afterward. IF/DECIDE, kind/value dispatch, and FIND are covered; local
bindings, helper postconditions, and possibly empty FOR loops do not escape.
The [semantics](native-branch-proofs.md) explain proof intersection/union,
runtime lifetime, and deliberate compatibility changes.

[Qualification](../evaluations/native_editor/2026-10-16-branch-proofs/README.md):
388 Rust tests and Clippy pass on both supported versions. Seven collection
authorization scenarios and 32 independent inputs qualify the example; removing
the locker check changes exactly two outcomes. An equivalent source adaptation
preserves decisions and state across all inputs. All 32 baseline policy cases
and 57 retained portfolio cases preserve complete observations across engine
migration. Separate compatibility cases retain two new alias-mutation failures
and two newly redundant-check compilation refusals. No migration is approved.

A fresh static release passes the independent host/installed/relocated package
checks. Thirty-nine actual VS Code checks verify the new continuation navigation
and invalid-edit diagnostics. All 658 Python tests, 74 example formatting checks,
reference workflows, and ten JavaScript tests pass. The five-domain maintenance
corpus is also requalified on this packaged engine with 6,828 reference executions;
previous experiment artifacts keep their original identities. Visual review remains pending;
no production rollout, live model result, or human-benefit claim follows from
these checks. The full project goal remains active.

## Connected native execution model (2026-10-16)

The [execution-model guide](native-execution-model.md) brings the implemented
request lifecycle, state sharing/copying, ordered decisions, flow proofs,
arithmetic, failure, evidence, and host boundary into one reading path. It uses
the existing member-pricing example and links to the detailed semantic rules.
The root README, crate README, Python reference, semantic decisions, and feature
matrix now identify that path and distinguish the experimental native profile
from the published Python v0.2 language.

The audit clarified two overbroad descriptions: only bare-path arguments share
caller state, and append evidence records the inserted item/index rather than
full before/after lists. The objective table and implementation milestones now
treat unsupported Python syntax as explicit retain/redesign/omit decisions;
they do not turn Python parity into a requirement contrary to the project goal.
No unsupported form has been declared permanently omitted by this documentation
change, and no language version or compatibility guarantee has been introduced.

Request phases and state handling were checked against `program_runtime.rs`;
initializer ordering against `program.rs` and its runtime; proof lifetime against
the branch-proof rules and implementation. Both guide commands were executed:
native validation passed all four member-pricing scenario rows, and the request
returned the exact documented `{"quote":{"total":"35.91"}}` with the original
order retained in run state. All twenty guide link targets exist, and
`git diff --check` passed. Runtime, examples, and engine identity are unchanged;
the full suites from the preceding implementation checkpoint were not rerun for
this documentation-only work.

This improves the documented current execution model. Outstanding language
decisions, a versioned transition, broader conformance/deployment qualification,
live native maintenance comparison, and actual human-review evidence remain
open. The full goal is active and incomplete.

## Recoverable human-review observations (2026-10-16)

New offline study packets can restore an explicitly downloaded partial record.
Validation binds the exact packet, assignment, source, profile, and sequential
task answers. Restoration retains the response ID and frozen submitted/skipped
tasks, restores the draft, and starts paused. Work since the download is not
recoverable; there is no automatic storage or upload. Existing frozen version 1
records remain scoreable, while new packet identities bind response version 2
and per-task recovery counts.

Resumed tasks retain only observed time segments. The unknown interruption is
not invented as active or wall time. Their answers remain in the study, but
timing medians exclude those tasks and report the eligible denominator. Task and
session recovery flags support explicit analysis of interruption effects.
Saved snapshots are cooperative records, not authentication of answers or proof
that the latest checkpoint was chosen.

[Qualification](../evaluations/human_review/2026-10-16-recovery/README.md) passes
664 Python tests and twenty focused checks. Two synthetic JavaScript recoveries
interoperate with actual preparation, scoring, and assessment CLI commands;
legacy records still score. Browser discovery returned no available browser,
so file-selection, restored-form interaction, and visual validation remain
pending. Policy fixtures and native engine inputs are unchanged. This improves
study resilience but supplies no participant evidence. The full goal remains
active; actual human benefit and live native model comparison are still missing.

## Deliberate standalone existence adaptation (2026-10-16)

The native profile now records an explicit choice for standalone existence:
name the domain question in a boolean-returning behavior using the existing
`FIND ... ELSE`, rather than copy the Python `exists` statement. The
[subscription adaptation](native-existence-decisions.md) supplies the missing
standalone example alongside the earlier expense double-search refactor. Its
public request shapes and checked outcomes remain intact. Its plan helper's
input deliberately narrows to the declared account domain; a retained old/new
caller demonstrates the incompatible unknown-plan case. Other legacy collection
forms still require separate decisions.

[Evidence](../evaluations/subscription/2026-10-16/README.md) includes 3,276
independent valid integer-domain inputs evaluated by both Python revisions and
the existing packaged native engine, thirteen scenario executions on both engines,
four detected policy faults, a reuse/reset regression, and thirteen native
capture/replays. Ten actual Python cases verify against the frozen baseline and
produce unchanged outputs with changed paths in source-backed review. Browser
validation of that report remains pending and no review is approved.

All 391 Rust tests and Clippy pass on both supported toolchains; all 664 Python
tests pass. The runtime and its 56 qualified build/source inputs remain unchanged.
The deferred-language note no longer describes first-match handling as an
unimplemented future feature. This is an evidence-backed language/source decision,
not measured readability or a claim of universal engine equivalence. The full
goal remains active and incomplete.

## Typed raw facts and empty-object validation (2026-10-16)

The native profile explicitly retains a typed, closed host boundary rather than
adding `any`. The [contact adaptation](native-input-boundary-decisions.md)
replaces four known raw field reads with a declared input record, optional text,
and an independent domain-state label. Domain validation messages and outcomes
remain in GWT. Input acceptance deliberately narrows; the output contract remains
unchanged. Arbitrary dynamic or heterogeneous data still requires a worked
representation decision, not an assumed textual migration.

The boundary qualification found and fixed a Python validation defect: flattening
must preserve explicit empty objects rather than convert optional scalar values
to absence or hide unknown fields. An exact retained prior runtime module and
three before/after observations demonstrate the fix; regression tests also cover
one-of fields and retained Python `any` values.

[Evidence](../evaluations/input_normalization/2026-10-16/README.md) records 94
independent inputs under both Python source revisions and the existing packaged
native engine. Native outcomes comprise 56 profiles, eight behavior failures,
and thirty failures before execution. Ten old accepted malformed inputs become
incompatible with the new Python contract; extra top-level state remains a
documented Python/native difference. Sixteen retained cases expose those changes,
including a changed failure and preserved-output paths, without approval.

All 394 Rust tests and Clippy pass on both toolchains; all 666 Python tests and
required example/reference/extension checks pass. Native engine inputs are
unchanged. Browser review remains pending, and no human benefit or external
adoption is claimed. The full goal remains active and incomplete.

## Native grammar and context rules (2026-10-16)

The [native grammar](native-grammar.md) now documents the experimental Rust
profile in one reference, separate from Python v0.2. It covers layout, types,
declarations, calls, statements, setup, requests, scenarios, tables, and the
actual expression binding strengths. Context rules explain root-only ordinary
setup/outputs, typed table fields, literal setup versus singleton input contracts,
the different uses of `AND`, returning calls, and required branch coverage.
No language release or compatibility guarantee is introduced.

The source audit corrected an overbroad import description: type names, request
names, and behavior signatures have separate collision rules. The execution
guide, semantic decisions, Python grammar, root/crate READMEs, and agent guidance
now link or identify the native reference.

[Retained observations](../evaluations/native_documentation/2026-10-16-grammar/README.md)
show 23 focused checks meeting their expected acceptance/rejection outcomes;
all twelve accepted programs also execute successfully. The three documented
validation commands pass thirteen existing scenario executions. Link/anchor and
whitespace checks pass; the 56 native engine inputs remain unchanged. Full suites
were not rerun for this documentation-only change. This improves authoring and
semantic clarity without establishing human comprehension benefit. Remaining
language decisions, live native model comparison, actual human-review evidence,
and broader deployment qualification keep the full goal active and incomplete.

## Explicit failure exits and required inventory inspection (2026-10-16)

The native structural exit analysis now recognizes literal `REQUIRE false`
alongside returns. A required lookup can return its match or fail explicitly
without an unreachable fallback value. The same analysis excludes failing
alternatives from continuation joins, retaining the existing presence/kind
guards. Arbitrary constant evaluation, helper failure inference, and nonempty
loop assumptions remain excluded; unreachable source is still checked.

The inventory example adds a named snapshot-returning inspection helper and a
native scenario entry importing the shared policy. The Python entry retains its
own scenario syntax. The [migration note](native-failure-exits.md) distinguishes
read-only inspection from legacy mutable lookup destinations, explicit assertion
failure from Python's missing-match error, and the still-open optional-lookup
adaptation. This does not copy Python behavior merely for compatibility.

[Qualification](../evaluations/native_editor/2026-10-16-failure-exits/README.md)
checks 720 independently modeled inputs across both Python source revisions and
the packaged native engine, with five native scenarios and failure/copy/proof
regressions. All 57 retained portfolio cases migrate with their observations
preserved. Separate migration probes expose an alias-clearing failure and a
redundant-presence compilation refusal; neither is treated as transparent
compatibility or approved automatically.

All 398 Rust tests and Clippy pass on both supported toolchains; all 666 Python
tests and required example/reference/extension checks pass. A static release
passes independent package, host, relocation, replay, and concurrency checks.
Interactive review and fresh installed-editor UI qualification remain pending.
The full goal remains active: this closes a concrete authoring gap without
establishing actual human benefit or completing the remaining language,
deployment, and comparative-evidence work.

## Failure-exit editor integration (2026-10-16)

The [installed editor qualification](../evaluations/native_editor/2026-10-16-failure-exits/README.md)
now passes forty checks against the packaged failure-exit engine. Its added
check verifies hover and imported payload definitions after literal-false
guards, refusal of stale semantic results after invalid unsaved edits, recovery
after restoring guards, and navigation after moving an imported declaration.
Both saved files remain unchanged. The test accounts for the editor's line-ending
normalization when checking source positions. Two initial incorrect expectations
are retained with their failed runs; the extension and runtime needed no change.

Ten JavaScript tests, source syntax checks, and whitespace checks pass. The
engine's 56 source/build inputs and packaged executable are unchanged, so prior
runtime/package qualification remains applicable. Browser discovery still finds
no available browser; interactive review and study-recovery checks remain open.
This completes the pending editor integration check for this feature, not the
full project goal or the missing actual human-review evidence.

## Example audit and feature-flag domain contracts (2026-10-16)

The [example audit](../evaluations/native_validation/2026-10-16-example-audit/README.md)
freezes all 75 source files and records fresh native validation. Forty-six files
validate, twenty fail static checking, two modules have no entry scenarios, and
six Python input files require paired rules. Loan underwriting passes checking
but fails all three scenarios on nonterminating decimal division; its rounding
policy needs an explicit decision. Across executed scenarios, 225 pass and three
fail. First diagnostics identify adaptation work without assuming Python parity.

The [feature-flag adaptation](native-domain-literals.md) names the closed reason
contract for both decision fields and helper inputs and quotes domain constants.
Ten scenarios now expose override ordering, enabled-rule priority, inclusive
cutoffs, and decision reuse. No engine implementation change was required.

[Qualification](../evaluations/feature_flags/2026-10-16/README.md) records 6,272
independent closed-schema inputs across both Python source revisions and native:
18,816 matching output observations. Eight actual baseline captures compare
unchanged. Separate probes retain the narrowed helper's earlier rejection and
Python's legacy resolution of quoted tokens through extra top-level bindings;
neither difference is hidden by a general compatibility claim.

The retained full-suite logs show 401 Rust tests and Clippy passing on both
supported toolchains, and 666 Python tests passing. Recovery completed 97
example, reference, extension, formatting, and documented-command checks, plus
source identity and whitespace checks. The native engine and packaged executable
are unchanged. Interactive review, actual human benefit, live native model
comparison, and broader language/deployment work remain open. External pilots
remain deferred; the full goal is active and incomplete.

## Exact underwriting ratios (2026-10-16)

The [native underwriting variant](native-exact-ratios.md) addresses a concrete
audit failure without making rounding an implicit language behavior. Ordinary
records retain numerator and denominator, and named comparisons test exact
thresholds after asserting positive denominators. The original Python example
remains available. Ratio output shapes and negative/zero input handling change
explicitly; this is a reviewed migration candidate, not a transparent replacement.

[Independent evidence](../evaluations/underwriting/2026-10-16/README.md) covers
1,072 rational-oracle results and fifteen scenarios. Fifty-two paired Python
executions differ in status, reason, and rate near exact reserve thresholds;
the evidence retains both host number representations. Six original-source
native cases compare successfully, including two former recurring-decimal
failures. Separate denominator probes retain acceptance/failure changes, and
five fault witnesses expose changed policy inequalities and precedence.

All 404 Rust tests and Clippy pass on both supported toolchains, and all 666
Python tests pass. Native engine source/build inputs remain unchanged. The
qualification checkpoint records repository checks and source identities.
Interactive review and human benefit remain unverified. This supplies a concrete
alternative for recurring domain ratios, not a general rational type, release,
production lending policy, or completion of the full project goal.

## Native declaration completion (2026-10-16)

The [native editor](native-editor.md#declaration-completion) now suggests current
imported behavior signatures, request names, and type names on incomplete
call/type lines. Parameter snippets and declared contracts help authors write
domain calls; `LET` suggestions require a declared return contract. Suggestions
are source declarations, distinct from successful compilation. The adapter
checks current source hashes and discards stale or cancelled results.

[Qualification](../evaluations/native_editor/2026-10-16-completion/README.md)
passes 41 installed-editor checks, including actual snippet insertion and an
import rename during an in-flight completion. Five Rust integration groups
exercise the new protocol and contexts. All 409 Rust tests and Clippy pass on
both supported toolchains; 666 Python tests, eleven JavaScript tests, and 97
repository checks pass. Initial cursor conversion, editor-text expectation, and
minimum-toolchain lint failures are retained with their fixes.

A fresh static release passes package, independent host, relocation, profile,
replay, and concurrent execution checks. All 63 retained portfolio/underwriting
observations are preserved through explicit engine migration. Scoped field/local
completion and native debugging remain open, as do broader language decisions,
deployment qualification, interactive review, actual human evidence, and the
live native model comparison. The full project goal remains active and incomplete.

## Language-choice audit and nested record validation (2026-10-16)

The [decision register](native-language-decisions.md) now records explicit native
choices for call results, comparison spelling, root request contracts, typed
tables, lookup/existence forms, exact numbers, and typed raw facts. It separates
those choices from unresolved numeric/singleton boolean contracts, general
optional lookup, indexed access, and version-transition work. Neither arithmetic
call nesting nor indexed expressions in the tested spelling is a current Python
feature; they are no longer treated as automatic compatibility requirements.

[Thirty executable probes](../evaluations/native_language/2026-10-16/README.md)
qualify specific alternatives and expose conditional-call, boundary, finite-type,
and aliasing differences. They do not establish a universal rewrite. The audit
also found and fixed Python validation flattening through declared record fields.
Four regressions cover nested aliases, optional records, variants/lists, dotted
declarations, and explicit raw objects. The exact previous runtime is retained;
the valid root request now succeeds and an extra sibling receives the correct
unknown-field failure.

All 410 Rust tests and Clippy pass on both toolchains, and all 670 Python tests
pass. Native source/build inputs and the packaged engine are unchanged. This
advances intentional semantics and migration guidance; broader language decisions,
a version transition, human-benefit evidence, live native model comparison, and
deployment work still prevent completion of the full goal.

## Captured-case regression gates (2026-10-16)

The [native regression command](native-regressions.md) now enforces an explicit
outcome/state or execution preservation scope. It verifies every frozen baseline,
uses the case's original input, target, and limits, and fails for changed or
unavailable observations. Complete review evidence remains available, including
source differences outside the selected scope. Report rows identify their
captured limits and case integrity. A matching boundary/resource failure can pass
preservation without becoming a successful execution or domain scenario.

[Qualification](../evaluations/native_review/2026-10-16-regressions/README.md)
covers nine captured cases and twelve actual CLI reports, six new integration
groups, and a separate packaged Rust consumer. All 416 Rust tests and Clippy pass
on both supported toolchains. The final static package passes independent host,
relocation, profile/replay, and concurrent execution checks; all 63 retained
observations survive explicit migration to the new engine fingerprint.

This closes the missing corpus preservation gate for boundary/resource
observations. It does not choose desired outcomes, approve snapshots, or measure
human understanding. Broader source adaptation, remaining language choices,
representative deployment, actual human evidence, and the live native model
comparison remain unfinished. External pilots remain deferred. The full project
goal remains active and incomplete.

## Complete capture identity in review decisions (2026-10-16)

The [saved-decision audit](native-review-decisions.md#artifact-contract) found that
schema-1 reviews omitted captured limits and full case identities. Four budget
changes left execution identical and incorrectly retained earlier synthetic
acceptance. Schema-2 reports now bind the complete corpus, including unavailable
payloads and migration provenance, and expose validated case identities and
captured limits. The existing decision digest therefore refuses those changes
as stale without altering runtime observations.

[Qualification](../evaluations/native_review/2026-10-16-review-identity/README.md)
records the before/after reproductions, 418 Rust tests and Clippy on both supported
toolchains, a freshly qualified static package, and 72 preserved migration
observations. With the owner's explicit Playwright CLI authorization, twenty
actual browser checks pass, including decision download/restore, rejection of
all four changed budgets while retaining current notes, and mobile layout.
The downloaded decisions also pass/fail fresh CLI assessment as expected.

This fixes a concrete gap in review fidelity. It does not authenticate reviewers
or establish comprehension benefit. Broader language/adoption work, actual human
evidence, and live native model comparison remain outstanding; external pilots
remain deferred. The full goal is active and incomplete.

## Browser validation of retained workflow adaptations (2026-10-16)

[Playwright CLI qualification](../evaluations/workbench/2026-10-16-adaptations/README.md)
now checks four retained reports whose browser validation was pending: underwriting,
feature flags, typed contact normalization, and subscription entitlements. All
173 interaction/rendering checks pass across forty recorded cases. Changed-case
selection, failure messages, exact ratio values, source-linked predicates, operand
navigation, classification filters, and search are checked against the retained
comparison data. Eight desktop/mobile screenshots were inspected.

This closes the historical artifacts' interaction/visual validation gap without
claiming fresh engine replay or upgrading their approval contracts. The original
reports remain unchanged. No runtime or editor changes were made. The mobile
inspection identifies the next readability task: identity hashes occupy 251
pixels before domain evidence, and the selected contact rejection message starts
1,332 pixels below its panel's top. Fold identity details and prioritize failures
while retaining full evidence access.

Actual participant comprehension, error detection, review time, live native model
comparison, remaining language choices, and deployment work remain outstanding.
External pilots remain deferred. The full project goal remains active and incomplete.

## Prioritize failures in comparison review (2026-10-16)

The Python workbench now places errors immediately after the selected case
summary and moves capture identities into a keyboard-accessible disclosure after
the supporting evidence. All evidence remains available. Three retained dossiers
were re-rendered through the production renderer with exact embedded-data
equality; their historical originals remain unchanged.

[Qualification](../evaluations/workbench/2026-10-16-readability/README.md) records
310 passing Playwright CLI checks across 34 retained cases, eight passing existing
workbench tests, and twelve inspected screenshots. On the measured mobile contact
case, the first rejection moves from 1,332 to 183 pixels below the panel top and
is fully visible without scrolling. Expanded identities remain accessible and
fit the desktop/mobile page width. This resolves the presentation issue identified
by the previous adaptation review without changing behavior or approving cases.

Actual participant comprehension, live native model comparison, remaining
language choices, and deployment work are still outstanding. External pilots
remain deferred. The full project goal remains active and incomplete.

## Native execution from a Node host (2026-10-16)

The [Node reference adapter](../examples/native_node_host/README.md) calls the
packaged native executable directly, preserving large integers and decimal text.
Rule failures retain their diagnostic/evidence envelope; process termination,
compiler diagnostics, and protocol errors remain separate. Calls use private
temporary inputs, no shell, and explicit input/output/wall-time bounds.

[Qualification](../evaluations/native_packaging/2026-10-16-node-host/README.md)
records thirteen passing tests with the unchanged static engine. Four independent
invoice totals and complete observations match direct CLI runs; twelve concurrent
requests retain independent state. A copied module, binary, rules file, and Node
driver execute outside the repository with an empty command path. Timeout,
output-limit, input-contract, native-budget, malformed-response, and cleanup
checks pass. Package CI now runs this host qualification in its existing matrix;
no hosted CI result is claimed.

This supplies a concrete additional host boundary without introducing another
evaluator. It recompiles on every invocation and is qualified locally only on the
recorded Node/Linux combination. Production rollout, browser execution, broader
targets, remaining language choices, live model comparison, and actual human
benefit remain open. External pilots remain deferred; the full goal is active
and incomplete.

## Explicit optional lookup contracts (2026-10-16)

The [lookup decision](native-language-decisions.md) now deliberately retains
`FIND ... ELSE` rather than adding lowercase `find optional`. A new stock-count
example separates a preview snapshot with absence, a retained previous selection,
and a write to the first matching inventory item. It uses the existing native
copy/alias rules and adds no syntax or runtime semantics.

[Qualification](../evaluations/native_language/2026-10-16-lookup/README.md) covers
150 independent requests, seven embedded scenarios, and a nine-case review that
catches three changed outcomes from a deliberately faulty copied-record write.
The full Rust suite now passes 421 tests and Clippy on both supported toolchains;
the existing packaged engine passes the CLI matrix. Sixty-five actual browser
checks verify the review's results, failures, filters, and exact download. All
review choices remain pending.

This resolves the optional-lookup statement choice for the current profile, not
arbitrary migration of Python aliases or evidence of human preference. Finite
literal types, indexed-access needs, broader dynamic boundaries, version
transition, deployment, live model comparison, and actual human evidence remain
open. External pilots stay deferred; the full goal remains active and incomplete.

## Browser-qualified human-study recovery (2026-10-16)

The [recovery browser checkpoint](../evaluations/human_review/2026-10-16-recovery-browser/README.md)
closes the outstanding interactive check for the study's downloaded checkpoints.
Seventy-eight Playwright CLI checks cover repeated desktop/mobile recovery,
frozen submitted/skipped answers, draft restoration, invalid/completed-file
refusal, keyboard resumption, and pause accounting. The scorer consumes the
actual browser downloads: all twelve planned tasks remain accounted for, and the
two interrupted submissions are excluded from timing medians. Six screenshots
were inspected. Visibility events are simulated rather than a claim about OS
tab scheduling or human attention.

The current engines pass all 1,305 independent study policy executions, and the
twenty focused study tests pass. Application code and study fixtures remain
unchanged. These are synthetic apparatus checks with no participants; they do
not supply the human-benefit evidence required by the project goal. Actual human
review, live model comparison, remaining language choices, and deployment work
remain unfinished. External pilots stay deferred; the full goal is active.

## Native browser execution assessment (2026-10-16)

The [browser preview](../examples/native_browser_host/README.md) exercises a
concrete integration need: local invoice what-if execution from frozen rules,
with the same exact facts, limits, and full evidence as the native host. A small
WebAssembly bridge calls the existing core in a fresh bounded worker. Engine
sources and semantics remain unchanged.

[Qualification](../evaluations/native_browser/2026-10-16/README.md) records 210
passing Playwright CLI checks. Both Rust 1.85.0 and 1.96.0 builds match all 97
captured request observations while the browser is offline. Their modules have
no host imports. Cancellation, deadlines, malformed inputs, budget ceilings,
concurrent state isolation, exact numbers, and desktop/mobile layout are covered.
Both bridge builds pass their ABI test and Clippy.

This supplies the concrete browser feasibility assessment in objective 5. Other
browsers, offline reload, production deployment, memory/load qualification, and
improved human review remain unproven. Actual human evidence, live model
comparison, remaining language choices, and deployment work remain unfinished.
External pilots remain deferred; the full goal is active and incomplete.

## Closed scalar domain contracts (2026-10-16)

[Finite contracts](native-finite-literals.md) now close the numeric and singleton
boolean type gap. A source declaration can constrain supported codes or exact
factors at the host boundary and require exhaustive value branches. Calculations
widen to ordinary scalar types; no computed membership or mutable alias narrowing
is guessed. The worked receipt policy keeps code meanings visible in its actions.

[Qualification](../evaluations/native_language/2026-10-16-finite/README.md) records
429 passing Rust tests and Clippy on both toolchains, five scenarios, 144
independent request expectations through both the library and packaged CLI,
exact-value/refusal/alias checks, editor and inspection evidence, and generated
scenario replay. The static package passes host and relocation checks plus an
explicit previous-engine migration. Twelve captured cases detect exactly three
outcome changes from an intentionally faulty retry multiplier; 87 browser checks
verify their review and exact download. Decisions remain pending.

Repository-wide verification also exposed native-only examples accidentally
included in Python execution discovery. The example inventory now names their
Rust coverage, and the Python formatter preserves native finite annotations
without changing Python's type semantics. Numeric/singleton boolean contracts are
now deliberate implemented choices rather than unresolved compatibility items.
Indexed access, broader dynamic boundaries and source migration, version
transition, additional deployment/editor work, live model comparison, and actual
human evidence remain open. External pilots stay deferred; the full goal remains
active and incomplete.

## Finite contracts across browser engines (2026-10-16)

The [current browser qualification](../evaluations/native_browser/2026-10-16-finite/README.md)
covers Chromium, Firefox, and Linux WebKit with both Rust toolchains. All 263
requests match complete native executions, including finite contracts and exact
numbers: 1,578 execution comparisons and 1,626 total browser checks pass. The
97 original observations also replay under their explicitly selected previous
engine and remain unchanged under the current engine. Migration proposals remain
unapproved; historical evidence is preserved.

Testing found that WebKit refused the first blob worker after switching offline.
The host now confirms worker-script readiness before returning a usable preview,
without executing WebAssembly or GWT during preparation. The first actual request
runs offline, and final checks pass on all three engines. Six inspected responsive
screenshots show the exact outcome and controls. Core semantics are unchanged.

WebKit is tested in a pinned existing Linux container because its direct host
launch lacks a library. This is not Safari, mobile-device, arbitrary-OS, production,
or human-benefit evidence. Remaining language/editor/adoption decisions, actual
human review, and live model comparison remain open. External pilots stay
deferred; the full goal remains active and incomplete.

## Native support and transition contract

The [support contract](native-language-transition.md) consolidates the current
profile, deliberate omissions, source/host migration responsibilities, native
artifact transition, and remaining release work. It preserves separate language,
package, and artifact identities rather than treating the Rust crate version as
a language version. No default engine or version changed.

[Current and previous engine qualification](../evaluations/native_language/2026-10-16-transition/README.md)
reruns all thirty original language probes. Exactly two finite-contract
observations change; historical source and results remain intact. The evaluation
runner now records explicit expectation overrides, and the detailed semantics
no longer describes implemented numeric/boolean contracts as unsupported. The
focused Rust language-choice test, runner checks, documentation links, and
whitespace checks pass. This closes the consolidation task, not the outstanding
versioned release or human-benefit criteria.

## Native toolchain identity

`gwt version --json` and Rust `version_info()` now identify the package,
experimental language profile, explicitly unassigned language release version,
and exact case engine. The editor's **GWT: Show Engine Information** reports
the active Python or native implementation without saving or executing source.
It fails explicitly for unavailable or malformed native identity responses.

The [identity checkpoint](../evaluations/native_identity/2026-10-16/README.md)
records 431 Rust tests and Clippy on both supported toolchains, installed and
relocated CLI agreement with an independent Rust host, 18 host observations,
288 concurrent executions, and actual editor checks in both modes. Twelve
finite-contract cases preserve their complete observations across the engine
change; originals and unapproved migration proposals are retained. No language
release number, package version, default engine, or publication changed.

Identity tooling is complete for these surfaces. A stable native language
release/support commitment and actual human-benefit evidence remain separate
requirements; human sessions and external pilots remain deferred.

## Direct Python/native CLI performance and available model route

The [direct CLI comparison](../evaluations/native_performance/2026-10-16-python-cli/README.md)
measures 360 fresh invocations on three shared policies. Median Python timings
are 113.4–118.0 ms and optimized native timings 1.7–3.9 ms, with independent
result checks. These are complete CLI costs with different output envelopes,
not isolated evaluator throughput or embedded-service measurements.

The owner pointed out that Codex CLI is available. Its current ChatGPT sign-in
and the earlier live refund trial establish an available alternative evaluation
route. Missing API credentials block the prepared Responses runner, not model
evaluation in general. Adapting and qualifying the larger experiment for CLI
is actionable engineering work; keep its protocol/results distinct from the
Responses experiment and preserve withheld scoring. Human sessions remain pending.

## Backed-up checkpoint and live five-domain CLI comparison

The accumulated native implementation is committed as `052d14d` on
`work/native-foundation-checkpoint`, pushed to the public origin, and available in
[draft PR #2](https://github.com/georgemclaughlin/gwt/pull/2). All seven checkpoint
CI jobs passed: Python/host/editor validation and the six Rust toolchain/profile/
target combinations. Large historical generated artifacts remain local with a
compressed backup and a versioned inventory; the source suite was also verified
from an export containing only staged files.

The [live Codex CLI comparison](../evaluations/native_maintenance/2026-10-16-codex-cli/README.md)
closes the previously pending five-domain model run. It requested `gpt-6-astra`
at medium effort through CLI 0.163.0 using the existing login. Thirty independent
calls cover five policies, two languages, and three repeats. Both native GWT and
Python pass 15/15 trials on their first attempts, including all withheld cases.
There are no repairs or missing trials. This is parity on the selected tasks,
not evidence of a GWT advantage. Unequal guides and Codex built-in context are
recorded; CLI events do not independently attest the returned model.

The new transport preserves original events and usage, stops on tool/unknown/error
events, bounds process lifetime, and keeps the established public-feedback and
sealed-withheld-scoring boundary. All 678 Python tests and the retained artifact
audit pass. The current packaged native engine was separately qualified against
6,828 trusted-fixture executions before model calls. Exact live records and the
audit are versioned together; no raw API response or token cap is fabricated.

This removes the API-key obstacle for CLI-based model evaluation. The Responses
API transport remains separately unqualified live. Human comprehension, review
benefit, native release commitments and adoption remain open; human sessions and
external pilots stay pending by owner choice. The full goal is not complete.

## Consolidated native draft and executable review walkthrough

The [native language draft](spec/native-draft.md) is now the primary reference
for the experimental profile. It brings source forms, contracts, arithmetic,
state sharing, control flow, proofs, requests, scenarios, failure semantics and
conformance references into one document. Implementation bounds and tool/artifact
contracts are identified separately. The grammar retains full productions;
detailed feature notes retain design history. No native language version is
assigned and no runtime behavior changes.

[Read, change, explain, review](native-review-walkthrough.md) gives readers one
complete example: extend the delivery low-fee band from 1,000g to 1,500g while
preserving membership, overweight precedence and rejection. Fourteen candidate
scenarios pass. Nine independently specified captured requests verify exactly
two changed outcomes and one preserved failure. The helper generates an offline
review and nine pending decisions; downloaded pending choices also assess as
pending. CI runs this path on the current Rust development build.

The [qualification record](../evaluations/native_walkthrough/2026-10-16/README.md)
retains hashes, comparison counts and Playwright CLI checks. Desktop/mobile
case filtering, source/operand evidence navigation, expected rejection, and
pending-decision download pass; screenshots were inspected. All 678 Python tests
pass after explicitly classifying the native-only failure scenario in the example
inventory. The native formatter and Python layout check pass for the new source.
Local documentation links and anchors resolve.

The README now provides a short reading path instead of a long feature inventory.
These changes make the implemented language and review process easier to find;
they do not establish measured human benefit. Human sessions, external pilots,
compatibility freezing, and release decisions remain open.
