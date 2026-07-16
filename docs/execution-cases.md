# Execution Cases

An Execution Case is GWT's portable, source-linked record of one named
`REQUEST` execution. It is the interchange object used by explanation,
scenario generation, old/new comparison, and the local review workbench.
It is deliberately separate from OTLP operational traces.

Execution Case v1 records completed and, when explicitly requested, failed
local executions. Capture policy, value availability, runtime limits, and the
execution outcome are data in the artifact; consumers do not have to infer a
profile from empty objects or nulls.

## Capture

Capture a case to standard output:

```sh
python -m gwtlang capture examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor"
```

Write it atomically to a file:

```sh
python -m gwtlang capture examples/vendor_onboarding/rules.gwt \
  --json-input examples/vendor_onboarding/request.json \
  --request "review vendor" \
  --output review.execution-case.json
```

The defaults are `onError: "raise"` and `values: "full"`. Record a GWT parse
or runtime failure as a source-linked case instead of returning no artifact:

```sh
python -m gwtlang capture rules.gwt \
  --json-input request.json --request "review request" \
  --record-failures --output failed.execution-case.json
```

A successfully recorded failed case is a successful capture command and exits
zero; inspect `execution.outcome` to distinguish it from a completed run.
Unreadable files, invalid input JSON, and failures that prevent construction of
the dependency-closure identity still return a command error without a case.

Execute while omitting captured values and physical provenance paths:

```sh
python -m gwtlang capture rules.gwt \
  --json-input request.json --request "review request" \
  --record-failures --omit-values --output shareable-shape.execution-case.json
```

`--execution-budget N|none` and `--max-call-depth N|none` select the semantic
limits for the run. Every case records the exact values used. `none` is the
only CLI spelling that records a disabled, JSON `null` limit; the defaults
remain 100000 work units and 100 nested behavior calls.

The Python API expresses the same choices with
`ExecutionCaseCapturePolicy(on_error="raise" | "record", values="full" |
"omit")` passed as `policy=`, plus `execution_budget=` and `max_call_depth=`.

### Served Capture

The experimental HTTP service can record the execution that produced a live
response without executing the request a second time:

```sh
python -m gwtlang serve examples/deployable_api/rules.gwt \
  --port 8080 \
  --capture-dir /tmp/gwt-cases
```

This profile differs intentionally from the standalone `gwt capture` default.
Served capture records failures and omits values by default because HTTP input
may be less controlled. Each completed GWT execution or GWT runtime/contract
failure is written atomically as
`<digest>.execution-case.json`. The response includes
`x-gwt-case-id: sha256:<digest>` only after the artifact has been written.
Capture write failure is reported on server stderr and does not replace the
decision response. Malformed JSON, unsupported media types, oversized bodies,
unknown routes, and undeclared transport fields are rejected before GWT
execution and do not create cases.

Select one or more exact named requests with repeated `--capture-request`
flags. Without them, every named request is captured. Supplying a static
`--fact-provenance` sidecar validates it at startup against every selected
request. Provenance is server configuration, not HTTP decision input.

Shape-only artifacts retain program identity, source-linked execution shape,
and redaction markers, but they cannot replay an input or establish an exact
result. Explicitly opt into sensitive, replayable evidence with:

```sh
python -m gwtlang serve rules.gwt \
  --capture-dir /tmp/gwt-cases \
  --capture-request "review request" \
  --capture-values \
  --fact-provenance provenance.json
```

Review retention before enabling this. If OTLP trace export is enabled at the
same time, full case capture requires `--trace-values`; otherwise startup fails
instead of silently sending full recorder values through a nominally redacted
trace. The embedded API exposes the same boundary as
`HttpExecutionCaseConfig` on `GwtHttpService.from_file(...)`.

### Host Fact Provenance

A host adapter can optionally attach descriptive provenance to normalized
request facts:

```json
{
  "facts.previously_funded": {
    "source": "FundingEligibility#previously_funded?",
    "description": "Derived from registration and funded-place state."
  }
}
```

Pass the file with `--fact-provenance provenance.json` to `gwt capture` or
`gwt explain`. The Python capture and explanation APIs accept the same mapping
as `fact_provenance=`. GWT requires `source`, permits an optional non-empty
`description`, rejects unknown fields, sorts entries by path, and verifies that
every path is a declared request input or a declared field beneath a record
input. Lists are provenance-addressed as a whole rather than by runtime index.

This metadata is context supplied by the host, not evaluator observation. GWT
does not contact, authenticate, or verify the named source. The integrity
digest protects the exact claim stored in one artifact but does not make the
claim true or establish who supplied it. The workbench labels this distinction
explicitly.

