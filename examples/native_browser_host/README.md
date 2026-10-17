# Local browser preview

This experiment runs the Rust GWT engine in a Web Worker through WebAssembly.
The concrete use is an invoice what-if preview: change facts, see the exact total,
and inspect execution evidence from the saved rules. Execution needs no network
connection after assets load. Offline reload is unsupported; there is no service
worker or installed application cache.

The bridge compiles a frozen `SourceBundle` and calls `run_request` in the existing
core. It adds no evaluator or language semantics. The invoice fixture comes from
the selected core package and includes executable scenarios. The UI keeps integer
input tokens intact and displays decimal results as text.

## Build and try

Use Python 3.11+, Rust 1.96.0 (or qualified minimum 1.85.0), its WebAssembly target,
and cached locked Cargo dependencies. Select an extracted
[core source package](../../docs/native-embedding.md) and a new output directory:

```sh
rustup target add wasm32-unknown-unknown --toolchain 1.96.0
python examples/native_browser_host/build.py \
  --core /path/to/extracted/gwt-core-0.1.0 \
  --output /tmp/gwt-browser-preview \
  --toolchain 1.96.0
python -m http.server 8902 --bind 127.0.0.1 --directory /tmp/gwt-browser-preview
```

Open `http://127.0.0.1:8902/`. The build runs bridge tests and Clippy, checks the
registry dependency baseline, and records commands, logs, compiler selection, and
binary hash. Cargo runs offline; obtain dependencies first if needed. The loaded
page requires no Python or Rust runtime. This remains an unpublished experiment.

## Host contract

`createPreview(wasmBytes)` in `preview.mjs` loads the worker adapter and waits for
its readiness message before returning a host. This preparation runs no GWT rules
or WebAssembly, has a ten-second deadline, and terminates its worker. Call
`host.run(requestJsonText, {timeoutMs, signal})`; it returns raw JSON text.
Call `host.dispose()` when finished. Each run creates and terminates a fresh
worker and instance. Disposal prevents new calls; use the AbortSignal to cancel
an active call. There is no shared compiled-program cache.

The request has `bundle`, `request`, `input`, and `limits` fields. Successful
compilation returns `gwt.browser-preview`, schema version 1, engine identity, and
the complete native `execution`. Inspect `execution.ok`: domain failures retain
diagnostics, state, and evidence. Invalid JSON, compilation errors, and excessive
limits return `gwt.browser-error`. Worker failures, WebAssembly traps,
cancellation, and deadlines reject the JavaScript promise.

Preserve raw JSON or parse integers exactly. Ordinary JavaScript `JSON.parse`
can round large integers. The UI uses the tested browser's JSON reviver source
context; older-browser compatibility is unqualified.

## Bounds and scope

- Request text, including source and facts, is capped at 2 MiB.
- Native limits may be lowered, including to zero, but cannot exceed 100,000
  steps, 1 MiB evidence, 1 MiB text, and call depth 64.
- Builds cap WebAssembly linear memory at 64 MiB. Allocation failure may trap;
  it is a host failure, not a domain decision.
- Output is capped at 8 MiB after serialization. This does not bound intermediate
  allocations or total browser-process memory.
- The default deadline is ten seconds. Completion, errors, cancellation, and
  deadlines terminate the worker. Browser scheduling can delay timers; this is
  not a hard real-time guarantee or a concurrency admission limit.

Imports must be supplied in the source bundle; the bridge does not call filesystem
compilation. Rust documents the restricted host facilities of
[wasm32-unknown-unknown](https://doc.rust-lang.org/rustc/platform-support/wasm32-unknown-unknown.html).
The qualified modules have no WebAssembly host imports. The surrounding page
still has ordinary browser capabilities; this is not an adversarial page sandbox.

[Qualification](../../evaluations/native_browser/2026-10-16-finite/README.md) covers
Chromium 153.0.8010.12, Firefox 151.0, and Linux WebKit 26.4, both Rust toolchains,
263 requests per build/browser, complete execution equality, first execution
after going offline, controls, and desktop/mobile layout. Safari, mobile devices,
older versions, other operating systems,
production hosting/CSP, accessibility studies, throughput, scenarios through this
ABI, and actual human comprehension remain unqualified. No business effects are
performed; a client-controlled preview is not an authoritative production decision.
