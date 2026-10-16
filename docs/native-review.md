# Native corpus review

The native toolchain can reconcile a corpus of saved cases against a candidate
program and generate an offline HTML review. The report retains every entry,
including invalid cases, incompatible engines, baseline mismatches, and failed
candidate executions. It uses the same native execution and replay engine as
[native cases](native-cases.md).

This remains an experimental review format. It does not establish human benefit,
replace the Python workbench schema, or imply complete language support.

## Create a review

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt-native -- capture \
  crates/gwt-core/tests/fixtures/invoice.gwt \
  --request 'price invoice' \
  --input crates/gwt-core/tests/fixtures/invoice-input.json \
  > /tmp/gwt-native-invoice.case.json
cargo run --locked -p gwt-core --bin gwt-native -- corpus \
  /tmp/gwt-native-invoice.case.json > /tmp/gwt-native-corpus.json
cargo run --locked -p gwt-core --bin gwt-native -- review \
  /tmp/gwt-native-corpus.json \
  --candidate crates/gwt-core/tests/fixtures/invoice.gwt \
  --html /tmp/gwt-native-review.html > /tmp/gwt-native-review.json
```

Open the HTML file in a browser. It contains its own styles, scripts, source
snapshots, and report data; no service or network connection is required.
For an actual revision review, pass the changed rules file as the candidate.
A trailing `--import-root DIRECTORY` selects the candidate's import root.
`--html` is optional; review JSON always goes to stdout. The HTML path is an
output destination and an existing file at that path is replaced.

`corpus` accepts 1–256 case files. The filename stem becomes each case ID and
label; duplicate IDs fail explicitly. Invalid case JSON is retained as an
unavailable entry when the corpus is reviewed. Unreadable files fail corpus
creation rather than producing an incomplete manifest without notice.

For meaningful names and labels, the equivalent manifest is:

```json
{
  "kind": "gwt.native-corpus",
  "schemaVersion": 1,
  "cases": [
    {"id": "customer-refund-17", "label": "Damaged item without receipt", "case": {}}
  ]
}
```

Replace `case` with the complete saved native case object. The empty object
above illustrates placement and would be reported as unavailable. Cases may
have different frozen baselines; each is replayed against its own source and
recorded execution settings before applying the common candidate.

Corpora can mix version 1 request cases and version 2 scenario cases. Scenario
rows expose `scenario`, no request name, and no supplied host input. The page
labels their result as scenario state and explains that each revision supplies
its own scenario setup and assertions. Request rows retain their existing shape.
Both target types participate in search, filters, exact report downloads, and
saved reviewer decisions. See [scenario capture](native-cases.md#capture-and-compare-a-scenario).

## Reading the report

The schema-2 `gwt.native-review` JSON has a candidate identity, engine identity,
deduplicated source snapshots, totals, and one row per manifest entry in original
order. `corpusIntegrity` binds the complete captured corpus, including execution
limits, migration provenance, and unavailable payloads. Rows include
`caseIntegrity` and `capturedLimits` after case integrity validation; null values
mean the case could not be validated. Non-null metadata does not prove replay.
The page exposes captured limits in each case panel.

Schema 1 omitted those fields. Regenerate reports and saved choices before using
them to approve a different captured corpus; see the
[decision identity contract](native-review-decisions.md#artifact-contract).

`total = compared + baselineMismatch + unavailable` always holds. `complete`
means every entry was compared; it is a coverage flag, not acceptance of the
candidate. Outcome/state/evidence/source change counts overlap and are not
additional partitions of the corpus. Candidate failures are counted separately,
including failures that reproduce an already-failing baseline.

Rows use these statuses, in priority order:

| Status | Meaning |
| --- | --- |
| `unavailable` | Invalid/incompatible case, failed source verification, or unavailable explanation; a diagnostic identifies the reason |
| `baseline_mismatch` | The full recorded execution did not reproduce; the candidate was not run |
| `candidate_failed` | Baseline verified; candidate execution failed, possibly matching an existing failure |
| `outcome_changed` | Candidate completed with a different outcome |
| `state_changed` | Same outcome, different initialized state |
| `evidence_changed` | Same outcome/state, different events, diagnostic detail, or step count |
| `source_changed` | Only the exact source identity changed |
| `unchanged` | Source, outcome, state, and evidence all match |

Each compared row retains the complete comparison and its independent change
flags, so the primary status cannot hide an accompanying change. For example,
a newly failing candidate has both the `candidate_failed` status and an outcome
change. The “Outcome changed” filter includes such rows. State/evidence filters
select their primary statuses, which keep the outcome or state unchanged.

A review with unavailable or mismatched rows still emits JSON and requested
HTML, and exits nonzero. Invalid manifests, duplicate IDs, candidate compilation
failures, and resource failures stop report generation with a diagnostic. A
fully compared corpus exits zero even if outcomes changed or candidates failed;
automation must apply its own acceptance policy to the contents.

Use [captured-case regression testing](native-regressions.md) for an explicit
preservation gate. `test-cases --match outcomes-and-state|execution` exits nonzero
when the selected observations change or any baseline cannot be verified.

## Factual explanations

The page presents outcome differences, then a verified baseline and candidate
side by side. Decision trails describe recorded facts: conditions matched or
failed, branches were selected or skipped, assertions passed or failed, calls
entered, output contracts validated, and state changes recorded as before/after
values or explicit [append deltas](native-append-evidence.md). The renderer does
not infer counterfactual causes or desired outcomes.

Collection trails include visited item values and paths, filter selections,
first-match search, before/after mutations, appended items/indices, and each sum contribution with its
subtotal. These events remain visible when expression details are hidden.
An item rejected by a filter has a recorded selection result; a later item
never reached by a successful first-match search has no invented evaluation.

Every event points to an exact UTF-8 source slice in a frozen module. Call events
also link to their definition spans and retain parameter-to-state bindings.
Expression operand links identify earlier events. Following a link reveals the
referenced expression event; a toggle exposes the entire event sequence.
Skipped operands and branches remain marked as not evaluated, without invented
results. Failures retain their source location and the evidence collected before
the failure.

The `explain_execution` library helper checks source identity, byte/line/column
positions, event ordering, operand references, and boolean condition evidence.
It describes a supplied native run; it does not authenticate a caller-constructed
run or establish that an historical observation happened. Corpus review first
verifies the saved baseline through replay and uses fresh candidate executions.
It never presents a mismatched saved baseline as a verified explanation.

## Browser behavior and data handling

The page supports case search, status filters, an empty-search state, selecting
every case, expression-event expansion, operand navigation, and JSON download.
Values are rendered as escaped text, including large integer tokens and exact
decimal strings. The browser does not parse report numbers into JavaScript
numbers. Downloading copies the embedded JSON text, preserving exact integers.
Labels and source text cannot introduce HTML elements; embedded JSON escapes
HTML delimiters. A content security policy forbids connections and external
resources. [Reviewer decisions](native-review-decisions.md) can be downloaded
and restored as a separate file bound to the exact report. Rules and source
artifacts are not edited by the page.

The artifact includes full input, state, evidence, and source, as described in
the case capture policy. It has no redaction mode. JavaScript is needed for case
selection; use the JSON report when it is unavailable. Screenshots/printouts
show the selected case, not the entire corpus.

## Limits and validation

Corpora are bounded to 256 entries and 64 MiB. Case limits still apply to each
entry. Generated review JSON is bounded to 128 MiB, presentation markup to
128 MiB, and the complete HTML with embedded JSON to 256 MiB. Exceeding a bound
fails explicitly rather than silently dropping rows. These guards do not claim
a strict memory or execution-time sandbox.

`tests/review.rs` checks reconciliation, mixed baselines, failed runs, source and
operand validation, imported definition/failure spans, exact integer rendering,
HTML escaping, CLI behavior, corpus bounds, and all 336 independently specified
refund probes with source-backed explanations.

The optional browser reproduction uses Playwright 1.63.0 and Chromium:

```sh
cargo build --locked -p gwt-core
python evaluations/native_review/generate.py /tmp/gwt-native-review-fixtures
python evaluations/native_review/check_browser.py \
  /tmp/gwt-native-review-fixtures /tmp/gwt-native-browser-results
```

The generator uses approved local fixtures and independent expected outcomes.
Python is only the test driver; native capture, replay, comparison, explanation,
and HTML generation run in Rust. See the
[initial browser evidence](../evaluations/native_review/2026-10-16/README.md) and
the [collection checkpoint](../evaluations/native_review/2026-10-16-collections/README.md),
and [saved-decision qualification](../evaluations/native_review/2026-10-16-decisions/README.md).
This is engineering qualification, not a human comprehension study. [Scenario generation](native-scenarios.md) now covers verified successful
requests with declared outputs. [Scenario capture qualification](../evaluations/native_review/2026-10-16-scenarios/README.md)
covers a mixed 13-case review with failed scenarios and exact printed integers.
Expected-failure generation,
engine migration, broader language
support, and actual comparative human review evidence remain unfinished.