Fact provenance may itself contain sensitive operational information. Under
`--omit-values`, GWT removes the entire optional field and records
`/factProvenance` in `redaction.redactedPaths` when a sidecar was supplied.

The JSON contract is published at
[`schemas/execution-case.schema.json`](schemas/execution-case.schema.json).
Readers reject unsupported versions, malformed identities, non-JSON values,
out-of-order or incomplete evidence, inconsistent behavior-call nesting,
profile contradictions, unsupported redaction modes, and integrity mismatches.
Direct `ExecutionCase(...)` construction enforces the same boundary as
`ExecutionCase.from_payload(...)` and `ExecutionCase.load(...)`.
Cross-domain v1 compatibility artifacts live in
[`tests/fixtures/v0.4`](../tests/fixtures/v0.4/) and are loaded, integrity-
checked, schema-validated, and replayed by the unit suite.

Semantic evidence follows the evaluator's event order. Behavior calls have
paired `enter` and `exit` facts with a deterministic call ID, parent call ID,
nesting depth, call-site source, signature, and exit outcome. Failed behavior
calls have ordered `exit` facts with `behaviorOutcome: "failed"`. Successful
condition and assertion facts include the identifier values actually resolved
by that evaluation, including short-circuit behavior; these are evaluator
observations rather than values reconstructed from the expression text. Each
operand carries its runtime value type so decimal strings remain distinct from
text values. An expression with no identifier operands has an available empty
list. If a resolved runtime value cannot be represented faithfully as JSON,
the fact says `availability: "unavailable"` with a reason instead of inserting
a display string.

Evidence and state-change source files use the same logical module specifiers
as `program.identity.modules` (for example, `./rules.gwt` or
`../shared.gwt`). Pseudo-sources such as `<request>` remain explicit. Readers
reject real source paths outside the captured identity, so moving an intact
program tree does not rewrite its semantic source links or expose a workstation
path through them.

## Program Identity And Replay

`program.hash` is not a hash of only the entry file. It identifies the exact
entry module and its complete transitively loaded `USE` dependency closure.
The manifest uses logical module specifiers and deterministic ordering. Any
byte change in that closure produces a different digest.

Replay and comparison first verify the supplied program closure against the
captured identity. A mismatch is reported as a baseline or identity error; GWT
does not silently replay a case against different rules. Replay uses the
captured execution budget and call-depth limit, not current defaults.

Scenario generation explicitly refuses failed and omitted-value cases because
they cannot establish an exact reproducible result. Comparison accounts for
an omitted-value case as `unavailable` and does not execute it. A full-value
failed case is replayed against the baseline before candidate attribution and
can be classified as unchanged, path-changed, failure-changed,
`resolved_failure`, incompatible, or baseline-mismatched. “Resolved” means
only that execution completed under the candidate; it does not imply a domain
approval.

## Canonical Integrity Digest

Every v1 case contains:

```json
{
  "integrity": {
    "algorithm": "gwt-execution-case-sha256-v1",
    "scope": "artifact-without-integrity",
    "digest": "sha256:..."
  }
}
```

The digest input is the complete artifact with the top-level `integrity`
member removed, encoded as UTF-8 JSON with lexicographically sorted object
keys, no insignificant whitespace, unescaped Unicode, and non-finite numbers
rejected. Arrays retain their order. The digest is SHA-256 prefixed with
`sha256:`.

This is an accidental-change and content-addressing control. It is not a
signature and does not establish who captured, reviewed, or preserved the
case. Anyone who can change the artifact can recompute the digest. Claims such
as authenticated provenance, non-repudiation, approval history, retention, or
chain of custody require a trusted host with identity, authorization, signing,
and controlled storage; the local workbench does not make those claims.

## Sensitivity And Retention

The default capture profile is `redaction.mode = "none"` and includes request,
result, state-change, operand, and full error-detail values. Treat a default
case as at least as sensitive as its input JSON and program output:

- do not commit cases containing secrets, personal data, or production data
  without an explicit repository policy
- store and retain them only where the underlying input would be permitted
- review cases before attaching them to tickets or sharing them externally
- do not treat a plain hash of a low-entropy secret or identifier as
  anonymization

The `omit-values` profile stores `{}` placeholders for `request.input` and
`result`, but they are never ambiguous: `redaction.availability` says whether a
surface is `redacted`, `unavailable`, `available`, or `absent`. State
before/after and expression operands carry explicit redacted markers. A failed
case marks its unproduced result, status, and reason unavailable rather than
pretending that they are absent. Literal JSON null remains a present value in a
full-value case and is distinct from all of those states.

