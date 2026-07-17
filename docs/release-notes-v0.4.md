# GWT v0.4 Draft Release Notes

Status: **draft release-candidate notes; not approved for publication**.

GWT v0.4 is planned as a local-first behavior-review tooling release over the
existing `v0.2` source language. It connects a concrete named-request run to
factual evidence, a reviewable scenario, old/new behavior comparison, and a
self-contained local workbench. It does not add a hosted service, a visual rule
editor, or an audit/compliance system.

These notes describe candidate scope in the development repository. They do
not announce a released package version. The project currently still reports
package version `0.3.0`, and no name, license, version, tag, or publication
change is authorized by this document.

## Candidate Highlights

- Deterministic runtime safeguards include execution budgets, behavior-call
  depth limits, source-located expected failures, and iteration accounting.
- Program identity covers the entry module and its transitively loaded `USE`
  dependency closure with a portable, canonical SHA-256 manifest.
- `gwt serve` shares one transport-neutral request application across the
  built-in HTTP/1.1 adapter and an optional ASGI/Uvicorn engine, with bounded
  evaluator admission, liveness/readiness probes, graceful draining, stable
  program-identity headers, and bounded background telemetry export.
- `gwt qualify-serve` exercises a specific ASGI program and full-value Case
  Corpus through the real CLI boundary, OpenAPI discovery, deterministic
  overload, and active-request SIGTERM, with a versioned JSON report.
- `gwt capture` writes a versioned Execution Case for a completed named JSON
  request; `--record-failures` records normalized failures and `--omit-values`
  records a shape-only, explicitly redacted value profile.
- `--fact-provenance` can attach validated, host-supplied derivation notes to
  request facts without changing runtime state or language syntax; the
  workbench labels these notes as unauthenticated metadata.
- `gwt explain` renders generic execution facts rather than example-specific
  business prose; `--json` uses the same Execution Case path.
- `gwt scenario-from-run` emits a formatted, checked scenario only after the
  supplied program matches the captured dependency closure and reproduces the
  result.
- `gwt compare` evaluates captured inputs against frozen old and new GWT
  program closures and separates output changes, path-only changes, new,
  changed, and resolved failures, incompatibilities, unavailable cases, and
  baseline mismatches. Field changes include last-change source evidence and
  comparisons carry old/new evaluated predicates.
- Case Corpus v1 maps domain-facing references to integrity-checked Execution
  Cases without changing their digests; `gwt corpus create` and `gwt corpus
  check` provide CLI-native authoring and validation, while `gwt compare` and
  `gwt workbench` accept it through `--corpus`.
- `gwt workbench` composes those same artifacts into a self-contained local
  HTML behavior-review dossier without a second evaluator or network service.

The intended workflow is:

```text
captured run -> factual explanation -> intent review -> verified scenario -> old/new comparison
```

## New Artifact Contracts

Execution Case v1 is a separate interchange object for review, replay,
scenario generation, comparison, and workbench rendering. It does not enlarge
or replace the stable host-facing `ExecutionResult.as_payload` envelope.

An Execution Case includes the named request and full input, declared result,
complete program-closure identity, ordered semantic evidence, ordered state
changes, capture metadata, explicit redaction metadata, and a canonical
integrity digest. The digest detects content changes; it is not a signature and
does not establish who captured, approved, or retained the artifact.

Comparison v1 is likewise versioned independently. Its totals account
explicitly for every input case, including incompatibilities and baseline
mismatches.

Case Corpus v1 is a separate selection artifact. Its digest protects ordered
membership, human references, and relative artifact mappings; each member's
Execution Case digest is verified independently. It deliberately excludes
candidate-specific classifications and does not authenticate its labels.

Published candidate schemas live in [`docs/schemas`](schemas/). Historical
artifact kind and schema identifiers must remain readable across any future
project rename.

## Compatibility

