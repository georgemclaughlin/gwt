# Project status

GWT is an experimental Rust language and review tool. The
[project goal](project-goal.md) is **not yet achieved**: actual human benefit
remains unmeasured. Internal human sessions are pending and external pilots are
deferred by owner choice. Those are evidence gaps, not reasons to stop engineering.

## Current product

- Rust is the only active runtime; the installed command is `gwt`.
- The current contract is the [native draft](spec/native-draft.md), supported by
  the [grammar](native-grammar.md) and [execution model](native-execution-model.md).
- The CLI, Rust/Node embedding, VS Code integration, capture/replay, and offline
  change review are implemented for the documented experimental profile.
- The [public site](https://georgemclaughlin.github.io/gwt/) is deployed. Source
  installation and qualified GNU/musl CI artifacts are available; public binary
  releases and a versioned language release remain pending.
- [PR #2](https://github.com/georgemclaughlin/gwt/pull/2) merged the Rust cutover
  and language consistency work. [Cutover evidence](../evaluations/product_cutover/README.md)
  and [consistency evidence](../evaluations/language_consistency/implementation.md)
  record those checkpoints; current pass/fail status lives in
  [Actions](https://github.com/georgemclaughlin/gwt/actions).
- The five-domain model comparison tied at 15/15 first-attempt trials per
  language. It demonstrates neither model superiority nor human benefit.

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


## Next decisions

1. Run representative human-review sessions when participants are available.
2. Select an external integration pilot when the owner chooses to begin one.
3. Freeze a supported language scope and qualify its migration contract before
   assigning a language release version.
4. Use the [release checklist](release-checklist.md) for public distribution.

## Evidence and history

- [Feature-to-evidence matrix](native-conformance.md): implementation coverage.
- [Evaluation index](../evaluations/README.md): results, limitations, and reproduction.
- [Documentation index](README.md): current guides versus historical plans.
- [Contributor guide](contributing.md): commands for fresh verification.
- [Full pre-cleanup ledger](https://github.com/georgemclaughlin/gwt/blob/52f56d34b117f2bccd8e3f70bde4381d3a3d2b8b/docs/project-goal-progress.md): immutable
  implementation chronology, earlier counts, commands, and checkpoint identities.
  Its historical pending/complete statements do not override this current page.

Keep this page a concise current status. Store new dated observations under
`evaluations/` and link their summaries; do not append another chronological log
here or rewrite old evidence to match a new engine.
