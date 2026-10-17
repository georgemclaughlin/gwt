# Review a contact with kind-dependent conditions

Missing contact data needs review. Unconfirmed email also needs review; confirmed
email is ready. SMS is ready only with consent, otherwise it is blocked. Pickup
is ready only when pickup is enabled. A non-ready decision keeps its destination
empty. This example chooses a route; delivery, address validation, and external
effects belong to the host. Empty destination text is accepted by this policy.

`DECIDE` first handles absence, then combines each kind with its policy flags.
Later conditions and the final fallback retain the kinds left by earlier tests.
The source stays in the domain vocabulary while the checker proves payload
access safe.

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt -- validate examples/native_kind_conditions/rules.gwt
cargo run --locked -p gwt-core --bin gwt -- run examples/native_kind_conditions/rules.gwt --request "review contact" --input examples/native_kind_conditions/request.json
gwt format examples/native_kind_conditions/rules.gwt --check
```

The request returns `ready`, channel `email`, and destination
`orders@example.test`. Seven embedded scenarios have 21 top-level expectations.
Independent tests cover 22 combinations of contact data and pickup permission;
reversing SMS consent changes eight outcomes. This example runs in the Rust
engine. Python's formatter/checker accept it, but its runtime currently rejects
the nested optional record path.

See [kind conditions](../../docs/native-kind-conditions.md) for supported proof
forms, alias protection, copied/shared helper arguments, and current limits.
