# GWT v0.4 External Pilot Runbook

Status: template ready; no external pilot has been completed yet.

This runbook evaluates the complete local behavior-review loop on two
unrelated workflows:

```text
capture -> explain -> review intent -> scenario-from-run -> compare -> workbench
```

The goal is to learn whether GWT makes a real behavior change easier to
understand and preserve. It is not a demo script, a syntax-design exercise, or
evidence that the project is ready for hosted or audit use. At least one pilot
must be run primarily by a maintainer outside the GWT project.

## Release Relationship

Both pilot worksheets below must be completed before a public v0.4 release.
Repository examples and project-maintainer rehearsals are useful engineering
checks, but they do not count as external pilots.

A pilot blocks release when it exposes:

- incorrect or misleading execution evidence
- a privacy leak or an artifact that cannot be handled safely
- a generated scenario that does not reproduce the captured result
- comparison totals or classifications that conceal a skipped or failed case
- a workbench fact that differs from the corresponding command-line JSON
- a workflow failure that prevents an outside maintainer from completing the
  loop without a project contributor reconstructing the answer manually

Use the [v0.4 release-candidate checklist](release-v0.4-checklist.md) to track
those gates.

## Choose Two Unrelated Workflows

Fill both rows before scheduling sessions. The workflows are unrelated only if
they have different domain decisions, domain reviewers, source data, and
operational owners. Two variations of onboarding, release approval, or incident
routing do not satisfy this requirement.

| Pilot | Required shape | Candidate examples (not prescriptions) | Owner and workflow |
| --- | --- | --- | --- |
| A: operational behavior | A deterministic operational or internal decision with a review/escalation outcome | exception routing, deployment eligibility, inventory intervention | **TBD:** owner, organization/team, workflow |
| B: business behavior | A deterministic customer, commercial, or fulfillment decision with a materially different vocabulary and output | refund eligibility, order routing, benefit calculation, contract exception | **TBD:** owner, organization/team, workflow |

At least one owner must maintain the existing behavior and must not be a GWT
project contributor. Prefer two outside owners when possible.

Reject a candidate before implementation when its core behavior depends on
live network calls, time, randomness, broad querying, user-interface state, or
side effects that cannot be normalized into a JSON request. The host should
continue to own those concerns.

## Data And Privacy Gate

Execution Case v1 captures completed runs and can explicitly record failures.
Its default full-value profile includes input, result, evaluated operands,
state changes, failure detail, and physical input labels. `--omit-values`
removes runtime values and physical provenance paths, but preserves source
text, paths, request names, predicates, and branch structure; it is not
anonymization. Comparison output, generated scenarios, and workbench HTML can
repeat every available fact. The standalone HTML embeds its evidence; it is
not a sanitized screenshot.

Use synthetic data by default. A useful synthetic case preserves the branch
shape, boundary conditions, collection sizes, and type structure of the real
surprise without preserving a person's, customer's, vendor's, or system's
identifiers or secrets.

Before capture, record:

| Control | Pilot A | Pilot B |
| --- | --- | --- |
| Data classification | **TBD** | **TBD** |
| Synthetic-data recipe | **TBD** | **TBD** |
| Person approving the fixture | **TBD** | **TBD** |
| Allowed storage and sharing locations | **TBD** | **TBD** |
| Retention/deletion date and owner | **TBD** | **TBD** |
| Confirmation that no secrets or personal data remain | **TBD** | **TBD** |

Do not capture production values merely because the session is local. Do not
commit, attach, email, or screen-share an artifact until its contents have been
reviewed. A plain hash of a low-entropy identifier is not anonymization. If an
approved synthetic case cannot exercise the behavior faithfully, record that
as a product/privacy finding; do not work around it by silently using real
data.

## Pilot Repository Shape

Use this layout in each workflow's own repository. Keep the baseline immutable
after capture so its dependency-closure identity continues to match the case.

```text
.gwt-pilot/
  baseline/rules.gwt
  candidate/rules.gwt
  fixtures/surprise.json
  cases/surprise.execution-case.json
  generated/surprise.gwt
  reports/comparison.json
  reports/review.html
  findings.md
```

If the program uses `USE`, copy its complete relative dependency tree under
both `baseline/` and `candidate/`. Record the original source revision in
`findings.md`; do not put unauthenticated provenance into the GWT program as if
it were trusted metadata.

## Install The Candidate

The facilitator provides a wheel and `SHA256SUMS` produced by the manual
distribution-candidate workflow. The evaluator should not need a GWT repository
checkout.

