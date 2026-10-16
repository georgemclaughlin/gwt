# Saved-decision browser qualification — October 16, 2026

Five native review pages were exercised in Chromium with Playwright 1.63.0 in a
disposable container with networking disabled. All 380 cases remained selectable:
336 refund comparisons, seven failure/precision/escaping cases, and 37 stock
reservation comparisons.

Each page was given one explicitly synthetic rejection and note, downloaded,
reloaded, and restored from the decision file. Decision filters retained the
right case and note. Stale identities, missing cases, invalid statuses, duplicate
JSON keys, and attempted acceptance of unverified evidence were refused without
discarding existing choices. Notes containing HTML/script-like text stayed plain
text. The original exact-integer review download still preserved
`9007199254740993`. No JavaScript errors, external requests, or horizontal
overflow at 390px were observed.

An independent Python encoding reproduced each report's SHA-256 identity.
The five files downloaded by the browser were then assessed by the native CLI
against freshly executed reviews. Each returned one rejection, every other case
pending, and `allAccepted: false`, with exit status 1 as expected. This tests the
browser-to-CLI contract; it records no project approval or human-comprehension
result. The reviewer is explicitly named `Synthetic browser test reviewer`.

- [Browser assertions](browser-report.json)
- [Fresh CLI assessments](cli-assessment-report.json)
- [Desktop screenshot](desktop.png)
- [Mobile screenshot](mobile.png)
- [Example synthetic decision file](decisions-stock-reservation.json)

The Rust suite passes 98 integration tests and Clippy on both Rust 1.85.0 and
1.96.0. Formatting passes on 1.96.0. Tests include report binding, coverage,
reviewer/note limits, expected failures, and stale decision refusal. Screenshots
were inspected for readable notes, controls, wrapping, and outcome differences.

Reproduce with Playwright 1.63.0 and Chromium installed:

```sh
cargo build --locked -p gwt-core
python evaluations/native_review/generate.py /tmp/gwt-native-review-decisions
python evaluations/native_review/check_browser.py \
  /tmp/gwt-native-review-decisions /tmp/gwt-native-decision-browser-results
python evaluations/native_review/check_decisions.py \
  /tmp/gwt-native-review-decisions /tmp/gwt-native-decision-browser-results
```

Full cases, reports, and HTML stay in the chosen fixture directory. Rebuild and
regenerate together after native engine changes; saved choices bind to the exact
report and do not migrate automatically. These checks cover the implemented
offline workflow, not authenticated reviewer identities or immutable history.
