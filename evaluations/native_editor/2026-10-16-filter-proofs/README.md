# Collection filter proof checkpoint

FOR/FIND WHERE conditions now establish supported true presence/kind facts in
each selected body. This removes repeated inner conditions while preserving
explicit traversal, first-match behavior, and missing-case handling. The language
uses existing syntax; see [native filter semantics](../../../docs/native-filter-proofs.md).

## Correctness and tooling

- **319 native tests** pass on Rust **1.85.0** and **1.96.0**, both in development
  mode and in static musl release mode. Clippy with warnings denied passes on
  both versions. Logs and [checked counts](test-counts.json) are retained here.
- Eight new semantic test groups exercise optional scalar items and nested fields,
  safe/unsafe boolean proofs, item aliases and ancestor replacement, allowed kind
  sets, exact shared contracts and copies, external-state filters, live later-item
  updates, returns, caught failures, body/caller guard cleanup, FIND fallback,
  Unicode/CRLF scenario evidence, and every step budget through a complete run.
- The [pickup example](../../../examples/native_filter_proofs/README.md) has five
  scenarios and **15** top-level expectations. Independent inputs cover **57**
  empty, single-item, and ordered two-item queues, including missing routes,
  courier routes, unready/ready counters, empty codes, duplicates, and existing
  prepared flags. Request observations capture/replay and generate runnable
  scenarios. Item state and output order match independent expectations.
- The twentieth editor type/navigation test checks both FOR/FIND bodies, nested
  optional fields and optional list items, copied payloads, equal-shaped kind
  declarations, and checked hover types. The installed static executable passes
  **28 actual VS Code checks** in [the retained result](editor-installed/extension-host.json),
  including removal/change of an unsaved filter and exact source diagnostics.
- **627 Python tests**, all example formatting, top-level checking, reference
  order/tour workflows, five extension unit tests, and formatting checks pass.
  Python checking accepts the example, but execution fails on its nested optional
  route initializer; [the diagnostic](python-validation.json) is retained and
  the example is explicitly assigned to native execution.

The implementation stores filter guards in the checked iteration, refines its
local environment before checking the body, and activates guards only after a
true selection. The existing guarded-body path releases them on normal exit,
return, and failure. Caller/surrounding guards remain active. The selection
predicate itself is not frozen: ordinary boolean fields may change, and later
visits read current state. FIND's fallback gains no filter facts.

## Policy review and engine change

[Independent expectations](policy/independent-expectations.json) and all 57
captured inputs are retained. Removing readiness produces exactly **14** changed
outcomes and states. The [review JSON](policy/review.json) and
[offline review](policy/review.html) contain all cases, with no unavailable case,
baseline mismatch, or candidate failure. Source/evidence changes are retained
separately from outcome changes. No new browser check is claimed for the
unchanged renderer, and no human review approval was recorded.

The [explicit engine transition](policy/guard-migration.json) captures a real
compatibility change. The previous engine allowed a selected optional value to
be cleared through a second traversal alias. The new engine rejects that write
with `presence_mutation`, preserves the prior item value, and records no
successful set event. The previous case remains byte-for-byte unchanged, and
candidate replay verifies the full failure observation. This is an unapproved
proposal. Narrowed shared helper contracts can also reject old source; broader
compatibility is not inferred from a preserved regression corpus.

## Packaging and execution

The [final static package qualification](package-1.96.0-final/qualification.json)
passes three library tests, two embedded scenarios, 18 host observations,
288 concurrent calls, 18 relocated-build replays, and 18 extracted-binary replays.
All **48** archived source/build inputs [match the workspace](package-source-verification.json).
All [18 invoice observations](invoice-observation-comparison.json) are preserved
against the prior engine, with a separate verified retained-case transition.

The packaged source engine identity is:

`sha256:01c54a60aa448dd8fb5df14a36dc5ed74ac2296e703fb59688c648adbf4da6ea`

The executable SHA-256 is:

`652cca32856210b7d478d725da29d96e2a7b12322bcf03ca9b37d202a2db1c07`

The executable passes the example and all 18 host replays in
[Alpine and GLIBC 2.36 containers](static-runtime/qualification.json), with no
networking, read-only mounts/filesystem, and empty PATH. These checks share the
host kernel; they do not establish arbitrary-platform or production support.

An initial package build and the first 1.85.0 static release attempt hit the
`/tmp` filesystem's disk quota. Their logs remain under `package-1.96.0/` and
`rust-1.85.0-musl-release-tests.log`. Those processes were confirmed terminal
before retrying in fresh scratch directories on the main filesystem. The
successful package uses `TMPDIR=/home/g/.cache/gwt-qualifications`; full native
release tests use the [recorded scratch location](build-scratch.json). Existing
executables, cases, and source artifacts were preserved.

## Reproduce

With the newly qualified executable and a retained previous engine:

```sh
python evaluations/native_editor/qualify_filter_proofs.py \
  --native /path/to/new/gwt-native \
  --previous-engine /path/to/previous/gwt-native \
  --output /tmp/gwt-filter-policy
```

The output directory must be new. The prior executable path is explicit, not
inferred from case contents. The full project goal remains active: early-return
proofs, remaining language/tooling work, production qualification, and actual
comparative human evidence remain open. Nothing was published and no external
pilot was initiated.
