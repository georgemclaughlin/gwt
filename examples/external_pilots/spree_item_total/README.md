# Spree item-total promotion: local pilot zero

This is a small, independent evaluation of GWT against the item-total
promotion rule in [`spree/spree`](https://github.com/spree/spree). It does not
modify or integrate with Spree, and nobody from the project was contacted.
The inspected revision is
`249dbf3c68461288f8444d754bcf27d0fa962250` (2026-07-14). Exact source and
BSD 3-Clause attribution are in [UPSTREAM-LICENCE.md](UPSTREAM-LICENCE.md).

The boundary is intentionally narrow:

```text
Spree order item total + rule preferences -> eligibility + ordered error codes
```

`rules.gwt` models the strict and inclusive minimum/maximum behavior, an absent
`optional<decimal>` maximum, and the upstream class's maximum-error-first
ordering when both limits fail. Seven embedded scenarios make the boundary
cases executable.

`ruby_oracle.rb` loads the actual pinned upstream class in Ruby and supplies
minimal stubs for `PromotionRule`, `Spree::Order`, money formatting, and the
error collection. `run_pilot.py` sends the same ten cases to that class and to
GWT. The result is:

```text
exact Ruby/GWT parity: 10/10
upstream: spree/spree@249dbf3c68461288f8444d754bcf27d0fa962250
```

The slice covers totals below, equal to, inside, and above the configured
range; all four operator combinations at their important boundaries; an absent
maximum; a fractional interior value; and contradictory bounds that produce
two errors.

## Run it

From the GWT repository root:

```sh
python -m gwtlang format examples/external_pilots/spree_item_total/rules.gwt --check
python -m gwtlang check examples/external_pilots/spree_item_total/rules.gwt
python -m gwtlang test examples/external_pilots/spree_item_total/rules.gwt
python -m gwtlang run examples/external_pilots/spree_item_total/rules.gwt \
  --json-input examples/external_pilots/spree_item_total/request.json \
  --request "assess item total eligibility" --json
python examples/external_pilots/spree_item_total/run_pilot.py /path/to/pinned/spree
```

The last command requires Docker and rejects a checkout at any other commit.
The checked-in oracle slice lets ordinary tests preserve the verified outputs
without Docker or a Spree checkout.

## What fit well

- This is an excellent scale for a first external shadow: two numeric bounds,
  two operator choices, and one optional preference are easy to inspect.
- GWT's exact `decimal` values map cleanly to Spree's `BigDecimal` comparisons;
  the JSON boundary keeps them as strings rather than passing through binary
  floating point.
- GWT scenarios make `>`, `>=`, `<`, and `<=` equality behavior much harder to
  skim past than nested RSpec contexts.
- The explicit behavior signature reads in domain terms, and evidence identifies
  which limit failed without introducing query-like syntax.
- Modeling the first error and error count exposed a subtle but real behavior:
  Spree adds the maximum error before the minimum error when both fail.

## What did not fit cleanly

- Missing and JSON `null` intentionally collapse to one GWT absence. That fits
  Spree's `nil` maximum here, but would be insufficient for a domain where
  omitted and explicitly cleared values mean different things.
- The upstream public errors include localized, currency-formatted messages.
  The pilot compares the internal translation keys and ordering, not translated
  prose or `Spree::Money` formatting.
- Spree treats any unrecognized minimum operator like `gt` and any unrecognized
  maximum operator like `lt` in this method, while GWT's literal unions reject
  unknown operators at the boundary. That stricter contract is useful, but it
  is not identical behavior for invalid preference data.
- Loading the actual class still requires framework stubs. The pilot verifies
  its comparison and error-order logic, not Active Record preference storage,
  validation, localization, or a complete promotion lifecycle.

## Take

This pilot is more convincing than a large policy port as a first integration
shape. The adapter is tiny, the parity claim is exact and reviewable, and the
boundary tests say something specific. GWT adds the most value as a shadow
explanation and regression artifact here, not as a proposed replacement.

The optional-value spike materially improved this pilot: `amount_max` now has
the shape of the upstream preference, and its use is guarded explicitly before
comparison. The remaining product question is whether localized messages
belong inside or outside GWT—not whether the language needs broader control
flow.
