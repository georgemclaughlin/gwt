# External pilot: semantic-release commit analyzer

This local pilot-zero fit exercise models one deterministic function from an
existing project: match a normalized commit against ordered release rules and
retain the highest-priority matching release outcome.

It is intentionally not a replacement for `@semantic-release/commit-analyzer`.
The pilot asks whether GWT makes this small decision core easier to inspect and
review while preserving its important boundary cases.

No upstream maintainer was contacted, no upstream repository was modified, and
this is not an upstream integration proposal.

## Upstream source and attribution

- Project: [`semantic-release/commit-analyzer`](https://github.com/semantic-release/commit-analyzer)
- Repository: `https://github.com/semantic-release/commit-analyzer.git`
- Reviewed commit: `f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758`
- Behavior source: [`lib/analyze-commit.js`](https://github.com/semantic-release/commit-analyzer/blob/f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758/lib/analyze-commit.js)
- Precedence helper: [`lib/compare-release-types.js`](https://github.com/semantic-release/commit-analyzer/blob/f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758/lib/compare-release-types.js)
- Release hierarchy: [`lib/default-release-types.js`](https://github.com/semantic-release/commit-analyzer/blob/f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758/lib/default-release-types.js)
- Test cases consulted: [`test/analyze-commit.test.js`](https://github.com/semantic-release/commit-analyzer/blob/f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758/test/analyze-commit.test.js)

The upstream project is MIT licensed, copyright (c) 2017 Pierre-Denis
Vanduynslager. See its [MIT license](https://github.com/semantic-release/commit-analyzer/blob/f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758/LICENSE).
This pilot is an independent expression of the observed behavior. The scenario
inputs are adapted from the upstream tests; substantial upstream prose or
implementation code is not copied.

## Run it

From the GWT repository root:

```sh
python -m gwtlang format examples/external_pilots/semantic_release_commit_analyzer/rules.gwt --check
python -m gwtlang check examples/external_pilots/semantic_release_commit_analyzer/rules.gwt
python -m gwtlang test examples/external_pilots/semantic_release_commit_analyzer/rules.gwt
python -m gwtlang run examples/external_pilots/semantic_release_commit_analyzer/rules.gwt \
  --json-input examples/external_pilots/semantic_release_commit_analyzer/request.json \
  --request "analyze normalized commit" --json
python -m gwtlang capture examples/external_pilots/semantic_release_commit_analyzer/rules.gwt \
  --json-input examples/external_pilots/semantic_release_commit_analyzer/request.json \
  --request "analyze normalized commit" \
  --fact-provenance examples/external_pilots/semantic_release_commit_analyzer/fact-provenance.json \
  --output /tmp/commit-analysis.execution-case.json
python -m gwtlang run examples/external_pilots/semantic_release_commit_analyzer/rules.gwt \
  --json-input examples/external_pilots/semantic_release_commit_analyzer/evaluated-request.json \
  --request "select release from evaluated rules" --json
python -m gwtlang capture examples/external_pilots/semantic_release_commit_analyzer/rules.gwt \
  --json-input examples/external_pilots/semantic_release_commit_analyzer/evaluated-request.json \
  --request "select release from evaluated rules" \
  --fact-provenance examples/external_pilots/semantic_release_commit_analyzer/evaluated-fact-provenance.json \
  --output /tmp/commit-selection.execution-case.json
python -m gwtlang openapi examples/external_pilots/semantic_release_commit_analyzer/rules.gwt \
  --output /tmp/commit-analyzer-openapi.json
python -m gwtlang serve examples/external_pilots/semantic_release_commit_analyzer/rules.gwt \
  --port 8080 \
  --capture-dir /tmp/commit-analyzer-cases \
  --capture-request "select release from evaluated rules" \
  --capture-values \
  --fact-provenance examples/external_pilots/semantic_release_commit_analyzer/evaluated-fact-provenance.json
python examples/external_pilots/semantic_release_commit_analyzer/run_conformance.py
```

The JSON example selects `major` through the breaking-feature rule. The
optional provenance sidecar records which normalized facts remain owned by the
host parser, configuration loader, and matcher; GWT validates the paths but
does not authenticate the descriptions.

## OpenAPI and `gwt serve`

The host-evaluated request is projected as OpenAPI 3.1 operation
`selectReleaseFromEvaluatedRules` at:

```text
POST /requests/select-release-from-evaluated-rules
```

Its request body is a closed `RuleEvaluation[]` contract and its successful
response is the declared `AnalysisResult`. The `ReleaseOutcome` schema retains
`"false"`, `"null"`, and `"undefined"` as explicit tagged strings because JSON
cannot preserve JavaScript `undefined`; a JavaScript client can map those tags
back to native values at its outer boundary.

The live demo generates a temporary `typescript-fetch` client from the pilot's
OpenAPI document, starts `gwt serve` on an ephemeral local port, and sends all
20 pinned host-evaluated cases through HTTP:

```sh
node examples/external_pilots/semantic_release_commit_analyzer/openapi_client_demo.mjs \
  /tmp/commit-analyzer
```

It requires the exact prepared upstream checkout described below, Node 20 or
newer, npm/npx, and the Java runtime used by OpenAPI Generator. Generated files
remain temporary and are not committed. The expected result is:

```text
generated OpenAPI client/gwt serve parity: 20/20
```

OpenAPI describes execution facts and results; it does not transport the
optional Execution Case provenance sidecar. Capture and workbench artifacts
retain that unauthenticated review metadata separately, so provenance does not
become decision input. The served-capture command above makes the integration
boundary concrete: each selected HTTP decision returns an `x-gwt-case-id` and
writes the corresponding replayable case under `/tmp/commit-analyzer-cases`.
Omit `--capture-values` for shape-only evidence when inputs must not be retained.

## Served evidence lifecycle

The local lifecycle demo runs the complete pinned host-evaluated corpus through
the actual HTTP service, verifies every `x-gwt-case-id` against the written
full-value artifact, and attaches the static matcher provenance. It uses `gwt
corpus create` to derive and write the ordered manifest, verifies it again with
`gwt corpus check`, then makes a temporary candidate that intentionally
reverses the named-release priority comparison, compares all captured cases,
and renders a self-contained review workbench:

```sh
python examples/external_pilots/semantic_release_commit_analyzer/served_evidence_demo.py \
  /tmp/commit-analyzer-evidence
```

The output directory must be new or empty. It receives:

- `cases/`: 20 content-addressed Execution Cases;
- `corpus.json`: the integrity-checked pilot case ID to Execution Case mapping;
- `candidate-rules.gwt`: the explicitly synthetic local mutation;
- `comparison.json`: the versioned old/new comparison;
- `workbench.html`: a local review dossier over the same corpus.

The expected result is 20/20 verified served captures, 17 unchanged cases, and
3 `output_changed` cases. Those three are the precedence-sensitive
`patch-then-minor`, `minor-then-patch`, and `prerelease-ladder` inputs. This
demo uses the checked-in host-match observations and does not require an
upstream checkout, network access, generated client, or contact with the
external maintainer. The cases and HTML contain full request and output values;
keep them local and apply the same retention rules as the underlying corpus.

## Differential conformance

[`conformance_cases.json`](conformance_cases.json) pins 20 upstream-shaped
commit/rule inputs and their observed results at the reviewed commit. The
offline command above checks the GWT side against that snapshot. For a live
comparison, prepare an exact upstream checkout and pass it to the runner:

```sh
git clone https://github.com/semantic-release/commit-analyzer.git /tmp/commit-analyzer
git -C /tmp/commit-analyzer checkout f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758
npm --prefix /tmp/commit-analyzer ci --omit=dev --ignore-scripts
python examples/external_pilots/semantic_release_commit_analyzer/run_conformance.py \
  /tmp/commit-analyzer
```

The live oracle imports the pinned upstream `lib/analyze-commit.js`; it does
not reimplement the JavaScript decision. The runner verifies the checkout
commit before executing it.

The harness compares two GWT boundaries. The direct boundary lets GWT match
the normalized `type` and `scope` facts. The host-evaluated boundary uses
[`host_match_adapter.mjs`](host_match_adapter.mjs) to apply the upstream
checkout's micromatch dependency and passes ordered `RuleEvaluation` facts to
GWT for release selection.

Current live result:

- the direct boundary has 18 exact matches and 2 intentional disagreements:
  upstream micromatch patterns `b*` and `f*` match, while GWT exact text does
  not;
- the host-evaluated boundary has 20/20 parity, including the two glob cases,
  missing and null commit properties, falsy release outcomes, precedence, and
  the early stop at `major`.
- the generated OpenAPI TypeScript client has the same 20/20 result through a
  real `gwt serve` process.

Both disagreements are classified as a known integration-boundary limitation,
not an upstream defect or a GWT runtime bug. They do not justify adding a
general pattern language to GWT: the second path proves that a host adapter can
calculate rule matches and leave the reviewable precedence decision in GWT.
The harness will make that tradeoff visible if future evidence changes it.

## Normalized boundary

The JavaScript function accepts open-ended parsed commit objects and rule
objects. GWT records are closed and GWT has no source-level `null`, so this
pilot makes an adapter boundary explicit:

- `type_state` and `scope_state` distinguish `missing`, `null`, and `present`;
- `type_value` and `scope_value` are meaningful only when state is `present`;
- note arrays become `has_breaking_note`;
- revert objects become `is_revert`;
- JavaScript `false`, `null`, and `undefined` outcomes become the tagged text
  values `"false"`, `"null"`, and `"undefined"`;
- missing or false `breaking`/`revert` rule flags both normalize to a false
  `requires_*` flag, matching the upstream truthiness gates.

This makes absence visible and contract-checkable. The alternative
`RuleEvaluation` boundary is smaller: each row contains only a host-owned
`matched` fact plus the rule id and release outcome. Its provenance sidecar
explicitly labels those matching facts as host-derived.
The shared `ReleaseOutcome` type permits `"undefined"` in a normalized rule for
assignment compatibility with the result record; the adapter must reject that
value for rules. This is a limitation of the pilot contract, not upstream
behavior.

## Deliberate scope limits

The direct model supports exact text matching for the conventional `type` and
`scope` fields plus breaking-note and revert gates. The checked-in host adapter
adds micromatch for those two fields only. Neither path claims compatibility
with the full upstream matcher:

- no arbitrary dynamic commit/rule properties such as `tag`, `emoji`, or
  parser-specific fields;
- no non-text scalar criteria such as the numeric `scope` case in the upstream
  unit tests;
- no parsing of commit messages, loading of presets, default-rule fallback,
  revert filtering, or aggregation across multiple commits;
- no validation/loading of user configuration.

Adding fake partial matching inside GWT would make the direct pilot look more
compatible than it is. The evaluated-rule request demonstrates the preferred
production seam: keep micromatch outside the GWT decision and pass explicit
host-provided match facts.

## Fit findings

### Good

- The precedence list becomes a readable, explicit behavior with exact ranks.
- Embedded scenarios clearly separate no match from matched `false` and matched
  `null`, which JavaScript otherwise communicates through runtime values.
- Rule order, the special falsy comparison behavior, and the early stop at
  `major` are visible rather than buried in array callbacks.
- Closed input/output records document the adapter contract and make malformed
  normalized input fail before rule evaluation.
- Each scenario calls the public request, so examples are executable interface
  evidence rather than helper-only tests.
- Host-evaluated facts reduce the GWT contract while retaining the policy's
  unusual falsy precedence and early-stop behavior.
- The same request contract produces a closed OpenAPI operation and generated
  client without adding adapter-specific language syntax.

### Bad or awkward

- Fixed records are a poor direct representation of the upstream open object
  matcher. Every supported criterion must become another field and matching
  branch.
- Explicit absence normalization is honest but verbose. The model needs both a
  property-state tag and a placeholder text value.
- Representing JavaScript `false` and `null` as tagged strings preserves the
  distinction but introduces adapter vocabulary that is not native to the
  domain.
- The nested release-rank behavior is longer and visually heavier than the
  upstream seven-element priority array.
- Repeating fully populated rule rows makes scenarios noisy because records do
  not have defaults or optional fields.
- GWT cannot break a `FOR` directly, so early termination is represented by a
  state flag and guarded later iterations.

## Semantic observations

The core is not simply “take the maximum rank.” In the reviewed commit:

- an initial `undefined` means no rule matched;
- a matched `false` or `null` is a distinct result;
- a current `false`/`null` is falsy, so the next match replaces it;
- a candidate `false`/`null` has release-list index `-1`, so it replaces a
  previously selected named release;
- selecting `major` immediately stops scanning, so later rules cannot replace
  it.

Those details are modeled because they are observable, even though some are
surprising. The upstream unit tests cover lone `false` and `null`; the pilot's
early-stop scenario also protects the interaction with `major`.

## Recommendation

This is a **useful but bounded fit** for GWT. The priority decision and its
edge-case evidence read well once inputs are normalized. The generic matcher
does not: reproducing lodash deep partial matching plus micromatch over
arbitrary object fields would push GWT toward a query/pattern language and
against its behavior-oriented design.

For a real integration, keep commit parsing, dynamic property matching, and
micromatch in JavaScript. Pass the ordered matching rule outcomes—or a narrow
normalized commit/rule shape agreed by one deployment—into GWT for the
reviewable selection policy. The 20/20 host-adapter result validates that seam
for the pinned corpus. Do not broaden GWT syntax solely to achieve drop-in
compatibility with this package.
