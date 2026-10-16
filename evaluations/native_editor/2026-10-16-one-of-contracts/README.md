# One-of contract checkpoint

The native engine now checks closed tagged records at request boundaries and in
source setup. Common fields remain readable and writable; changing kind requires
whole-value replacement. This checkpoint provides the contract/value foundation.
Kind-specific branch access, alias-safe narrowing, and exhaustive dispatch remain
unfinished.

## Verification

- Rust 1.85.0 and 1.96.0 each pass 245 workspace tests (241 integration and four
  unit tests) and Clippy with warnings denied: `test-*.log`, `clippy-*.log`.
- Seven tests in `crates/gwt-core/tests/one_of.rs` cover closed input shapes,
  optional normalization, nested/list/optional setup, common-field updates,
  protected discriminator aliases, invalid declarations, complete replacement
  under step limits, captured/generated scenarios, replay, and type/value budgets.
  An additional editor provenance test checks imported aliases and payload field
  declarations across Unicode/CRLF source.
- All 614 Python tests pass (`python-tests.log`). The example runner explicitly
  assigns this native-only source form to its Rust tests. All examples retain
  Python formatter coverage. Formatting, top-level Python example checking, and
  whitespace checks are recorded in `final-checks.log`; reference request results
  are in `python-order_fulfillment-request.json` and
  `python-language_tour-request.json`.
- Actual VS Code 1.137.0 passes 20 checks using both the final workspace executable
  (`native-final/extension-host.json`) and installed package
  (`native-packaged/extension-host.json`). The added check resolves an unsaved
  imported one-of alias and reports unsupported private-field access at its exact
  span, then clears the diagnostic after correction without saving the buffers.
- Final package qualification verifies the independent source fingerprint and
  dependency graph, 18 host observations, 288 concurrent executions, and 18
  relocated replays (`package-final-1.96.0/qualification.json`). The engine identity
  is `sha256:c1d47bd339ed820e2326f3381a34fbc7d3a04b2dc6fe452b61f69e8a165beb3b`.
  A subsequent byte comparison confirms all 46 implementation/build inputs in
  that archive match the current workspace, accounting for Cargo's original
  manifest filename. Executable and archive hashes are recorded separately.

The earlier `package-1.96.0/` and `native/` results precede a Clippy cleanup and
are retained as history. `clippy-1.85.0-before-cleanup.log` records that resolved
lint failure. The final directories above are authoritative for this checkpoint.

## Behavioral evidence

The packaged CLI produces [a passing validation report](contact-validation.html)
for three contact scenarios and eight expectations, with no evidence warnings.
Email and phone requests both run, capture, and replay successfully
(`email.*.json`, `phone.*.json`). Scenario generation also succeeds; the Rust tests
compile and execute generated nested/list/optional cases. A phone carrying an
email address is rejected with `unknown_input` before execution events are emitted
(`invalid.run.json`).

[The comparison report](contact-review.html) compares two captured contacts
against an intentionally incorrect email route in `candidate.gwt`. It detects
the email outcome change while the phone outcome stays unchanged. Both cases
have changed source/evidence; neither baseline mismatches. The candidate is a
fault-detection fixture, not an accepted routing policy. The unchanged HTML
renderers were not requalified in a browser at this checkpoint.

`source-hashes.json` records the implementation, tests, documentation, and example
used. These checks establish the documented contract behavior, not human
comprehension gains or complete one-of support. No external pilot or publication
was performed. The full project goal remains open.
