# Native support-contract qualification — 2026-10-16

The [support and transition contract](../../../docs/native-language-transition.md)
consolidates native language scope, explicit omissions, host/source/artifact
migration responsibilities, and remaining versioned-release work. No runtime,
language version, package version, default engine, or publication changed.

The audit found stale finite-contract refusals in the Python language-choice
runner and stale unsupported-feature statements in the semantic guide. The
runner now reads an explicit, hashed expectation overlay. The original thirty
source probes and historical observations remain unchanged. Overrides can only
change native expectations, not probe source or host inputs.

Both actual executables were rerun against the same thirty probes:

| Engine | Accepted | Successful runs | Deliberate runtime failures |
| --- | --- | --- | --- |
| Previous `f5b1f33b…` | 17 | 15 | 2 |
| Current `79444fc4…` | 18 | 16 | 2 |

The boolean-union probe is now accepted and executes successfully. The numeric
union probe now reaches argument checking and refuses its out-of-domain value
with `argument_type`; the earlier engine refused the type itself. The remaining
acceptance, success/failure, diagnostic codes, state, result, and captured output
are unchanged. Source paths in diagnostic/evidence payloads are temporary and
are not claimed byte-identical. Full observations and binary hashes are retained
in the two result directories. Python checks 28 probes and executes 26
successfully in each run; those observations are not the native oracle.

`current-choice-expectations.json` in the parent directory is the runner's
default. `historical-expectations.json` here selects the original fixture
expectations for the previous engine. These expectations are deliberately
selected, not inferred from whichever output the tested engine produces.

Reproduce from the repository root, using fresh output directories:

```sh
python -m evaluations.native_language.qualify_choices \
  --native /home/g/.cache/gwt-qualifications/finite-literals-79444fc4/gwt-native \
  --output /tmp/gwt-current-language-choices
python -m evaluations.native_language.qualify_choices \
  --native /home/g/.cache/gwt-qualifications/gwt-package-host-fc2qk7m9/installed/bin/gwt-native \
  --expectations evaluations/native_language/2026-10-16-transition/historical-expectations.json \
  --output /tmp/gwt-previous-language-choices
cargo +1.96.0 test --locked -p gwt-core --test language_choices
git diff --check
```

The focused Rust language-choice test passes. Invalid overrides naming an
unknown probe or attempting to replace source are refused before creating output.
All 60 current engine-source inputs match the prior qualified manifest. This
turn changed documentation and evaluation tooling; it did not rerun the full
runtime suites or establish general migration equivalence, human benefit, or
production readiness. Human sessions and external pilots remain pending.
