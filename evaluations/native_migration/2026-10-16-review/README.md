# Native migration review qualification

Eighteen retained cases were replayed through their real previous executables,
recaptured on the current engine, presented in offline Chromium, and assessed
again using browser-saved decisions. The earlier [engine-transition qualification](../2026-10-16/README.md)
contains the original cases and previous-engine source archives. Its deliberately
changed assertion message remains a controlled qualification fixture, not a
production language change.

The page separates outcome, state, and evidence changes. A raw failing scenario
shows changed failure text; the expected-rejection scenario still passes while
its failure evidence changes. Both retain source locations and operand links.
Screenshots were inspected at desktop and 390-pixel mobile widths.

All 18 pages passed complete exact-value proposal download, decision save/load,
stale/duplicate-key/malformed/oversized decision refusal without form loss, and
mobile width checks. Event-bearing cases passed operand navigation; zero-event
boundary/budget cases remained reviewable. Large integers survived download
exactly. Text resembling HTML stayed text. There were no page errors or external
requests. Recorded behavior remained readable with JavaScript disabled.

Saved choices are explicitly synthetic: one acceptance, one rejection, one
needs-information choice, and fifteen pending choices. Fresh CLI assessment
reproduced all eighteen and rechecked both engines. Only the accepted exact-print
fixture exported a new case; it replayed successfully. Existing-file overwrite
and cross-proposal stale acceptance were refused. Original files remained
byte-identical. These checks approve no real corpus and demonstrate no human
comprehension benefit.

- [Browser results](browser.json)
- [Fresh assessments and export checks](assessments.json)
- [Synthetic export receipt](preserved-exact-prints.export.json)
- [Exported qualification case](preserved-exact-prints.case.json)
- [Native verification and current engine identity](native-verification.json)
- [Current engine source archive](target-engine-source.tar.gz)
- [Desktop raw failure](changed-message-raw-failure-desktop.png)
- [Mobile raw failure](changed-message-raw-failure-mobile.png)
- [Desktop evidence-only change](changed-message-expected-rejection-desktop.png)
- [Desktop exact prints](preserved-exact-prints-desktop.png)

Full proposals and synthetic decisions are retained beside this document. Each
proposal retains the exact original and candidate observations. All 162 native
tests and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes. The thirteen
migration tests include unavailable-candidate review/acceptance refusal, escaped
source, exact embedded JSON, stale decisions, bounded parsing, and CLI reexecution.
Unavailable-candidate presentation is unit-tested; the eighteen real-engine
browser cases all have available candidates.

## Reproduction

Rebuild the previous engines using the earlier qualification's instructions.
The current archive expands to `review-target-engine/` and contains source,
manifests, lockfile, and license. Build it with Rust 1.96.0. Rebuilt executable
hashes can differ, so regenerate proposals and decisions together. Old saved
acceptances are intentionally not portable across changed executable identities.

With those engines available, use fresh output directories:

```sh
python evaluations/native_migration/review_fixtures.py \
  evaluations/native_migration/2026-10-16 /tmp/gwt-review-fixtures \
  --previous-engine /path/to/previous/gwt-native \
  --changed-engine /path/to/changed/gwt-native \
  --native /path/to/review-target/gwt-native
python evaluations/native_migration/check_review_browser.py \
  /tmp/gwt-review-fixtures /tmp/gwt-review-browser
python evaluations/native_migration/assess_review_choices.py \
  /tmp/gwt-review-fixtures /tmp/gwt-review-browser /tmp/gwt-review-assessment \
  --native /path/to/review-target/gwt-native
```

The browser script requires Playwright and Chromium. This run used the
`mcr.microsoft.com/playwright/python:v1.63.0-noble` image with network disabled,
read-only fixture/dependency mounts, and Playwright 1.63.0. The fixture generator
was separately rerun against all eighteen cases and reproduced the proposals.

Bulk corpus promotion, source adaptation across engine versions, deployment
qualification, and comparative human evidence remain open. No external pilot
was started.
