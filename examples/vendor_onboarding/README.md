# Vendor Onboarding Review

This is the flagship GWT demo. It shows a practical vendor review workflow as
one executable spec module: readable rules, embedded scenarios, a named JSON
request boundary, generated host types, and Python/TypeScript host calls.

The request provides vendor facts, documents, and risk signals. The result is a
typed decision record with status, reason, tier, risk points, and missing
requirements.

```txt
vendor request
  -> required document checks
  -> inherent risk scoring
  -> risk signal scoring
  -> onboarding decision
```

The public named request is:

```gwt
REQUEST review vendor
```

For the included Cloud Ledger request, the expected decision is:

```json
{
  "status": "needs_review",
  "reason": "manual_review_required",
  "tier": "critical",
  "risk_points": 10,
  "missing_requirements": [
    "insurance_expired",
    "security_questionnaire"
  ]
}
```

## Five-Command Path

1. Validate the executable spec module:

```sh
python -m gwtlang validate examples/vendor_onboarding/rules.gwt \
  --import-root examples/vendor_onboarding \
  --no-absolute-imports
```

Expected:

```txt
OK examples/vendor_onboarding/rules.gwt (check, format, test; 3 scenarios)
```

2. Run the same workflow through JSON, as a host application would:

```sh
python -m gwtlang run examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor" \
  --json
```

Expected result excerpt:

```json
{
  "result": {
    "decision": {
      "status": "needs_review",
      "reason": "manual_review_required",
      "risk_points": 10
    }
  }
}
```

3. Explain why the request produced that decision:

```sh
python -m gwtlang explain examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor"
```

Expected result excerpt:

```txt
review vendor returned needs_review

Input:
vendor.vendor_name: "Cloud Ledger"
vendor.annual_spend: 125000

Result:
decision.status: "needs_review"
decision.reason: "manual_review_required"

Cloud Ledger needs review because:
- insurance is expired
- security_questionnaire is missing
- risk score 10 crossed the review threshold 6
```

4. Refresh generated host types when contracts change:

```sh
python -m gwtlang types examples/vendor_onboarding/rules.gwt \
  --language typescript \
  --output clients/typescript/examples/vendor-onboarding.generated.d.ts

python -m gwtlang types examples/vendor_onboarding/rules.gwt \
  --language python \
  --output examples/vendor_onboarding/rules_types.py
```

5. Run the typed Python host app:

```sh
python examples/vendor_onboarding/host_app.py
```

Expected final line:

```txt
typed decision: needs_review (manual_review_required)
```

## CI And Editor Coverage

The repository treats this example as the typed executable-spec module fixture.
CI validates `rules.gwt`, runs the Python host app, verifies the generated
Python and TypeScript host types are current, checks the TypeScript host
client, runs strict Pyright over the Python package and host examples, and
checks the VS Code extension.

That means the flagship path stays covered across local validation, host
language integration, generated contracts, strict Python typing, and editor
support.

## Shadow Mode

Before replacing an existing production rule, run GWT beside the legacy path and
compare decisions. The shadow example keeps a small legacy Python decision
function, calls `REQUEST review vendor` through the generated client, and logs
field-level differences without failing the request.

```sh
python examples/vendor_onboarding/shadow_mode.py
```

Expected summary:

```json
{
  "cases": 2,
  "matches": 1,
  "mismatches": 1,
  "promotion_ready": false
}
```

The mismatch is intentional: the legacy function treats an expired document as
acceptable, while the GWT spec records `insurance_expired` and adds one risk
point. In a real adoption, this is the kind of mismatch to review before
promoting GWT as the source of truth.

## Host Examples

- Python host app:
  [`examples/vendor_onboarding/host_app.py`](host_app.py)
- Python shadow-mode comparison:
  [`examples/vendor_onboarding/shadow_mode.py`](shadow_mode.py)
- Generated Python helpers:
  [`examples/vendor_onboarding/rules_types.py`](rules_types.py)
- TypeScript host app:
  [`clients/typescript/examples/vendor-onboarding.ts`](../../clients/typescript/examples/vendor-onboarding.ts)
- Generated TypeScript declarations:
  [`clients/typescript/examples/vendor-onboarding.generated.d.ts`](../../clients/typescript/examples/vendor-onboarding.generated.d.ts)

## What This Demonstrates

- one `.gwt` file as the durable behavior artifact
- typed named request inputs and outputs
- typed JSON-shaped host input
- generated TypeScript host types, including `GwtRequestName`
- generated Python `TypedDict` contracts and request-specific client wrapper
- `gwt validate` as the local and CI validation gate
- strict Pyright coverage for the Python package and host examples
- TypeScript client and VS Code extension checks in CI
- typed tables for documents and risk signals
- explicit missing and expired document handling
- first-matching decision classification with `DECIDE`
- deterministic status and reason output
- embedded scenarios for approved, review, and rejected outcomes
