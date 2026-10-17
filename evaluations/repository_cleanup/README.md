# Repository cleanup qualification

Reference before cleanup: `52f56d34b117f2bccd8e3f70bde4381d3a3d2b8b`.
This is a storage, documentation, and CLI maintenance change, not a new language
feature or evidence of human benefit.

- Archived 66 raw files (9,561,378 bytes) in immutable Git history. Restored the
  complete historical evaluation tree into a fresh directory and verified every
  archived size and SHA-256 against `evaluations/archive.json`.
- Audited the restored 30-call Codex experiment: original prompts and response
  seal verify; scores match original observations; runner sources are unchanged.
- Compared parsed original/current fixture JSON: all 1,072 underwriting and
  630 rounding cases, their values, and order are identical. Neither corpus has
  duplicate cases after excluding case IDs; no regression cases were removed.
- Consolidated current status and added documentation/architecture indexes.
  The full original ledger remains available at the reference revision.
- Shared paired-option validation across five CLI loops. Existing successful
  command tests and new rejection checks across ten commands pass.
- Rust 1.85.0 and 1.96.0 each pass 438 tests; current-toolchain fmt and Clippy pass.
  Python passes 62 tests, the editor 16, and the Node host 13.
- A clean staged export passes all 62 Python tests and product verification:
  28 example entries, nine download cases, two outcome changes, one expected
  failure, and install/upgrade/uninstall checks.
- All nine pre-cleanup delivery cases replay with the original executable and
  report `observation_preserved` through explicit migration to the new engine.
  Site/download artifacts were freshly generated; review decisions remain pending.
- Desktop (1440px) and mobile (390px) review pages retain syntax highlighting,
  render without horizontal overflow, and produce no JavaScript errors.

Reproduction commands are in the [contributor guide](../../docs/contributing.md)
and [archive instructions](../README.md#archived-raw-evidence). The archived
originals are observations, not inputs to be silently regenerated. Git history
is retained, so this cleanup does not reduce full-clone history size.
