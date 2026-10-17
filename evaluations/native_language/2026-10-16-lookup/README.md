# Explicit lookup contracts — 2026-10-16

The [stock lookup example](../../../examples/native_lookup/README.md) distinguishes
snapshot/absence, retained selection, and mutation of a found inventory item.
The native profile deliberately keeps `FIND … ELSE` rather than adding the
Python lowercase optional lookup statement. This is a documented choice within
the experimental profile, not a new release or an automatic source migrator.

## Evidence

- Seven native scenarios pass, including duplicate first-match handling, missing
  items, empty inventory, an absent prior selection, and a preview that leaves
  stock unchanged.
- 150 independently expected requests pass through both the Rust API tests and
  the existing packaged CLI. The matrix spans five list shapes, three lookup
  keys, four proposed counts, and absent/present previous selections. Rust tests
  also reject negative readings before inventory mutation and require presence
  proof before optional field assignment.
- Three new Rust test groups bring the full suite to **421 passing tests** on
  Rust **1.85.0 and 1.96.0**. Clippy passes with warnings denied on both; formatting
  passes. No engine source changed: the previously packaged executable and all
  59 tracked engine build inputs remain unchanged.
- Nine frozen cases replay and compare against the candidate. The baseline is a
  **deliberately faulty copy rewrite**, where recording edits `LET selected be
  item` instead of the matched inventory item. It is not a historical production
  program or an approved prior policy. Correcting it changes exactly three
  outcomes: first match, later match, and first duplicate. Six other outcomes
  remain, including the expected negative-count failure. All cases have changed
  source/evidence, no case is unavailable, and none has a baseline mismatch.
- **65 Playwright CLI checks pass** in Chromium 153.0.8010.12. Every baseline and
  candidate result, completion status, error code, and changed field path matches
  the report. Filters, empty search, and exact review download pass. Desktop
  1440×1100 and mobile 390×844 have no horizontal document overflow. Both
  [desktop](desktop.png) and [mobile](mobile.png) screenshots were inspected.

The initial browser harness selected the replay envelope instead of its `actual`
execution; the final check uses the correct baseline object. No reviewer choices
were saved, and all nine cases remain pending. Functional browser checks do not
measure human comprehension or review effort.

## Retained artifacts

- [Independent request matrix](packaged/independent-probes.json),
  [validation](packaged/validation.json), and [inspection](packaged/inspection.json).
- [Comparison JSON](packaged/review.json), [offline review](packaged/review.html),
  [case selection](packaged/selection.json), and nine full captures in `packaged/`.
- [CLI qualification](packaged/qualification.json), complete command records,
  both toolchains' test/Clippy logs, and `rust-checks.json`.
- `browser-check.js`, `browser-result.json`, and `downloaded-review.json`.
- `verification.json` binds final files, engine identities, and checks.

The unchanged packaged executable has SHA-256
`f3c425ef4ff8d00a73f0e92121d61d25a8220febd0820057120bfd4eb2ab298a` and engine source
digest `sha256:f5b1f33b4ce11bd6721ab3fd2546e3827e193fcb6928736a2d97e9fa530dfd1c`.

## Reproduce

Use a new output directory and an explicitly selected native executable:

```sh
python evaluations/native_language/qualify_lookup.py --native /absolute/path/to/gwt-native --output /tmp/gwt-lookup-evidence
cargo test --locked --test lookup_contracts
python -m gwtlang format examples/native_lookup/rules.gwt --check
```

For the retained browser check, serve this checkpoint on loopback in another
terminal, then run the CLI commands sequentially:

```sh
python -m http.server 8900 --bind 127.0.0.1 --directory evaluations/native_language/2026-10-16-lookup
```

```sh
playwright-cli -s=gwt-lookup open http://127.0.0.1:8900/packaged/review.html --config evaluations/native_language/2026-10-16-lookup/browser-config.json
playwright-cli -s=gwt-lookup run-code --filename evaluations/native_language/2026-10-16-lookup/browser-check.js --json
playwright-cli -s=gwt-lookup close
```

The browser configuration and screenshot paths refer to this workspace. Check
the CLI's `isError` field, not only its exit status; `result` is JSON text. Stop
the loopback server after the check.

## Limits

The recipes do not preserve arbitrary aliases across later list changes. A
second key lookup requires justified uniqueness/order assumptions to select the
same item. Numeric/singleton literal types, indexed access, broader dynamic-data
needs, and a deliberate version transition remain unresolved. The absence recipe
uses typed optional-field omission; no new bare-null expression was added.
Production deployment, live model comparison, and actual representative human
evidence remain open. External pilots remain deferred.
