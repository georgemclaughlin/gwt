# Printed-output review qualification

The [packing receipt](../../../examples/native_print_expectations/README.md)
prints a heading, a parcel record, and quantity `9007199254740993`. The candidate
changes only the final print to `parcel.quantity + 1`.

| Case | Baseline | Candidate |
| --- | --- | --- |
| Receipt scenario with exact print expectation | Passes | Fails with `print_assertion_failed`; final output is 9007199254740994 |
| Quiet scenario expecting `[]` | Passes, no output | Passes, no output |
| Named request with fixed host input | Succeeds | Succeeds; final printed quantity changes |

All three cases are compared, with two outcome changes and one candidate failure.
`generate_prints.py` checks the full output arrays against independent constants.
Chromium verifies case selection/filters, the assertion in the default trail,
matched/mismatched explanations, operand links back to print events, exact integer
report download, saved-decision round trips, rejected stale/malformed choices,
and 390px layout. Evidence and mobile screenshots were visually inspected.
No JavaScript errors, external requests, or executed HTML injection occurred.

Downloaded choices contain one **synthetic rejection** and two pending cases.
A fresh CLI assessment reproduces their report identity and returns
`allAccepted: false`. This establishes storage/replay behavior, not human approval
or improved comprehension.

- [Browser report](browser-report.json)
- [Fresh CLI assessment](cli-assessment-report.json)
- [Synthetic choices](decisions-prints.json)
- [Assertion evidence](prints-evidence.png) and [mobile layout](prints-mobile.png)
- [Native verification record](native-verification.json)

Reproduce from the repository root using Playwright 1.63.0 and its Chromium:

```sh
cargo +1.96.0 build --locked -p gwt-core
python evaluations/native_review/generate_prints.py /tmp/gwt-native-print-fixtures
python evaluations/native_review/check_browser.py \
  /tmp/gwt-native-print-fixtures /tmp/gwt-native-print-browser --workflows prints
python evaluations/native_review/check_decisions.py \
  /tmp/gwt-native-print-fixtures /tmp/gwt-native-print-browser --expected-count 1
```

The recorded browser run used `mcr.microsoft.com/playwright/python:v1.63.0-noble`
with networking disabled. All 137 native tests and Clippy pass on Rust 1.85.0 and
1.96.0. Eight new tests cover mixed/empty output, changes and ordering, bounded
JSON, duplicate keys, execution/evidence limits, original source spans, generated
scenarios, capture/replay, and revisions. Twelve Python formatter tests pass;
Python checking/execution do not support the new assertion. Expected-failure
scenario generation remains pending.
