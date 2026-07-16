# GWT v0.4 Release-Candidate Checklist

Status: **blocked; preparation only**.

This checklist is the publication gate for the v0.4 behavior-review milestone.
It does not authorize a rename, license choice, version change, tag, GitHub
Release, package upload, or editor publication.

## Hard Publication Blockers

The following are owner or external-state decisions, not engineering boxes that
can be checked speculatively:

- [ ] **Project identity:** the owner explicitly chooses to retain GWT or
  approves a replacement name. If renamed, the compatibility migration matrix
  in [Project Identity Decision For v0.4](project-identity-v0.4.md) is reviewed,
  registry/domain checks are repeated at decision time, and appropriate legal
  review is complete.
- [ ] **License:** the owner chooses a license and authorizes publication under
  it. The repository currently has no root license file and `pyproject.toml`
  has no project license metadata. Do not infer a repository-wide license from
  a component README or package convention.
- [ ] **Two actual external pilots:** two unrelated pilot-owned workflows
  complete the full loop in the
  [external pilot runbook](external-pilot-v0.4.md), with at least one maintained
  primarily by someone outside the project.
- [ ] **Pilot trust and privacy findings:** incorrect evidence, misleading
  explanations, unsafe artifact handling, and unreconciled comparisons from
  both pilots are fixed or explicitly block the release. These findings cannot
  be waived as ordinary polish.

Until all four gates are complete, distribution automation may build and
attest candidate artifacts for evaluation but must not publish them to PyPI,
GitHub Releases, an editor marketplace, or another public channel.

## Version Surfaces

Keep each version independent. This preparation intentionally leaves current
values unchanged.

| Surface | Current repository value | v0.4 release action |
| --- | --- | --- |
| Python distribution | `gwtlang` | Owner identity decision first; preserve compatibility if renamed |
| Python package version | `0.3.0` | Choose and update only in an authorized release change |
| Language specification | `v0.2` | Remain `v0.2` unless source syntax/semantics intentionally change with full spec alignment |
| Existing execution payload | schema version `3` | Preserve `ExecutionResult.as_payload`; incompatible change requires an explicit version and migration |
| Execution Case | artifact kind `gwt.execution-case`, schema version `1` | Preserve historical kind across branding changes; freeze fixtures before release |
| Case Corpus | artifact kind `gwt.case-corpus`, schema version `1` | Freeze membership, path, and integrity semantics before release |
| Comparison | artifact kind `gwt.comparison`, schema version `1` | Freeze schema and fixtures before release |

- [ ] `pyproject.toml` and `gwtlang/version.py` agree on the authorized package
  version.
- [ ] `gwt version --json` reports the expected package, language, and payload
  values from the installed wheel, outside the source checkout.
- [ ] Release notes identify every schema/API incompatibility and its migration
  path.
- [ ] Historical Execution Case fixtures remain readable after any public-name
  change.

## Product Contract Gate

The v0.4 roadmap exit criteria remain normative. In particular:

- [ ] Runtime budgets and expected failures are deterministic and source
  located, with adversarial recursion, depth, iteration, import, contract, and
  runtime-failure coverage.
- [ ] Program identity covers the exact transitive `USE` dependency closure and
  replay refuses a mismatched closure.
- [ ] Execution Case v1 has schema-validated, round-tripping fixtures for full
  value, redacted/omitted, success, contract failure, and runtime failure from
  unrelated domains.
- [ ] Case Corpus v1 has a schema-validated fixture covering portable paths,
  domain references, corpus integrity, and member case-ID verification.
- [ ] Capture/read/write boundaries validate artifact structure, canonical
  integrity, redaction availability, and evidence ordering.
- [ ] Generic explanation has no domain-field heuristics and handles success,
  no-op, nested behavior, alternate branch, failure, and unavailable/redacted
  evidence without guessing.
- [ ] Generated scenarios cover scalar, nested record, list, exact-number,
  union, and empty-collection inputs; each formats, checks, and reproduces its
  captured result.
- [ ] Comparison fixtures cover unavailable, unchanged, path-changed,
  output-changed, new, changed, and resolved failure, incompatible, and
  baseline-mismatch cases, with exactly reconciled totals and source-backed
  change evidence.
- [ ] The local workbench uses the same case, comparison, explanation, and
  scenario implementations as the CLI; it contains no second evaluator or
  domain-specific policy code.
- [ ] Full-value sensitivity, value omission, recorded failures, and each
  unavailable/refusal path are presented consistently everywhere they matter.
- [ ] No screen or documentation describes unsigned local evidence as an audit
  log, authenticated provenance, tamper-proof history, or compliance proof.

Known candidate limitations: completed, recorded-failure, full-value, and
omit-value profiles are implemented and exercised by tests. A checked-in
cross-domain JSON compatibility corpus exists under `tests/fixtures/v0.4`, but
it still needs explicit release review and freezing after pilot feedback.
The static HTML workbench displays exact logical source locations but cannot
open an editor directly; editor navigation remains a future integrated-surface
item.

## Standard Repository Verification

- [ ] Run the full unit suite:

  ```sh
  python -m unittest discover
  ```

- [ ] Check every example with the canonical formatter:

  ```sh
  find examples -name '*.gwt' -print0 | while IFS= read -r -d '' file; do
    python -m gwtlang format "$file" --check >/dev/null || exit 1
  done
  ```

