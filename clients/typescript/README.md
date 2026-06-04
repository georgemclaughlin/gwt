# @gwtlang/client

Node/TypeScript client for running GWT programs through the GWT CLI.

This package is intentionally small. It wraps the process runner protocol:

```sh
gwt run rules.gwt --json-input - --entry "review vendor into decision" --json
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
  { vendor, decision },
  { entry: "review vendor into decision" },
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
`GwtRequest`, `GwtOutput`, and `GwtEntry` declarations that can be imported by
host application code.

Use those generated types as client generics:

```ts
import { GwtClient } from "@gwtlang/client";
import type { GwtEntry, GwtOutput, GwtRequest } from "./rules.js";

const input: GwtRequest = { vendor, decision };
const entry: GwtEntry = "review vendor into decision";
const client = new GwtClient("rules.gwt");
const execution = await client.runJson<GwtRequest, GwtOutput>(input, {
  entry,
});

console.log(execution.result.decision.status);
```

With NodeNext-style ESM, import the generated `rules.d.ts` declarations through
the runtime-style `./rules.js` specifier.

See [`examples/vendor-onboarding.ts`](examples/vendor-onboarding.ts) for a
complete typed host example that runs the repository's vendor onboarding
workflow.

## API

- `new GwtClient(fileOrOptions)`
- `client.check()`
- `client.runJson<TInput, TResult>(input, { entry })`
- `client.runRequest(requestFile)`
- `checkFile(file, options)`
- `runFile<TInput, TResult>(file, options)`

Failures from the GWT process are raised as `GwtClientError` with `exitCode`,
`stdout`, and `stderr` fields.
