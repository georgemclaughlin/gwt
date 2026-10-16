# Recovery checkpoint — 2026-10-16

## Latest recovery: language decisions and nested record validation

The project goal, progress ledger, Rust foundation, editor completion, and latest
[language-choice qualification](../evaluations/native_language/2026-10-16/README.md)
are present after the reported crash. Fresh SHA-256 checks match all forty
checkpoint source/artifact entries and all 57 native engine inputs: 97 checks,
no mismatches. The checkpoint checks include the retained native executable.
No matching test or evaluation process remained running at inspection.

The saved qualification records 410 Rust tests on each supported toolchain,
670 Python tests, and 96 repository checks passing. These full suites were not
rerun during recovery; a fresh `git diff --check` passed. The latest completed
work documents thirty language-choice probes and fixes Python validation of
declared nested record fields.

The interrupted next task was investigation of regression testing for captured
boundary and resource failures. No implementation edits for that task had been
made at the saved handoff. Resume by inspecting existing case comparison and
scenario-generation semantics before deciding how to expose such regression
expectations. Resource exhaustion must remain distinct from an ordinary passing
domain scenario.

All existing uncommitted and untracked work is preserved. No commit or push was
made. This inspection cannot establish whether unsaved editor buffers were lost.
The full goal remains active and incomplete; human evidence and live model
comparison remain outstanding, and external pilots remain deferred.

## Earlier recovery: example audit and feature-flag contracts

The reported crash left the comprehensive [goal](project-goal.md), Rust
foundation, example audit, feature-flag changes, test logs, and four new
documentation files on disk. The interrupted work was the final verification
record and progress-ledger update; those are now completed in the
[feature-flag checkpoint](../evaluations/feature_flags/2026-10-16/README.md).

The retained full runs passed 401 Rust tests on each supported toolchain and
666 Python tests. Fresh recovery checks passed 97 example/reference, extension,
formatting, and documented-command checks. The engine's 56 source/build hashes,
packaged executable, and audited example sources were checked against the saved
records. See the checkpoint's `verification.json` for identities and evidence.
Full suites and the 18,816-run comparison were not repeated during recovery.

The [audit](../evaluations/native_validation/2026-10-16-example-audit/README.md)
provides a concrete next-work list: remaining explicit parameter contracts,
closed domain reasons, lookup adaptations, and underwriting arithmetic policy.
Actual human review and live native model comparison remain outstanding;
external pilots remain deferred. The full goal remains active and incomplete.
Existing uncommitted and untracked work is preserved. No commit or push was made.
This inspection cannot establish whether unsaved editor buffers were lost.

## Earlier recovery: typed input boundary and grammar audit

The latest crash inspection found the project goal, progress ledger, Rust
foundation, and completed contact-input qualification on disk. All 56 native
engine source/build inputs, eleven files hashed by the contact qualification,
and the retained static executable match their recorded SHA-256 hashes:
68 checks, no mismatches. No matching test or evaluation process remained
running at inspection.

Fresh checks passed both Python empty-object regression tests, all three Rust
contact-input integration tests on 1.96.0, and `git diff --check`. The retained
[full qualification](../evaluations/input_normalization/2026-10-16/README.md)
records 666 Python tests and 394 Rust tests on each supported toolchain. Those
full suites were not rerun during this recovery check.

The interrupted work was a native grammar audit. Source inspection had begun;
no separate `docs/native-grammar.md` had been written. Resume by documenting the
experimental native syntax against the parser, distinguishing it from the
Python v0.2 grammar and linking it to the execution-model guide. Confirm any
suspected documentation contradictions against implementation before editing.

