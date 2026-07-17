# GWT Adoption Modes

GWT works best when it is introduced around deterministic behavior with clear
JSON-shaped inputs and outputs. It should not own UI rendering, persistence,
network side effects, hardware timing, audio/display latency, or real-time
embedded paths.

Use [Pilot Evaluation](pilot-evaluation.md) when testing a real workflow. It
captures the artifact shape, shadow-mode posture, and criteria for deciding
whether a workflow should influence future language work.

## Executable Spec Mode

Use this mode when a `.gwt` file is executable documentation and regression
coverage for host-side rules.

Good fits include:

- OTA manifest validation
- release and versioning rules
- provisioning state flows
- input-event traces reduced to deterministic state changes
- domain logic such as scale, chord, degree, mode, or transformation rules

Start with an optional spec file and run it locally:

```sh
python -m gwtlang validate specs/ota_update.gwt \
  --import-root specs \
  --no-absolute-imports
```

If the spec catches real regressions, pin `gwtlang` and add the same command to
CI. In this mode, GWT is a host-side test dependency, not an application or
firmware runtime dependency.

## Behavior Review Mode

Use this mode when GWT already describes a deterministic decision and you need
to understand the effect of a proposed rule change before promotion.

Capture representative JSON requests as versioned Execution Cases, then assign
stable domain references in a portable corpus:

```sh
gwt capture rules-v1.gwt \
  --json-input requests/boundary.json \
  --request "review request" \
  --output cases/boundary.execution-case.json

gwt corpus create \
  --name "review request boundaries" \
  --case boundary=cases/boundary.execution-case.json \
  --output cases/review.case-corpus.json

gwt corpus check cases/review.case-corpus.json
```

Replay the same corpus against the baseline and candidate, then render a local
review dossier:

```sh
gwt compare --corpus cases/review.case-corpus.json \
  --old rules-v1.gwt \
  --new rules-v2.gwt \
  --json

gwt workbench --corpus cases/review.case-corpus.json \
  --old rules-v1.gwt \
  --new rules-v2.gwt \
  --output review.html
```

The corpus says which cases matter; it does not declare whether a change is
acceptable. Candidate classifications belong to the comparison, and rollout or
approval policy remains outside GWT.

## Served Decision Mode

Use this mode when an application—especially a non-Python application—wants
GWT to own a deterministic request-to-decision rule. This is the recommended
cross-language integration path.

Validate and project the contract in CI, then run the same checked source behind
the standard HTTP boundary:

```sh
gwt validate rules/main.gwt --import-root rules --no-absolute-imports
gwt openapi rules/main.gwt --output openapi.json
gwt serve rules/main.gwt \
  --engine asgi \
  --import-root rules \
  --no-absolute-imports \
  --execution-budget 100000 \
  --max-call-depth 100
```

Host applications call the generated `POST /requests/<request-slug>` routes
with ordinary JSON and consume only declared `OUTPUT` fields. Keep TLS,
authentication, authorization, rate limiting, and rollout policy in the host's
gateway or deployment layer. Install `gwtlang[serve]` for the optional ASGI
engine shown above. The default built-in transport remains a dependency-free
development/reference server; neither engine should be treated as a complete
internet-facing security boundary.

## Embedded Decision Mode

Use this mode when an application wants GWT to own a deterministic
request-to-decision rule.

Check the rules in local development and CI:

```sh
python -m gwtlang validate rules/main.gwt \
  --import-root rules \
  --no-absolute-imports
```

`gwt validate` checks imports, parser/checker diagnostics, canonical formatting,
and embedded scenarios when the file has scenario content. Use `gwt inspect
rules/main.gwt --json` when CI, review tools, or agents need a versioned
manifest of records, named requests, behaviors, scenarios, and the program hash
without executing a host application.

Compile once at application startup as a final safety gate:

```python
from gwtlang import compile_file

rules = compile_file(
    "rules/main.gwt",
    import_roots=["rules"],
    allow_absolute_imports=False,
)
```

Run with host-owned request mapping:

```python
execution = rules.run_json(
    request_state,
    request="review request",
)
decision = execution.as_payload()["result"]["decision"]
```

Adopt embedded decisions gradually:

1. Use GWT as executable contract/spec coverage.
2. Run GWT in shadow mode beside existing application code and log mismatches.
3. Promote one low-risk deterministic rule only after shadow results are stable.

The vendor onboarding flagship demo includes a concrete shadow-mode host:

```sh
python examples/vendor_onboarding/shadow_mode.py
```

It compares a small legacy Python decision function with
`REQUEST review vendor`, reports one matching case and one intentional mismatch,
and leaves promotion disabled:

```json
{
  "cases": 2,
  "matches": 1,
  "mismatches": 1,
  "promotion_ready": false
}
```

That is the intended migration posture: observe mismatches, review whether GWT
or the legacy code is correct, and promote only after the shadow report is
stable for the chosen workflow.

The host application should still own data loading, persistence, network calls,
time sources, logging, and rollout controls.
