# Offline validation report qualification

Local functional evidence for the native validation HTML view. This is not a
human comprehension study, external pilot, or publication.

Open [delivery.html](delivery.html) for a real example: ten delivery scenarios,
20 passing expectations, and a visible gap for the request that those embedded
scenarios do not enter. Separate host tests cover that request. The report
includes its captured source and retains the validation scope distinction.

## Native checks

Rust 1.85.0 and 1.96.0 pass all 218 tests (214 integration and four unit tests),
plus Clippy with warnings denied. Logs are `test-*.log` and `clippy-*.log`.
Formatting, view JavaScript syntax, and whitespace checks pass. CI now includes
the view's JavaScript syntax check; no hosted CI run is claimed.

Six new integration tests cover immutable report/source pairing, rendering after
files change/disappear, markup escaping, load/check/no-scenario states, omitted
oversized source snapshots, exact numeric limits, and CLI no-overwrite/exit
behavior. A unit test verifies that escaping is bounded during serialization,
including Unicode and expansion of markup delimiters.

## Browser and visual checks

`fixtures-final/` contains seven independently specified cases: a mixed six-
scenario program, a clean pass, allowed declarations only, a type-check failure,
a formatting failure with passing execution, 105 declarations, and a loading
failure. The mixed fixture has seven expectations: four passed, two failed, and
one without an outcome. Its one scenario without expectations and one uncalled
helper remain visible. Input text includes CRLF, Unicode, a large integer, and
markup-like source and names.

`browser-final/browser.json` records nine groups of interaction checks on
Chromium 153.0.8010.12:

- Gate states, exact totals, evidence warnings, and escaped markup.
- Scenario search, failed/gap filters, and no-match/missing-evidence states.
- UTF-8/CRLF and example-template source highlights, full module views, Escape,
  and restoration of keyboard focus.
- Imported definition links and the no-recorded-call filter.
- Report/source downloads matching exact JSON and source contents.
- A 390px layout with visible declaration source links and a usable modal.
- All 105 declarations accessible through pagination.
- Distinct clean, no-scenario, check, load, and formatting failure views.
- No script errors and no network requests.

Desktop, phone, and source-dialog screenshots were inspected. The initial
`fixtures/` and `browser/` results predate a mobile table improvement and clearer
singular/plural warning text; `*-final/` records the verified revision.

The Browser plugin had no connected browser after its documented discovery
checks. Qualification used the already-installed Playwright 1.63.0 dependencies
and local `mcr.microsoft.com/playwright/python:v1.63.0-noble` image with networking
disabled. No browser or dependencies were downloaded for this checkpoint.

## Packaged artifact

`package-1.96.0/qualification.json` records independent fingerprint verification,
matching package/host dependency graphs, 18 host observations, 288 concurrent
executions, and 18 relocated replays. Its installed source fingerprint is
`sha256:ca7cc8e4195af605614b13a006e3f060654f1263a4119bf59c4c665aef010183`.
This identifies package source, not compiler flags, the executable, or its
effective host dependencies; those are recorded separately.

The installed executable independently generated `fixtures-packaged/`. All nine
browser check groups pass on those artifacts, including source links, downloads,
mobile layout, and every failure state. See `browser-packaged/browser.json`.
The packaged renderer includes its HTML, CSS, and JavaScript without relying on
files outside the Cargo artifact. `source-hashes.json` binds the implementation,
test, and qualification scripts used here.

## Reproduce

With a built native CLI and locally installed Python Playwright/Chromium:

```sh
python evaluations/native_validation/generate.py /tmp/gwt-validation-fixtures
python evaluations/native_validation/check_browser.py /tmp/gwt-validation-fixtures /tmp/gwt-validation-browser
```

Both output directories must be new. Pass `--native PATH` to the generator to
exercise an independently installed executable. The validation command creates
only a new HTML destination, still returns its ordinary JSON, and retains exit
one for failed validation. These reports provide observation summaries and
captured source, not full traces, approval controls, or proof of policy correctness.
