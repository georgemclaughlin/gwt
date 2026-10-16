# Whole-corpus migration qualification

Two corpora exercise real retained previous executables and the current native
engine. Previous engines and their source archives are recorded in the earlier
[engine-transition qualification](../2026-10-16/README.md). The deliberately
changed assertion message remains a controlled fixture, not a claim about an
actual production language revision.

The complete corpus has nineteen entries: nine from each previous engine and
one already belonging to the current engine. Fifteen old observations are
preserved, three change, and the current case replays and remains exact. The
incomplete corpus adds a corrupt case and a forged current observation with a
recomputed checksum, while omitting one engine mapping. All twenty-one entries
remain in its report: ten are ready and eleven are unavailable. Missing mappings,
corruption, and a baseline mismatch never disappear into a successful subset.

Both reports' corpus and report identities were independently recomputed in
Python. Entry IDs, labels, and order match their inputs. Original corpus files
remain byte-identical. A label containing HTML-shaped text stays text.

Offline Chromium checks cover all forty displayed entries: exact JSON downloads
including `9007199254740993`, case search and status filters, complete decision
save/load, stale/duplicate/oversized/missing-entry rejection without form loss,
and refusal to accept unavailable evidence. Operand targets are globally unique
and stay within their originating case. A recorded operand was followed to its
source. Desktop and 390-pixel mobile screenshots were inspected; the pages have
no horizontal overflow. Both remain readable with JavaScript disabled. There
were no page errors or external requests.

All saved choices are explicitly synthetic. The complete fixture has nineteen
acceptances. The incomplete fixture has ten acceptances and eleven requests for
information. Fresh CLI assessment reproduces those choices after reexecuting
all available verification. Only the complete fixture exports a new corpus;
each of its nineteen cases then replays successfully. IDs, labels, order, and
candidate records are unchanged from the reviewed transition. Existing-file
overwrite is refused, and relabeling one original entry invalidates the saved
acceptances. No live corpus was approved or modified.

- [Generation, totals, and independent hashes](generation.json)
- [Browser results](browser.json)
- [Fresh assessments and exported case replay checks](assessments.json)
- [Complete report](complete.report.json) and [incomplete report](incomplete.report.json)
- [Complete original corpus](complete.corpus.json) and [incomplete original corpus](incomplete.corpus.json)
- [Synthetic complete decisions](complete.decisions.json) and [incomplete decisions](incomplete.decisions.json)
- [Exported qualification corpus](complete.promoted.json) and [receipt](export-receipt.json)
- [Native tests and engine identity](native-verification.json)
- [Current engine source archive](target-engine-source.tar.gz)
- [Desktop review](complete-desktop.png), [mobile review](incomplete-mobile.png),
  [evidence-only change](complete-evidence.png), and [unavailable case](incomplete-evidence.png)

Six new protocol/library/CLI tests bring native coverage to 168 tests. All tests
and Clippy pass on Rust 1.85.0 and 1.96.0; formatting passes. Unit and integration
fixtures additionally cover candidate compilation failure, every non-acceptance
state, changed executable digests, removed/reordered/renamed entries, complete
coverage validation, explicit engine maps, and new-file-only export. Synthetic
protocol fixtures are labeled separately from the real-executable qualification.

## Reproduction

Rebuild the previous engines using the earlier qualification's instructions.
The current source archive expands to `corpus-target-engine/`; build with Rust
1.96.0 and its retained Cargo lockfile. Rebuilt executable hashes can differ,
so regenerate the reports and choices together. Old decisions must not be reused
against changed proposal identities.

Use fresh output directories:

```sh
python evaluations/native_migration/corpus_fixtures.py \
  evaluations/native_migration/2026-10-16 /tmp/gwt-corpus-fixtures \
  --previous-engine /path/to/previous/gwt-native \
  --changed-engine /path/to/changed/gwt-native \
  --native /path/to/corpus-target/gwt-native
python evaluations/native_migration/check_corpus_browser.py \
  /tmp/gwt-corpus-fixtures /tmp/gwt-corpus-browser
python evaluations/native_migration/assess_corpus_choices.py \
  /tmp/gwt-corpus-fixtures /tmp/gwt-corpus-browser /tmp/gwt-corpus-assessment \
  --native /path/to/corpus-target/gwt-native
```

The browser check requires Playwright and Chromium. This run used Playwright
1.63.0 in `mcr.microsoft.com/playwright/python:v1.63.0-noble`, with network
disabled and read-only fixture/dependency mounts. The single-case page shares
its evidence renderer with corpus review; its eighteen-case browser regression
is recorded separately in [single-case browser results](single-case-browser.json).

These checks qualify a complete-corpus development workflow. They do not prove
human comprehension gains, authenticate reviewers, qualify production deployment,
or adapt old source to a changed language. Those remain open under the full
project goal. The external pilot remains pending.
