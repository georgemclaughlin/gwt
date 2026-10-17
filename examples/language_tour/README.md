# Language Tour

> Historical example/reference. Only entries in the [active catalog](../catalog.json) are qualified for current GWT. Retired host commands can be reproduced from [the pre-retirement tree](https://github.com/georgemclaughlin/gwt/tree/4f403dc51eda5382c6a12c0757cb26deac34012a/examples/language_tour).

This example is a small expense reimbursement workflow. It shows the current
language surface in one place without the size of the larger order fulfillment
sample.

- `rules.gwt` declares records, a named request with `OUTPUT`, reusable behavior,
  and eight embedded regression scenarios, including expanded example rows.
- `request.gwt` is an app-style input file. It provides data and runs the
  behavior, but it does not hardcode expected output.
- `native_request.gwt` explicitly imports the rules and includes expectations,
  so it can run directly through the Rust engine.

The workflow computes a reimbursement decision from expense lines. It uses:

- explicit behavior parameters: `WHEN review <report> into <decision>`
- record-backed request and output contracts
- `TYPE` aliases for reusable list and literal-union contracts
- `count` and projected `sum` for list summaries
- `FOR ... WHERE` and `append` for approved line descriptions
- one `FIND ... ELSE` step for the first policy violation and its missing case
- literal-union status and reason contracts
- stable JSON output where `result` contains only declared `OUTPUT` paths

A violation means an amount strictly greater than the limit, regardless of
whether the line is reimbursable. The first violation in input order supplies
its description and amount. Approved totals include only reimbursable lines at
or below the limit. The no-match branch clears all previous violation fields,
including when the behavior reuses a decision record. Scenarios cover exact
limits, multiple violations, non-reimbursable violations, and empty input after
an earlier review.

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

The same rules also run on the native engine:

```sh
target/debug/gwt validate examples/language_tour/rules.gwt
target/debug/gwt run examples/language_tour/native_request.gwt
```

Native `number` values use exact decimal strings in JSON, so the native approved
total is `"60"`. Direct entry execution returns the complete scenario state;
explicit JSON request execution returns declared outputs. See
[native request entries](../../docs/native-request-entries.md).

The `exists`-then-`find` refactor preserves the existing policy on 436 checked
integer-domain inputs across original Python, revised Python, and the packaged
Rust engine. It is a source-adaptation example, not a measured human-readability
result. [Evidence and review](../../evaluations/language_tour/2026-10-16/README.md)
record the tested limits and deliberate mutation checks.
