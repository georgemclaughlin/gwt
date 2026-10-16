# Expected-failure review qualification

The [stock-rejection example](../../../examples/native_expected_failures/README.md)
requires positive quantities and sufficient stock before reserving. The candidate
removes only the sufficient-stock guard.

| Case | Baseline | Candidate |
| --- | --- | --- |
| Shortage scenario expecting rejection | Passes, stock remains 2 | Fails with `failure_assertion_failed`; request unexpectedly succeeds and stock becomes -1 |
| Valid reservation scenario | Passes, stock becomes 1 | Same outcome |
| Zero-quantity scenario expecting rejection | Passes, stock remains 3 | Same outcome |
| Raw shortage request with fixed host input | Fails with `assertion_failed` | Succeeds with incorrect stock -1 |

All four cases are compared, with two outcome changes and one candidate scenario
failure. `generate_failures.py` checks these outcomes, states, and captured messages
against independent constants. Expected rejection is a passing scenario condition;
it does not turn direct host execution into a successful request.

Chromium verifies filters/selection, the failure assertion in the default trail,
the original rejected action's source excerpt, expected/unexpected explanations,
operand links, saved-decision round trips, stale/malformed import rejection, and
390px layout. Evidence and mobile screenshots were visually inspected. No
JavaScript errors, external requests, or executed HTML injection occurred.
Exact large-integer download was not repeated; its report flag is false, and the
previous printed-output checkpoint qualifies it.

Saved choices contain one **synthetic rejection** and three pending cases. Fresh
CLI assessment reproduces the report identity with `allAccepted: false`. These
are storage and execution checks, not human approval or comprehension evidence.

- [Browser report](browser-report.json)
- [Fresh CLI assessment](cli-assessment-report.json)
- [Synthetic choices](decisions-failures.json)
- [Failure evidence](failures-evidence.png) and [mobile layout](failures-mobile.png)
- [Native verification record](native-verification.json)

Reproduce from the repository root using Playwright 1.63.0 and its Chromium:

```sh
cargo +1.96.0 build --locked -p gwt-core
python evaluations/native_review/generate_failures.py /tmp/gwt-native-failure-fixtures
python evaluations/native_review/check_browser.py \
  /tmp/gwt-native-failure-fixtures /tmp/gwt-native-failure-browser --workflows failures
python evaluations/native_review/check_decisions.py \
  /tmp/gwt-native-failure-fixtures /tmp/gwt-native-failure-browser --expected-count 1
```

The recorded run used `mcr.microsoft.com/playwright/python:v1.63.0-noble` with
networking disabled. All 149 native tests and Clippy pass on Rust 1.85.0 and
1.96.0. Twelve new tests include 25 independent stock boundaries, generated
revisions, partial-state checks, binding/scope safety, unsupported error refusal,
budgets, recursion, and original source evidence. Thirteen Python formatter tests
pass; Python checking/execution do not implement this native extension.
