# GWT release checklist

Status: development cutover; public publication is pending. GWT retains its name
and MIT license. One Rust engine owns the `gwt` executable. Package version,
language version, and artifact schema versions are separate decisions.

## Product qualification

- [ ] Freeze the intended source revision and deliberately select release versions.
- [ ] Run Rust conformance on the minimum/current toolchains and dev/release profiles.
- [ ] Qualify GNU and static musl x86-64 Linux bundles and record actual runtime
  compatibility. Qualify additional platforms before advertising support.
- [ ] Verify package contents, dependency locks, source identity, checksums,
  standalone execution without Python/Rust, installation, upgrade, and removal.
- [ ] Verify old Python PATH collisions fail explicitly in editor/host integration.
- [ ] Run the active example catalog, standalone download, review, and installed editor.
- [ ] Regenerate site assets from the qualified engine; verify links and desktop/mobile UI.
- [ ] Review semantic changes, artifact migration paths, unsupported historical
  capabilities, and retained evidence; preserve immutable originals.
- [ ] Record support and security boundaries. Resource limits are not an OS sandbox.

## Evidence and owner decisions

Human sessions remain pending and external pilots deferred by owner choice.
They are not completed by tests, model comparisons, or this cutover. Preserve the
external-pilot requirements from the [historical milestone checklist](release-v0.4-checklist.md)
unless the owner explicitly revises the release scope. The
[project goal](project-goal.md) still requires demonstrated human-review value.

## Publication (separate authorization)

- [ ] Review the candidate and unresolved evidence requirements with the owner.
- [ ] Obtain explicit authorization for versions, channels, release scope, and publication.
- [ ] Build matching artifacts from the frozen source, with checksums and provenance.
- [ ] Publish only to the authorized channels; verify downloaded artifacts and
  clean install/upgrade/uninstall from those channels.
- [ ] Deploy the matching site and examples and verify the public links.

The distribution workflow prepares downloadable CI artifacts only. It does not
create a tag, GitHub Release, registry upload, or automatic website deployment.
