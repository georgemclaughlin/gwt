# Sequential REQUIRE proof checkpoint

Successful REQUIRE steps now carry optional-presence and one-of-kind facts into
the remaining steps of their containing body. They reuse the existing condition
proof rules and protect the resulting state addresses against invalidating
alias or ancestor mutation. No new syntax was introduced. See the
[semantics and compatibility notes](../../../docs/native-require.md).

## Implementation and evidence

- The checked assertion stores its proof guards. Runtime guard registration
  follows successful assertion evaluation/evidence; failed assertions add none.
  Every body releases only its own guards on normal completion, return, or
  failure. Surrounding branch/caller guards remain active.
- Request bindings retain their original declared type separately from temporary
  refinement. OUTPUT still matches that declared state contract. This fixes a
  real boundary mismatch exposed by the new request-level proof test.
- The compiler remaps assertion guard spans through expanded examples. Subsequent
  read/write/copy paths retain checked kind information for editor navigation.
- **310 native tests** and Clippy with warnings denied pass on Rust **1.85.0** and
  **1.96.0**. Eight new proof test groups cover policy boundaries, boolean proof
  rules, unsafe forms, alias/ancestor writes, allowed kind sets, cleanup on calls,
  returns, caught failures, branches and loop iterations, root/background
  scopes, exact contracts, Unicode/CRLF examples, budgets, replay, and generation.
  A nineteenth editor type/navigation test checks sequential payload/copy targets.
  The full **310-test static musl release suite** also passes on both compilers;
  the separate release logs are retained at this checkpoint root.
- **627 Python tests** pass. All example formatting, top-level checks, reference
  order/tour workflows, five extension unit tests, and formatting checks pass.
  Python validation rejects the worked example's native expected-failure syntax;
  [its diagnostic payload](python-validation.json) is retained. The example is
  explicitly assigned to native execution, not reported as Python-compatible.
- The frozen installed static executable passes **27 actual VS Code checks**.
  The [result](editor-installed/extension-host.json) includes removing each
  presence/kind proof from unsaved source, exact unsafe-path diagnostics,
  imported payload definition lookup, correction, and unchanged disk files.

## Policy and review

The [transfer example](../../../examples/native_require/README.md) has seven
embedded scenarios and 14 top-level expectations. The qualification freezes
24 independent amount/method inputs: negative/zero/positive amounts; absent and
cash methods; empty/nonempty bank references; verified/unverified banks. Two
inputs succeed; 22 fail before output mutation.

All cases capture and replay exactly. The native suite also generates and runs
scenarios from each request observation. Removing the verification requirement
changes exactly two outcomes. The [review JSON](policy/review.json) and
[offline review](policy/review.html) reconcile all 24 cases with no baseline
mismatch or unavailable case. The 20 `candidateFailed` rows are the candidate's
remaining assertion rejections, not missing comparisons. All 24 evidence traces
change because source spans/content change, while only two outcomes change.
No human review decision was recorded, and no new browser qualification is
claimed for the unchanged review renderer.

## Engine compatibility and deployment

The qualified static package is in [package-1.96.0](package-1.96.0/qualification.json).
It passes three packaged library tests, two embedded scenarios, 18 independent
host observations, 288 concurrent calls, 18 relocated-build replays, and 18
extracted-binary replays. Its source fingerprint is:

`sha256:b11e407f7ada4e23f9371dc984456440af6a4b69dc7b486172db3cff7432b417`

The installed executable SHA-256 is:

`5f6d566cbe9a3ed31f8035ad79966ff984d01d0c59d5fb21f351de1dc0ce7764`

[All 48 archived source/build inputs](package-source-verification.json) match the
workspace. [Eighteen complete invoice observations](invoice-observation-comparison.json)
match the prior engine, and package qualification verifies an explicit retained
case transition. The executable passes the invoice and all 18 host replays in
[Alpine and GLIBC 2.36 containers](static-runtime/qualification.json), with no
networking, read-only mounts/filesystem, and empty PATH. These share the host
kernel and do not establish arbitrary-platform or production qualification.

A separate [actual engine migration](policy/guard-migration.json) records an
intentional incompatibility: the old engine asserted presence and then allowed
a wider alias to clear the value. The new engine refuses that write with
`presence_mutation`, preserving the value and emitting no successful set event.
The prior case bytes remain unchanged, and the candidate case replays exactly.
The migration remains an unapproved proposal. Preserved invoice behavior does
not establish compatibility for every old program.

## Reproduce

With a newly qualified native executable and the retained previous executable:

```sh
python evaluations/native_editor/qualify_require.py \
  --native /path/to/new/gwt-native \
  --previous-engine /path/to/previous/gwt-native \
  --output /tmp/gwt-require-policy
```

The output directory must be new. The previous-engine path is explicit and is
never inferred from case contents. The full project goal remains active: this
checkpoint does not prove improved human understanding, complete language
coverage, or production readiness. No external pilot or publication occurred.