Omission also replaces `program.file` with the logical identity entry and sets
`request.inputFile` to null, with their availability recorded separately. It
does not remove program source text, field paths, condition text, request
names, or decision structure. Those can themselves be sensitive, so
`--omit-values` is a data-minimization profile, not anonymization or proof that
an artifact is safe to publish.

Operational traces and omitted-value Execution Cases never emit structured
operand names or values; they carry a redacted-availability marker. Redacted
failure text is the fixed message `GWT execution failed; error detail omitted
by capture policy`, while source location remains factual and portable.
Supplied host fact provenance is also omitted rather than attempting to redact
free-form descriptions selectively.

## Stable And Unstable Fields

Program identity, capture policy, semantic limits, request input when present,
declared result when available, semantic evidence, and state changes are
intended for deterministic review. `traceId`, `capturedAt`, and full-profile
input file labels are capture provenance and can differ between otherwise
equivalent executions. The integrity digest covers them because it protects a
specific artifact; semantic comparison deliberately normalizes or excludes
capture-only provenance where appropriate.

Optional host fact provenance is deterministic caller-supplied metadata. It is
covered by the case integrity digest and preserved in the primary workbench
case, but it does not affect replay, scenario generation, or old/new behavior
classification.

## Case Corpora And Human References

An Execution Case integrity digest is the precise identity of one artifact,
but it is not a useful domain label. Case Corpus v1 keeps those concerns
separate. It maps a locally meaningful reference to an immutable case ID and a
portable relative artifact path:

```json
{
  "schemaVersion": 1,
  "kind": "gwt.case-corpus",
  "name": "semantic-release priority cases",
  "cases": [
    {
      "reference": "patch-then-minor",
      "caseId": "sha256:...",
      "artifact": "cases/....execution-case.json"
    }
  ],
  "integrity": {
    "algorithm": "gwt-case-corpus-sha256-v1",
    "scope": "artifact-without-integrity",
    "digest": "sha256:..."
  }
}
```

The corpus digest protects its name, membership, ordering, references, and
mappings. Every referenced Execution Case retains its own independent digest.
Neither digest authenticates who chose a reference or assembled the corpus.
The same case may appear under different references in distinct corpora
without changing its evidence identity.

The corpus digest input is the complete corpus with the top-level `integrity`
member removed, encoded as UTF-8 JSON with lexicographically sorted object
keys, no insignificant whitespace, unescaped Unicode, and non-finite numbers
rejected. Arrays retain their declared order. The digest is SHA-256 prefixed
with `sha256:`. This matches the Execution Case canonicalization shape while
using the distinct `gwt-case-corpus-sha256-v1` algorithm identifier.

Strings use JSON escaping for quotation marks, reverse solidus, and control
characters; non-ASCII characters remain literal UTF-8 and `/` is not escaped.
For example, this unsigned value:

```json
{"cases":[{"artifact":"cases/one.json","caseId":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","reference":"réf \"one/two\""}],"kind":"gwt.case-corpus","name":"Café \"A/B\"","schemaVersion":1}
```

has corpus digest
`sha256:424ccc1d98e551fd221d69445d0c162a0e628451f36aca797e4553cc15f76d94`.

Corpus readers preserve declared order, require unique references and case IDs
within one corpus, reject missing artifacts and digest mismatches, and accept
only normalized relative POSIX paths that resolve beneath the corpus
directory without symbolic links. A corpus cannot overwrite one of its own
member artifacts. References are untrusted, potentially sensitive display
text. They are escaped by the workbench, do not affect replay or
classification, and are never accepted by `gwt serve` as decision input or
capture metadata.

Create and validate the selection through the CLI:

```sh
gwt corpus create \
  --name "release decision cases" \
  --case patch-then-minor=cases/patch-then-minor.execution-case.json \
  --case prerelease-ladder=cases/prerelease-ladder.execution-case.json \
  --output corpus.json
gwt corpus check corpus.json
```

Case paths are resolved from the current working directory and must be beneath
the output corpus directory. `create` derives each `caseId`, stores a normalized
relative POSIX path, and preserves the order of the repeated `--case` options.
`check` performs the same strict manifest, path, member, and digest validation
as the comparison and workbench consumers without modifying the corpus.

Use a corpus directly with the review tools:

```sh
gwt compare --corpus corpus.json --old rules-v1.gwt --new rules-v2.gwt --json
gwt workbench --corpus corpus.json --old rules-v1.gwt --new rules-v2.gwt \
  --output review.html
```

The comparison retains its deterministic `case.id` and adds optional
`reference` plus authoritative `executionCaseId` fields for corpus-backed
runs. Candidate-specific classifications and output differences remain only
in the independent `gwt.comparison` artifact; they are not stored as corpus
membership metadata.
