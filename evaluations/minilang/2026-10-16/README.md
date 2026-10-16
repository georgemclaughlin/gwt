# Shared MiniLang evaluator qualification

The original Python fixture passes whole one-of statements into helpers that
implicitly assume a kind. The revised dispatcher passes the needed payload
fields to explicitly typed helpers. `engine.gwt` is shared by both engines;
Python and native entries supply their own supported setup syntax. Public request
and output contracts remain unchanged. No native engine code changed.

`before.gwt` freezes the original source. `after/` freezes the shared engine,
both scenario entries, and JSON input. See the
[adaptation and readability tradeoff](../../../docs/native-minilang-adaptation.md).

## Independent semantic comparison

`../qualify.py` compares the original Python source, revised Python source, and
previously qualified packaged Rust executable against a separate host model.
All 943 probes match (`comparison/report.json`, `comparison/observations.json`):

- every permutation of the six AST statements: 720 orderings;
- 125 combinations of numeric bindings and comparison thresholds;
- original input, missing token lexemes, each individual token/statement/list/
  binding removal, unknown source, varied lists, stale state, and duplicate names.

The host oracle defines expected complete front-end/runtime outputs independently
of GWT execution. Numeric fields are compared by value because native exact
decimals serialize as strings; text and other structure remain strictly compared.
Inputs here are integer-domain fixtures, not a fractional-number equivalence test.
The revised Python output also equals the original Python output directly.

Among the original and 125 arithmetic probes, an incorrect inclusive threshold is
detected seven times and an incorrect triple-map multiplier 126 times. Probe IDs
are retained in the report. These deliberately incorrect sources are not accepted
domain changes.

## Regression and artifact checks

- Three new Rust tests verify seven explicit request expectations with ordered
  domain errors, source explanations and replay; two native scenarios with 15
  expectations; clearing reused state with a missing-reset mutation; and a
  captured equality boundary against an inclusive-comparison mutation.
- Rust 1.85.0 and 1.96.0 each pass 259 tests (255 integration and four unit) and
  Clippy with warnings denied (`test-*.log`, `clippy-*.log`). All 614 Python tests
  pass (`python-tests.log`). The native scenario entry is explicitly assigned to
  `minilang.rs` in the Python example runner, while its formatter coverage remains.
- All example formatting, top-level Python checking, both reference request
  workflows, extension syntax, Rust formatting, and whitespace checks pass
  (`final-checks.log`, `python-*-request.json`).
- The previously qualified package from
  `evaluations/native_editor/2026-10-16-kind-dispatch/package-1.96.0` is reused.
  All 47 implementation/build inputs match its archive, and the installed binary
  hash matches its qualification (`reused-package.json`). Its engine identity is
  `sha256:47fe818db31bfd48eb4a7f1f92ae1c2ff60aa2965c4161b2e591bf557e30f52b`.
  Packaging and editor suites were not rerun: implementation/editor code did not
  change. Their previous qualification remains separately recorded.

## Reviewable results

[The Python refactor review](refactor-review.html) reconciles five captured
fixtures with zero output/failure changes, four changed paths, one unchanged
case, and no mismatches, incompatibilities, or unavailable cases
(`python-comparison.json`). The missing-map case stops before the changed helpers.

All five corresponding native cases replay successfully. [The native boundary
review](boundary-review.html) changes `>` to `>=` and detects only the equality
case's output change from `small` to `large`; the remaining four outputs are
preserved. Source/evidence changes are reported independently. [Native scenario
validation](native-validation.html) passes all 15 expectations.

Offline Chromium 153.0.8010.12 checks both review pages at 1440 and 390 pixels:
all four changed refactor cases and all five native cases are selectable, search
and outcome filtering work, and there are no script errors, external requests,
or horizontal overflow. All four screenshots were visually inspected (`browser/`).
The scripts `../build_reviews.py` and `../check_browser.py` reproduce artifact and
browser checks. The first artifact attempt supplied native CLI flags in the wrong
order; its command log is retained as `artifact-commands-before-flag-fix.log`.
Correcting the invocation required no engine change.

`source-hashes.json` records the relevant source, tests, and qualification scripts.
This is one bounded source adaptation. It does not prove general migration,
complete MiniLang parsing, fractional-number equivalence, faster execution, or
better human comprehension. Separate setup fixtures and the long threshold-helper
signature are documented tradeoffs. The full project goal remains incomplete;
no external pilot or publication occurred.
