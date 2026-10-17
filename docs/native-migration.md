# Explicit native engine migration

Saved cases belong to the engine that observed them. Normal `replay` continues
to reject a different engine fingerprint. `migrate` prepares a separate proposal
by running a trusted previous executable first, then the current engine:

```sh
gwt migrate saved.case.json --previous-engine /path/to/previous/gwt \
  > proposed-migration.json
```

Keep the previous executable before replacing it, along with its source, build
toolchain, and dependency lockfile. The command requires an explicit executable
path; it never discovers or runs code named inside a saved case. Its input case
is read without modification. The proposal does not update a corpus or copy any
reviewer's approval to the new observation.

## What is verified

1. Load the original case and check its shape, limits, and integrity.
2. Copy the explicitly selected executable and exact case into a private
   temporary directory. Hash the executable bytes that will be run.
3. Execute that copy with `replay`. It must exit successfully and return a
   verified native replay report whose complete actual observation equals the
   original case, with no differences or truncation. Wrong engines, forged
   observations, process errors, and inconsistent reports stop migration.
4. Compile the same frozen source on the current engine and require the same
   program identity. Re-execute the same request or scenario, raw input, and
   limits. Migration cannot also change the source or relax budgets.
5. Return the original case, previous replay report, new observation, executable
   digest, engine identities, and differences as an unapproved proposal.

The previous executable is a trusted local tool supplied by the operator.
Its source fingerprint and byte digest identify it; neither authenticates its
publisher or proves that a malicious replacement is truthful. The command runs
it as a process, not in a security sandbox. The temporary copies prevent ordinary
changes to the input paths from changing which bytes are supplied to the replay.
This is not a hostile-filesystem or process-tree containment guarantee.

## Proposal and case formats

`gwt.native-case-migration`, schema version 1, has one of these statuses:

| Status | Meaning |
| --- | --- |
| `observation_preserved` | Both engines produced identical complete observations |
| `observation_changed` | Some part of the observation changed; inspect the flags and differences |
| `candidate_unavailable` | Previous replay succeeded, but the current engine could not compile/capture the frozen case |

`approved` is always false. Successful process exit means a candidate case was
produced, even if its execution failed or behavior changed. An unavailable
candidate produces a nonzero exit with a proposal containing `candidateDiagnostic`.
Failures before the previous replay is verified produce a diagnostic response
without a candidate. A case already belonging to the current engine is refused;
use ordinary replay for it.

`changes` distinguishes outcome, state, and evidence changes. Source changes are
always false: the source must be preserved. Outcome includes success/failure,
result, prints, and diagnostic code/message. Evidence includes event details,
diagnostic source locations, and step counts. The complete observation determines
status even when a difference list reaches its 128-entry limit. Both observation
and outcome lists indicate truncation explicitly. These flags describe differences;
they do not establish that a new behavior is correct.

The candidate is a `gwt.native-case` schema 3 artifact. It has one request or
scenario target and the same source/input/limits as its parent. Its mandatory
`record.migration` contains:

- `parentCaseIntegrity`, identifying the complete original case;
- `previousEngine`, identifying the engine that verified it;
- `previousExecutableSha256`, identifying the actual replay executable bytes.

Request/scenario cases captured normally still use schemas 1/2 without migration
metadata. All three schemas can replay on their own matching engine. A migrated
case can be captured in a later migration proposal, retaining an immediate-parent
chain. Keep each complete proposal to retain its original case and verification
record; the new case alone is not the entire history. Case integrity is not an
authenticated provenance signature.

The proposal's `integrity` uses SHA-256 over
`gwt-native-case-migration-sha256-v1`, a zero byte, and canonical JSON of every
field except `integrity`. Canonical JSON uses the same recursive key sorting,
UTF-8, and exact numeric representation as native cases. This binds both cases,
the supplied replay, differences, diagnostics, and executable digest against
accidental modification. It does not represent approval.

## Limits and library boundary

The previous executable is limited to 256 MiB. Replay stdout is limited to
32 MiB, stderr to 64 KiB, and the proposal to 64 MiB. The selected replay process
has a default timeout of 30 seconds; `--timeout-ms` accepts 1–60000 milliseconds.
Timeout or excess output stops the selected process and produces no candidate.
The timeout covers replay, not copying or compiling. Usual source, case, input,
execution, evidence, and JSON limits also apply. These are bounded development
operations, not a general resource-isolation service.

`prepare_migration(case, response, executable_sha256)` is the I/O-free library
entry point. Its caller **must** execute the trusted previous engine successfully
on the exact case and supply that response and executable digest. The function
checks their consistency and performs current-engine recapture; it cannot
authenticate a transcript or prove that its caller ran a process. Use the CLI
when that orchestration is needed. `CaseMigration` exposes borrowed original and
candidate cases and its integrity digest. Ordinary `replay_case` is unchanged.

## Human review, decisions, and case export

