# GWT v0.3 Release Checkpoint

Status: active stabilization checkpoint.

This checkpoint turns the v0.3 roadmap into a concrete release-candidate gate.
It does not introduce new language syntax. The current goal is to prove that the
v0.2 language surface, named `REQUEST` boundary, validation command, generated
host types, and JSON payloads are stable enough for a v0.3 tooling milestone.

## Version Surfaces

The project currently exposes these independent version surfaces:

| Surface | Current Value | Release Meaning |
| --- | --- | --- |
| Python package version | `0.3.0` | Distribution/package identity in `pyproject.toml` and `gwtlang/version.py` |
| Language spec version | `v0.2` | Implemented source language documented in [`spec/v0.2.md`](spec/v0.2.md) |
| Payload schema version | `3` | Stable JSON envelope version for CLI/API payloads |
| Roadmap milestone | `v0.3` | Stabilization target for tooling, integration, diagnostics, and pilots |

This checkpoint prepares Python package version `0.3.0`. Do not change the
language spec version unless the implemented source language changes and the
versioned spec is updated with it.

## Current Pilot Evidence

Two realistic host-facing pilots are implemented and should remain green:

| Pilot | Public Request | Evidence |
| --- | --- | --- |
| [`examples/release_readiness`](../examples/release_readiness) | `REQUEST review release` | `gwt validate`, JSON request execution, generated Python host types, typed host app, advisory release gate, and 8 embedded scenarios |
| [`examples/incident_triage`](../examples/incident_triage) | `REQUEST triage incident` | `gwt validate`, JSON request execution, generated Python host types, typed host app, and 3 embedded scenarios |

The local advisory gate should approve a release candidate when ordinary local
checks pass:

```sh
python examples/release_readiness/release_gate.py \
  --evidence local \
  --release-approved \
  --ignore-working-tree \
  --json
```

Expected decision:

```json
{
  "status": "approved",
  "reason": "ready",
  "failed_checks": 0
}
```

## v0.3 Decisions

These decisions are explicit for the v0.3 checkpoint:

- Do not add new source syntax for v0.3 from the current pilot evidence.
- Keep named `REQUEST` blocks as the host-facing callable unit.
- Treat `gwt validate` as the local and CI product gate.
- Keep `ExecutionResult.as_payload` and CLI JSON result shapes stable.
- Keep generated Python/TypeScript types, JSON Schema, and OpenAPI output
  aligned with `gwt inspect --json`.
- Keep substantial public examples scenario-backed with top-level assertions.
- Treat host applications as responsible for I/O, persistence, timestamps,
  networking, rollout controls, and normalization before calling GWT.

## Deferred Design Pressure

The pilots surfaced real pressure, but not enough to justify v0.3 syntax:

| Pressure | Evidence | Current Decision |
| --- | --- | --- |
| Repeated decision initialization | `REQUEST` setup and reset behavior duplicate default fields in both release readiness and incident triage | Defer default/init syntax until another pilot confirms the shape |
| Verbose collection scans | Release readiness scans checks, approvals, incidents, rollback, and flags through explicit behaviors | Defer filtered-count or grouping syntax; current source is verbose but reviewable |
| String-coded findings | Release readiness appends blocker and warning codes such as `failed_check_*` and `risky_flag_*` | Try structured finding records in a future pilot before adding syntax |
| Long scenario setup | Release scenarios repeat full request facts beside assertions | Prefer helper behavior names and explicit fixtures before considering scenario fixture syntax |

If any deferred item is promoted later, capture a before/after GWT snippet and
evaluate it against [`design-principles.md`](design-principles.md) before
implementation.

## Release-Candidate Gate

Run the standard repository verification before tagging or publishing:

```sh
python -m unittest discover
find examples -name '*.gwt' -print0 | while IFS= read -r -d '' file; do python -m gwtlang format "$file" --check >/dev/null || exit 1; done
for file in examples/*.gwt; do python -m gwtlang check "$file" >/dev/null || exit 1; done
python -m gwtlang run examples/order_fulfillment/rules.gwt --input examples/order_fulfillment/request.gwt --json >/tmp/gwt-order.json
python -m gwtlang run examples/language_tour/rules.gwt --input examples/language_tour/request.gwt --json >/tmp/gwt-tour.json
(cd vscode-gwt && npm run check)
python examples/release_readiness/release_gate.py --evidence local --release-approved --ignore-working-tree
git diff --check
```

For package-release preparation, also confirm generated artifacts are clean:

```sh
python -m gwtlang types examples/release_readiness/rules.gwt \
  --language python \
  --output examples/release_readiness/rules_types.py
python -m gwtlang types examples/incident_triage/rules.gwt \
  --language python \
  --output examples/incident_triage/rules_types.py
git diff --exit-code -- examples/release_readiness/rules_types.py examples/incident_triage/rules_types.py
```

## Release Is Ready When

- The worktree is clean except for intentional release edits.
- The release-candidate gate passes locally and in CI.
- The advisory release gate returns `approved` with `reason: "ready"`.
- Public docs link to the roadmap, pilot evaluation guide, and this checkpoint.
- Package version changes, if any, are reflected in `pyproject.toml`,
  `gwtlang/version.py`, generated metadata, and
  [`release-notes-v0.3.md`](release-notes-v0.3.md).
- Any payload or language incompatibility has an explicit schema/spec version
  bump or migration note.
