# Project Identity Decision For v0.4

Status: owner decision required before public v0.4 publication.

Recommendation: rename the public project before investing in a hosted brand,
while preserving GWT's source and artifact compatibility through a documented
transition. The leading working candidate is **CauSpec** (pronounced
“cause-spec”), pending owner preference and professional trademark review.

This file is a decision memo, not a rename authorization. No package, command,
file extension, schema identifier, trace namespace, marketplace listing, or
repository has been renamed by this work.

## Why `GWT` Should Not Be The Public Brand

The collision is substantive, not theoretical:

- [GWT Web Toolkit](https://www.gwtproject.org/) is an active, established
  open-source Java project and still uses GWT as its primary name.
- [Google's description](https://support.google.com/code/answer/54830?hl=en)
  likewise defines GWT as Google Web Toolkit.
- The short [`gwt` Python distribution](https://pypi.org/project/gwt/) is now
  occupied by an unrelated Git-worktree CLI.
- The [GWT Helper marketplace listing](https://marketplace.visualstudio.com/items?itemName=RhuanHianc.gwt-helper)
  is one of several editor surfaces using GWT for Google Web Toolkit.

That makes search, package installation, editor discovery, and verbal referrals
needlessly ambiguous. `gwtlang` is a workable implementation identifier during
development, but it does not resolve the public search collision.

## Working Candidate: CauSpec

Why it fits:

- it points toward source-linked causal facts and executable specification,
  without claiming formal proof or legal audit sufficiency
- it is pronounceable, short enough for a CLI, and not coupled to one domain
- it can name both the language/toolchain and the behavior-review workbench
- it avoids “rules engine,” “workflow,” and “test case” positioning

Point-in-time checks performed on 2026-07-09 found no exact-name GitHub
repository and HTTP 404 responses for the `causpec` names on the PyPI and npm
registry APIs. RDAP returned not-found responses for `causpec.dev` and
`causpec.org`. Those observations are not reservations and can change at any
time. Search results are not trademark clearance, do not cover unregistered
rights, and are not a substitute for legal review.

## Names Eliminated During Initial Search

- **Casewright**: an active local-first manual test-case editor already uses the
  name at [casewright.dev](https://casewright.dev/).
- **Specwright**: multiple active specification/agent-development projects use
  it, including the [`specwright` Python distribution](https://pypi.org/project/specwright/).
- **RunProof**: active release-safety, ecommerce, and provenance products use
  the name; it also overstates what an unsigned local case digest proves.
- **TraceSpec**: too close to an operational trace viewer and already appears
  as a technical term in verification work.
- **Thenwise**: point-in-time package checks were open, but it is phonetically
  close to the active AI company Thanwise and says less about the product.

## Migration Matrix If CauSpec Is Chosen

The migration should be compatibility-first. Historical artifacts are records,
not branding collateral.

| Surface | Current | Proposed v0.4 transition | Compatibility rule |
| --- | --- | --- | --- |
| Public project | GWT | CauSpec | Documentation redirects and a prominent “formerly GWT” window |
| Python distribution | `gwtlang` | `causpec` | Publish the new distribution; keep a pinned compatibility package or explicit migration package if ownership permits |
| Python import | `gwtlang` | `causpec` | Keep `gwtlang` import aliases for the documented deprecation window |
| CLI | `gwt` | `causpec` | Install both entry points over the same implementation during transition |
| Source extension | `.gwt` | no v0.4 change | Do not churn source files for branding; evaluate an alias only after pilots |
| VS Code extension ID | current GWT ID | CauSpec listing | Preserve language-ID aliases and provide uninstall/install instructions |
| Language ID | `gwt` | `causpec` plus `gwt` | Existing settings, launch configs, and syntax associations keep working |
| Environment variables | `GWT_*` | `CAUSPEC_*` | Read both; new name wins only when both are present and docs say so |
| Artifact kind | `gwt.execution-case` | unchanged for v1 | Never rewrite archived cases solely for branding |
| Schema IDs | `gwtlang.dev/schemas/...` | keep resolvable | New presentation URLs may redirect; stored `$id` values remain valid |
| Trace attributes | `gwt.*` | dual emit only if needed | Existing dashboards and collectors must not silently break |
| Repository/docs URLs | current GitHub repository | owner-selected rename | Preserve redirects supported by the hosting platform |

## Decision Needed

The owner should choose one of:

1. approve **CauSpec** for formal clearance and implementation of the migration
   matrix
2. provide a preferred candidate to evaluate against the same matrix
3. explicitly retain **GWT**, accepting the search, package, and marketplace
   collisions and positioning `gwtlang` as the discoverable long name

Until that choice is recorded, v0.4 artifacts should retain their current
identifiers and release automation must not publish a renamed distribution.
