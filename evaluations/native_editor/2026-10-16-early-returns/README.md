# Early-return proof and source-adaptation checkpoint

IF/DECIDE continuations now retain supported condition facts common to every
branch that can continue. Kind dispatch joins surviving kind sets; FIND with a
returning fallback can retain outer-state facts from its selected filter. The
item binding and facts introduced inside child bodies remain local. See the
[intentional inference boundaries](../../../docs/native-early-returns.md).

## Implementation and correctness

The compiler uses the existing structural all-path return analysis, intersects
kind restrictions within a path, unions alternatives, and retains common presence
paths. Ancestors refine before children; paths not valid in the joined parent
cannot escape. The checked statement stores continuation guards. Runtime adds
them only after normal continuation and releases them with their containing body.
No new syntax, synthetic reads, assertion events, or budget steps were added.

- **328 native tests** pass on Rust **1.85.0** and **1.96.0**, in development and
  static musl release modes. Clippy with warnings denied passes on both.
  [Counts](test-counts.json) and complete logs are retained at this checkpoint.
- Eight new semantic groups cover 20 independent exchange inputs, eight scenarios,
  IF continuations on either side, nested returns, DECIDE shared facts, kind-set
  joins and dispatch, optional ancestors, alias mutation, exact scopes, FIND
  fallback, local item rejection, caller guard lifetime, returns/caught failures,
  CRLF evidence, short-circuit reads, and every step budget through three runs.
- Invalid forms remain invalid: one continuing path without a fact, branch-local
  REQUIRE facts promoted outward, possibly empty FOR used as a definite return,
  REQUIRE false treated as a return, a returning helper used as caller control
  flow, and unchecked unreachable source.
- **627 Python tests**, example formatting, top-level checking, reference
  order/tour workflows, five extension unit tests, and formatting checks pass.
  Python validation rejects this example's native request-level LET form;
  [its diagnostic payload](python-validation.json) is retained. The example is
  explicitly registered for native execution.
- The 21st editor type/navigation test checks uniquely selected payload fields
  and copies after optional/kind guards. The installed static executable passes
  **29 actual VS Code checks** in [the retained result](editor-installed/extension-host.json),
  including changing either guard's RETURN to PASS in unsaved source, exact
  unsafe-path diagnostics, imported definitions, and correction without saving.

## Independent policy and source adaptation

The [exchange example](../../../examples/native_early_returns/README.md) handles
unsupported conditions with a sequence of early returns. Twenty independently
expected inputs cover enabled/disabled exchanges, absent/gift/receipt proofs,
verification, and receipt ages -1/0/30/31. All cases capture/replay and generate
runnable scenarios. Replacing `> 30` with `>= 30` changes exactly one outcome.
The [fault review](policy/review.json) and [offline artifact](policy/review.html)
retain all 20 cases, with no mismatch, unavailable case, or candidate failure.

A separately frozen [nested-ELSE source](policy/nested-rules.gwt) runs on the
actual previous executable. Each of its 20 observed decisions matches the
independent expectation, and each case migrates to the new engine with the
**full observation preserved**. Original case bytes remain unchanged.

The migrated cases then compare against the new guard-clause source. The
[source-adaptation review](policy/refactor.json) and [offline artifact](policy/refactor.html)
retain all 20 cases with **zero outcome or state changes**, and changed source
and evidence in all 20. Engine migration and source adaptation are separate
operations: the latter is not misreported as full observation preservation.
The proposals remain unapproved; no human review benefit or new browser check
of the unchanged renderer is claimed.

## Deliberate compatibility change

A separate [actual old/new engine comparison](policy/guard-migration.json)
records an intentional change. The previous executable could return on absence,
continue on presence, and then clear the value through a wider alias. The new
engine rejects that write with presence_mutation, retaining the prior value
and emitting no successful set event. The old case is unchanged and candidate
replay verifies the complete failure. This is an unapproved migration proposal.

## Packaging and runtime evidence

The [static package qualification](package-1.96.0/qualification.json) passes
three packaged library tests, two embedded scenarios, 18 host observations,
288 concurrent calls, 18 relocated-build replays, and 18 extracted-binary replays.
All [48 archived source/build inputs](package-source-verification.json) match the
workspace. All [18 invoice observations](invoice-observation-comparison.json)
match the previous engine, and an explicit retained-case transition verifies
that preservation. These cases do not establish universal source compatibility.

The packaged engine source identity is:

`sha256:7383db1091c490d6e81d0c121d570ea043f93a9fee3195db42c1b7d56874d01e`

The executable SHA-256 is:

`8d536ccecc3486e21b49c8c7c9e397f641b9f78e4d96e07061fdddd8ae73c598`

The executable passes the invoice example and all 18 host replays in
[Alpine and GLIBC 2.36 containers](static-runtime/qualification.json) with no
networking, read-only filesystem/mounts, and empty PATH. These share the host
kernel and do not establish arbitrary-platform or production support. Builds
used main-filesystem scratch directories to avoid the previously observed
`/tmp` quota; the reused full-suite target cache is recorded in
[build-scratch.json](build-scratch.json).

## Reproduce

```sh
python evaluations/native_editor/qualify_early_returns.py \
  --native /path/to/new/gwt-native \
  --previous-engine /path/to/previous/gwt-native \
  --output /tmp/gwt-early-returns
```

The output directory must be new. The prior engine path is explicitly supplied,
never inferred from a case. The full project goal remains active. General joins
of facts produced inside branch bodies, remaining language and tooling work,
production qualification, and actual comparative human evidence remain open.
Nothing was published and no external pilot was initiated.
