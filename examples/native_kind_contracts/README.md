# Helpers with kind-specific contracts

The evaluator handles literals, addition, and comparisons. Its comparison helper
accepts a `Comparison`, an explicitly selected kind of `Expression`, so its call
can remain `compare sum expression into result`. The contract makes all five
payload fields available inside the helper.

```gwt
TYPE Comparison is Expression of kind comparison

WHEN compare sum <expression> into <result>
  GIVEN expression is Comparison
  AND result is Result
```

The dispatcher proves the kind through `DEPENDING ON` before calling the helper.
A caller with an unrefined `Expression` cannot pass it as a `Comparison`. Typed
setup can create an `Addition` directly, retaining its explicit `kind` field.

From the repository root after building the native executable:

```sh
target/debug/gwt validate examples/native_kind_contracts/rules.gwt
target/debug/gwt test examples/native_kind_contracts/rules.gwt
```

Five scenarios contain ten expectations: a negative literal, addition, and
comparison below, at, and above the threshold. The source is native-profile GWT;
Python's formatter preserves these annotations, but Python execution does not
implement kind selectors. See [kind contracts](../../docs/native-one-of.md).