That audit was subsequently completed in the
[native grammar checkpoint](project-goal-progress.md#native-grammar-and-context-rules-2026-10-16).
Use the progress ledger for current work.

Live native model comparison, actual human-review evidence, and interactive
browser validation remain outstanding. External pilots remain deferred. The
full goal is active and incomplete. Existing uncommitted and untracked work is
preserved; no commit or push was made. This inspection cannot establish whether
unsaved editor buffers were lost.

## Earlier recovery: common branch proofs

The latest crash check found the project goal, implementation, examples, and
[completed branch-proof qualification](../evaluations/native_editor/2026-10-16-branch-proofs/README.md)
on disk. All 56 engine source/build inputs and eight additional checkpoint files
match their recorded SHA-256 hashes. The retained static native executable also
matches its recorded hash. No evaluation or test process remained running at
inspection.

A fresh Rust 1.96.0 run passed all fourteen branch-proof and early-return tests;
`git diff --check` passed. The retained full-suite logs record 388 Rust tests on
each supported toolchain and 658 Python tests. Those full suites were not rerun
during this recovery check.

The next planned work was an audit of the native language documentation for
contradictions and a clearer execution-model guide. No edits from that audit
had been made at the saved checkpoint. Live native model comparison, actual
human-review evidence, and pending browser validation remain outstanding;
external pilots remain deferred. The full project goal is active and incomplete.

The documentation audit was subsequently completed as the
[connected execution-model checkpoint](project-goal-progress.md#connected-native-execution-model-2026-10-16).
Use the progress ledger for work completed after this recovery inspection.

The extensive uncommitted and untracked work is preserved. No commit or push
was made during recovery. This check cannot establish whether unsaved editor
buffers were lost.

## Earlier recovery: maintenance scorer

The later reported crash left the isolated native maintenance scorer, its test
logs, and completed reports present. The full Python run finished with 641 tests
passing; the final focused run passed twelve tests. No evaluation containers or
maintenance evaluation/test processes remained at inspection. Fresh full-score
and initial public-feedback runs were made in new directories against the final
scorer files. The [scorer checkpoint](../evaluations/native_maintenance/2026-10-16-isolated/README.md)
records evidence and remaining work. Its documentation and progress ledger are
now updated. No commit, push, release, live model call, or external pilot was made
during recovery. Unsaved editor buffers cannot be recovered or verified here.

The subsequent [experiment checkpoint](../evaluations/native_maintenance/2026-10-16-experiment/README.md)
connects the native public-feedback/scoring workflow to a frozen model experiment
and qualifies orchestration with synthetic responses and real containers. Live
API/model qualification remains pending because no API key was configured.
Representative human review evidence also remains pending. The full project goal
is active and incomplete. Preserve the extensive existing uncommitted/untracked work.

## Earlier recovery: profiling

The project goal, Rust foundation, examples, evaluation artifacts, and unfinished
profiling implementation were present after the reported computer crash. This
check establishes the state of the recovered working tree; it cannot establish
whether any unsaved editor buffers were lost.

## Verified during recovery

- `cargo +1.96.0 test --workspace --locked` completed successfully, including
  all six new profiling tests.
- The pending Rust 1.96.0 workspace Clippy check completed successfully with
  warnings denied.
- `cargo +1.96.0 fmt --all -- --check` and `git diff --check` passed.
- The [project goal](project-goal.md) and [progress ledger](project-goal-progress.md)
  remain present. The full goal is still active and incomplete.

No implementation changes, commits, pushes, or releases were made during this
recovery check. The working tree contains extensive uncommitted and untracked
work from the preceding implementation; preserve it when resuming.

## Interrupted work

The latest implementation adds `gwt-native profile` and the Rust
`CompiledProgram::profile_request` / `profile_scenario` APIs. They execute one
request or scenario with its normal limits and report exact retained evidence
bytes, grouped by operation and source span, together with the execution step
count and diagnostic. Failed executions retain partial accounting. Profiling
does not measure elapsed time, memory, or the budget needed to finish a refused
execution.

Implementation is in `crates/gwt-core/src/profiling.rs`, with CLI integration in
`src/main.rs`, exports in `src/lib.rs`, and six integration tests in
`crates/gwt-core/tests/profiling.rs`. The tests cover independent byte accounting,
deterministic ordering, failures and limits, imported source locations, report
size bounds, and CLI selection. These files survived the crash.

## Resume here

These recovery tasks were subsequently completed in the
[profiling checkpoint](../evaluations/native_editor/2026-10-16-profiling/README.md).
The list below records what remained at recovery time; use the
[goal ledger](project-goal-progress.md) for current progress.

1. Finish profiling documentation and link it from the native usage guides.
   Explain partial results, value/metadata byte definitions, and the separate
   eight-MiB profiling bound.
2. Verify the new code on the minimum supported Rust version, 1.85.0. The prior
   append-evidence checkpoint passed there; the new profiling work has not yet
   been requalified there.
3. Complete profiling qualification against representative successful and
   evidence-limited workloads, and verify ordinary observations across explicit
   migration from the retained append-evidence engine. Record actual results.
4. Qualify packaging and the independent host API before claiming packaged
   profiling support. Previous static release qualification predates this work.
5. Update the progress ledger with completed evidence and remaining limitations.

The last completed feature checkpoint is
[append evidence growth](native-append-evidence.md), with retained results under
`evaluations/native_editor/2026-10-16-evidence-growth/`. Larger allocation inputs
still exhaust the default evidence budget. Visual review validation remains
pending after browser unavailability. Human benefit remains unmeasured, and the
owner's instruction to defer external pilots still applies.
