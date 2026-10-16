# Reimbursement review with optional evidence

The policy requires a nonnegative amount and, when supplied, a nonnegative
limit. Missing policy or receipt data goes to review; an unverified receipt or
an over-limit amount is denied; otherwise the amount is payable. Missing policy
has priority over a missing receipt. A receipt reference is copied when present,
including an empty reference string.

`DECIDE` handles missing records before reading their fields. Later conditions
can rely on those earlier absence checks having failed. The final `IF` proves
both the receipt and its optional reference present before copying the text.

From the repository root:

```sh
cargo run --locked -p gwt-core --bin gwt-native -- validate examples/native_presence/rules.gwt
cargo run --locked -p gwt-core --bin gwt-native -- run examples/native_presence/rules.gwt --request "review reimbursement" --input examples/native_presence/request.json
python -m gwtlang format examples/native_presence/rules.gwt --check
```

The request returns an approved decision with reason `within_limit`, payable
amount `100`, and reference `R-1`. Six embedded scenarios have 18 top-level
expectations. Native tests independently cover 80 valid combinations, omitted
versus explicit null inputs, and two invalid inputs. Changing `>` to `>=`
incorrectly denies nine exact-limit cases in that probe set.

See [native presence semantics](../../docs/native-presence.md) for scoped proofs,
alias protection, and boundaries. Python formatting and checking accept this
source, but Python execution currently rejects the nested optional record path;
this example's executable evidence comes from the Rust engine.
