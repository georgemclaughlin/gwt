# Common branch-exit proofs — 2026-10-16

Native continuation analysis now retains successful REQUIRE and nested
continuation proofs common to all paths that can reach the next statement.
IF/DECIDE, kind/value dispatch, and both FIND outcomes participate. Local bindings,
called-helper postconditions, and possibly empty FOR loops do not establish
outer facts. Runtime guards protect the joined presence/kind facts through the
containing body's remaining execution. See the [semantics](../../../docs/native-branch-proofs.md).

## Policy and source adaptation

The new [collection authorization example](../../../examples/native_branch_proofs/README.md)
checks counter and locker requirements separately, then reads the common receipt
reference afterward. Seven embedded scenario executions include intended failures.
All 32 independent mode/check/proof inputs have the expected outcomes. A candidate
that removes the locker check changes exactly two outcomes.

`workflow/` retains actual capture, migration, replay, and corpus review evidence:

- All 32 old-engine cases from an equivalent source with duplicated branch
  endings migrate with their complete observations preserved.
- Comparison with the new shared ending preserves all outcomes and state.
  Evidence changes in all 32 cases because execution locations change. Twenty-eight
  cases remain intended assertion failures, visible as candidate failures in the
  review; they are not silently counted as successful requests.
- All 57 actual retained portfolio cases from the preceding CLI-budget engine
  migrate with complete observation preservation and replay on the new engine.
- Two alias-clearing cases deliberately change from success to
  `presence_mutation`, retaining the original value and no successful write event.
- Two cases with a later presence check become unavailable on the new engine:
  the value is already refined, making the old check redundant. Their failed
  compilation remains explicit instead of disappearing from migration evidence.
- Originals remain unchanged and every migration proposal remains unapproved.

The generated `adaptation.html` and `fault-review.html` are review artifacts.
Browser interaction/visual verification remains pending after browser unavailability;
no browser approval or human comprehension result is claimed.

## Tests, packaging, and editor

All **388 Rust tests** and warning-free Clippy pass on Rust **1.85.0 and 1.96.0**.
Six new test groups cover independent policy results, common and missing proofs,
FIND/empty collections, optional/kind joins and alias writes, guard release, exact
source/evidence/budget behavior, replay/scenario generation, and payload navigation.
The existing early-return test now treats branch REQUIRE proofs according to the
new deliberate semantics instead of expecting the old checker refusal.

`package/` qualifies a fresh static musl release: independent source fingerprint
and dependency verification, packaged library tests, eighteen host/installed/
relocated CLI profiles, eighteen relocated case replays, and 288 concurrent host
executions. No new container-runtime or production deployment claim is made.

Native executable SHA-256:
`0008ff9638d89f930b25a28faeae8765a1b0f4368193f966324296d9a12c4c6f`.
Engine source identity:
`sha256:dadbf1c27369642ae87f33d22ce0860aeed68c36ba18958cdfece7e946c61941`.
The retained executable is under the workspace recorded in the package report.

`editor/` passes **39 checks** in installed VS Code **1.137.0**, including the
new common-proof navigation test over unsaved Unicode/CRLF source and imported
types. Removing either required branch fact diagnoses the unsafe continuation;
restoring it clears the error without changing saved files. These are editor
integration checks, not participant observations.

All **658 Python tests**, **74 example formatting checks**, sixteen top-level
checks, both reference workflows, and ten JavaScript tests pass. The initial
Python run found the new native-only example missing from the explicit registry;
it is now registered against `branch_proofs.rs`, while formatting still covers
it. The final run is `python-tests-final.log`; the initial log remains retained.

`maintenance-fixtures/` freshly qualifies the five-domain maintenance corpus on
this packaged engine: all 6,828 baseline/correct/faulty reference executions meet
their independent expectations, with thirty frozen paired task records. Earlier
experiment artifacts remain tied to their previous engine; no live model result
is inferred from this fixture requalification.

## Reproduce and limitations

```sh
cargo test --locked --test branch_proofs --test early_returns
python evaluations/native_editor/qualify_branch_proofs.py --native /path/to/new/gwt-native --previous-engine /path/to/previous/gwt-native --output /path/to/new-qualification
```

The previous executable must own the preceding CLI-budget portfolio cases.
The output directory must be new. Changes to the engine are explicit; older
maintenance/review artifacts retain their qualified executable and identities.
No model was called and no human participated. Independent semantics, broader
language/deployment work, and demonstrated human benefit remain part of the
active full project goal.