- [ ] Check top-level example programs:

  ```sh
  for file in examples/*.gwt; do
    python -m gwtlang check "$file" >/dev/null || exit 1
  done
  ```

- [ ] Run the reference workflows:

  ```sh
  python -m gwtlang run examples/order_fulfillment/rules.gwt \
    --input examples/order_fulfillment/request.gwt --json >/tmp/gwt-order.json
  python -m gwtlang run examples/language_tour/rules.gwt \
    --input examples/language_tour/request.gwt --json >/tmp/gwt-tour.json
  ```

- [ ] Run strict Python type checks, TypeScript client checks, and the VS Code
  extension check used in CI.
- [ ] Run `git diff --check` and review all generated/untracked files.
- [ ] Confirm public examples remain formatted and scenario-backed.

## Distribution Candidate

The manual
[`build-distribution.yml`](../.github/workflows/build-distribution.yml)
workflow is deliberately build-only. It installs pinned build tooling, builds
the current sdist and wheel, inspects both archives for runtime modules and
schemas, installs each in a separate clean virtual environment, runs
command/hello/corpus/workbench smokes, creates `SHA256SUMS`, uploads the files
as a workflow artifact, and requests GitHub build-provenance attestations. It
has no package-registry or release-publishing step.

- [ ] Review the workflow run's exact commit SHA and dependency/action
  versions.
- [ ] Download the artifact, run `sha256sum --check SHA256SUMS`, and retain the
  workflow attestation with the candidate record.
- [ ] Inspect both archives; confirm they include `gwtlang/execution_case.py`,
  `program_identity.py`, `comparison.py`, `scenario_generation.py`,
  `workbench.py`, `py.typed`, all three v1 JSON schemas, and all existing runtime
  modules.
- [ ] Install the wheel with `--no-deps` in a clean environment and run:

  ```sh
  gwt version --json
  gwt --help
  gwt run hello.gwt --json
  gwt corpus create --name smoke \
    --case review=case.execution-case.json \
    --output smoke.case-corpus.json
  gwt corpus check smoke.case-corpus.json
  gwt workbench case.execution-case.json --output review.html
  ```

- [ ] Install the sdist in a second clean environment and repeat the smoke
  tests.
- [ ] Test a clean upgrade from the latest supported prior release, then test
  uninstall and confirm no stale command remains.
- [ ] Test on every supported Python version and target operating system.
- [ ] Confirm candidate installation instructions do not require a repository
  checkout.
- [ ] Confirm the workbench artifact is self-contained, opens locally without
  network requests, and is treated as sensitively as its Execution Case.

Build-provenance attestation identifies the workflow and subject digest; it
does not establish domain approval, artifact confidentiality, or a trusted
Execution Case author.

## Metadata, License, And Identity

Complete only after the owner decisions above:

- [ ] Add the owner-approved root license file and matching package metadata.
- [ ] Review package description, authors/maintainers, project URLs,
  classifiers, keywords, and support status for the chosen identity.
- [ ] Verify Python distribution, CLI, editor ID, language ID, docs URLs,
  environment variables, schemas, trace attributes, and repository naming
  against the approved migration matrix.
- [ ] Preserve compatibility aliases and historical artifact identifiers for
  the documented deprecation window.
- [ ] Recheck package, editor, repository, domain, and trademark risk at the
  time of decision; earlier availability observations are not reservations.
- [ ] Document the experimental/pre-1.0 support boundary and security boundary:
  runtime budgets are not a remote-code sandbox.

## External Pilot Evidence

- [ ] Pilot A and Pilot B meet the unrelatedness and ownership rules.
- [ ] Each evaluator records the exact candidate checksum and version output.
- [ ] Each pilot uses approved synthetic or explicitly authorized data.
- [ ] Each completes capture, factual explanation review, scenario generation,
  direct old/new comparison, and local workbench review.
- [ ] Each leaves a reviewed scenario in its own source control, with a durable
  revision link.
- [ ] Facilitator interventions, completion time, misleading evidence,
  redaction/privacy friction, and source-language pressure are recorded.
- [ ] Product/workflow findings are separated from syntax pressure.
- [ ] Syntax proposals include concrete before/after source and repeated
  evidence across unrelated workflows.
- [ ] Hosted collaboration, identity, approval, or retention work is proposed
  only when both pilots show a repeated need that ordinary repository review
  cannot meet.

## Manual Publication Gate

Publication is a separate, authorized operation after every preceding section
is complete.

- [ ] Freeze the intended commit and rerun CI plus the distribution-candidate
  workflow from that SHA.
- [ ] Review and finalize [v0.4 release notes](release-notes-v0.4.md).
- [ ] Obtain owner signoff for name, license, versions, pilot evidence, and
  unresolved risk.
- [ ] Create a signed tag according to the project's release policy.
- [ ] Manually publish matching sdist/wheel, checksums, release notes, and
  editor/workbench artifacts to the owner-approved channels.
- [ ] Verify downloaded public artifacts and attestations against the frozen
  commit.
- [ ] Perform clean install, upgrade, workbench, version, and uninstall checks
  from public channels.
- [ ] Confirm stored Execution Case v1 artifacts remain readable.

No checkbox in this section should be automated into a publish-on-tag workflow
without a separate owner decision and protected release process.
