# Review and promote a native corpus across engines

A corpus can contain cases captured by different native engines, plus cases
already belonging to the current engine. Whole-corpus migration reconciles every
entry, presents the evidence in one offline page, and exports a separate corpus
only after every entry has a matching explicit acceptance. It preserves IDs,
labels, entry order, source, targets, inputs, and execution limits.

## Select the previous engines

Supply an operator-owned engine map. Paths are never taken from saved cases:

```json
{
  "kind": "gwt.native-migration-engines",
  "schemaVersion": 1,
  "engines": [
    {
      "sourceDigest": "sha256:62cee770b291bfffe3082c8a81d6c2a1aba57013b78b562b6b4d6345f1c7e0d7",
      "executable": "/path/to/previous/gwt-native"
    }
  ]
}
```

Each digest is the saved case's `record.engine.sourceDigest`. Add one mapping
for each previous engine needed by the corpus. Relative executable paths resolve
against the map file's directory. Duplicate digests and unknown fields are
rejected. Empty maps are allowed for a corpus containing only current-engine
cases. Unused mappings do not authorize any process execution.

The selected executables are trusted local tools, with the same process boundary
as [single-case migration](native-migration.md#what-is-verified). Each old case
is replayed by a frozen copy of its selected executable; the full observation
must match before current-engine recapture. The executable's actual byte digest
is bound into that case's proposal. Selection by digest is not binary publisher
authentication and execution is not sandboxed.

## Prepare and review the complete transition

```sh
gwt-native migrate-corpus original.corpus.json --engines engines.json \
  --html corpus-migration.html --decisions-template corpus-decisions.json \
  > corpus-migration.json
```

Optional output paths must be new files. The report retains every corpus entry:

| Row status | Meaning | Eligible for acceptance |
| --- | --- | --- |
| `observation_preserved` | Previous replay verified; current observation is identical | Yes |
| `observation_changed` | Previous replay verified; current observation differs | Yes, after reviewing the change |
| `current_verified` | The saved case already uses the current engine and replays exactly | Yes; export retains this case unchanged |
| `candidate_unavailable` | Previous replay verified, but the current engine could not capture the frozen case | No |
| `baseline_mismatch` | A current-engine case failed to reproduce its saved observation | No |
| `unavailable` | Invalid case, missing engine mapping, previous replay failure, or another verification error | No |

Failures stay visible while the other entries are processed. `complete` means
all entries have verified candidate observations; it is not approval. `approved`
is always false. The command exits successfully only when complete, but an
incomplete report can still produce an offline page and pending decisions.
Invalid corpus structure or overall size limits stop report creation.

The page supports search by ID/label, changed/unavailable/pending filters,
per-case choices and notes, before/after observations, explicit outcome/state/
evidence differences, and source/operand navigation. Operand links remain within
their own corpus entry. Missing evidence cannot be accepted through the page or
library. Downloaded report JSON retains exact large integers. All recorded cases
remain readable without JavaScript; decision controls and filters need it.

Decisions start pending. Every non-pending choice, including acceptance,
requires a reviewer name and note. The name is self-reported. Download decisions
to save them, or load a previous file for this exact report. Invalid, stale,
duplicate-key, oversized, incomplete, or unavailable-case acceptances are refused
without changing the current form. Filters never remove entries from saved
choices or alter the requirements for export.

## Assess and export

```sh
gwt-native assess-corpus-migration original.corpus.json --engines engines.json \
  --decisions corpus-decisions.json
gwt-native export-corpus-migration original.corpus.json --engines engines.json \
  --decisions corpus-decisions.json --output migrated.corpus.json \
  > corpus-export.json
```

Both commands independently rerun every required replay and recapture. They
rebuild the complete report and require its integrity to match the saved
choices. A change to membership, ID, label, order, source, input, limits, observed
behavior, target engine, or used previous executable invalidates those choices.
No supplied report or transcript replaces fresh execution in these CLI commands.

Assessment exits successfully for valid matching decisions, including pending,
rejected, and needs-information choices. Inspect `allAccepted` and the counts.
Export requires `allAccepted`; it cannot omit unresolved cases or publish a
partial selection. The exported corpus has the ordinary `gwt.native-corpus`
schema 1 shape. Migrated entries contain schema 3 cases with parent provenance;
current-engine entries retain their existing cases exactly. Even failed requests
or scenarios can be retained when their complete failure observations verify.
Acceptance approves the observation's inclusion, not a claim that execution
succeeded or the policy is correct.

Export creates one new file and refuses any existing destination, including the
original corpus path. No corpus is edited in place. The receipt identifies the
new corpus and includes the assessment's original-corpus, report, and decision
identities. Retain the original corpus, complete report, decisions, and receipt
together. The exported corpus alone does not contain reviewer decisions or the
full transition history. As with single-case artifact writes, an I/O failure can
leave an incomplete new file; a successful exit is required before using it.
Multiple optional output files are not a transactional write.

## Formats and bounds

- `gwt.native-corpus-migration`, schema 1: target engine, original corpus
  integrity, coverage totals, every row and its evidence, and report integrity.
- `gwt.native-corpus-migration-decisions`, schema 1: exactly `kind`,
  `schemaVersion`, `reportIntegrity`, `reviewer`, and `decisions`. Each decision
  has exactly `id`, `status`, and `note`; statuses are `pending`, `accept`,
  `reject`, and `needs_information`. Every report ID must appear exactly once.
  Decision order may differ; corpus order is fixed by the report.
- `gwt.native-corpus-migration-assessment`, schema 1: report, decision, and
  original-corpus identities; reviewer; decision counts; and `allAccepted`.
- `gwt.native-corpus-migration-export`, schema 1: output path, new corpus
  integrity, and complete assessment.

Canonical JSON hashes use these domains followed by a zero byte:
`gwt-native-corpus-sha256-v1` for a normalized corpus,
`gwt-native-corpus-migration-sha256-v1` for the report excluding `integrity`, and
`gwt-native-corpus-migration-decisions-sha256-v1` for decisions. Object key order
and file whitespace do not affect identity. Entry order and all metadata do.
Hashes bind content; they do not authenticate people or executables.

Normal corpus limits remain 1–256 entries and 64 MiB, with existing per-case
bounds. Engine maps allow 256 mappings, 64 KiB total, and 4096 UTF-8 bytes per
executable path without controls. Reports are capped at 128 MiB and rendered
pages at 256 MiB. Decision files allow two MiB; reviewer names allow 256 UTF-8
bytes without controls, notes 4096 bytes per entry. `--timeout-ms` is a per-case
previous-process timeout, default 30000 and range 1–60000. Work is sequential;
this does not impose a whole-corpus wall-clock deadline or production isolation.

The library exposes immutable `CorpusMigration`, `CorpusMigrationDecisions`,
`prepare_corpus_migration`, `assess_corpus_migration`,
`promote_corpus_migration`, `render_corpus_migration_html`, and `corpus_integrity`.
`Corpus::entries()` provides read-only access. Preparation's executor callback
must actually run the trusted previous engine for the supplied case and return
its verified response and executable digest. The library cannot authenticate a
transcript. Current-engine cases replay locally without invoking the callback.
Promotion returns a new validated corpus and assessment; filesystem writes are
owned by the CLI or host.

## Evidence and remaining scope

Six corpus-migration tests cover mixed engines/current cases, unchanged metadata,
independent hash encoding, stale/partial/invalid decisions, all non-acceptance
states, unsupported/corrupt/unverified cases, exact HTML, operand IDs, explicit
engine-map handling, fresh execution, and refusal to overwrite or partially
export. [Executable and browser qualification](../evaluations/native_migration/2026-10-16-corpus/README.md)
reconciles 19-entry complete and 21-entry incomplete corpora using retained real
engines. All choices are synthetic; no live corpus is approved or modified.

This workflow promotes complete frozen-source corpora across engines. Adapting
source that a new engine rejects remains separate unfinished work. Deployment
qualification, authenticated approval systems, and evidence of human benefit
are not supplied by these checks.
