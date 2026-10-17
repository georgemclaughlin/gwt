# Native toolchain identity — 2026-10-16

The CLI and Rust library now expose the identity of the selected native engine
without loading GWT source. **GWT: Show Engine Information** exposes the active
editor engine's identity in the output channel, including the selected command.
See the [support contract](../../../docs/native-language-transition.md).

The native report is `gwt.native-version`, schema 1. Package `gwt-core` remains
0.1.0. The language profile is `gwt-native-experimental`; `languageVersion` is
explicitly null and status is experimental. No language release, default-engine
change, artifact schema change, or publication is implied. The engine identity
is exactly the one used by captures and migration.

## Final qualification

| Check | Result |
| --- | --- |
| Rust 1.85.0 and 1.96.0 | 431 tests pass on each; Clippy passes with warnings denied; formatting passes |
| Identity API/CLI tests | Library, all CLI spellings, and case engine agree; CLI works with an empty environment, no source checkout, and closed stdin; extra arguments are refused |
| Packaged Rust consumer | Version report agrees with installed and rebuilt/relocated CLI; independent source fingerprint reproduced |
| Package regression | 18 independent host observations, 288 concurrent executions, 18 relocated case replays, and explicit previous-engine migration pass |
| VS Code 1.137.0 native mode | 44 qualification checks pass, including no-document identity, invalid unsaved source, missing executable, incomplete identity response, and exact CLI agreement |
| VS Code Python mode | 3 qualification checks pass, including existing Python package/spec identity and unchanged default mode |
| JavaScript tools | Syntax checks and 11 process/command tests pass |
| Finite-contract migration | 12 complete prior observations preserved; original case bytes unchanged; proposals remain unapproved |

`package-final/` and `editor-*-final/` are the authoritative final runs. The
earlier package run predates the package README addition; the final package
includes it. Earlier editor runs are retained separately. The two package builds
have identical engine source identities but distinct binary build paths; editor
qualification of the final package uses its exact installed executable.

The final packaged engine is
`sha256:0195175b5f32e9e140257b2f1e03e57c3d28730eda6b51b4ec68aa5b8c27fdc5`.
Its executable SHA-256 is
`22803923302696abe60e382fce16dc4b1cb841ea597505b7692e50b7a8df1696`.
A retained executable is at
`/home/g/.cache/gwt-qualifications/native-identity-0195175b/gwt-native`.
The source manifest records 61 inputs; package normalization makes the packaged
engine identity different from the checkout build, as documented previously.

```sh
/home/g/.cache/gwt-qualifications/native-identity-0195175b/gwt-native version --json
cargo +1.96.0 test --locked -p gwt-core --test version
```

Complete build/host commands and observations are in `package-final/`. Editor
launch arguments, executable hashes, extension hashes, and assertions are in
the final editor directories. `finite-migrations.json` records the twelve
explicit previous/current executable commands, and `finite-migrations/` retains
the proposals. None exports or approves a migrated case.

The new identity API changes engine source identity even though no language
semantics changed. Existing case replay continues to refuse a different engine;
identity reporting does not bypass migration. A profile name or package version
alone is not a compatibility guarantee, signature, or dependency-graph attestation.

These are local development/package/editor qualifications. No new browser,
production deployment, hosted CI, live model experiment, or human study is
claimed. Previous browser and performance checkpoints retain their original
engine scope. Human sessions and external pilots remain pending by owner choice.
