# Vendor Onboarding Review

This example is a practical GWT workflow for reviewing a vendor before
onboarding. It is intentionally business-readable: the request provides vendor
facts, documents, and risk signals; the output is a typed decision record.

This is a workflow/spec demo, not a policy decision point demo. GWT is not
trying to replace Open Policy Agent or Rego-style policy evaluation. The point
is to keep a deterministic review workflow, scenarios, typed boundaries, and
observable output in one executable artifact.

```txt
vendor request
  -> required document checks
  -> inherent risk scoring
  -> risk signal scoring
  -> onboarding decision
```

The entry behavior is:

```gwt
WHEN review <vendor> into <decision>
```

The output decision includes:

```txt
decision.status == "approved" | "needs_review" | "rejected"
decision.reason
decision.risk_points
decision.missing_requirements
decision.data_review_required
```

## Commands

Static check:

```sh
python -m gwtlang check examples/vendor_onboarding/rules.gwt
```

Run embedded scenarios:

```sh
python -m gwtlang test examples/vendor_onboarding/rules.gwt
```

Run with JSON input:

```sh
python -m gwtlang run examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --entry "review vendor into decision" \
  --json
```

## What This Demonstrates

- typed `REQUEST` and `OUTPUT` contracts
- JSON input as host-facing state
- typed tables for documents and risk signals
- explicit missing and expired document handling
- deterministic status and reason output
- embedded scenarios for approved, review, and rejected outcomes
