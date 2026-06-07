# Language Tour

This example is a small expense reimbursement workflow. It shows the current
language surface in one place without the size of the larger order fulfillment
sample.

- `rules.gwt` declares records, a named request with `OUTPUT`, reusable behavior,
  and an embedded regression scenario.
- `request.gwt` is an app-style input file. It provides data and runs the
  behavior, but it does not hardcode expected output.

The workflow computes a reimbursement decision from expense lines. It uses:

- explicit behavior parameters: `WHEN review <report> into <decision>`
- record-backed request and output contracts
- `TYPE` aliases for reusable list and literal-union contracts
- `count` and projected `sum` for list summaries
- `FOR ... WHERE` and `append` for approved line descriptions
- `exists` and `find` for optional policy violations
- literal-union status and reason contracts
- stable JSON output where `result` contains only declared `OUTPUT` paths

## Commands

Format check:

```sh
python -m gwtlang format examples/language_tour/rules.gwt --check
python -m gwtlang format examples/language_tour/request.gwt --check
```

Static check:

```sh
python -m gwtlang check examples/language_tour/rules.gwt
```

Run embedded regression coverage:

```sh
python -m gwtlang test examples/language_tour/rules.gwt
```

Run like an application would:

```sh
python -m gwtlang run examples/language_tour/rules.gwt --input examples/language_tour/request.gwt --json
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
      "has_violation": true,
      "violation_description": "monitor",
      "violation_amount": 225,
      "status": "needs_review",
      "reason": "line_over_policy_limit"
    }
  }
}
```
