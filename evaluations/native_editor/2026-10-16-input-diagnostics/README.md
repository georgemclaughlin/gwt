# Host-input diagnostic checkpoint

Contract failures now identify the expected GWT type and the supplied JSON kind,
while retaining nested field and zero-based item locations. Missing values name
the required type. Decimal mismatches explain exact input encoding. One-of
failures distinguish missing/nontext discriminators and unknown tags; the latter
list allowed tags. Untrusted field/tag names are escaped and bounded. See the
[host contract documentation](../../../docs/native-embedding.md).

No input coercion, acceptance rule, diagnostic code, source span, or first-error
ordering changed. The shared normalizer also performs internal value checks.
Message text changes, so recorded failures can have different full observations.

## Boundary evidence

The [actual old/new comparison](boundary-final/qualification.json) uses 15
independently expected nested record/list/optional/one-of inputs:

- Three valid inputs retain exact normalized output and execution observations.
- Eleven invalid inputs change only the diagnostic message; all other observation
  fields, including codes, spans, state, events, and prints, remain identical.
- One malformed-decimal failure is fully unchanged.
- Every original case remains byte-identical. Every migration candidate replays
  exactly. Eleven migrations report `observation_changed`, four report
  `observation_preserved`, and all proposals remain unapproved.

The [runner](../qualify_input_diagnostics.py) retains inputs, old/current cases,
migration proposals, candidate cases, and commands. An initial fixture used an
invalid TYPE block; the failed run remains in `boundary/`. The corrected RECORD
fixture and all completed assertions are in `boundary-final/`.

[Invoice comparison](invoice-comparison.json) separately covers 18 observations
from the earlier packaged engine: 13 are fully unchanged and five differ only
in diagnostic wording. These comparisons do not prove universal compatibility.

## Implementation and packaging verification

- [Rust checks](rust-checks.json): **343 tests** and warning-free Clippy on
  **1.85.0** and **1.96.0**, in development mode. Five new groups cover expected
  and actual types, exact decimal rules, missing inputs, nested indices, optional
  values, no execution on rejected input, kind errors, and bounded Unicode names
  and structural descriptions.
- [Python](python-tests.log): **627 tests passed**. [Reference checks](reference-checks.json):
  **71 examples** pass formatting, top-level examples check, and order/tour
  workflows execute successfully. JavaScript syntax and five unit tests pass;
  Rust formatting and diff checks pass. See [final checks](final-checks.json).
- [Static musl release package](package-1.96.0/qualification.json), Rust 1.96.0:
  three packaged library tests, two embedded scenarios, 18 independent Rust
  host observations, 288 concurrent calls, 18 relocated replays, and 18 extracted
  standalone binary replays pass. All [52 archived source/build inputs](package-source-verification.json)
  match the current tree. The prior successful case migrates with full
  observation preservation.
- [Installed VS Code 1.137.0](editor-installed/extension-host.json): all **33
  existing checks** pass against that packaged executable. This is regression
  coverage; no new editor behavior is claimed here.
- [Alpine and GLIBC 2.36 containers](static-runtime/qualification.json) pass the
  invoice execution, two scenarios, and all 18 package case replays with empty
  PATH, no network, and read-only filesystems. They share the host kernel and
  do not establish arbitrary-platform or production qualification.

## Reproduce

```sh
cargo test --test input_diagnostics --locked
python evaluations/native_editor/qualify_input_diagnostics.py \
  --native /path/to/new/gwt-native \
  --previous-engine /path/to/previous/gwt-native \
  --output /tmp/gwt-input-diagnostics
```

Use a fresh output directory and explicitly retained prior executable. The
[source hashes](source-hashes.json) bind this checkpoint's implementation and docs.
The packaged source and binary identities are retained in its qualification.

The full project goal remains active. More diagnostic/tooling work, language and
production decisions, and comparative human evidence remain open. No outside
pilot, human-benefit claim, approval, or publication occurred.
