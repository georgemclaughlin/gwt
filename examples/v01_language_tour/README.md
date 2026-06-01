# v0.1 Language Tour

This example is a small expense reimbursement workflow. It is meant to show the
current v0.1 language surface in one place without the size of the larger order
fulfillment sample.

- `rules.gwt` declares DTOs, `REQUEST` / `OUTPUT` contracts, reusable behavior,
  and an embedded regression scenario.
- `request.gwt` is an app-style input file. It provides data and runs the
  behavior, but it does not hardcode expected output.

The workflow computes a reimbursement decision from expense lines. It uses:

- explicit behavior parameters: `WHEN review <report> into <decision>`
- DTO-backed request and output contracts
- `count` and `sum` for list summaries
- `FOR ... WHERE` and `append` for approved line descriptions
- `find` for the first policy violation
- stable JSON output where `result` contains only declared `OUTPUT` paths

## Commands

Format check:

```sh
python -m gwtlang format examples/v01_language_tour/rules.gwt --check
python -m gwtlang format examples/v01_language_tour/request.gwt --check
```

Static check:

```sh
python -m gwtlang check examples/v01_language_tour/rules.gwt
```

Run embedded regression coverage:

```sh
python -m gwtlang test examples/v01_language_tour/rules.gwt
```

Run like an application would:

```sh
python -m gwtlang run examples/v01_language_tour/rules.gwt --input examples/v01_language_tour/request.gwt --json
```

Excerpt from the JSON output:

```json
{
  "ok": true,
  "result": {
    "decision": {
      "line_count": 4,
      "submitted_total": 297,
      "approved_total": 60,
      "approved_descriptions": ["airport taxi", "team lunch"],
      "violation_description": "monitor",
      "violation_amount": 225,
      "status": "needs_review",
      "reason": "line_over_policy_limit"
    }
  }
}
```