```sh
sha256sum --check SHA256SUMS
python -m venv .venv-gwt-pilot
. .venv-gwt-pilot/bin/activate
python -m pip install ./gwtlang-*.whl
gwt version --json
gwt --help
```

Record the wheel filename, checksum, complete `gwt version --json` output,
Python version, operating system, install duration, and every setup
intervention. A project contributor taking over the terminal is an
intervention, even when the fix is quick.

## Prepare The Case

For each pilot, define these shell variables with paths relative to the
workflow repository:

```sh
export PILOT_ROOT="$PWD/.gwt-pilot"
export OLD="$PILOT_ROOT/baseline/rules.gwt"
export NEW="$PILOT_ROOT/candidate/rules.gwt"
export INPUT="$PILOT_ROOT/fixtures/surprise.json"
export CASE="$PILOT_ROOT/cases/surprise.execution-case.json"
export REQUEST_NAME="replace with the named request"
```

The JSON fixture is the complete initial-state object expected by the named
`REQUEST`, not just the inner business record. Validate the exact baseline and
run its existing scenarios before capture:

```sh
gwt validate "$OLD" --import-root "$PILOT_ROOT" --no-absolute-imports
gwt test "$OLD"
gwt run "$OLD" \
  --json-input "$INPUT" \
  --request "$REQUEST_NAME" \
  --json
```

The owner records, before seeing a proposed fix:

- why this input is surprising or important
- the output produced by the current system
- the outcome the owner believes is intended
- any ambiguity that requires a product decision rather than a code change

## 1. Capture

Capture the exact baseline program and approved fixture:

```sh
gwt capture "$OLD" \
  --import-root "$PILOT_ROOT" \
  --no-absolute-imports \
  --json-input "$INPUT" \
  --request "$REQUEST_NAME" \
  --output "$CASE"
```

Immediately inspect the case for unexpected values and confirm its program
closure hash is stable across a second capture of unchanged source. Do not edit
the baseline after this point.

Pass condition: the case records the correct named request, input, declared
result, source-linked evidence, program closure, and full-value sensitivity
notice.

## 2. Explain And Review Intent

Render the factual explanation from the same baseline and fixture:

```sh
gwt explain "$OLD" \
  --import-root "$PILOT_ROOT" \
  --no-absolute-imports \
  --json-input "$INPUT" \
  --request "$REQUEST_NAME"
```

The domain owner marks every material condition, selected branch, result, and
state change as correct, incorrect, unavailable, or unclear. Explanation is a
rendering of execution facts; it must not be credited for a plausible business
story it did not actually record.

Then classify the captured output:

- **intended:** preserve the exact result as regression coverage
- **unintended:** preserve the input, but change the expected assertions only
  after the owner states the intended output
- **undecided:** stop the change; resolving product intent is outside the tool

Any inferred intent, hidden operand, example-specific prose, or incorrect
source reference is a release-blocking trust finding. Static workbench source
references are display-only in v0.4; opening them in an editor requires a
future editor-integrated surface.

## 3. Generate A Scenario

Generate a canonical scenario that reproduces what the baseline actually did:

```sh
gwt scenario-from-run "$CASE" \
  --program "$OLD" \
  --name "pilot surprise" \
  --output "$PILOT_ROOT/generated/surprise.gwt"
```

This output is verified **actual behavior**, not automatically approved
expected behavior. Review every `GIVEN`, `REQUEST`, and `THEN` line.

- If the result is intended, the reviewed exact-output assertions can become
  regression coverage.
- If the result is unintended, retain the generated setup but have the domain
  owner explicitly replace its output assertions with the intended values.
- Never commit a generated scenario solely because generation succeeded.

Add the reviewed scenario to the candidate source through the workflow's
ordinary code-review process, then run:

```sh
gwt format "$NEW" --check
gwt check "$NEW"
gwt test "$NEW"
```

Pass condition: the scenario is readable to the domain owner, preserves exact
types and values, passes in the candidate program, and fails against the
baseline when it intentionally specifies a corrected result.

## 4. Compare Baseline And Candidate

The candidate starts as a source copy of the baseline and contains only the
reviewed behavior change or refactor. Compare all captured cases, not only the
surprise:

