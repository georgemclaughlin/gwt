# DfE NPQ funding eligibility: local pilot zero

This is an independent, read-only evaluation of whether GWT can express and
review a real deterministic decision from an external project. It is not a
contribution, integration proposal, or endorsement by the upstream
maintainers. Nobody from the project was contacted, and no upstream checkout
was modified.

The source opportunity is the funding decision in
[`DFE-Digital/npq-registration`](https://github.com/DFE-Digital/npq-registration).
It is a good pilot candidate because the service has an ordered decision tree,
domain-specific reason codes, and a sizeable table of acceptance scenarios.
The inspected revision was
`f3601047213660121a5b8e0850c8ecef798f8e03` (2026-07-14). See
[UPSTREAM-LICENCE.md](UPSTREAM-LICENCE.md) for exact source, test, fixture, and
MIT licence attribution.

## What this pilot contains

- `rules.gwt` independently models the decision after Rails and database facts
  have been normalized. It keeps the upstream ordering and distinguishes the
  service's status codes and public descriptions.
- `compare_corpus.py` adapts the upstream CSV vocabulary into those facts and
  executes the compiled GWT request for every row. It requires an explicit CSV
  path; the 1,368-row fixture is not copied here.
- `request.json` is one small host-boundary example. The embedded scenarios in
  `rules.gwt` exercise priority, RISE/PP50, childcare, alternative settings,
  and referral behavior.

The intended boundary is:

```text
Rails models and lists -> normalized EligibilityFacts -> GWT decision -> FundingDecision
```

GWT does not query users, applications, cohorts, courses, schools, or external
eligibility lists. A real shadow integration would have to build the fact
record from the same live state as the Ruby service.

## Result

At the pinned revision, the complete CSV comparison produced:

```text
corpus rows: 1368
coarse outcome parity: 1368/1368
mismatches: 0
expected outcomes: {"funded": 62, "not_funded": 1284, "subject_to_review": 22}
actual outcomes: {"funded": 62, "not_funded": 1284, "subject_to_review": 22}
```

The fixture's 62 funded cases consist of 61 plain `yes` rows and one
`yes (if on ITT provider list)` row.

This is faithful parity only at the fixture's asserted outcome level. The CSV
uses `no` for many distinct failures and treats both review status codes as
`subject to review`. It therefore cannot verify exact GWT status-code parity.
The GWT model emitted these more precise codes, based on the service logic:

```text
early_years_invalid_npq                         42
funded                                         62
ineligible_establishment_not_a_pp50            18
ineligible_establishment_type                  38
not_entitled_childminder                        1
not_in_england                                330
not_lead_mentor_course                          9
not_new_headteacher_requesting_ehco             21
previously_funded                             165
referred_by_return_to_teaching_adviser          10
subject_to_review                               12
unfunded_cohort                                660
```

Those counts are a modeled diagnostic, not an upstream oracle result. A reason
branch could be wrong while still matching a CSV `no`. Exact parity would need
direct Ruby/GWT shadow execution or an upstream fixture that records status
codes.

## Exact-status review zero

`review_zero.py` closes that narrow evidence gap for 12 stratified fixture
rows without booting Rails or changing the upstream checkout. It runs the
pinned `FundingEligibility` class itself in the upstream Ruby 3.4.9 runtime,
supplying small stub objects for only the cohort, course, institution, user,
and application interfaces that the service calls. The same normalized facts
then run through GWT.

The result is exact parity for all three declared decision fields:

```text
exact Ruby/GWT status parity: 12/12
```

`exact_status_slice.json` preserves those pinned oracle outputs and normalized
inputs as a small offline regression fixture. The test suite replays it through
GWT and also recreates the seeded precedence error, requiring the comparison to
remain one output change plus eleven path-only changes. Re-running
`review_zero.py` is still the stronger audit because it executes the pinned
Ruby class directly.

The slice includes global precedence, outside catchment, previous funding,
RISE and PP50 paths, three childcare paths, alternative-setting review,
provider approval, and return-to-teaching referral. This proves exact service
parity for that slice, not for all 1,368 rows and not for Rails fact derivation.

The script then creates a deliberately wrong candidate that evaluates outside
catchment before the unfunded-cohort rule. Both branches produce the coarse
`not_funded` outcome, so the original CSV still sees `no`. GWT comparison
reports:

```text
1 output changed
11 execution paths changed
```

For the overlapping case, the exact status changes from `unfunded_cohort` to
`not_in_england` and the description changes from `unfunded_cohort` to
`outside_catchment`. This is the strongest positive finding from the local
exercise: source-linked comparison catches a meaningful reason/precedence
change that the broad acceptance corpus cannot see.

The 11 path-only changes are also a caution. Reordering two early predicates
changes recorded execution evidence for every case that reaches that decision,
even when the result is identical. That is factually correct, but a larger
corpus could make a simple refactor noisy. Reviewers need output and path
changes presented as different kinds of evidence, as the current comparison
does.

The Ruby harness is intentionally narrow. It verifies the actual service class
but stubs Rails-derived facts; it does not prove that the adapter and live Rails
models compute those facts identically. It requires Docker and reads a separate
pinned upstream checkout mounted read-only. Generated Execution Cases and the
self-contained workbench contain full fixture values and stay in a temporary
directory by default.

## Run it

From the GWT repository root:

```sh
python -m gwtlang format examples/external_pilots/dfe_npq_funding_eligibility/rules.gwt --check
python -m gwtlang check examples/external_pilots/dfe_npq_funding_eligibility/rules.gwt
python -m gwtlang test examples/external_pilots/dfe_npq_funding_eligibility/rules.gwt
python -m gwtlang run examples/external_pilots/dfe_npq_funding_eligibility/rules.gwt \
  --json-input examples/external_pilots/dfe_npq_funding_eligibility/request.json \
  --request "assess funding eligibility" --json
python examples/external_pilots/dfe_npq_funding_eligibility/compare_corpus.py \
  /path/to/npq-registration/spec/fixtures/scenarios/eligibility_testing_scenarios.csv
python examples/external_pilots/dfe_npq_funding_eligibility/review_zero.py \
  /path/to/npq-registration
```

Pass `--json` to the comparison command for a machine-readable report including
the first mismatches, if any. The review-zero command prints the temporary
artifact directory containing the 12 captured cases, exact-parity manifest,
seeded candidate, comparison JSON/text, generated scenario, and local
workbench HTML. Each captured case includes the host-supplied paths in
`fact-provenance.json`, so the dossier identifies where selected normalized
facts were derived without treating those claims as verified GWT evidence.
Use `--output-dir` only with a new directory.

## What fit well

- The service is already a first-match decision tree. GWT's `DECIDE` makes
  precedence visible: unfunded cohort, catchment, and prior funding cannot be
  mistaken for peer conditions farther down the policy.
- Natural behavior names divide the four work-setting policies without hiding
  their sequence behind framework objects.
- Literal unions make status-code drift a checker error. The request guarantees
  that a decision cannot leave the placeholder state.
- Embedded scenarios are readable examples of policy claims, while the host
  harness provides broad regression pressure from a real corpus.
- The decision returns both a coarse outcome and an exact reason code. That is
  a better review artifact than the CSV's single yes/no-style column.
- Compiling once and evaluating all 1,368 normalized cases took about three
  seconds on the pilot machine, so local shadow comparison is practical.

## What did not fit cleanly

- The readable rule file is verbose. A flat 16-field input record repeats many
  irrelevant booleans in scenarios, and long course/employment membership
  checks become chains of `or` expressions.
- GWT's non-null record boundary encourages normalization, but it also erases
  which facts are unavailable versus irrelevant. For example, an absent
  institution is meaningful in the Ruby service; this pilot supplies derived
  booleans instead.
- The adapter duplicates application knowledge: course aliases, cohort funding,
  work-setting groups, institution traits, and employment identifiers. If that
  adapter drifts, perfect GWT/CSV parity can be falsely reassuring.
- The most useful explanation is currently the selected GWT branch. It does not
  explain how Rails decided that a user was previously funded or a school was
  on RISE/PP50. Evidence stops at the normalized boundary.
- The acceptance corpus is broad but shallow. It says `no`, not why, and several
  inputs are fixed or inferred by the RSpec harness rather than represented as
  fixture columns.

## Scope and semantic gaps

This pilot deliberately matches the scenario harness, not every possible
production call:

- `new_headteacher` is always false in the CSV suite, so the positive early
  headship coaching path is modeled from the service but not corpus-verified.
- `childminder_entitled` is always false because the fixture constructs an
  unlisted provider; its positive path is not corpus-verified.
- All fixture school institutions use an eligible establishment type. The
  GWT ineligible-institution branch is modeled but not varied by this corpus.
- The fixture has no approved-provider column. Its RSpec derives approval from
  the special expected phrase. This adapter instead derives it from the lead
  mentor work setting plus the teaching-development course. That avoids reading
  the expected value as an input, but cannot test the same case with approval
  denied.
- `previously_funded` is reduced to the fixture's registration flag. The Ruby
  service additionally considers accepted state, funding eligibility, funded
  place, and rebranded alternative courses.
- The Ruby `MissingMandatoryInstitution` exception is outside this normalized
  decision model.
- Database lookup failures and unknown UI values fail in the Python adapter;
  they are not expressed as GWT outcomes.

## Candid take

GWT adds review value here, but the corpus result alone overstates it. The
strongest artifact is the explicit ordering plus exact reason vocabulary in one
executable file. A policy reviewer could discuss whether RISE should precede
establishment eligibility or whether a referred applicant deserves a distinct
review code, then preserve that claim as a scenario.

The weak point is provenance. Most difficult facts are computed before GWT, so
the language explains a decision over supplied booleans rather than the full
application behavior. This would be worthwhile as a shadow policy layer only
if the integration captured both normalized inputs and the Ruby service's exact
status code, then compared them in production-like cases. Without that, this is
a useful readability experiment—not evidence that replacing the Rails service
would reduce risk.

The best next experiment is therefore small: expose exact Ruby status codes for
a representative captured slice, run the same normalized records through GWT,
and ask an external maintainer whether the GWT branch evidence makes one real
policy change easier to review. Do not expand the language or propose an
upstream rewrite on the strength of this local pilot zero.