Generate a self-contained offline review alongside the proposal:

```sh
gwt migrate saved.case.json --previous-engine /path/to/previous/gwt \
  --html migration-review.html --decision-template migration-decision.json \
  > proposed-migration.json
```

Both optional output paths must be new files. The page shows before/after
outcomes, state and evidence changes, bounded field differences, source excerpts,
recorded operand links, engine identities, and frozen source. It displays old
observations as recorded facts without interpreting old source through the
current compiler. Complete observations remain in the downloadable proposal;
large integers are preserved exactly. Recorded behavior is readable without
JavaScript; decision save/load requires it. The page makes no network requests.

Choose pending, accept, reject, or needs information. A non-pending choice
requires a reviewer name and note. Download the decision file to retain it;
editing the page does not write back to the original case or template. A loaded
file must refer to this exact proposal. Invalid, duplicate-key, oversized, and
stale files leave the current form unchanged. Unavailable candidates cannot be
accepted. Reviewer names are self-reported, not authenticated identities.

Assess a saved choice against a newly verified proposal:

```sh
gwt assess-migration saved.case.json \
  --previous-engine /path/to/previous/gwt --decision migration-decision.json
```

Assessment reruns the selected previous executable, verifies the entire old
observation, and recaptures on the current engine. It then requires an exact
proposal-integrity match. Changing the previous executable bytes, engine source,
case, observations, or settings invalidates the earlier choice. The CLI accepts
no supplied proposal/transcript as a substitute for this fresh execution.
Assessment exits successfully for any valid matching choice; inspect `accepted`
and `status` to distinguish acceptance from pending, rejection, or questions.

Export requires acceptance and repeats the same fresh verification:

```sh
gwt export-migration saved.case.json \
  --previous-engine /path/to/previous/gwt --decision migration-decision.json \
  --output migrated.case.json > migration-export.json
gwt replay migrated.case.json
```

Export creates one new case file, with exact values and parent provenance.
Existing files are refused, including the original case path. The JSON receipt
records the output path, case integrity, and assessment with proposal and decision
identities. Keep the original case, full proposal, saved decision, and receipt
together. The case alone does not record the reviewer choice. A candidate can
then enter ordinary replay/comparison/review or supported scenario generation.
This command exports a single case. Use [whole-corpus migration](native-corpus-migration.md)
for complete reconciliation and verified export across multiple engines.

All three commands accept `--timeout-ms`. Optional artifact writes are individual
file operations, not a transaction: if writing a later artifact fails, an earlier
new file may remain. A failed export write can leave an incomplete new file;
check the command result and replay before using it. Existing files are never
replaced.

### Decision and assessment formats

`gwt.native-migration-decision`, schema 1, contains exactly `kind`,
`schemaVersion`, `proposalIntegrity`, `reviewer`, `status`, and `note`. Status is
`pending`, `accept`, `reject`, or `needs_information`. Files are limited to 32 KiB;
reviewer names to 256 UTF-8 bytes without control characters, notes to 4096 UTF-8
bytes. Duplicate and unknown fields are rejected. Non-pending names/notes must
contain non-whitespace text.

`gwt.native-migration-assessment`, schema 1, records proposal/decision/original
case/candidate case identities, reviewer, status, note, and `accepted`. Decision
integrity hashes canonical JSON with the domain
`gwt-native-migration-decision-sha256-v1` followed by a zero byte. These checks
bind the choice to the complete transition; they do not establish domain
correctness or authenticate a person. The proposal's `approved` field remains
false regardless of separate decisions.

The library exposes `MigrationDecision::pending`, `from_json`, and `to_json`,
`assess_migration`, and `render_migration_html`. Assessment takes an immutable
`CaseMigration` prepared by a trusted caller. Its previous-engine execution
obligation is the same as `prepare_migration`; use the CLI for orchestration.
HTML presentation is capped at 64 MiB per execution and 256 MiB overall.

## Evidence and remaining work

Thirteen protocol/process tests cover transition mechanics, decision binding,
validation limits, escaped/exact HTML, unavailable candidates, fresh CLI
assessment, and new-file export. The [review qualification](../evaluations/native_migration/2026-10-16-review/README.md)
adds 18 real previous-engine replays, offline browser interactions, and fresh
assessment of synthetic saved choices. No real corpus was approved or modified.
[Whole-corpus review and promotion](native-corpus-migration.md) now provides
complete reconciliation and accepted export. Source adaptation remains unfinished.

If the current engine no longer accepts the old syntax, the proposal records an
unavailable candidate. Source adaptation across engines needs its own explicit
workflow; this command does not silently rewrite source to obtain a passing case.
There is also no automatic previous-engine archive or binary distribution service.

The earlier [engine-transition qualification](../evaluations/native_migration/2026-10-16/README.md) runs
real executables over 18 transitions, including a clearly labeled engine variant
with an intentionally changed assertion message. This is engineering evidence,
not human approval or a comprehension study.