```sh
gwt compare \
  --old "$OLD" \
  --new "$NEW" \
  --import-root "$PILOT_ROOT" \
  --no-absolute-imports \
  "$PILOT_ROOT"/cases/*.execution-case.json

gwt compare \
  --old "$OLD" \
  --new "$NEW" \
  --import-root "$PILOT_ROOT" \
  --no-absolute-imports \
  "$PILOT_ROOT"/cases/*.execution-case.json \
  --json >"$PILOT_ROOT/reports/comparison.json"
```

Reconcile the total case count exactly across unavailable, unchanged,
path-changed, output-changed, new-failure, changed-failure, resolved-failure,
incompatible, and baseline-mismatch categories.
The owner must review every non-unchanged case. A baseline mismatch is not a
candidate behavior change and must never be waived as unchanged.

Pass condition: the reported changes match direct execution of both supplied
programs, every case is accounted for, and no incompatible or failed case is
hidden by the summary.

## 5. Open The Local Workbench

Build a self-contained local review artifact from the same case, comparison,
and verified baseline scenario:

```sh
gwt workbench \
  "$PILOT_ROOT"/cases/*.execution-case.json \
  --old "$OLD" \
  --new "$NEW" \
  --program "$OLD" \
  --name "pilot surprise" \
  --output "$PILOT_ROOT/reports/review.html"
```

Open `review.html` locally. Do not upload it to an arbitrary HTML preview site;
it embeds full case values. Compare its counts, field diffs, conditions, source
locations, and scenario preview with the CLI artifacts.

Pass condition: the outside maintainer can answer “what changed under this
candidate, why did this case take its path, and what scenario should be
reviewed?” without a project contributor translating the evidence.

## Findings Template

Create one `findings.md` per pilot with this header:

```markdown
# Pilot findings

- Workflow:
- Domain owner:
- Outside-project maintainer: yes/no
- Facilitator:
- Source revision:
- Candidate wheel and SHA-256:
- `gwt version --json`:
- Data approval and deletion date:
- Session date and duration:
- Completed full loop: yes/no
- Durable scenario merged (link/revision):
```

Log each observation separately:

| ID | Step | Observed evidence | Expected | Category | Severity | Owner | Resolution |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P?-001 | capture/explain/scenario/compare/workbench/install | command, short output, or artifact path | concrete expected behavior | product/workflow, trust/privacy, docs, diagnostics, integration, performance, or syntax pressure | blocker/high/medium/low | name | open/fixed/accepted |

### Product And Workflow Findings

These include discoverability, installation, privacy, evidence clarity,
scenario review, comparison usefulness, source navigation, collaboration, and
retention needs. Record whether the participant could finish unaided, the
number and nature of facilitator interventions, misleading facts, and the time
for each step.

After the full loop, ask without proposing a hosted answer:

- Who else needed to review or retain this case?
- What sharing, identity, approval, or retention requirement could not be met
  locally?
- Would a repository artifact and ordinary code review be sufficient?
- Which repeated task would make the participant use this workflow again?

A dashboard preference alone is not evidence for a hosted product.

### Syntax Findings

Do not turn general awkwardness into syntax. A syntax-pressure entry requires:

- the exact current GWT snippet
- the task the owner could not express or review clearly
- a short hypothetical before/after
- alternatives tried with existing behaviors, records, scenarios, or host
  normalization
- evidence that the pressure recurs in the other unrelated pilot

Until repeated evidence exists, classify the finding as documentation,
diagnostics, integration, or a deferred language idea. Any accepted syntax
proposal must still follow the parser/runtime/checker/formatter/spec process
and the [design principles](design-principles.md).

## Completion Record

Complete one row for each pilot. Links must point to durable pilot-owned
artifacts or revisions, not a GWT repository rehearsal.

| Gate | Pilot A | Pilot B |
| --- | --- | --- |
| Outside owner and unrelated workflow confirmed | **BLOCKED: not run** | **BLOCKED: not run** |
| Candidate installed without repository checkout |  |  |
| Approved synthetic/full-value fixture captured safely |  |  |
| Domain owner verified factual explanation |  |  |
| Scenario reviewed and reproduced intended behavior |  |  |
| Old/new comparison reconciled every case |  |  |
| Workbench facts matched CLI artifacts |  |  |
| Durable scenario merged in workflow repository |  |  |
| Privacy cleanup/retention action completed |  |  |
| Blocking findings resolved |  |  |
| Findings and revision links |  |  |

The pilot milestone is complete only when every row is filled for both
workflows and every trust/privacy blocker is resolved. A conclusion that GWT is
the wrong fit is valid product evidence, but it does not count as completion of
the full-loop release gate unless the tools themselves behaved correctly.
