# Finite scalar contracts — 2026-10-16

The native profile now declares closed integer, exact-decimal, and singleton
boolean domains, with boundary validation, checked assignments, and exhaustive
value dispatch. See [the semantic decision](../../../docs/native-finite-literals.md)
and [receipt example](../../../examples/native_finite_codes/README.md).

## Verified behavior

- Eight new Rust test groups bring the full native suite to **429 passing tests**
  on Rust **1.85.0 and 1.96.0**. Both toolchains pass Clippy with warnings denied;
  workspace formatting passes.
- **671 Python tests pass**, including formatter preservation. All example files
  pass formatting checks, root Python examples check, the order/tour workflows
  run, and the VS Code JavaScript syntax checks pass.
- The receipt matrix checks **144 independently specified requests** through the
  library and separately through the packaged CLI. Twelve are accepted; 132 fail
  the input contract with no execution events. Five embedded scenarios pass.
- Static/semantic tests cover singleton/full boolean domains, mixed-category and
  duplicate refusals, exact decimal distinctions beyond floating-point precision,
  large integer tokens, exhaustive/impossible branches, negative constants,
  copied subsets, mutable alias contracts, arithmetic widening, nested lists and
  optionals, malformed public type values, and unsupported computed narrowing.
- Inspection retains exact numeric strings in its type metadata. Editor hover
  renders finite decimal contracts with their base and links to the original
  field through Unicode/CRLF source. Captures replay; generated scenarios retain
  nested finite contracts. A deliberately faulty multiplier changes exactly the
  intended retry outcomes.
- The release source package builds and runs outside the repository. Its static
  CLI and Rust host pass 18 host observations, 288 concurrent executions, and 18
  relocated case replays. The explicit previous-engine transition passes against
  the retained f5b1 engine; this does not silently upgrade old captures.
- Twelve current-engine cases replay in the case-review workflow: nine accepted
  inputs and three expected boundary failures. Changing the retry multiplier
  from ten to twelve changes exactly three outcomes. All review decisions remain
  pending. The candidate is an intentional fault, not an approved policy.
- **87 Playwright CLI checks pass** in Chromium 153.0.8010.12. All twelve cases,
  exact before/after results, failures, changed paths, filters, empty search, and
  the exact review download are checked. Inspected desktop/mobile screenshots
  show the retry delay changing from `"5"` to `"6"` without page overflow.

The initial broad Python checks found that new singleton annotations were not
accepted by the shared formatter, and native-only example discovery omitted both
this example and the earlier lookup example. Formatter projection now preserves
native annotations without enabling them in Python execution. Both examples are
explicitly assigned to their Rust test suites. The historical language-choice
fixture remains unchanged; its current native test expectations account for the
new finite contracts. Earlier unsupported-form captures remain historical.

## Artifacts and reproduction

- `tests-1.85.log`, `tests-1.96.log`, and corresponding Clippy logs.
- `python-tests.log`, `formatter-examples-tests.log`, and `verification.json`.
- `package/`: source/binary artifacts, dependency/engine identities, host outputs,
  relocation evidence, and selected previous-engine migration.
- `packaged/`: all 144 observations, five-scenario validation, inspection, twelve
  frozen cases, corpus, exact review JSON/HTML, commands, and qualification.
- `browser-check.js`, `browser-result.json`, actual downloaded review, and two
  inspected screenshots. Browser checks are synthetic, with no participants.

Repeat package qualification with `evaluations/native_packaging/qualify.py` and
an explicitly selected previous engine/case. Then run:

```sh
python evaluations/native_language/qualify_finite.py \
  --native /path/to/installed/bin/gwt-native \
  --output /tmp/gwt-finite-evidence
```

For browser checks, serve this checkpoint on loopback port 8903 and run the saved
Playwright CLI harness with its config. Adjust the absolute output path before
moving it, and retain separate result paths for a new run.

The new engine identity is
`sha256:79444fc4a87f366006de4d4be90ac3bf3fb81a8789bea9e01071e0a2adb8d42b`.
The prior browser/WASM checkpoint remains qualification of its recorded engine;
this turn does not claim WebAssembly coverage for the new finite forms. No hosted
CI, production deployment, external pilot, or human-understanding benefit is
claimed. Language version transition and remaining design/adoption work stay open.
