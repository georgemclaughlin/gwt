# GWT Pilot Evaluation

Use this guide when trying GWT on a real workflow. The goal is not to prove that
GWT can express anything. The goal is to learn whether GWT makes a specific
deterministic behavior clearer, safer, and easier to integrate than the current
approach. For broader fit guidance, see [Adoption Modes](adoption-modes.md) and
the [Spec Is Code](spec-is-code.md) thesis.

The first recommended pilot is the
[Release Readiness Pilot](release-readiness-pilot.md), implemented at
[`examples/release_readiness`](../examples/release_readiness).

## Choose A Good Pilot

Prefer a workflow with:

- deterministic inputs and outputs
- clear JSON-shaped request data
- visible state transitions or decision records
- examples that domain reviewers already discuss
- meaningful failure or missing-data cases
- low production blast radius
- a host application that can keep owning I/O, persistence, time, networking,
  rollout, and logging

Avoid pilots where the core problem is:

- UI rendering
- streaming or real-time behavior
- non-deterministic external calls
- broad data querying or reporting
- authorization enforcement across distributed systems
- behavior that cannot yet be described with concrete examples

## Pilot Artifact

A useful pilot should produce:

- one `rules.gwt` file with a named `REQUEST`
- at least three embedded `SCENARIO` blocks with top-level `THEN` assertions
- one JSON request fixture for the host-facing path
- one host call, preferably through `compile_file`, `GwtClient`, or a generated
  client wrapper
- a short note describing mismatches with existing behavior, if any

Use the [vendor onboarding example](../examples/vendor_onboarding/rules.gwt) as
the current reference shape:

```sh
python -m gwtlang validate examples/vendor_onboarding/rules.gwt \
  --import-root examples/vendor_onboarding \
  --no-absolute-imports

python -m gwtlang run examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor" \
  --json
```

## Evaluation Questions

Answer these before changing the language:

- Does the named `REQUEST` boundary match how the host application wants to call
  the workflow?
- Can a domain reviewer follow the `RECORD`, `REQUEST`, `WHEN`, and `THEN`
  sections without reading runtime code?
- Are missing, unknown, rejected, and not-applicable states modeled explicitly?
- Do scenarios cover the happy path, a boundary case, and a failure or review
  path?
- Does each important branch or public outcome have scenario coverage, or is the
  missing coverage explicitly waived in the pilot note?
- Does the output contract return only what the host should consume?
- If a request declares `OUTPUT` without a request-level `THEN` invariant, is
  that acceptable for this workflow or should the invariant be added?
- Are diagnostics good enough when the request shape, field type, or behavior
  call is wrong?
- Does generated host typing reduce integration mistakes?
- Does the GWT source replace duplicated host rules, or does it create a second
  implementation?
- If the program has multiple named requests, do host fixtures and tests name
  the request explicitly instead of relying on declaration order?

## Capture Language Pressure

When the pilot feels awkward, classify the problem before proposing syntax.

Use this table in the pilot note:

| Observation | Evidence | Likely Category | Next Step |
| --- | --- | --- | --- |
| Repeated initialization block | Link or paste short before/after snippet | Syntax pressure or lint | Compare with another example before designing syntax |
| Error message unclear | Command and exact diagnostic | Diagnostics | Improve checker/runtime message and test it |
| Host call awkward | Host snippet | Client/API | Improve client docs or wrapper before changing GWT |
| Scenario too verbose | Scenario snippet | Docs or syntax pressure | Try naming helper behavior first |
| Collection logic reads like a query | Behavior snippet | Design risk | Look for a narrower behavior-shaped operation |

Keep snippets short. The useful unit of evidence is a concrete GWT before/after,
not a general complaint.

## Shadow Mode

For embedded-decision pilots, start in shadow mode when existing host behavior
already exists:

1. Run legacy behavior and GWT behavior from the same normalized request.
2. Log the request name, normalized input hash, legacy result, GWT result,
   source hash or release id, and mismatch category.
3. Classify mismatches as GWT bug, legacy bug, modeling gap, or product
   decision.
4. Choose a sample window and mismatch threshold before starting the trial.
5. Require owner signoff for accepted mismatches and promotion.
6. Promote only after mismatch handling is understood and stable.

Shadow mode is not required for executable-spec pilots that are only used as CI
coverage, but it is the safest migration path when GWT would replace production
rules.

## Success Criteria

A pilot is successful when:

- `gwt validate` passes with import policy enabled
- embedded scenarios catch at least one meaningful regression or ambiguity
- the host-facing request can run from JSON
- the output contract matches what the host should consume
- reviewers can point to the GWT source as the durable behavior artifact
- any syntax pressure is supported by concrete examples
- uncovered branches or outcomes have an explicit waiver

A pilot can also succeed by showing that GWT is the wrong fit. That is useful
if the workflow is too non-deterministic, too query-heavy, or too tied to host
side effects.

## Promotion Criteria

Do not promote GWT as the source of truth for a workflow until:

- the `.gwt` file is validated in CI
- scenarios cover the primary decision paths
- generated host types or explicit host validation protect the JSON boundary
- operational owners know how to inspect diagnostics and runtime failures
- shadow-mode mismatches, if used, are resolved or accepted
- the promotion owner signs off on the sample window and mismatch threshold
- rollback means switching the host back to the prior decision path, not editing
  GWT in production

When a pilot creates pressure for new language surface, evaluate it against the
[Design Principles](design-principles.md) before writing implementation code.
