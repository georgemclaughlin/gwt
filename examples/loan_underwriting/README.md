# Loan Underwriting Example

This folder shows GWT as a small embeddable rules/workflow engine.

- `rules.gwt` contains reusable underwriting behavior and embedded regression
  scenarios.
- `request.gwt` is a production-style input: it provides facts and runs the
  workflow, but it does not hardcode expected output.
- `request_with_assertions.gwt` is the same request with `THEN` assertions,
  useful when a caller wants runtime validation.

Decision status and reason fields use literal-union contracts so the workflow
can only produce declared states such as `"approved"`, `"manual_review"`, and
`"denied"`.

## Commands

Static check only:

```sh
python -m gwtlang check examples/loan_underwriting/rules.gwt
```

Run embedded tests:

```sh
python -m gwtlang test examples/loan_underwriting/rules.gwt
```

Run like an application would:

```sh
python -m gwtlang run examples/loan_underwriting/rules.gwt --input examples/loan_underwriting/request.gwt --json
```

Run the request and assert expected output:

```sh
python -m gwtlang run examples/loan_underwriting/rules.gwt --input examples/loan_underwriting/request_with_assertions.gwt --json
```

## Check Vs Test Vs Run

`gwt check` does not execute underwriting logic. It parses the file and runs
static checks such as behavior matching, contract types, expression syntax, and
invalid statement shapes.

`gwt test` executes the embedded `SCENARIO` and `EXAMPLES` table in `rules.gwt`.
The expected values in the table are test assertions. They do not drive the
decision; they only verify the decision that the workflow computed.

`gwt run --input request.gwt --json` is the production-style path. A host app
would collect data from an API, database, or form, create a request, run the
rules file, and read the JSON output.

Excerpt from `request.gwt` JSON output:

```json
{
  "ok": true,
  "scenario_count": 1,
  "result": {
    "decision": {
      "status": "approved",
      "reason": "strong_application",
      "risk_points": 2,
      "interest_rate": 6.25
    }
  }
}
```
