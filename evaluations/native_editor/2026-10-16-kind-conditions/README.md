# Native kind-condition checkpoint

Literal discriminator comparisons now refine native short-circuit expressions,
`IF`/`ELSE`, and ordered `DECIDE` conditions/bodies. Equality, inequality,
negation, true conjunctions, and false disjunctions establish conservative kind
sets. Runtime guards prevent alias and ancestor writes from invalidating those
sets. A multi-kind proof permits replacement within its set; existing exhaustive
kind dispatch still protects its selected runtime kind. See
[the semantic decision](../../../docs/native-kind-conditions.md).

Nested optional record initializers now explicitly construct present values.
This was needed to express the worked contact inputs directly in scenarios.
Closed-field checks and literal discriminators still apply, and optional scalar
types still reject record bodies. No new source tokens were introduced.

## Verification

- Rust **1.85.0** and **1.96.0** each pass **295** workspace tests (291 integration
  and four unit tests) and Clippy with warnings denied. Logs are
  `rust-*-tests.log` and `rust-*-clippy.log`.
- Nine `kind_conditions.rs` tests cover 22 independently expected contact
  inputs, seven embedded scenarios with 21 top-level expectations, direct and
  reversed comparisons, negation/short-circuiting, unsafe proof refusal, alias
  and ancestor writes, multi-kind replacements, optional presence, copies and
  selected helper contracts, collection items, return/failure cleanup, budgets,
  original Unicode/CRLF spans, generated scenarios, and capture/replay/revision
  comparison. Reversing SMS consent changes exactly eight of the 22 outcomes.
- All **621 Python tests** pass. Every example passes formatting; top-level
  Python checking, order and language-tour request workflows, extension syntax
  and five JavaScript tests, Rust formatting, and whitespace checks pass.
  `final-checks.json` records the final documented example commands and checks.
- Actual VS Code **1.137.0** passes **25** installed-engine checks
  (`editor-installed-final/extension-host.json`). The new check accepts an
  unsaved compound presence/kind guard, exposes the checked payload type in
  hover, and reports the exact unsafe path after editing the kind. Restoring
  the condition clears the error without changing the disk source.
- The first editor run failed in the new test's hover assertion: VS Code's
  plain-text Markdown conversion escapes punctuation/spaces. The assertion now
  decodes that display representation before comparing the text. The failed
  `editor-installed/` logs are retained. No editor implementation change was
  needed for this correction.
- Field declaration provenance through a kind-refined branch remains incomplete.
  Both the Rust editor test and actual editor check require the known binding
  fallback rather than asserting an invented payload declaration. Selected-kind
  type annotations continue to retain their explicit field origins.

## Installed package and review

The Rust 1.96.0 package passes independent source-fingerprint and dependency
checks, **18** host observations, **288** concurrent executions, and **18**
relocated replays. The installed executable is
`/tmp/gwt-package-host-tqtkekad/installed/bin/gwt-native`, SHA-256
`ad7d6158de3987b60e0cbde49fb41c74bfb1a786924427c77226af2798689cbd`.
Its engine source identity is
`sha256:a8baa6988babd23e9d848049f927011458b285c11f6c9ab84e668b3028647f7f`.
`package-source-verification.json` compares all **48** archived implementation
and build inputs to the current workspace. The shared branch-proof module is
now `refinement.rs`; it retains the previous presence behavior and adds kind sets.

The installed package validates seven scenarios and captures/replays eight
representative contact requests. The [offline review](contact/kind-review.html)
identifies exactly three changed outcomes when SMS consent is reversed:
`sms-consent`, `sms-no-consent`, and `sms-empty-number`. All eight cases compare;
baseline mismatches, candidate failures, and unavailable cases are zero. All
eight have source/evidence changes, which are distinct from changed outcomes.

A separate alias case captures/replays `kind_mutation` when an email proof is
invalidated by a phone replacement. The email remains unchanged and no successful
write event is recorded. `qualify_kind_conditions.py` retains inputs, both source
revisions, validation, captures, replay results, corpus, review, and failure case.

Offline Chromium **153.0.8010.12** checks at **1440px** and **390px** pass all
eight case selections, visible branch evidence, the three-case outcome filter,
and operand navigation from a compound condition to its kind equality. Missing
contact data produces no fabricated kind or payload reads. There are no script
errors, external requests, or horizontal overflow. Both
`contact/browser/kind-condition-decisions-*.png` screenshots were inspected; the
selected conditions, source excerpts, and operand links remain readable.

## Boundaries and remaining goal

`python-reference-limitation.json` records successful Python formatting/checking
and failed Python execution of a nested optional payload path. The example is
explicitly native-only for execution, with independent native expected outputs
including its actual JSON request fixture. This is not cross-engine parity.

No external pilot or human study occurred. The checks establish the tested
semantics, Linux package/host behavior, editor behavior, and review rendering.
They do not prove human comprehension benefits, broader deployment support, or
completion of the full project goal. Broader flow proofs, branch-field provenance,
remaining language decisions, deployment qualification, and actual comparative
human evidence remain open. `source-hashes.json` identifies this checkpoint's
relevant implementation, tests, examples, documentation, and qualification tools.
