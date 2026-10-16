# Current engine across three browser engines — 2026-10-16

The finite-contract engine reproduces complete native observations in the recorded
Chromium, Firefox, and WebKit builds, using both Rust WebAssembly builds. Every
GWT request runs after Playwright sets the browser context offline. The first
request does not depend on a previous online GWT execution.

| Browser engine | Version | Checks | Full execution comparisons |
| --- | --- | ---: | ---: |
| Chromium | 153.0.8010.12 | 542 | 526 |
| Firefox | 151.0 | 542 | 526 |
| WebKit | 26.4 | 542 | 526 |
| Total | | 1,626 | 1,578 |

Each browser compares the same 263 requests on each compiler build. Equality
covers engine identity and the entire execution, including exact values, state,
failures, source identity, steps, and evidence. This is not just final-output
matching. The [browser host](../../../examples/native_browser_host/README.md)
remains an experimental local invoice what-if preview.

## Cases and engine transition

`corpus/` contains 97 retained observations from the original browser checkpoint,
144 independently expected receipt requests, and 22 extra exact-value and boundary
requests. The additional cases include integers beyond JavaScript precision,
decimals differing after 27 places, negative/equivalent decimal spellings,
singleton/full booleans, and invalid representations.

For every earlier observation, `prepare_finite.py` explicitly supplies the trusted
previous executable to native `migrate`. All 97 previous replays verify and all
97 complete observations are unchanged under the new engine. The proposals are
retained with `approved: false`; no corpus or review approval is promoted. Current
receipt observations are recaptured and compared with the separately qualified
144-request native matrix. The 22 additional cases have explicit expected results
or boundary errors. All captures preserve original source and limits.

## Offline preparation fix

The initial Chromium and Firefox runs passed. WebKit failed on its first offline
worker. A separate probe reproduced this for fresh classic and module blob workers:
loads before offline succeeded, and subsequently reused URLs worked offline.
The loaded WebAssembly engine itself worked. Raw diagnostics and the failing
harness result are retained under `webkit/`; this observation is scoped to the
recorded WebKit/Playwright combination.

`createPreview` now loads a worker and waits for a readiness message before
returning its host. This preparation worker receives no request or WebAssembly
bytes and is terminated immediately. Preparation errors revoke the blob URL;
a ten-second preparation deadline prevents an indefinitely pending worker load.
Each actual run still creates a new worker/instance and ignores the readiness
message until its execution response arrives. Thus the UI reports Ready only
when the adapter has loaded, without executing any rules online.

The final full run passes on all three engines after this change. Checks also
cover pre/in-flight cancellation, execution deadline, excessive input/budget,
invalid WebAssembly, malformed JSON, eight isolated concurrent runs, the exact
large-integer invoice total, a malformed-input UI response, and ordinary invoice
execution. Six screenshots were inspected at 1440×1000 and 390×1000; the results
and controls fit with no horizontal page overflow.

## Artifacts and runtime scope

Both toolchains pass the bridge ABI test, Clippy with warnings denied, and locked
offline WebAssembly release builds. All 60 core source inputs remain equal to the
finite-contract native checkpoint. The engine is
`sha256:79444fc4a87f366006de4d4be90ac3bf3fb81a8789bea9e01071e0a2adb8d42b`.

| Rust | WASM bytes | SHA-256 |
| --- | ---: | --- |
| 1.96.0 | 1,116,981 | `17dc282695cd1cfb27ed095e5a6698c0217537ac804959c3901097032ecc174d` |
| 1.85.0 | 1,184,420 | `91d173fddb3a7bda3f55a3422f139ac5405f8232948edd4f08883ce3fe57e8e8` |

Version-prefixed metadata and logs identify the selected source artifact and build
commands. The final host assets are copied from the example after the preparation
fix; the bridge and core binaries do not change for that JavaScript fix.
`verification.json` binds the final assets, sources, corpus, evidence, and binaries.
The verifier also reads the actual WASM memory section to check the 64-MiB maximum.

Chromium and Firefox run on the host. WebKit's direct host launch lacks
`libicudata.so.74`. Its successful run uses the already available Linux image
`sha256:59fe35832a79d1324e778b737760b2afc11cffcbaeba325012f96cabae832a75`.
The CLI runs inside that container so WebKit's inspector pipes stay local. An
initial wrapper attempting to forward the browser process through Docker closed
before creating a page; that launch log remains separate from the successful run.
The Node executable is copied from a pinned local image recorded in
`webkit/node-runtime.json`; no image was pulled. The container has a 1-GiB memory
limit, which is a qualification configuration, not a bound on other browser hosts.

`webkit/prepared-run.log` is the raw CLI transcript; `webkit/browser-result.json`
extracts its JSON result. Chromium and Firefox retain their direct CLI results.
Each harness and runtime config is retained. `webkit-cold-workers.js` and
`webkit-diagnose.js` retain the isolation probes. The failed first corpus-preparation
attempt compared a prefixed executable digest with a bare hash; the corrected
preparation reran the whole corpus and is the final evidence.

## Repeat

Build each toolchain using the example's `build.py` and an explicitly selected
core package. Prepare a new corpus:

```sh
python evaluations/native_browser/prepare_finite.py \
  --native /path/to/current/gwt-native \
  --previous-native /path/to/previous/gwt-native \
  --output evaluations/native_browser/new-checkpoint/corpus
```

The helper intentionally uses the retained source checkpoints as its input. Serve
this checkpoint on loopback port 8904 and run its browser-specific Playwright CLI
harnesses. For a new checkpoint, adjust their absolute output directories. The
WebKit container command and mounts are in `webkit-run-command.json`; paths and
image identities are explicit local inputs. Inspect CLI JSON for failure even
when the process exits successfully. `verify.py` rechecks retained artifacts;
it does not rerun browser execution.

These are local Linux engine checks, including responsive viewport layouts.
They do not qualify Safari, iOS/Android devices, older browsers, arbitrary OSes,
physical connectivity transitions, production hosting/CSP, offline reload, or
adversarial resource loads. No participants, business effects, external pilots,
production deployment, or hosted CI results are claimed. Human-review benefit
remains unproven.
