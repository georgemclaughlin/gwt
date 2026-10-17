# GWT

**Readable rules. Executable behavior. Reviewable changes.**

GWT is an experimental language for policies and workflows that people need to
understand and review. The specification is the program: named `WHEN` behaviors
operate on typed state, and `GIVEN / WHEN / THEN` scenarios check their outcomes.
The Rust engine records execution evidence that connects decisions to source.

Use it for bounded decisions such as eligibility, delivery pricing, refunds, or
inventory allocation. The host application owns I/O, persistence, and external
effects. Human understanding is the design goal; comparative human benefit has
not yet been demonstrated.

## Try it

Open the [project site](https://georgemclaughlin.github.io/gwt/). The site includes an interactive delivery-policy review
and a standalone example download. See [Getting Started](docs/getting-started.html)
and [installation](docs/installation.html). Download the [Linux x86-64 preview](https://github.com/georgemclaughlin/gwt/releases/tag/preview-1); no Rust or Python installation is needed.

With Git and Rust installed, build the developer preview from this checkout:

```sh
cargo +1.96.0 install --path crates/gwt-core --locked
gwt version --json
gwt validate examples/native_delivery/rules.gwt
gwt run examples/native_review_walkthrough/candidate.gwt --request "quote delivery" --input examples/native_review_walkthrough/input.json
```

The request quotes a 1,500g nonmember parcel at fee 5. The full
[review walkthrough](docs/native-review-walkthrough.md) checks the change against
nine captured cases and leaves reviewer decisions pending.

## Language and tools

| Start here | Purpose |
| --- | --- |
| [Language reference](docs/spec/native-draft.md) | Syntax, types, state, contracts, failures, and evidence |
| [Examples](examples/README.md) | Validated programs and focused language examples |
| [Review walkthrough](docs/native-review-walkthrough.md) | Read, change, explain, and review one policy |
| [Editor](vscode-gwt/README.md) | Checking, navigation, formatting, and execution in VS Code |
| [Embed GWT](docs/native-embedding.md) | Rust library and host boundaries |
| [Upgrade guide](docs/python-retirement.md) | Retired Python implementation and command conflicts |
| [Documentation index](docs/README.md) | Current guides and historical context |
| [Contributor guide](docs/contributing.md) | Source builds, checks, site generation, and packaging |
| [Release checklist](docs/release-checklist.md) | Distribution qualification and publication gates |
| [Project goal](docs/project-goal.md) | Human understanding and the evidence still needed |

The installed command is `gwt`; there is one active engine. The Rust package is
`gwt-core` 0.1.0. Its language profile is experimental, with no assigned language
release version. Package, language, and artifact versions are separate.
Historical `gwt.native-*` artifact identifiers remain stable.

The project retains the GWT name and uses the [MIT license](LICENSE).
Human sessions remain pending and external pilots deferred. The prior
[five-domain model comparison](evaluations/native_maintenance/2026-10-16-codex-cli/README.md)
tied at 15/15 first-attempt trials per language; it establishes no superiority.
