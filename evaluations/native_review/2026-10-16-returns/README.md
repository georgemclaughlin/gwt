# Return-value review qualification

Three independently specified request cases exercise the
[return-value pricing example](../../../examples/native_return_values/README.md).
The candidate changes the returned member discount from `0.1` to `0.2`:

| Case | Verified baseline | Candidate |
| --- | --- | --- |
| Two member units at 19.95 | Exact total 35.91 | Exact total 31.92 |
| Two ordinary units at 19.95 | Exact total 39.9 | Exact total 39.9 |
| Zero quantity | Assertion failure | Assertion failure |

All three cases are compared, with one changed outcome and one candidate
failure. The generator checks these expectations independently. Native capture,
replay, comparison, explanations, and HTML rendering run in Rust.

Chromium verifies selection/filtering, return steps visible in the default trail,
their return-contract explanation, operand links to the evaluated expression,
saved decision round trips, rejected stale/malformed imports, and 390px layout.
No JavaScript errors, external requests, or executed HTML injection occurred.
This checkpoint does not repeat exact-integer download qualification; the report
records that check as false, and earlier scenario/request checkpoints cover it.

The saved file has one **synthetic rejection** and two pending choices. A fresh
`assess-review` invocation reproduces the report identity and returns those counts
with `allAccepted: false`. These are storage and verification checks, not human
approval or evidence of improved comprehension.

- [Browser report](browser-report.json)
- [Fresh CLI assessment](cli-assessment-report.json)
- [Synthetic saved choices](decisions-returns.json)
- [Return evidence screenshot](returns-evidence.png)
- [Desktop](returns-desktop.png) and [mobile](returns-mobile.png) screenshots

Reproduce from the repository root with Playwright 1.63.0 and its Chromium:

```sh
cargo +1.96.0 build --locked -p gwt-core
python evaluations/native_review/generate_returns.py /tmp/gwt-native-return-fixtures
python evaluations/native_review/check_browser.py \
  /tmp/gwt-native-return-fixtures /tmp/gwt-native-return-browser --workflows returns
python evaluations/native_review/check_decisions.py \
  /tmp/gwt-native-return-fixtures /tmp/gwt-native-return-browser --expected-count 1
```

The recorded run used `mcr.microsoft.com/playwright/python:v1.63.0-noble` with
networking disabled. Native conformance additionally exercises 32 exact-pricing
inputs and their candidate revisions/generated scenarios, typed returns,
branches/traversals, aliasing, resource failures, recursion, and source evidence.
The full 119 native tests and Clippy pass on Rust 1.85.0 and 1.96.0. The example
passes Python canonical formatting/validation and native check/test/run.
