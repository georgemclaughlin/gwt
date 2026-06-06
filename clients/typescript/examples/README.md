# TypeScript Examples

`vendor-onboarding.ts` shows a TypeScript host application calling the GWT
vendor onboarding workflow through `@gwtlang/client`. It checks the GWT rules
file, builds a typed `GwtRequest`, uses a generated `GwtRequestName`, and prints
a typed decision summary from the generated `GwtOutput` contract.

The example imports generated declarations from
`vendor-onboarding.generated.d.ts`. Refresh them when
`examples/vendor_onboarding/rules.gwt` changes:

```sh
python -m gwtlang types examples/vendor_onboarding/rules.gwt \
  --language typescript \
  --output clients/typescript/examples/vendor-onboarding.generated.d.ts
```

Type-check the example with local temporary development dependencies:

```sh
cd clients/typescript
npm install --no-save --package-lock=false typescript @types/node
npx tsc \
  --noEmit \
  --strict \
  --module NodeNext \
  --moduleResolution NodeNext \
  --types node \
  examples/vendor-onboarding.ts
```

Run it with a TypeScript runner such as `tsx`:

```sh
cd clients/typescript
npx --yes --package tsx tsx examples/vendor-onboarding.ts
```
