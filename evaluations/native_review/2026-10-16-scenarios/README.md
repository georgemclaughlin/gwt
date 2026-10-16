# Native scenario capture and mixed review qualification

This checkpoint exercises 13 cases in one review: ten captured delivery example
rows, one failing scenario, one scenario that prints an exact integer, and one
request with fixed host input. Cases are captured/replayed/compared by the native
engine. Python drives the test; it does not supply the execution results.

The candidate changes the ordinary delivery fee from nine to eight and the
printed integer from `9007199254740993` to `9007199254740994`. Independent
expectations require four changed outcomes: two original example rows now fail
their fee assertion, the print scenario changes output, and the host request
returns eight. The invalid-weight scenario remains a verified execution failure.
All 13 cases are compared; three candidate executions fail. A complete review
is coverage, not approval.

Chromium checks every case's selection, changed/failure filters, search by the
scenario name, explicit scenario/setup labels, exact printed integer display and
download, saved-decision round trips, rejected malformed/stale imports, and no
horizontal overflow at 390px. The new workflow does not repeat operand-link
qualification; earlier request/collection checkpoints cover it. No external
requests or JavaScript errors occurred, and escaped note text did not execute.

The downloaded decision file contains one **synthetic rejection** and 12 pending
choices. A fresh native `assess-review` run reproduces its report identity and
returns those counts with `allAccepted: false`. This tests persistence and
verification; it is not a real reviewer decision or human-benefit evidence.

Artifacts:

- [Browser report](browser-report.json)
- [Fresh CLI assessment](cli-assessment-report.json)
- [Synthetic saved decisions](decisions-scenarios.json)
- [Desktop screenshot](scenario-desktop.png)
- [Mobile screenshot](scenario-mobile.png)

Reproduce from the repository root with Playwright 1.63.0 and its Chromium
installed in the Python environment used for the browser check:

```sh
cargo +1.96.0 build --locked -p gwt-core
python evaluations/native_review/generate_scenarios.py /tmp/gwt-native-scenario-fixtures
python evaluations/native_review/check_browser.py \
  /tmp/gwt-native-scenario-fixtures /tmp/gwt-native-scenario-browser --workflows scenarios
python evaluations/native_review/check_decisions.py \
  /tmp/gwt-native-scenario-fixtures /tmp/gwt-native-scenario-browser --expected-count 1
```

The recorded browser run used the isolated
`mcr.microsoft.com/playwright/python:v1.63.0-noble` image with networking disabled.
Generated baseline/candidate sources pass Python format/check; their deliberate
failing scenarios are not claimed to pass validation. Native tests cover
scenario selection, failure/print/budget capture, versioned target validation,
frozen imports, forged baselines, missing candidate names, and changing candidate
setup. Tests and Clippy pass on Rust 1.85.0 and 1.96.0, with 108 total tests;
formatting passes on 1.96.0.

Scenario comparisons run each revision's own setup and assertions; they do not
freeze host inputs. Source-level failure/print expectations, generated tests for
those observations, and engine migration remain unfinished.
