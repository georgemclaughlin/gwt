# Goal evidence audit — 2026-10-16

The engineering foundation is substantial. The full
[project goal](../../../docs/project-goal.md) remains unachieved because actual
human understanding and review benefit have not been demonstrated.

The owner explicitly chose **Keep human sessions pending** on 2026-10-16.
External pilots remain deferred. These choices do not pause engineering work,
authorize recruitment, or waive the goal's human-benefit criterion.

## Fresh qualification

Both fixture runners completed successfully using native engine
`sha256:79444fc4a87f366006de4d4be90ac3bf3fb81a8789bea9e01071e0a2adb8d42b`.
The binary SHA-256 is
`3f5e08d4fcfc56f1ce80c954b2152361c059a7088db78533d4f0d9e5eb61bf7c`.

| Evidence | Result | What it establishes |
| --- | --- | --- |
| Human-study fixtures | 1,305 executions across four domains and three engines | Baseline, correct, and intentionally faulty candidates behave as specified, including prediction questions |
| Native maintenance fixtures | 6,828 executions; 1,138 independent probes per revision across five domains | Correct revisions satisfy the requested policy; baseline and faulty revisions exhibit the expected differences |
| Current engine source | All 60 manifest inputs match the finite-contract checkpoint | The retained engine corresponds to the audited runtime sources |

The maintenance scores intentionally include failures for baseline and faulty
candidates against the requested new policy. They are expected experimental
controls, not failed qualification. There were **zero live model calls and zero
human participants** in these runs.

Reproduction (substitute the current qualified native binary if relocated):

```sh
python -m evaluations.human_review.qualify \
  --native /home/g/.cache/gwt-qualifications/finite-literals-79444fc4/gwt-native \
  --output /tmp/gwt-human-fixture-qualification.json
python -m evaluations.native_maintenance.study \
  --native /home/g/.cache/gwt-qualifications/finite-literals-79444fc4/gwt-native \
  --output /tmp/gwt-native-maintenance-audit
git diff --check
```

## Evidence boundaries

- The [small live refund comparison](../../maintenance/2026-10-15/gwt-report.json)
  and [Python arm](../../maintenance/2026-10-15/python-report.json) tied: each
  passed nine code tasks on the first attempt and three clarification tasks.
  This does not establish superiority or predict the larger experiment.
- The [five-domain model experiment](../../native_maintenance/experiment.md)
  prepares 30 trials with public repair feedback and withheld scoring. Its
  provider rehearsal is synthetic. No API key was configured in this audit
  process; the live experiment remains outstanding.
- The [human study](../../../docs/human-review-study.md) compares source review.
  It cannot establish explanation-workbench benefit, authoring productivity,
  or adoption. Browser rehearsals remain apparatus checks.
- The [current browser checkpoint](../../native_browser/2026-10-16-finite/README.md)
  records 1,578 complete execution comparisons and 1,626 total checks across
  two WASM builds and three browsers. Linux WebKit is not Safari qualification.
- The [language checkpoint](../../native_language/2026-10-16-finite/README.md)
  records 429 Rust tests on both supported toolchains and 671 Python tests.
  Those are retained checkpoint results, not full-suite reruns during this
  documentation audit. Historical performance measurements likewise retain
  their original engine and workload scope.

## Remaining decisions

Prepare a consolidated native scope and version-transition contract from the
existing semantics, grammar, decision register, and conformance evidence.
Deliberate omissions are not automatic compatibility bugs. Additional syntax,
platforms, editor completion, and debugging need concrete workflow justification.
The current experimental profile is not a new published language version.

Human evidence remains necessary for the full goal. External-pilot and final
publication gates in the release checklist remain separate and unchanged.
The [progress ledger](../../../docs/project-goal-progress.md) now distinguishes
these missing outcomes from already-qualified engineering and optional work.
