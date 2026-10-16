# Native collection review qualification — October 16, 2026

The native collection checkpoint was checked in Chromium with Playwright 1.63.0
in a disposable container with networking disabled. Five Rust-generated review
pages retained all 380 selectable cases: 336 refund comparisons, seven cases
covering failures/precision/escaping, and 37 stock-reservation comparisons.

The reservation candidate deliberately changes `available >= quantity` to
`available > quantity`. Independently calculated expectations cover stock from
zero through five and requested quantities from one through six, plus an empty
order. Exactly five outcomes change: orders that would consume the last units
now report shortages. All candidate outputs match those expectations.

Browser assertions exercise every case, search and status filters, empty search
results, expression operand navigation, and exact JSON download. Collection
items, selections, mutations, and sum contributions appear in the default trail;
expanding a sum contribution exposes its subtotal. No JavaScript errors,
external requests, injected HTML execution, or horizontal overflow at 390px
were observed. Download retained integer `9007199254740993` exactly.

- [Browser assertion results](browser-report.json)
- [Independent generation checks](generation-report.json)
- [Reservation desktop](reservation-desktop.png)
- [Reservation mobile](reservation-mobile.png)
- [Collection evidence](reservation-evidence.png)

The native suite passes 70 integration tests and Clippy on Rust 1.85.0 and
1.96.0. Collection tests cover source-order aliasing, active-collection shape
guards through calls and nested searches, static errors, exact sums, limits,
three embedded reservation scenarios, independent stock/quantity expectations,
and captured-case replay/comparison. Python format and validate pass for the
shared reservation source. These are engineering checks, not human review-time
or comprehension measurements.

Reproduce from the repository root with Playwright 1.63.0 and Chromium installed:

```sh
cargo build --locked -p gwt-core
python evaluations/native_review/generate.py /tmp/gwt-native-review-collections
python evaluations/native_review/check_browser.py \
  /tmp/gwt-native-review-collections /tmp/gwt-native-collection-browser-results
```

Generated cases, full JSON, and HTML stay in the chosen temporary directory.
Regenerate them after native engine changes because cases bind an engine source
fingerprint. The browser test driver uses Python; the reviewed language
execution, capture, replay, comparison, and HTML generation run in Rust.
