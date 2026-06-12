# Release Readiness Example

This example implements the
[release readiness pilot](../../docs/release-readiness-pilot.md). It models a
deterministic host-facing decision for whether a software release can proceed,
using only the existing v0.2 language surface.

- `rules.gwt` defines the release request and decision contracts, the public
  `REQUEST review release`, and embedded scenarios for the main outcomes.
- `request.json` supplies host-facing JSON input for `--json-input` plus
  `--request "review release"`.
- `rules_types.py` is generated from the GWT contracts and provides typed
  Python request, output, and client helpers.
- `host_app.py` validates, inspects, compiles, and calls `REQUEST review release`
  through the generated Python client.
- `release_gate.py` normalizes repo/CI evidence into a `ReviewReleaseRequest`,
  calls the same public request, and emits an advisory release decision report.
- The host remains responsible for CI systems, deployment APIs, incident
  lookups, rollout controls, timestamps, persistence, and notifications.

Run the pilot validation:

```sh
python -m gwtlang validate examples/release_readiness/rules.gwt \
  --import-root examples/release_readiness \
  --no-absolute-imports
```

Run the JSON request through the public interface:

```sh
python -m gwtlang run examples/release_readiness/rules.gwt \
  --json-input examples/release_readiness/request.json \
  --request "review release" \
  --json
```

Inspect the public boundary:

```sh
python -m gwtlang inspect examples/release_readiness/rules.gwt --json
```

Generate TypeScript host types:

```sh
python -m gwtlang types examples/release_readiness/rules.gwt \
  --language typescript \
  --output /tmp/release-readiness.d.ts
```

Refresh generated Python host types after contract changes:

```sh
python -m gwtlang types examples/release_readiness/rules.gwt \
  --language python \
  --output examples/release_readiness/rules_types.py
```

Run the typed Python host app:

```sh
python examples/release_readiness/host_app.py
```

Expected final line:

```txt
typed decision: needs_review (missing_approval)
```

Run the advisory repo release gate after the ordinary CI checks have passed:

```sh
python examples/release_readiness/release_gate.py --evidence ci-passed
```

Generate a machine-readable report:

```sh
python examples/release_readiness/release_gate.py \
  --evidence ci-passed \
  --release-approved \
  --ignore-working-tree \
  --json
```

Run the gate as a self-contained local check, using the installed Python, Node,
and npm tooling already required by CI:

```sh
python examples/release_readiness/release_gate.py --evidence local
```

The gate is advisory by default: a `needs_review` decision still exits `0`.
Use `--enforce` only after the release workflow is ready to block on the GWT
decision.

## Pilot Notes

The request returns only `decision` in the JSON/API `result`. The full execution
payload still includes `state` for debugging, so host applications should consume
`result.decision` as the public boundary.

`failed_checks` counts required checks that did not pass. The blocker text keeps
the reason reviewable by distinguishing `failed_check_*` from
`skipped_check_*`.

`blockers` means "evidence that prevents automatic approval." Some blockers
produce `blocked`, while others produce `needs_review` because a human can still
resolve the missing approval, missing rollback plan, or missing evidence.

The host must normalize external facts before calling GWT. Required checks and
approvals must appear as explicit rows. If no required check row or no required
approval row is present, the release returns `needs_review` with
`missing_evidence`.

| Observation | Evidence | Likely Category | Next Step |
| --- | --- | --- | --- |
| Request setup and reset duplicate the decision defaults. | `GIVEN decision is ReleaseDecision` and `WHEN reset release decision <decision>` both enumerate the same fields. | Syntax pressure or lint | Compare with another pilot before designing initialization syntax. |
| Priority decisions are readable with existing `DECIDE`. | `WHEN classify <release> into <decision>` orders active incident, failing checks, missing evidence, missing approval, missing rollback, risky flags, then approval. | None | Keep using `DECIDE` for first-match release decisions. |
| Repeated collection scans are verbose but reviewable. | `collect check evidence` scans required checks once for passed, once for failed, and once for skipped. | Syntax pressure | Try another pilot before adding filtered-count or grouping syntax. |
| Missing normalized facts require explicit behavior. | `FIND required_check ... ELSE append "missing_required_checks"` and the matching approval branch guard against empty host evidence. | Docs or host integration | Document that the host owns normalization and GWT owns deterministic classification. |
| Blocker and warning lists are string-coded. | `append "failed_check_" + check.name to decision.blockers` and `append "risky_flag_" + flag.name to decision.warnings`. | Host integration or syntax pressure | Consider structured finding records in a later pilot before proposing new syntax. |
| Request-level invariants are useful. | `THEN decision.status != "new"` and `AND decision.reason != "new"` avoid a public request that returns an unclassified decision. | Docs | Recommend small public invariants when `OUTPUT` records have sentinel defaults. |
| Scenario setup is long but scan-friendly. | The combined-priority scenario repeats full release setup so all collected evidence is visible beside assertions. | Docs or syntax pressure | Prefer helper behavior names first; do not add scenario fixture syntax from this pilot alone. |
