# Native grammar audit — 2026-10-16

The [native grammar](../../../docs/native-grammar.md) collects the current Rust
source forms and their contextual restrictions separately from Python v0.2.
It was checked against the layout parser, declaration/statement compiler,
scenario expansion, dispatch compiler, and expression parser. This audit changes
documentation, not the language or runtime, and introduces no released version.

The audit corrected the claim that all declarations share one namespace.
Imports contribute declarations without a module namespace, but type names,
request names, and behavior signatures have separate collision checks.

`probes.json` retains the exact source and CLI observations for 23 focused
checks: twelve accepted programs and eleven rejected programs. Accepted programs
were also executed: eleven as scenario suites and the singleton-type input as
a host request. The expected outcomes cover separate declaration namespaces,
both behavior uses of `AND`, binding a returning call, precedence and a trailing
list comma, explicit argument grouping, root-only ordinary setup, empty typed
tables versus empty scenario tables, lowercase collection filters, singleton
types versus literal setup, optional local construction, request postphase
ordering, root-only outputs, and immediate failure annotations. Rejections
include unsupported numeric forms and numeric unions. All expected acceptance
and execution outcomes matched. Sources are embedded in the report, so temporary
source paths are not needed to reproduce a probe.

Three retained validation reports cover the grammar guide's commands:

| Program | Executed scenarios | Result |
| --- | ---: | --- |
| Return values/member pricing | 4 | Passed |
| Typed setup tables | 3 | Passed |
| Scalar value dispatch | 6 | Passed |

The guide's three Cargo commands were also run directly with Rust 1.96.0.
These are focused documentation checks, not a new exhaustive conformance claim.
The engine's 56 recorded source/build inputs remain unchanged. Full Rust/Python
suites were not rerun for this documentation-only change; their last completed
[input-boundary qualification](../../input_normalization/2026-10-16/README.md)
remains separate evidence. Link/anchor and whitespace checks are recorded in
`verification.json`. No measured human benefit follows from this grammar audit.
