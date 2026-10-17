# Saved native review decisions

The native review page can save a reviewer's decision and note for every case.
Every case starts pending. Download decisions to retain them, then load that
file into the same report to resume. Changes held only in the page are lost when
it closes. Saving decisions does not edit rules, publish a release, or merge code.

A decision file is bound to the exact review: candidate and baseline sources,
inputs, execution evidence, explanations, engine identity, case IDs, labels,
order, coverage, and the complete captured corpus, including limits and migration
provenance. A budget change makes a saved decision stale even when every execution
value, step, and event stays identical. Changed report content makes the file stale. The page and
CLI refuse to silently apply it to the new report.

## Reviewer workflow

Open a native review page, enter a reviewer name or team, and inspect the cases.
For each case, choose:

- **Pending:** no decision yet; a draft note may still be saved.
- **Accept:** the compared outcome is acceptable for this case.
- **Reject:** the compared outcome or evidence needs correction; give a reason.
- **Needs information:** identify the question that prevents a decision.

Unavailable evidence and baseline mismatches cannot be accepted. A verified
execution failure can be accepted when failure is the intended behavior—for
example, rejecting an invalid quantity. Acceptance does not turn a failed
execution into a successful domain result.

Use the decision filters to find remaining work. Download the decision JSON
when finished or before closing the page. Loading validates the entire file
before replacing current choices; stale, malformed, or incomplete files leave
the current choices intact. Notes are plain text, and the original review JSON
download continues to preserve exact numeric values.

## Verify decisions against a fresh report

Generate a review from a captured corpus and candidate as described in
[native review](native-review.md). Optionally create an all-pending template
without opening a browser:

```sh
cargo run --locked -p gwt-core --bin gwt -- review \
  /tmp/gwt-native-corpus.json \
  --candidate crates/gwt-core/tests/fixtures/invoice.gwt \
  --html /tmp/gwt-native-review.html \
  --decisions-template /tmp/gwt-native-pending-decisions.json \
  > /tmp/gwt-native-review.json
```

The template destination must not already exist. The browser's Download
decisions action creates the same schema, including the choices actually made.
After saving a decision file, assess it against a freshly executed review:

```sh
cargo run --locked -p gwt-core --bin gwt -- assess-review \
  /tmp/gwt-native-corpus.json \
  --candidate crates/gwt-core/tests/fixtures/invoice.gwt \
  --decisions /tmp/gwt-native-review-decisions.json
```

`assess-review` replays the corpus and executes the candidate. It does not trust
a supplied report JSON as execution evidence. `--import-root DIRECTORY` is
available for candidates with sibling imports. Its JSON assessment reports
pending, accepted, rejected, and needs-information counts and `allAccepted`.

Exit zero means every case was compared and explicitly accepted in the supplied
decision file. Pending choices, rejections, requests for information, stale
files, incomplete coverage, or invalid decisions exit nonzero. A valid but
unfinished review still returns its counts; invalid files return a diagnostic.
Neither command performs a deployment or authenticates a human reviewer.

## Artifact contract

`gwt.native-review-decisions`, schema version 1, contains `reportIdentity`, a
`reviewer` string, and `decisions` with `{id, status, note}` for every report case
exactly once. Status values are `pending`, `accept`, `reject`, and
`needs_information`. Unknown fields, duplicate IDs or JSON fields, unsupported
statuses, and missing/extra cases are rejected. Entry order in the decision file
does not affect case matching.

The reviewer field is required for any non-pending decision and allows up to
256 UTF-8 bytes with no control characters. Notes allow up to 4,096 UTF-8 bytes;
reject and needs-information choices require a non-whitespace note. Files allow
1–256 case decisions and at most two MiB. The whole file must satisfy these
constraints, including decisions outside the current page filter.

The report identity uses algorithm `gwt-native-review-sha256-v1`: SHA-256 over
the UTF-8 algorithm name, one zero byte, then canonical JSON for the complete
`gwt.native-review` report. Canonical JSON sorts object keys recursively,
preserves array order and exact numeric tokens, writes UTF-8 text without ASCII
escaping, and omits insignificant whitespace. The digest is lowercase hexadecimal
prefixed by `sha256:`. Notes and reviewer choices live outside that report and
therefore do not change its identity.

Native review schema 2 adds `corpusIntegrity` and per-case `caseIntegrity` and
`capturedLimits`. The corpus digest covers every complete saved entry, including
unavailable cases; it uses the same canonical JSON encoding with domain prefix
`gwt-native-corpus-sha256-v1` followed by a zero byte. The review identity therefore
binds capture settings and provenance even if they do not affect this execution.
Per-case metadata appears after case integrity validation; it does not imply that
the baseline replayed. Case panels show saved limits separately from the outcome.

Schema 1 reports omitted capture limits and complete case identities. Their
decision files could remain applicable after a budget change that left execution
unchanged. Regenerate reviews and make fresh choices for schema 2; no old choices
are promoted automatically. The decision-file schema and hash algorithm remain
version 1 because their encoding is unchanged, but their report digest changes.

The library exposes `review_identity`, `ReviewDecisions::pending`,
`ReviewDecisions::from_json`, and `assess_decisions`. Assessment expects the report
produced by `review_corpus`. The CLI regenerates it before assessment. The hash
binds choices to data; it does not authenticate the report's origin, the page,
or the self-reported reviewer. This is a portable review record, not a signed
approval system or a tamper-proof history. Retain successive files in version
control or an external review system when that history matters.

Engineering tests cover exact report identity, stale decisions, complete case
coverage, notes/UTF-8 limits, unverified cases, expected failures, and CLI
regeneration. Browser checks use explicitly synthetic reviewers and test notes;
they are not project approval or evidence of improved human comprehension.

[Capture-identity qualification](../evaluations/native_review/2026-10-16-review-identity/README.md)
records the schema-1 budget-binding defect, corrected CLI assessments, and actual
browser download/restore and stale-budget refusal through Playwright CLI.
