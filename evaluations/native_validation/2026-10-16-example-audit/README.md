# Native checked-in example audit — 2026-10-16

`current/audit.json` is the final fresh audit against the packaged failure-exit
engine. `current/sources.json` freezes all 75 `.gwt` source files. Each validation
retains its phase results, scenario outcomes, source identity, and diagnostics.
Six files following the existing paired Python `request*.gwt` convention are
identified with their rules and are not misclassified by running them standalone.

| Current outcome | Files |
| --- | ---: |
| Native validation passed | 46 |
| Static checking failed | 20 |
| Checked modules with no entry scenarios | 2 |
| Checked entry with failing scenarios | 1 |
| Python paired input files, not independently executed | 6 |

The native entry/module validations execute 228 scenarios: 225 pass and three
fail. All three failures belong to loan underwriting and report
`nonterminating_decimal`. They are execution failures, not unexercised modules.
`checkout/rules.gwt` and `minilang_spec/engine.gwt` are the two declaration
modules without entry scenarios; separate checked-in entries exercise them.

Static first-blocker diagnostics are: twelve missing parameter contracts,
three assignments from unrestricted text into closed reason fields, two legacy
lowercase lookup steps, one incompatible shared kind argument, one legacy
one-of setup form, and one bare domain word interpreted as an unknown binding.
Counts are files, not independent language defects: imported dependencies can
block several entries, and a first diagnostic can hide further adaptation work.
Inventory and MiniLang already have separate passing native scenario entries.

The audit selected the feature-flag contract/literal adaptation as the next
concrete change. Root `audit.json`/`sources.json` freeze the before state: 45
passing entries and four closed-reason assignment refusals. `after.json` reuses
the 74 unchanged file results and rechecks the adapted feature-flag file; the
final `current/` directory reruns every applicable entry. The corrected before/
after summaries distinguish failed scenario gates from empty suites. Initial
terminal summaries had grouped the underwriting gate incorrectly because its
diagnostics live on individual scenario results; no raw result was discarded.

This audit establishes current checked-in example coverage, not full language
conformance, Python equivalence, production readiness, or human benefit. Files
under `examples/external_pilots/` are local fixtures; running them is not an
external pilot or contact with a maintainer. The owner's deferral remains intact.

Reproduce from the repository root into a new directory:

```sh
python -m evaluations.native_validation.audit_examples --native /path/to/gwt-native --output /path/to/new-example-audit
```