| Surface | v0.4 candidate behavior |
| --- | --- |
| Source language | Remains specification `v0.2`; no broad syntax release |
| Existing run/check/inspect/validate JSON | Existing payload schema remains version `3` |
| Execution Case | New independent `gwt.execution-case` schema version `1` |
| Case Corpus | New independent `gwt.case-corpus` schema version `1` |
| Comparison | New independent `gwt.comparison` schema version `1` |
| Debugger and OTLP traces | Remain developer/operational surfaces, not canonical review evidence |
| Stored cases after branding | Preserve v1 identifiers; do not rewrite evidence for presentation branding |

The experimental `explain` command changes from vendor-specific narrative
heuristics to domain-neutral factual output. Consumers that parsed the old
plain text must migrate to the versioned JSON artifact and should never depend
on prose. Direct `program + input` explanation now follows the same capture
path used by other behavior-review tools.

Scenario generation does not edit source automatically. Its exact-output
scenario records what the captured baseline did; a domain reviewer must decide
whether that actual result is the intended expected result before committing
or editing assertions.

## Trust, Privacy, And Security Boundary

Execution Case v1 supports completed and opted-in failed local runs. The
default full-value profile can contain request values, outputs, operand values,
state changes, failure details, and source references. The `omit-values`
profile removes runtime values and physical input/program paths with explicit
availability markers, but it retains source text, field paths, conditions,
request names, and branch structure. Neither profile is anonymization.
Comparison JSON, generated scenarios, and workbench HTML can repeat available
values and must receive the same storage, sharing, and retention controls.

Do not treat a self-contained workbench page as sanitized. Do not use a plain
hash of a low-entropy secret or identifier as anonymization. Use reviewed
synthetic data for external evaluation unless another data path is explicitly
authorized.

Execution Cases provide source-linked reviewable evidence, not authenticated
identity, non-repudiation, legal sufficiency, controlled retention, or chain of
custody. Runtime semantic budgets improve determinism and failure handling but
do not make GWT a sandbox for remotely supplied untrusted programs.

## Known Release Blockers

This draft is not release-ready. The
[release-candidate checklist](release-v0.4-checklist.md) records the complete
gate; the following blockers are non-optional:

- **Owner name decision:** `GWT` collides with the established Web Toolkit
  identity and package/editor surfaces. The owner must approve a rename or
  explicitly retain the name with its tradeoffs.
- **Owner license decision:** the repository has no root license file or
  Python project license metadata. Public distribution must not infer a
  license.
- **Two actual external pilots:** repository examples do not replace two
  unrelated workflow pilots, with at least one maintained primarily outside
  the project.
- **Pilot trust/privacy findings:** both pilots must finish the full loop and
  resolve any misleading evidence, unsafe artifact handling, reproduction
  failure, or incomplete comparison.
- **Compatibility-corpus review:** checked-in cross-domain fixtures now cover
  full, omitted, completed, contract-failure, runtime-failure, and comparison
  payloads. They still need explicit release review, a deliberate retention
  decision, and expansion if pilot findings add contract variants.

The project must not publish a final v0.4 package, release, or editor artifact
while these gates remain open.

## Candidate Distribution

A manual GitHub Actions workflow can build an sdist and wheel from a selected
commit, inspect packaged runtime modules and schemas, install both archives in
separate clean virtual environments, run CLI/hello/workbench smokes, create
SHA-256 checksums, and upload build artifacts with build-provenance
attestations. It intentionally has no PyPI or GitHub Release publishing step.
Installed schemas live under `share/gwtlang/schemas` in the environment.

An evaluator should verify and install a candidate with:

```sh
sha256sum --check SHA256SUMS
python -m venv .venv
. .venv/bin/activate
python -m pip install ./gwtlang-*.whl
gwt version --json
gwt --help
```

Build attestation links a subject digest to the repository workflow. It does
not attest the correctness of a domain decision or authenticate an Execution
Case author.

## External Evaluation

The [v0.4 external pilot runbook](external-pilot-v0.4.md) gives both pilots the
same measurable tasks and privacy gate. Each pilot must leave a reviewed
scenario in its own source control, reconcile the complete old/new corpus, and
record product/workflow findings separately from source-language pressure.

Only repeated pilot evidence should determine whether the next product step is
a stronger local tool, a shared case repository, authenticated governance, or
no hosted investment at all.
