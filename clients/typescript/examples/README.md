# TypeScript Examples

`vendor-onboarding.ts` shows a TypeScript host application calling the GWT
vendor onboarding workflow through `@gwtlang/client`. It builds a typed request,
runs the default named request through `createGwtProgram`, and prints a typed
decision summary from the generated `GwtOutputs` contract.

The example imports generated declarations from
`vendor-onboarding.generated.d.ts`. Refresh them when
`examples/vendor_onboarding/rules.gwt` changes:

```sh
python -m gwtlang types examples/vendor_onboarding/rules.gwt \
  --language typescript \
  --output clients/typescript/examples/vendor-onboarding.generated.d.ts
```

Type-check the example and package declarations:

```sh
cd clients/typescript
npm run typecheck
```

Run it with a TypeScript runner such as `tsx`:

```sh
cd clients/typescript
npx --yes --package tsx tsx examples/vendor-onboarding.ts
```
