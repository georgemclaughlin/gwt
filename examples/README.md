# GWT examples

Start with the [delivery policy](native_delivery/rules.gwt) and
[review walkthrough](../docs/native-review-walkthrough.md). The website's
[standalone example](../docs/downloads/delivery-example.zip) includes two policy
revisions, input, captured cases, and engine information.

The [active catalog](catalog.json) lists entry programs validated by the Rust
engine in product qualification and CI. It covers delivery, refunds through
focused review fixtures, inventory, contracts, arithmetic, decisions, expected
failures, and larger adapted programs. Run an entry with `gwt validate FILE`.

- [Typed requests and delivery decisions](native_delivery/README.md)
- [Ordered inventory reservation](native_reservation/README.md)
- [Named calculations and return values](native_return_values/README.md)
- [Node integration](native_node_host/README.md)
- [Browser/WebAssembly integration](native_browser_host/README.md)

Other sources in this directory are historical comparison fixtures retained by
conformance/evaluation tests. They are not an additional supported language or
runtime. Python host wrappers and service demonstrations have been retired;
[the upgrade guide](../docs/python-retirement.md) identifies the complete old tree.
