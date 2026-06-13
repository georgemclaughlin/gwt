# Incident Triage Pilot

This pilot tests GWT on deterministic incident-response triage. The host owns
monitoring, paging tools, ticket creation, and communications. GWT owns the
request contract, decision record, escalation rules, and executable examples.

The public request is:

```gwt
REQUEST triage incident
```

Run the local validation gate:

```sh
python -m gwtlang validate examples/incident_triage/rules.gwt \
  --import-root examples/incident_triage \
  --no-absolute-imports
```

Run the host-facing JSON request:

```sh
python -m gwtlang run examples/incident_triage/rules.gwt \
  --json-input examples/incident_triage/request.json \
  --request "triage incident" \
  --json
```

Regenerate the Python host types after contract changes:

```sh
python -m gwtlang types examples/incident_triage/rules.gwt \
  --language python \
  --output examples/incident_triage/rules_types.py
```

Run the typed host example:

```sh
python examples/incident_triage/host_app.py
```

Current pilot findings:

| Observation | Evidence | Likely Category | Next Step |
| --- | --- | --- | --- |
| Request-local decision initialization is explicit but repetitive | `TriageDecision` is initialized in `REQUEST triage incident` and reset in `reset triage decision` | Possible syntax pressure | Compare with another pilot before adding default-value syntax |
| Request-level invariants are useful and cheap | `THEN decision.status != "new"` and `AND decision.reason != "new"` catch unresolved decisions | Validation/lint | Keep as a convention for substantial public requests |
| Host integration is straightforward | `host_app.py` validates, compiles once, and calls the generated client wrapper | Client/API | Keep the CI generated-type fixture check in sync with contract changes |
