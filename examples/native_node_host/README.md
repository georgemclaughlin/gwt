# Call native GWT from Node

This reference adapter runs the standalone Rust engine from a Node application.
It needs Node 22+ and an explicitly selected `gwt` executable, with no npm
dependencies. It is separate from the existing Python-backed TypeScript client.
The [local qualification](../../evaluations/native_packaging/2026-10-16-node-host/README.md)
covers Node 22.22.2 and the packaged static Linux x86_64 engine.

Run the invoice example from the repository root:

```sh
node examples/native_node_host/quote.mjs /absolute/path/to/gwt
```

It uses the packaged crate's invoice fixture and supplies a quantity larger than
JavaScript's safe integer range. The expected result is:

```json
{"decision":{"status":"priced","total":"108086391056891.916"}}
```

The reusable boundary is in [native.mjs](native.mjs):

```js
import { runNativeRequest, parseExact } from './native.mjs';

const input = parseExact(receivedJsonText);
const { execution, stdout } = await runNativeRequest({
  executable: '/opt/gwt/bin/gwt',
  program: '/srv/rules/invoice.gwt',
  request: 'price invoice',
  input,
  timeoutMs: 10000,
  limits: {
    execution: { steps: 10000, evidenceBytes: 262144, textBytes: 1048576 },
    callDepth: 64,
  },
});

if (!execution.ok) {
  // Present the diagnostic and evidence; do not apply a successful decision.
  showFailure(execution.diagnostic);
} else {
  applyDecision(execution.result.decision);
}
// Keep stdout verbatim when retaining the complete returned observation.
```

`showFailure` and `applyDecision` are application-owned functions. The adapter
does not implement persistence, networking, or policy decisions. Compilation and
execution happen in a new process on every call. Source files are read afresh;
deploy immutable rule files and check `execution.programIdentity` when source
identity matters. This is not the compile-once Rust library boundary.

## Exact data

Use strings for decimals and `bigint` for integers outside the safe Number range.
`parseExact` uses the JSON reviver's original token text to preserve large
integers; safe integers remain Numbers. It rejects fractional/exponent numeric
tokens rather than coercing them into decimal strings or rounded integers.
The token access is specified by
[ECMAScript JSON parsing](https://tc39.es/ecma262/multipage/structured-data.html#sec-json.parse).

`stringifyExact` serializes bigint as integer tokens, including values in nested
state and evidence. It rejects unsafe/fractional Numbers, undefined values,
sparse arrays, cycles, and non-plain objects such as Date. It permits at most
100 nested containers. Use it when serializing parsed observations containing
bigint; ordinary `JSON.stringify` cannot serialize those values. Quoted decimal
values remain strings throughout.

An already rounded value cannot be recovered. Start with the raw JSON text or
exact host values, rather than parsing with ordinary `JSON.parse` first. The
adapter cannot detect every precision loss that occurred upstream.

## Failures and operating limits

An ordinary native execution failure returns `execution.ok === false`, its
diagnostic, available state/evidence, and exit code 1. This includes input-contract,
behavior requirement, and native execution-budget failures. Check `ok` before
using results; successful child-process invocation alone is insufficient.

`NativeHostError` is thrown for failures outside that execution envelope:

| `kind` | Meaning |
| --- | --- |
| `command` | A structured native diagnostic before request execution, such as a compile error |
| `process` | Missing executable, timeout, signal termination, unexpected exit, or excessive output |
| `protocol` | Invalid/nonexact JSON, unsupported schema, mismatched request/status, or no execution envelope |

The error retains stdout/stderr and, where available, the parsed payload and
process cause. Native stderr-only command failures fall into `protocol` because
there is no structured execution outcome. Do not turn these errors into a
business approval or denial. The envelope checks are a compatibility guard for
a trusted executable, not authentication or a complete JSON Schema validator.

The adapter uses Node's
[`execFile`](https://github.com/nodejs/node/blob/main/doc/api/child_process.md#child_processexecfilefile-args-options-callback)
without a shell. Each invocation gets a private temporary directory and input
files, removed after completion or failure. The input file is limited to 1 MiB;
stdout/stderr each have an 8 MiB default cap. The wall-clock timeout defaults to
ten seconds and kills the child with SIGKILL. These are host transport limits,
separate from the native `limits` object. Set positive `timeoutMs` and
`maxOutputBytes` explicitly when the workload requires different values.
`timeoutMs` cannot exceed Node's 2,147,483,647-millisecond timer range.

`temporaryRoot` selects a writable parent directory; it defaults to Node's system
temporary directory. `importRoot` supplies the native import boundary. File and
executable paths are arguments, including spaces and shell metacharacters.

This example does not provide a persistent worker pool, an HTTP service, browser
execution, a general subprocess sandbox, or production deployment qualification.
Cancellation of process trees and other operating systems require their own
integration work. The trusted native engine does not spawn child processes.

## Verify

```sh
GWT_NATIVE_PATH=/absolute/path/to/gwt node --test tests/native_node_host.test.mjs
```

The tests cover exact results and full observation equality with direct CLI runs,
contract/behavior/resource failures, twelve concurrent calls, a copied standalone
Node host with an empty PATH, timeouts, excessive output, invalid responses, and
temporary-file cleanup. CI runs them against each newly qualified package in the
existing Rust/toolchain/target matrix. Local execution is recorded; a hosted CI
run is not claimed.
