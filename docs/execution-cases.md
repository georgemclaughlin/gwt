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

## Stable And Unstable Fields

Program identity, capture policy, semantic limits, request input when present,
declared result when available, semantic evidence, and state changes are
intended for deterministic review. `traceId`, `capturedAt`, and full-profile
input file labels are capture provenance and can differ between otherwise
equivalent executions. The integrity digest covers them because it protects a
specific artifact; semantic comparison deliberately normalizes or excludes
capture-only provenance where appropriate.
