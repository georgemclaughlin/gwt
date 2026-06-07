# GWT Adoption Modes

GWT works best when it is introduced around deterministic behavior with clear
JSON-shaped inputs and outputs. It should not own UI rendering, persistence,
network side effects, hardware timing, audio/display latency, or real-time
embedded paths.

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

Run with host-owned DTO mapping:

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
