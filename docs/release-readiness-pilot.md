# Release Readiness Pilot

Status: proposed pilot.

This pilot should test GWT against a boring, deterministic, host-facing
workflow: deciding whether a software release is ready to proceed. The point is
to pressure the current v0.2 language without adding syntax during the first
pass.

## Why This Pilot

Release readiness is a good fit because it has:

- clear JSON-shaped input
- explicit decision outcomes
- reviewable failure and missing-data cases
- list-shaped evidence such as checks, approvals, blockers, and warnings
- a natural host boundary: `REQUEST review release`
- low need for side effects inside GWT

The host application should still own CI systems, deployment APIs, incident
lookups, rollout controls, timestamps, persistence, and notifications. GWT
should own only the normalized deterministic decision.

## Proposed Artifact

Create:

```text
examples/release_readiness/
  README.md
  rules.gwt
  request.json
```

Do not add new language syntax for the first version. If the source feels
awkward, capture the awkwardness as concrete before/after snippets in the pilot
notes.

## Request Boundary

The public request should be:

```gwt
REQUEST review release
  GIVEN release is ReleaseRequest

  GIVEN decision is ReleaseDecision
    status: "new"
    reason: "new"
    blockers: []
    warnings: []
    ready_checks: 0
    failed_checks: 0
    missing_approval_count: 0

  WHEN review release into decision

  OUTPUT decision is ReleaseDecision
```

The first pass may add a request-level `THEN` invariant if it reads naturally,
but it is not required. If omitted, note why in the pilot evaluation.

## Candidate Contracts

Suggested type aliases:

```gwt
TYPE ReleaseEnvironment is "staging" | "production"
TYPE ReleaseStatus is "new" | "approved" | "needs_review" | "blocked"
TYPE ReleaseReason is "new" | "ready" | "failing_checks" | "missing_approval" | "missing_rollback" | "active_incident" | "risky_flags"
TYPE CheckStatus is "passed" | "failed" | "skipped"
TYPE ApprovalStatus is "approved" | "missing"
```

Suggested records:

```gwt
RECORD ReleaseCheck
  name: text
  required: boolean
  status: CheckStatus

RECORD ReleaseApproval
  name: text
  required: boolean
  status: ApprovalStatus

RECORD FeatureFlag
  name: text
  enabled: boolean
  risky: boolean

RECORD ReleaseRequest
  version: text
  environment: ReleaseEnvironment
  rollback_plan_present: boolean
  active_incident_count: integer
  checks: list<ReleaseCheck>
  approvals: list<ReleaseApproval>
  feature_flags: list<FeatureFlag>

RECORD ReleaseDecision
  status: ReleaseStatus
  reason: ReleaseReason
  blockers: list<text>
  warnings: list<text>
  ready_checks: integer
  failed_checks: integer
  missing_approval_count: integer
```

These contracts are intentionally plain. Change names if the source reads more
like release behavior with different domain terms.

## Scenario Coverage

Start with at least five embedded scenarios:

- clean release is approved
- failing required check blocks release
- missing required approval blocks or needs review
- missing rollback plan needs review
- active production incident blocks release
- risky enabled feature flag needs review

If the scenario count feels high, do not reduce it immediately. First check
whether helper behavior names make the examples easier to scan.

## Expected Pressure Points

Capture evidence for these:

- initialization duplication between request setup and reset behavior
- priority decision readability in `DECIDE`
- collection scans over checks, approvals, and flags
- whether blocker/warning list updates stay behavior-shaped
- whether request/output contract diagnostics are sufficient
- whether scenarios are readable to someone who does not know the runtime

Use [Pilot Evaluation](pilot-evaluation.md) to classify each finding as docs,
diagnostics, host integration, or syntax pressure.

## Commands

Validate the pilot:

```sh
python -m gwtlang validate examples/release_readiness/rules.gwt \
  --import-root examples/release_readiness \
  --no-absolute-imports
```

Run the host-facing JSON path:

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

Generate host types if the request boundary feels stable:

```sh
python -m gwtlang types examples/release_readiness/rules.gwt \
  --language typescript \
  --output /tmp/release-readiness.d.ts
```

## Success Criteria

The pilot is useful if:

- `gwt validate` passes
- the JSON request path returns only `decision`
- scenarios cover the primary outcomes or explicitly waive missing branches
- the GWT source is easier to review than equivalent host code
- any awkward language pressure is backed by concrete source snippets

The pilot can also conclude that release readiness is a poor fit. That is still
useful evidence if the reason is clear.
