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
The [project goal](docs/project-goal.md) sets the direction toward human
understanding and a Rust foundation. An [experimental native
engine](crates/gwt-core/README.md) runs typed requests and scenarios in a documented
language subset. Start with [the native execution model](docs/native-execution-model.md)
to understand its state, decisions, failures, and evidence; use the
[native grammar](docs/native-grammar.md) for accepted source forms. Complete native language coverage
and human-benefit evidence remain open in the [goal ledger](docs/project-goal-progress.md).
Native [engine migration review](docs/native-migration.md) compares retained cases
across engines and supports saved decisions with verified case export.
[Whole-corpus migration](docs/native-corpus-migration.md) preserves all entries and
metadata across mixed engines, with complete review required before export.
[Captured-case regression tests](docs/native-regressions.md) enforce an explicit
outcome/state or execution scope, including retained boundary and resource failures.
The native crate also has a [qualified local packaging and Rust embedding path](docs/native-embedding.md).
[Native inspection](docs/native-inspection.md) exposes checked request contracts,
behavior signatures, types, scenarios, and source identity without executing rules.
An explicit [native editor mode](docs/native-editor.md) checks unsaved source and
imports and runs scenarios/requests from VS Code; Python remains the default.
Native editor commands can share an explicit operating-budget file with the CLI
and profile execution evidence from the command palette.
The [native formatter](docs/native-formatting.md) formats buffers or previews,
checks, and explicitly rewrites files without invoking Python.
Native authoring now includes a [combined validation command](docs/native-validation.md)
for checking source, formatting, and embedded scenarios from one captured closure.
Its optional HTML report makes expectation results, evidence gaps, and captured
source available for offline review. [Typed setup tables](docs/native-setup-tables.md)
provide readable record collection inputs for native scenarios and request setup.
[Readable request entries](docs/native-request-entries.md) explicitly import their
rules and can run or be captured directly when they contain one scenario.
[One-of contracts](docs/native-one-of.md) validate named domain states without
unrelated payload fields. Exhaustive kind branches expose their specific payloads
and guard against kind-changing writes through shared aliases.
Kind-specific contracts let helpers name their required payload and keep calls short.
[Scalar-value dispatch](docs/native-value-dispatch.md) selects behavior from one
status, flag, or exact numeric value, with checked coverage and source evidence.
The [native support and transition contract](docs/native-language-transition.md)
separates supported language, deliberate omissions, and migration responsibilities.
`gwt-native version --json` and the editor’s **GWT: Show Engine Information**
command identify the selected engine without executing source.
[Finite scalar contracts](docs/native-finite-literals.md) declare closed numeric
and boolean domains, reject unsupported inputs, and enable exhaustive decisions.
[Presence guards](docs/native-presence.md) let branches use optional values
safely and reject alias writes that would invalidate those branches' assumptions.
[Kind conditions](docs/native-kind-conditions.md) expose the appropriate payload
inside ordinary conditions, including rules that combine kind and consent.
[Explicit rounded division](docs/native-rounded-division.md) makes decimal scale
and rounding mode visible in native behavior steps while ordinary `/` stays exact.
[Weighted allocation](examples/native_weighted_allocation/README.md) combines
rounding, eligibility, remainder selection, and conservation checks, with an
independent oracle and captured review of a faulty change. Its documented limits
include evidence growth on larger inputs. [Typed local records](docs/native-local-records.md)
now let its behaviors construct results directly, removing template parameters.
[Append evidence](docs/native-append-evidence.md) records individual insertions,
reducing repeated list snapshots while retaining the item, position, and source.
[Native profiling](docs/native-profiling.md) identifies evidence costs by operation
and source location, including partial traces from executions that reach a limit.
[Explicit execution budgets](docs/native-execution-limits.md) let validation,
profiling, request execution, and captured review use a shared limit file.
Actual external pilots and release review remain open; see the
[current checkpoint](docs/development-checkpoint.md).

| Reference | Purpose |
| --- | --- |
| [Language guide](docs/language.md), [spec](docs/spec/v0.2.md), [grammar](docs/grammar.md) | Syntax and semantics |
| [Command and example reference](docs/reference.md) | Detailed CLI, API, editor, and example usage |
| [Execution Cases](docs/execution-cases.md) | Capture, replay, scenario generation, and comparison contracts |
| [Design principles](docs/design-principles.md) | Language scope and guardrails |
| [External pilot runbook](docs/external-pilot-v0.4.md) | Test adoption with real owners |
| [Release checklist](docs/release-v0.4-checklist.md) | Publication requirements |

Run `python -m unittest discover` for the Python suite. Full contributor checks
are listed in [AGENTS.md](AGENTS.md).
