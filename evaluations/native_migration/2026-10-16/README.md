# Native engine-transition qualification

Eighteen migrations exercise actual previous/current executables, with no cases
promoted into a live corpus. Nine use the preserved pre-migration engine. Nine
use a qualification-only variant of that engine whose assertion message was
deliberately changed to `assertion was false (qualification engine)`.

Each group includes a successful request, rejected request, invalid host input,
passing expected-rejection scenario, exact large-integer printed output, raw
scenario failure, imported source with its original files deleted, a zero-step
request, and a zero-step scenario. Zero-step observations are obtained and then
verified through the previous engine's own replay; no invented observations are
used for the successful migration checks.

All nine preserved-engine observations remain identical. The controlled variant
produces three differences: rejected request and raw scenario failure messages
change the outcome/evidence flags, while the passing expected-rejection scenario
changes only its recorded failure evidence. The other six remain identical.
Every candidate replays successfully on the current engine. Supported request
candidates also pass native scenario generation. Source, target, input, and
limits remain exact, and original files remain byte-identical.

Each previous engine rejects a deliberately forged invoice observation even
after its case checksum is recomputed. Neither refusal produces a candidate.
Proposal hashes are independently recomputed using Python's canonical JSON
encoding. The altered engine is a controlled test fixture, not a claim that an
actual language revision changed assertion behavior.

- [Qualification results](qualification.json)
- [Native tests and toolchain record](native-verification.json)
- [Migrated request/scenario/budget cases in ordinary corpus review](migrated-corpus-checks.json)
- [Archived source/binary identities](engines.json)
- [Original engine source](previous-engine-source.tar.gz)
- [Controlled changed engine source](changed-engine-source.tar.gz)
- [Target engine source](target-engine-source.tar.gz)
- Original cases, candidate cases, full proposals, and forged-case refusals are
  retained under [preserved](preserved/invoice.migration.json) and
  [changed-message](changed-message/rejected-request.migration.json).

The archives contain exact Rust sources/manifests/lockfile needed to rebuild
all three engines with their source fingerprints. They omit compiled binaries.
The exact executables used are identified by SHA-256 in the proposals and
identity record. Rebuilt binary hashes may differ with toolchain/build paths;
the rebuilt engine must still verify the complete original case observations.

Reproduce from the repository root in a fresh temporary directory:

```sh
mkdir -p /tmp/gwt-migration-reproduce
tar -xzf evaluations/native_migration/2026-10-16/previous-engine-source.tar.gz -C /tmp/gwt-migration-reproduce
tar -xzf evaluations/native_migration/2026-10-16/changed-engine-source.tar.gz -C /tmp/gwt-migration-reproduce
tar -xzf evaluations/native_migration/2026-10-16/target-engine-source.tar.gz -C /tmp/gwt-migration-reproduce
cargo +1.96.0 build --locked --manifest-path /tmp/gwt-migration-reproduce/previous-engine/Cargo.toml \
  --target-dir /tmp/gwt-migration-reproduce/previous-target
cargo +1.96.0 build --locked --manifest-path /tmp/gwt-migration-reproduce/changed-engine/Cargo.toml \
  --target-dir /tmp/gwt-migration-reproduce/changed-target
cargo +1.96.0 build --locked --manifest-path /tmp/gwt-migration-reproduce/target-engine/Cargo.toml \
  --target-dir /tmp/gwt-migration-reproduce/current-target
python evaluations/native_migration/qualify.py /tmp/gwt-migration-reproduced \
  --previous-engine /tmp/gwt-migration-reproduce/previous-target/debug/gwt-native \
  --changed-engine /tmp/gwt-migration-reproduce/changed-target/debug/gwt-native \
  --native /tmp/gwt-migration-reproduce/current-target/debug/gwt-native
```

To replay a recorded transition independently of later changes to repository
examples, use its retained original case after building the archived engines:

```sh
/tmp/gwt-migration-reproduce/current-target/debug/gwt-native migrate \
  evaluations/native_migration/2026-10-16/preserved/invoice.original.json \
  --previous-engine /tmp/gwt-migration-reproduce/previous-target/debug/gwt-native
```

Eight protocol/process tests cover transition mechanics, parent chains, schema
validation, changed/unavailable observations, difference truncation, wrong engines,
timeouts, and output limits. Their synthetic verifier fixtures are labeled in
the test source. All 157 native tests and Clippy pass on Rust 1.85.0 and 1.96.0.
These checks do not provide migration approval, binary authentication, production
deployment qualification, or human comprehension evidence. Dedicated migration
review and verified promotion remain unfinished.
