# Rust product cutover qualification

This checkpoint covers the single-engine product transition, not a public release
or human-benefit result. The installed command is `gwt`. The old Python runtime
and distribution are retired, with an immutable reference and file hashes in
[the inventory](../../docs/retirement-inventory.json).

The product qualification checks installed identity, 28 curated entry programs,
regenerated site assets, a downloaded example outside the repository, nine
captured cases (two changed outcomes and one preserved failure), execution with
no toolchain on PATH, installation/upgrade/removal, and refusal to overwrite an
old Python executable. Editor/Node integration verifies identity before execution.

Reproduce using the [contributor commands](../../docs/contributing.md) and
`python tools/verify_product.py --gwt PATH_TO_INSTALLED_GWT`.
The adjacent summaries record completed checks and their exact engine identities.
Source-tree and Cargo-normalized package manifests produce distinct engine
identities; each distribution must ship a review/download generated with its
own engine. The distribution workflow performs that generation and verification.

Dated historical artifacts remain unchanged. Reviewer choices remain pending;
no human session, external pilot, merge, tag, registry upload, or site deployment
is claimed by this checkpoint.

The standalone ZIP uses stored entries with fixed metadata. Python 3.11 and
3.14 produce byte-identical assets; the product verifier compares complete
artifact hashes. This avoids differences from host zlib compression versions.
