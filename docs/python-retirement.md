# Upgrading to the Rust GWT product

The Rust engine now installs **`gwt`** and is the only active GWT implementation.
The earlier Python runtime, Python package entry point, server/client distribution,
and editor debugger/LSP integration are retired from this branch. There is no
engine picker or automatic fallback.

## Existing installations

A previously installed Python wheel can still own `gwt` on your PATH. Repository
changes do not uninstall it. Run `gwt version --json`: the Rust executable reports
`kind: "gwt.native-version"` and `packageName: "gwt-core"`; the old wheel reports
`packageName: "gwtlang"`.

Uninstall `gwtlang` with the Python environment that installed it, or explicitly
select the new executable. The editor uses `gwt.command`; previous explicit
`gwt.native.command`, import-root, and limits settings are honored as migration
inputs. Obsolete Python engine/server settings produce an explanation. Editor
and Node host operations check identity before executing GWT source.

The local binary-bundle installer refuses to overwrite an unrelated executable.
It can upgrade an existing Rust GWT installation and remove that installation.
See [installation](installation.html) for source and bundle paths. Public release
publication remains pending.

## Programs and artifacts

Use the [current language reference](spec/native-draft.md) and
[semantic migration guidance](native-language-transition.md). Shared `.gwt`
syntax is not a guarantee of equivalence. Exact arithmetic, typed boundaries,
aliasing, failure phases, and deliberately omitted forms need review against
independent policy expectations.

Python HTTP serving, OpenAPI/type generation, debugging, and Python artifact
formats are historical capabilities, not implicit promises of the Rust engine.
Retained source fixtures outside the [active example catalog](../examples/catalog.json)
exist for comparison and conformance tests, not as supported onboarding paths.

Historical artifact identifiers and files have not been renamed. Native engine
updates use explicit replay and migration with the previous engine. Native
migration does not import Python evidence or inherit a previous human approval.

## Reproduce the previous implementation

The complete pre-retirement tree is commit
`4f403dc51eda5382c6a12c0757cb26deac34012a` (use the full authoritative reference in
[retirement-inventory.json](retirement-inventory.json)). Its dated evaluations
remain preserved. To reproduce a historical experiment, create a separate
checkout of that exact commit, follow its own instructions, and use an isolated
Python environment. Do not install its `gwt` command into the new product's environment.

The inventory records every retired file and its SHA-256. It distinguishes
retirement from preserved source fixtures. Current Rust conformance tests retain
independent expected outcomes. Research comparing GWT with ordinary Python code
still uses Python fixtures; those are not a second GWT runtime.
