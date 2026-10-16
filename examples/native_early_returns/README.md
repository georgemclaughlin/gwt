# Assess an exchange with early-return guards

This illustrative policy returns the first applicable reason: exchanges disabled,
missing proof, gift route, unverified receipt, invalid negative age, or outside
the 30-day window. A verified receipt aged 0 through 30 days is eligible. Disabled
exchanges take precedence over proof details; verification precedes age checks.
The host supplies facts and handles any actual exchange.

After the missing-proof guard returns, the remaining steps know proof is present.
After the non-receipt guard returns, they can read receipt fields directly.
The behavior returns text, and the named request exposes that result as decision.

```sh
cargo run -p gwt-core --bin gwt-native -- validate examples/native_early_returns/rules.gwt
cargo run -p gwt-core --bin gwt-native -- run examples/native_early_returns/rules.gwt --request "assess exchange" --input examples/native_early_returns/request.json
```

The sample returns `{"decision":"eligible"}`. Eight embedded scenarios check the
precedence and boundaries. Twenty independent inputs capture/replay and generate
runnable scenarios. Changing `> 30` to `>= 30` changes exactly the verified,
allowed, 30-day case in that corpus.

The [qualification checkpoint](../../evaluations/native_editor/2026-10-16-early-returns/README.md)
retains an equivalent older nested-ELSE rule. Twenty actual previous-engine
observations migrate unchanged, then compare against the guard-clause version
with identical decisions/state and changed execution evidence. No human approval
or comprehension benefit is inferred from that equivalence.

Python formatting accepts this source, but validation rejects its native
request-level LET form. Native execution is explicitly registered in the example
suite. See [early-return semantics](../../docs/native-early-returns.md) for common
facts, mutation protection, local scopes, and compatibility changes.
