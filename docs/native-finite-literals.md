# Closed scalar contracts

The experimental native profile supports named finite domains of integers,
exact decimals, booleans, and text. A contract rejects other values before a
request executes and lets `DEPENDING ON` check coverage of every allowed value.
This differs from an integer followed by `REQUIRE`: that assertion checks only
an executed step and does not supply a finite static contract.

```gwt
TYPE ReceiptCode is 10 | 20 | 30
TYPE RetryFactor is 0.5 | 1.0 | 2.0
TYPE Confirmed is true
```

The [receipt example](../examples/native_finite_codes/README.md) translates a
small protocol's codes into readable domain decisions. The codes are illustrative,
not an external standard. Use named text states where the domain has no reason
to use numeric codes. A singleton boolean constrains the supplied fact; it does
not establish the truth or authenticity of an external attestation.

## Meaning and representation

A literal contract contains one or more alternatives of a single category:
text, booleans, or numbers. Mixing text, booleans, and numbers is rejected.
Arithmetic expressions and references are not type alternatives. Parentheses
around an alternative in a union are accepted as literal grouping, as in value
dispatch; they do not permit computed alternatives. Prefer the canonical examples
above. Singleton declarations use the unparenthesized literal form.

An all-integer declaration has an integer base. Including a decimal spelling
selects the decimal base for the entire domain. Thus `1 | 2` is an integer domain,
while `1 | 2.0` is decimal. Decimal equality is exact: `1 | 1.0`, `0 | -0.00`, and
`0.5 | 0.50` repeat values and are rejected. Source order does not affect the type.
A declaration of both `true` and `false` resolves to ordinary `boolean`;
`true` or `false` alone is a singleton contract. Booleans never equal numbers.

Integer domains accept JSON integer tokens, including values beyond machine and
JavaScript integer precision. Decimal domains accept quoted exact base-10 text
or JSON integer tokens and return canonical decimal strings. Fractional JSON
number tokens remain rejected; decimal source literals remain available in GWT.
Existing numeric digit, input, expression, and evidence limits apply. An integer
contract still requires an integer representation: decimal `1.0` is an equal
dispatch label but is not an integer assignment or JSON input token.

Named aliases, record fields, lists, optionals, behavior parameters and return
contracts, request inputs, and outputs may use these domains. In a `GIVEN` setup,
`GIVEN count is 1` still initializes an ordinary integer. Use a named type to
express an input contract; the new forms do not reinterpret setup values as types.

## Assignments and calculations

An allowed source literal, including a negative numeric literal of the appropriate base, can be assigned
to a finite contract. A copied value whose finite contract is a subset may flow
into a wider finite domain or its ordinary scalar base. Integer domains can also
flow into compatible decimal domains. Mutable arguments still require matching
contracts: passing a bare integer path to a finite parameter is unsafe even if
its current value happens to be allowed. Parenthesized copies are checked values;
copying a plain integer does not by itself prove membership in a finite domain.

Arithmetic and boolean operations use ordinary scalar results. Neither constant
folding nor equality/presence guards infer finite membership. To return a code
from a broad input, select explicit allowed literals in checked branches. A result
such as `1 + 1` is an integer expression, not proof of a `1 | 2` contract.
Negation widens a finite numeric operand to its base before calculating.

`add`, `subtract`, `count`, and `sum` require unrestricted numeric destinations;
`divide` continues to require an ordinary decimal destination. These operations
cannot promise their result remains in a finite set. Reading finite values in
calculations or sums is supported. `set`, typed list construction, and `append`
retain the declared finite contract. Runtime normalization also checks writes.
Existing copied-record and shared-alias rules remain in force.

## Exhaustive decisions and evidence

A finite scalar subject can omit `ELSE` only when every possible value has a
branch. A singleton needs one branch. Impossible labels, duplicates with equal
numeric value, missing coverage, and `ELSE` after complete coverage are errors.
A partial decision can use a final `ELSE`. Branch labels use exact native equality,
so integer and decimal spellings of the same number select the same value.

As with existing scalar dispatch, selection does not narrow a mutable path's
contract. The subject is evaluated once; the engine records comparisons and their
source spans before executing the selected body. Ordinary budget failures and
source-linked explanations are retained. No implicit fallback invents a result
when an external code is outside the declared vocabulary.

Inspection serializes `integer_union` and `decimal_union` values as canonical
numeric strings, preserving precision; `boolean_union` contains its single JSON
boolean. Existing text unions retain their representation. Consumers must handle
these additional experimental type variants. Generated scenarios reconstruct the
numeric base, including `.0` when a decimal alternative has an integral value.
Editor hover renders these contracts and preserves definition locations.

## Compatibility and qualification

This extends the experimental Rust profile and changes its engine identity. It
does not revise Python v0.2 or claim that old captures replay under a different
engine. The original language-choice captures remain historical evidence. The
old numeric probe now rejects its mismatched mutable argument, while the full
boolean-union probe checks and runs successfully.

[Qualification](../evaluations/native_language/2026-10-16-finite/README.md) covers
independent request outcomes, static refusals, exact arithmetic, input boundaries,
alias safety, nested contracts, inspection/editor evidence, capture/replay,
revision detection, and generated scenarios. Tests establish these semantics;
actual reviewer comprehension and a deliberate language-version transition remain
outstanding.
