# Collection authorization after branch-specific checks

This synthetic policy authorizes a collection using a receipt reference. Counter
collection requires the staff check; locker collection requires the locker check.
Either route requires a receipt with a nonempty reference. A check for the other
route does not substitute for the required one. Gift messages are not receipts.

Each branch establishes receipt presence and kind, then the behavior reads the
reference after the decision. [Native branch proofs](../../docs/native-branch-proofs.md)
make that access valid without repeating the checks. The request returns
`{"reference":"R-2"}` for the supplied host input. Failed requests report an
assertion failure; callers must not use an unsuccessful request's output.

```sh
cargo run --locked -p gwt-core --bin gwt-native -- validate examples/native_branch_proofs/rules.gwt
cargo run --locked -p gwt-core --bin gwt-native -- run examples/native_branch_proofs/rules.gwt --request 'authorize collection' --input examples/native_branch_proofs/request.json
python -m gwtlang format examples/native_branch_proofs/rules.gwt --check
```

Seven scenario executions cover both successful routes, wrong-route checks,
missing proof, the wrong proof kind, and an empty reference. Rust tests compare
all 32 combinations of mode/checks/proof against independent expected outcomes,
replay saved cases, generate checked regression scenarios, and detect a candidate
that removes the locker check. This example targets the experimental native
semantics; it is not a production authorization integration or user study.
