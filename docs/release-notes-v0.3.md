# GWT v0.3 Release Notes

Status: package release preparation.

GWT v0.3 is a stabilization and tooling release. It keeps the implemented
source language at `v0.2` and keeps the payload schema version at `3`.

## Highlights

- Package version is prepared as `0.3.0`.
- Named `REQUEST` blocks remain the host-facing callable unit.
- `gwt validate` is the recommended local and CI product gate.
- CLI/API JSON payloads continue to use the stable execution envelope.
- Generated Python and TypeScript host types stay aligned with
  `gwt inspect --json`.
- OpenAPI generation documents named request boundaries for deployable host
  services.
- The VS Code extension continues to provide validation, formatting, testing,
  running, debugging, hover, completion, and diagnostics support.

## Pilot Evidence

Two host-facing pilots support this release:

- [`examples/release_readiness`](../examples/release_readiness) models an
  advisory software release gate with JSON execution, generated Python host
  types, a typed host app, and 8 embedded scenarios.
- [`examples/incident_triage`](../examples/incident_triage) models
  deterministic incident escalation with JSON execution, generated Python host
  types, a typed host app, and 3 embedded scenarios.

Both pilots validate through `gwt validate` with explicit import policy.

## No Source Syntax Changes

This release does not add source syntax. Current pilot pressure is real but
deferred:

- repeated request/reset initialization
- verbose collection scans
- string-coded blockers and warnings
- long scenario setup

Future syntax work should promote one of these only after another realistic
pilot provides concrete before/after GWT snippets.

## Version Surfaces

The release intentionally separates package, language, and payload versions:

| Surface | Value |
| --- | --- |
| Python package version | `0.3.0` |
| Language spec version | `v0.2` |
| Payload schema version | `3` |

Use `python -m gwtlang version --json` to inspect these values.

## Release Gate

The v0.3 release-candidate gate is documented in
[`release-v0.3-checklist.md`](release-v0.3-checklist.md). A release candidate
is ready when that gate passes locally and in CI, and the advisory release gate
returns `approved` with `reason: "ready"`.
