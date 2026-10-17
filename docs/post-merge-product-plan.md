# GWT after the Rust cutover

Status: implementation plan, not a completed transition or published release.

The public product is **GWT**. The Rust engine owns the **`gwt` command**.
People write `.gwt` programs, run scenarios, inspect decisions, and review
changes. Rust describes the implementation; it is not a separate product tier.
The website and onboarding should describe that destination.

The owner requested this post-merge direction after reviewing the website.
The recommendation is to retire the Python runtime from the active product,
rather than maintain two supported engines. Planning this transition does not
merge the branch, publish packages, or claim that it has already happened.

## The experience we are building

1. Understand the language from a short readable policy and its result.
2. Explore a worked behavior change in the browser without installing tooling.
3. Install GWT from a supported distribution and run `gwt version --json`.
4. Open a small example directory and use `gwt validate delivery.gwt` and
   `gwt run delivery.gwt --request "quote delivery" --input parcel.json`.
5. Change the policy, compare captured requests, and review source-backed
   evidence with `gwt review`.
6. Use the editor with the same installed engine and semantics by default.

These are target commands, not the current executable names. Build paths,
repository layout, work-branch names, and engine-selection switches belong in
contributor or migration documentation. The current checkout still uses
`gwt-native`, and the Python distribution still installs `gwt`.

## One supported engine

Retire `gwtlang/` as an active runtime, its Python console entry point, Python
editor integration, and its distribution workflow. Preserve the last complete
implementation through an explicit immutable Git commit reference and historical
documentation. Old programs and artifacts can be investigated with that checkout;
the new product does not promise to execute them through a compatibility layer.

Before deletion, inventory dependencies on `gwtlang`: example validation,
formatting, model comparisons, host fixtures, and release tooling. Preserve useful
independent expected results as native conformance cases. Do not port old syntax
or whole subsystems solely because they existed in Python.

Python scripts that orchestrate tests, package qualification, or experiments may
remain when useful. They must not import the retired runtime to validate the new
product, and end users must not need Python to install or execute GWT. Historical
cross-engine experiments should pin the historical checkout instead of keeping a
second engine in the production tree. Keep their existing results unchanged.

## Cutover work, in order

### 1. Inventory and preserve the reference

- Record the exact pre-retirement commit, supported old workflows, and how to
  reproduce historical evaluations from it. No new tag is required for this.
- Classify every Python-dependent example and tool as migrate, retain as
  independent development tooling, or retire with the old implementation.
- Publish deliberate language and host-contract differences. Python HTTP serving,
  OpenAPI generation, debugging, and old evidence formats are not implied native
  features; retain only those justified by the product's intended workflows.
- Keep original saved cases and decisions intact. Native engine migration does
  not import Python artifacts or establish cross-engine equivalence.

### 2. Make `gwt` the real executable

- Change Cargo binary packaging, usage text, install manifests, host defaults,
  example helpers, CI paths, and active documentation together.
- Remove the Python package's `gwt` entry point and active package publication.
  Existing installed wheels will not change merely because the repository does:
  document their removal and check command resolution during upgrades.
- Use `gwt version --json` to identify the resolved engine. Detect an old Python
  executable in editor/host setup and give an actionable error; never silently
  fall back or select semantics based on the source file.
- Use `gwt-native` only in historical documentation. A temporary executable alias
  is optional only if a concrete existing integration needs it; it is not a
  permanent second interface.
- Keep historical artifact kind names and integrity inputs stable unless an
  actual schema change requires migration. Renaming a command does not justify
  rewriting stored evidence. Requalify any engine fingerprint change.

### 3. Make the editor and examples coherent

- Default to the Rust engine and the installed `gwt` command. Remove the engine
  picker and Python launch/debug paths from the active extension.
- Migrate existing explicit native executable overrides; explain obsolete Python
  settings. Hide unavailable actions or report their limits clearly.
- Curate a small set of runnable examples and a standalone delivery walkthrough.
  Test them with the installed executable outside the repository.
- Keep checking, formatting, running, tests, captures, and review on the same
  engine. Native validation must replace Python formatter/checker dependencies.

### 4. Present GWT to users

- Lead with readable executable behavior and a concrete before/after example.
- Use `gwt`, ordinary filenames, and a short install/run/review path throughout
  the homepage, Getting Started, README, editor instructions, and example docs.
- Provide a browser-accessible worked review, plus a downloadable example folder
  that does not require understanding this repository. Generate both from checked
  sources to prevent drift.
- Replace work-branch links with the merged documentation/source locations;
  downloadable examples and releases should identify their matching version.
- Put source builds in contributor documentation. While public distribution is
  pending, label installation availability accurately. Do not invent download
  links or imply that merging publishes an installer.
- Keep experimental status concise and factual. Explain compatibility and
  implementation history in dedicated pages rather than in the primary pitch.

### 5. Qualify distribution and upgrade

- Start with already-qualified Linux targets; offer other platforms only after
  installation and runtime checks on those platforms.
- Package the executable, license, version metadata, and checksums. Verify a
  downloaded/extracted artifact outside the source tree, without Python or Rust
  available at runtime.
- Test clean install, command resolution when an old Python `gwt` is on PATH,
  upgrade, uninstall, editor detection, and the complete delivery review.
- Keep package version, language version, and artifact schema version distinct.
  Assign release versions deliberately; Rust becoming the default does not by
  itself freeze a language version.
- Replace Python-specific publication checks with an appropriate Rust product
  release checklist while preserving explicit publication authorization and
  the owner's deferred human sessions and external pilots. A release-plan rewrite
  must not silently mark those evidence requirements complete.

## Merge readiness and publication readiness

The cutover PR should reach merge with the real `gwt` executable, one active
engine, matching editor defaults, runnable installed examples, and coherent
consumer-facing documentation. The README must describe the actual merged
product. Do not merge a promised command name while leaving Python in control
of that command.

Public distribution is a separate deliverable: qualified artifacts, supported
platforms, usable installation instructions, a deliberate version, and the
applicable release review. If publication remains deferred, the merged project
can still present a coherent developer preview with a clearly identified source
installation path.

The full [project goal](project-goal.md) still requires evidence that people can
understand and review meaningful changes. Mechanical checks and a polished site
are not substitutes for those observations. Human sessions remain pending and
external pilots deferred by owner choice.

## Acceptance checks

- `gwt version --json` identifies the Rust engine in a clean installation.
- No active runtime, editor, host example, or native validation path imports
  `gwtlang` or falls back to Python.
- The walkthrough works from its standalone example folder with the installed
  command; all stated outcomes match independent expectations.
- The editor uses that same engine without requiring an implementation choice.
- Public pages contain no work-branch links, build-directory commands, or claims
  that retired Python-only features are supported by the new engine.
- Old artifacts and historical evaluation results remain intact and traceable.
- Rust conformance, package qualification, host/editor checks, and browser checks
  pass for the supported scope; merge/publication status remains explicit.
