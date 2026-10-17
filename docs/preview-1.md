# GWT Preview 1

[Preview 1](https://github.com/georgemclaughlin/gwt/releases/tag/preview-1) is a
GitHub prerelease for local evaluation of GWT's executable rules and change
review. The owner authorized this limited preview while keeping human sessions
pending and external pilots deferred. It does not satisfy the historical v0.4
milestone's pilot gates, establish human benefit, or designate a stable release.

## Scope and identities

- Release tag: `preview-1`; Rust package: `gwt-core` 0.1.0.
- Language profile: `gwt-native-experimental`; no assigned language version.
- Platforms: Linux x86-64, static musl (recommended) and GNU (glibc 2.39+).
  Both are qualified on GitHub's Ubuntu runner, not a comprehensive distro/kernel matrix.
- Channel: GitHub Releases only. No crates.io, npm, PyPI, or editor-marketplace publication.
- License: MIT. The executable is `gwt`; Python is not a runtime dependency.
- The release attaches exact binary checksums, source package, matching delivery
  example and offline review, qualification records, and a release manifest that
  identifies the source commit and successful distribution workflow.

The release binaries use the qualified Cargo source package. Cargo normalizes
its manifest, so its engine digest differs from a direct repository build.
Always use the matching example attached to the release. The website's live
review demonstrates the same policy; local contributor builds generate their own
matching captures. Package version alone does not identify a saved case's engine.

## Support and trust boundaries

This is an experimental preview without a stability guarantee, support SLA, or
production certification. No macOS, Windows, or ARM binaries are offered.
The host owns I/O, persistence, authentication, and external effects. Resource
limits bound supported execution; they do not provide an OS security sandbox.
Run untrusted rules and host integrations with appropriate process isolation.

Execution cases and exported HTML can contain input facts, state, and source.
Review them before sharing. Checksums identify bytes; the release does not claim
independent signing or authenticated audit evidence. Review decisions belong to
the exact captured comparison and must not be carried across identities silently.
Use the explicit migration workflow for old captures; do not rewrite their hashes.
The [Python retirement guide](python-retirement.md) covers earlier installations.

## Verification and use

Follow [installation](installation.html) and the [policy walkthrough](native-review-walkthrough.md).
The preview qualifies conformance on minimum/current Rust and dev/release builds,
packaged Rust and Node hosts, isolated install/upgrade/uninstall, and nine delivery
cases with two intended fee changes and one preserved rejection. Reviewer
choices remain pending. Automated walkthrough checks are not a participant study.

Future preview tags should retain their own immutable assets. Do not replace the
files attached to this tag with a different engine; publish a new preview instead.
