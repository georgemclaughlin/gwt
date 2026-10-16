# GWT

[![CI](https://github.com/georgemclaughlin/gwt/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/georgemclaughlin/gwt/actions/workflows/ci.yml)

GWT is an experimental language for deterministic domain rules. A `.gwt` file
contains the executable behavior, typed request/response contracts, and
examples that test it. Domain operations read like `review vendor into decision`.

Use it for bounded decisions such as eligibility, refund rules, release
selection, and exception routing. The host application owns persistence,
network calls, authentication, and input normalization.

The review workflow makes rule changes concrete:

```text
capture representative inputs → explain decisions → compare revisions → review affected cases
```

Execution Cases preserve source-linked facts. Generated scenarios reproduce
observed behavior; people still decide whether that behavior is intended.

## Try it

Python 3.11+ is required. From a checkout:

```sh
python -m gwtlang run examples/hello.gwt --json
python -m gwtlang validate examples/vendor_onboarding/rules.gwt
python -m gwtlang run examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor" --json
```

For a local `gwt` command, run `python -m pip install -e .`.

The [vendor onboarding example](examples/vendor_onboarding) connects readable
rules to generated Python and TypeScript host types and host applications.
CI covers the host examples, strict Pyright checks, and the VS Code extension. The
[getting-started guide](docs/getting-started.html) teaches the language step by step.

## Review successive rule changes

The [refund review example](examples/refund_review/README.md) provides equivalent
GWT and Python rules, three successive policy changes, independent acceptance
cases, and a small human review queue for each change:

```sh
python examples/refund_review/run_trial.py /tmp/gwt-refund-review
```

Use a new output directory. Open a generated `review.html` to inspect changed
outputs, search cases or affected fields, and expand path-only changes.
The output also includes frozen programs, portable case corpora, independent
candidate expectations, and an unfilled human-review worksheet.

This is a synthetic rehearsal, not an external adoption result. The
[paired maintenance benchmark](docs/maintenance-evaluation.md) measures GWT and
Python against the same acceptance cases. In the
[first live maintenance trial](evaluations/maintenance/2026-10-15/README.md),
both languages passed all nine code trials on the first attempt. No GWT
advantage is established by this small, single-domain result.

## Integrate a decision

A named request defines the boundary:

```gwt
REQUEST review vendor
  GIVEN vendor is VendorRequest
  WHEN review vendor into decision
  OUTPUT decision is VendorDecision
```

Project that checked source to ordinary HTTP/OpenAPI:

```sh
python -m gwtlang openapi examples/deployable_api/rules.gwt --json
python -m gwtlang serve examples/deployable_api/rules.gwt --port 8080
```

The default server is for local/reference use. The optional `gwtlang[serve]`
extra supplies the ASGI engine; see [host integration](docs/host-language-clients.md)
and [deployment qualification](examples/deployable_api/README.md) before deploying.
Python applications can also [compile and call rules in process](docs/reference.md#python-api).

## Work with an agent

The repository includes a [GWT authoring skill](.agents/skills/gwt-authoring/SKILL.md)
over existing inspection, validation, comparison, and workbench commands.
Start with [authoring guidance](docs/agent-authoring.md) and relevant worked
examples. The [historical model evaluation](evaluations/agent-authoring/2026-07-18/README.md)
shows why examples and deterministic repair matter.

## Project status and references

The package is `0.3.0`; the language specification is `v0.2`. The v0.4
behavior-review implementation is a development candidate, not a published
v0.4 release. `python -m gwtlang version --json` reports installed versions.
The project retains the GWT name and uses the [MIT license](LICENSE).
The [project goal](docs/project-goal.md) centers human understanding and a
Rust foundation. The native engine is explicitly selected and experimental;
Python remains the default. Start here:

| Native reference | Purpose |
| --- | --- |
| [Read, change, explain, review](docs/native-review-walkthrough.md) | A short runnable delivery-policy change with captured cases and pending review |
| [Consolidated native draft](docs/spec/native-draft.md) | Current syntax, types, execution, contracts, failures, and conformance map |
| [Execution model](docs/native-execution-model.md), [grammar](docs/native-grammar.md) | Narrative explanation and full source productions |
| [Native CLI and library](crates/gwt-core/README.md), [editor](docs/native-editor.md) | Build, run, embed, and author with the selected engine |
| [Support and transition](docs/native-language-transition.md) | Deliberate differences, source/artifact migration, and release preparation |
| [Feature/evidence matrix](docs/native-conformance.md), [goal ledger](docs/project-goal-progress.md) | Detailed feature notes, tested scope, and remaining work |

The [five-domain Codex CLI comparison](evaluations/native_maintenance/2026-10-16-codex-cli/README.md)
passed 15/15 first-attempt trials in each language, including withheld cases.
That establishes no advantage over Python or human-review benefit. Human sessions,
external pilots, and release review remain pending. See the
[current checkpoint](docs/development-checkpoint.md).

| Reference | Purpose |
| --- | --- |
| [Language guide](docs/language.md), [spec](docs/spec/v0.2.md), [grammar](docs/grammar.md) | Python v0.2 syntax and semantics |
| [Command and example reference](docs/reference.md) | Detailed CLI, API, editor, and example usage |
| [Execution Cases](docs/execution-cases.md) | Capture, replay, scenario generation, and comparison contracts |
| [Design principles](docs/design-principles.md) | Language scope and guardrails |
| [External pilot runbook](docs/external-pilot-v0.4.md) | Test adoption with real owners |
| [Release checklist](docs/release-v0.4-checklist.md) | Publication requirements |

Run `python -m unittest discover` for the Python suite. Full contributor checks
are listed in [AGENTS.md](AGENTS.md).
