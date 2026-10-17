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

The development history also produced roughly 600 MiB of generated HTML,
repeated full execution captures, browser screenshots/logs, and compiled package
artifacts. Those files remain on the development machine and are excluded from
Git. A local compressed backup was made before the checkpoint; no originals were
deleted. [`local-artifacts.json`](local-artifacts.json) records their paths,
sizes, and SHA-256 digests so references in historical reports are explicit.
That inventory identifies bytes; it does not validate their claims or imply
that Git contains them.

Historical reports may link to these local artifacts. Such links are available
in the original development checkout, not necessarily in a fresh clone. Use the
recorded qualification commands to produce new evidence in a fresh output
directory. Historical engine identities require the matching retained source
and executable; a current run cannot silently recreate an old engine checkpoint.
Do not overwrite old evidence or report a rerun as the original observation.

Source, test fixtures, reproduction scripts, compact qualification records, the
live refund comparison, the complete five-domain Codex CLI comparison, and the
direct Python/native CLI benchmark are versioned.
Tests run from a clean staged checkout before committing to verify that local
generated artifacts are not required for the source regression suite.

Useful entry points:

- [Current goal and evidence ledger](../docs/project-goal-progress.md)
- [Human-review study](../docs/human-review-study.md), with sessions pending
- [Five-domain maintenance experiment](native_maintenance/experiment.md)
- [Native identity qualification](native_identity/2026-10-16/README.md)
- [Python/native CLI timings](native_performance/2026-10-16-python-cli/README.md)
- [Earlier live refund comparison](maintenance/2026-10-15/README.md)
