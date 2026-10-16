# Copied-argument review qualification

Three independently specified request cases exercise the
[value-argument pricing example](../../../examples/native_value_arguments/README.md).
The candidate changes the member discount argument from `0.1` to `0.2`:

| Case | Verified baseline | Candidate |
| --- | --- | --- |
| Two member units at 19.95 | Exact total 35.91 | Exact total 31.92 |
| Two ordinary units at 19.95 | Exact total 39.9 | Exact total 39.9 |
| Zero quantity | Assertion failure | Assertion failure |

All three cases are compared, with one changed outcome and one candidate failure.
The generator checks these expectations independently, verifies the original
basket remains unchanged, and checks that the discount mutates `amount (value)`.
Native capture, replay, comparison, explanations, and HTML rendering run in Rust.

Chromium verifies selection/filtering, copied arguments in the default trail,
the local-copy explanation, operand links, saved-decision round trips, rejected
stale/malformed imports, and 390px layout. The evidence and mobile screenshots
were visually inspected. No JavaScript errors, external requests, or executed
HTML injection occurred. This checkpoint does not repeat exact-integer download
qualification: that field is false in the report, and earlier checkpoints cover it.

The saved file contains one **synthetic rejection** and two pending choices.
Fresh `assess-review` execution reproduces the report identity and returns those
counts with `allAccepted: false`. This verifies storage and replay; it does not
establish human approval or improved comprehension.

- [Browser report](browser-report.json)
- [Fresh CLI assessment](cli-assessment-report.json)
- [Synthetic saved choices](decisions-arguments.json)
- [Argument evidence](arguments-evidence.png)
- [Desktop](arguments-desktop.png) and [mobile](arguments-mobile.png) screenshots
- [Native verification record](native-verification.json)

Reproduce from the repository root with Playwright 1.63.0 and its Chromium:

```sh
cargo +1.96.0 build --locked -p gwt-core
python evaluations/native_review/generate_returns.py /tmp/gwt-native-argument-fixtures --value-arguments
python evaluations/native_review/check_browser.py \
  /tmp/gwt-native-argument-fixtures /tmp/gwt-native-argument-browser --workflows arguments
python evaluations/native_review/check_decisions.py \
  /tmp/gwt-native-argument-fixtures /tmp/gwt-native-argument-browser --expected-count 1
```

The recorded run used `mcr.microsoft.com/playwright/python:v1.63.0-noble` with
networking disabled. Ten argument tests cover 32 exact pricing inputs and
candidate revisions/generated scenarios, copies and aliases, contextual typing,
quoted text, source mapping, traversal guards, evaluation failures, evidence
limits, and recursion. All 129 native tests and Clippy pass on Rust 1.85.0 and
1.96.0; Rust formatting passes. The example passes native check/test/run and
Python canonical formatting. The eleven Python formatter tests pass; Python
runtime/checker compatibility is not claimed for grouped calls.

The prior nine development workloads retain all 189 normal/budget observations
exactly. The recorded one-iteration harness run is an observation regression
check, not a timing measurement. The verification record identifies the engines
and links the raw observations and test/Clippy logs.
