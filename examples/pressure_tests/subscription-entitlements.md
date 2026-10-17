# Subscription entitlement behavior

[`subscription_entitlements.gwt`](subscription_entitlements.gwt) is a synthetic
workflow for deciding feature access from plan, invoices, seats, and overrides.
It runs under both the Python toolchain and the experimental native profile.
It is not a production subscription policy or an external pilot.

The first matching override controls whether account blockers are bypassed.
If it is active, access is allowed and its reason is retained. Otherwise,
past-due invoice status takes priority over excessive seats, then unknown feature,
then plan eligibility. Later duplicate overrides are ignored, even if active.
Invoice age does not substitute for status. Equal seat usage and limit is allowed.

The standalone question `has past due invoice in invoices` returns a boolean
using an explicit first-match and missing branch. The decision retains this fact
even when an override allows access. The top-level behavior resets reusable
decision state before recomputing it.

From the repository root:

```sh
python -m gwtlang validate examples/pressure_tests/subscription_entitlements.gwt
cargo +1.96.0 run --locked -p gwt-core --bin gwt -- validate examples/pressure_tests/subscription_entitlements.gwt
```

Both commands pass thirteen scenario executions, including invoice order,
duplicate overrides, seat equality, and decision reuse. The
[design and migration note](../../docs/native-existence-decisions.md) explains
the deliberate replacement of `exists`, the narrower plan-helper contract,
independent input checks, and remaining limits. Native numeric outputs use
decimal strings; these commands do not establish complete cross-engine equivalence.
