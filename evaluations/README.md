# Evaluation sources and retained evidence

Current product qualification is recorded in [product_cutover](product_cutover/README.md).
Dated evidence remains immutable. Historical Python-runtime harnesses were
retired; reproduce them from the reference commit in
[the retirement inventory](../docs/retirement-inventory.json).
Independent policy oracles, ordinary-Python comparison fixtures, human-study
preparation tools, and native package/editor/browser qualification remain active.
Actual human sessions and external pilots remain pending.


This directory contains reproducible evaluation tools, independent fixtures,
curated checkpoint summaries, and selected observations. Real model results are
labeled separately from synthetic rehearsals. There are no human-participant
results in the current checkpoint.

## Archived raw evidence

Bulky execution captures, three full comparison reports, two retired Python
runtime snapshots, and the local-artifact inventory are archived at an
[immutable Git revision](https://github.com/georgemclaughlin/gwt/tree/52f56d34b117f2bccd8e3f70bde4381d3a3d2b8b/evaluations).
[`archive.json`](archive.json) lists all 66 removed files with sizes and SHA-256
checksums. Their bytes remain in repository history, without rewriting results,
source identities, or reviewer decisions. This reduces the checked-out tree and
review noise; it does not shrink existing Git history or full-clone downloads.

Restore the original evaluation tree, including the archived files and the
reports that reference them, into a new directory:

```sh
python tools/evidence_archive.py --output /tmp/gwt-historical-evidence
python -m evaluations.native_maintenance.verify_codex_run /tmp/gwt-historical-evidence/evaluations/native_maintenance/2026-10-16-codex-cli/live
```

The first command verifies every archived file against the manifest and refuses
an existing destination. It needs Git history (`git fetch --unshallow` for a
shallow checkout). The second audits the original model records without model
calls or candidate execution. New results are new evidence, never replacements
for historical observations. Historical relative links to archived files work
in the restored tree or when browsing the pinned revision.

The original development checkout also contains roughly 600 MiB of ignored
screenshots, HTML reports, and compiled outputs. Those were never versioned;
the archived `local-artifacts.json` identifies their local originals, but cannot
restore their bytes. A local backup was made at that checkpoint.

## What belongs in the working tree

Keep independent fixtures, reproduction tools, concise result summaries, and
regression inputs needed by the test suite. Existing smaller qualification
records remain available. Put new raw execution captures and generated browser
or package outputs in fresh ignored run directories; do not bulk-add them to a
PR. Preserve original evidence before archiving it and provide a pinned source
and checksums. Summaries must distinguish real observations from rehearsals.

Useful entry points:

- [Current goal and evidence ledger](../docs/project-goal-progress.md)
- [Human-review study](../docs/human-review-study.md), with sessions pending
- [Five-domain maintenance experiment](native_maintenance/experiment.md)
- [Native identity qualification](native_identity/2026-10-16/README.md)
- [Python/native CLI timings](native_performance/2026-10-16-python-cli/README.md)
- [Earlier live refund comparison](maintenance/2026-10-15/README.md)
