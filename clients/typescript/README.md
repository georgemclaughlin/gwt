# @gwtlang/client

Node/TypeScript client for running GWT programs through the GWT CLI.

This package is intentionally small. It wraps the process runner protocol:

```sh
gwt run rules.gwt --json-input - --request "review vendor" --json
```

The client writes a JSON request object to stdin and parses the stable GWT JSON
execution envelope from stdout.

The package source lives in this repository. Before a public npm release, use
the example from the repo or depend on it with a local `file:` dependency from a
host application.

## Usage

```ts
import { GwtClient } from "@gwtlang/client";

const client = new GwtClient("rules.gwt");

const check = await client.check();
if (!check.ok) {
  throw new Error(JSON.stringify(check.diagnostics));
}

const result = await client.runJson(
  { vendor },
  { request: "review vendor" },
);

console.log(result.result.decision);
```

During local repository development, use the Python module runner:

```ts
const client = new GwtClient({
  file: "examples/vendor_onboarding/rules.gwt",
  command: "python",
  commandArgs: ["-m", "gwtlang"],
  cwd: "/path/to/gwt",
});
```

Generate TypeScript declarations from the GWT contracts with:

```sh
gwt types rules.gwt --language typescript --output rules.d.ts
```

The generated file includes record interfaces, one-of record unions,
per-request input/output interfaces, `GwtRequestName`, `GwtRequest`, and
`GwtOutput` declarations that can be imported by host application code.

Use those generated types as client generics:

```ts
import { GwtClient } from "@gwtlang/client";
import type { GwtOutput, GwtRequest, GwtRequestName } from "./rules.js";

const input: GwtRequest = { vendor };
const request: GwtRequestName = "review vendor";
const client = new GwtClient("rules.gwt");
const execution = await client.runJson<GwtRequest, GwtOutput>(input, {
  request,
});

console.log(execution.result.decision.status);
```

With NodeNext-style ESM, import the generated `rules.d.ts` declarations through
the runtime-style `./rules.js` specifier.

See [`examples/vendor-onboarding.ts`](examples/vendor-onboarding.ts) for a
complete typed host example that runs the repository's vendor onboarding
workflow.

## Test Fixtures

For TypeScript test suites, `createGwtSpec` wraps the same client with a cached
`check()` and an optional default request. It is test-framework agnostic, so it
can be used from Vitest, Mocha, or Node's built-in test runner:

```ts
import { beforeAll, expect, it } from "vitest";
import { createGwtSpec } from "@gwtlang/client";
import type { GwtOutput, GwtRequest, GwtRequestName } from "./rules.js";

const rules = createGwtSpec<
  GwtRequest,
  GwtOutput,
  Record<string, unknown>,
  GwtRequestName
>({
  file: "rules.gwt",
  request: "review vendor",
  importRoots: ["rules"],
  allowAbsoluteImports: false,
});

beforeAll(() => rules.checkOnce());

it("reviews a vendor request", async () => {
  const input: GwtRequest = { vendor };
  const execution = await rules.runJson(input);

  expect(execution.result.decision.status).toBe("approved");
});

it("keeps embedded GWT scenarios passing", async () => {
  const execution = await rules.test();

  expect(execution.scenario_count).toBeGreaterThan(0);
});
```

Use `importRoots` and `allowAbsoluteImports: false` in local tests when they
should mirror CI import confinement.

## API

- `new GwtClient(fileOrOptions)`
- `client.check()`
- `client.test()`
- `client.runJson<TInput, TResult>(input, { request })`
- `client.runRequest(requestFile)`
- `createGwtSpec<TInput, TResult>(fileOrOptions)`
- `spec.checkOnce()`
- `spec.runJson(input)`
- `spec.test()`
- `checkFile(file, options)`
- `runFile<TInput, TResult>(file, options)`

Failures from the GWT process are raised as `GwtClientError` with `exitCode`,
`stdout`, and `stderr` fields.
