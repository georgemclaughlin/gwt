# Review a receipt with closed protocol values

This illustrative local protocol accepts receipt codes 10 (complete), 20 (retry),
and 30 (manual review), retry factors 0.5, 1, and 2, and a confirmation flag that
must be true. A retry waits ten minutes multiplied by the exact factor. Other
codes complete without delay or go to manual review without delay. These codes
are example policy, not a claim about an external protocol.

The input contract rejects unknown codes/factors and false confirmation before
execution. The three exhaustive branches name the resulting domain action.
Confirmation is only a declared input value; the host remains responsible for
where it came from. GWT performs no network operation, retry scheduling, or other
effect.

```sh
cargo run -p gwt-core --bin gwt -- check examples/native_finite_codes/rules.gwt
cargo run -p gwt-core --bin gwt -- test examples/native_finite_codes/rules.gwt
cargo run -p gwt-core --bin gwt -- run examples/native_finite_codes/rules.gwt --request 'review receipt' --input examples/native_finite_codes/request.json
```

The supplied request returns action `retry` and exact decimal delay `"5"`.
Five embedded scenarios cover every code and each retry factor. The Rust tests
also check 144 independently expected inputs, malformed representations, and a
fault changing the retry multiplier from ten to twelve.

See [finite contracts](../../docs/native-finite-literals.md) for assignment,
arithmetic, exact-number encoding, and compatibility rules. This is native-only
syntax; use the native formatter and validator. Closed numeric codes provide a
boundary contract, not evidence that numeric vocabulary is easier for humans to
understand than named domain states.
