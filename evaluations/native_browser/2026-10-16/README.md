# Browser execution qualification — 2026-10-16

The same frozen rules, facts, and limits produce equal complete native and browser
executions for all 97 retained requests on both builds. The
[invoice preview](../../../examples/native_browser_host/README.md) demonstrates a
concrete local what-if use. This establishes feasibility, not production readiness
or improved human comprehension.

## Evidence

`browser-result.json` records 210 passing Playwright CLI checks in Chromium
153.0.8010.12. Its `result` field contains structured JSON as text. There are 194
execution/engine equality checks: 97 requests per build. Equality includes all
state, diagnostics, evidence, source identities, and exact numbers.

`cases.json` contains sixteen packaged invoice requests, 71 portfolio requests,
nine intentionally faulty lookup captures, and one new two-module invoice capture.
The lookup cases preserve recorded faulty behavior for cross-target comparison;
they do not approve it. Scenario captures are excluded because the bridge exposes
requests. `origins.json` hashes the source captures; `imported/` retains the new
fixture and capture.

The harness loads assets, then sets the browser context offline for all execution,
host-control, and UI checks. Both actual WebAssembly modules report zero host
imports. Controls cover cancellation before/during a request, a one-millisecond
deadline, excessive input/budget, malformed JSON, invalid WebAssembly, and eight
concurrent isolated requests after failures. The deadline check proves termination
of that run, not worst-case latency under arbitrary browser scheduling.

The UI preserves quantity `9007199254740993` and exact total
`108086391056891.916`; malformed input stays an error. The final ordinary invoice
has total `36.9`. Inspected screenshots at 1440×1000 and 390×1000 show the controls,
outcome, and evidence disclosure without horizontal page overflow. These are
synthetic checks, with no participants.

## Builds and identities

Both builds use the extracted core from the review-identity package qualification:
engine `sha256:f5b1f33b4ce11bd6721ab3fd2546e3827e193fcb6928736a2d97e9fa530dfd1c`.
All 59 engine source inputs remain unchanged. Bridge registry dependencies match
the core baseline including checksums. Both toolchains pass the ABI unit test,
Clippy with warnings denied, and locked offline release compilation.

| Rust | WASM bytes | SHA-256 |
| --- | ---: | --- |
| 1.96.0 | 1,098,382 | `b86cda6e7401e2066b6be2cf7710c10d62fdf03224ecf61c697f83e6448a94e5` |
| 1.85.0 | 1,171,538 | `6882d84a0ae198830e3a5fb88d9ed72f02db5cf6e8ef1f42ad64f5db0a3cb83c` |

Version-prefixed metadata/logs retain commands and selected paths. Unprefixed files
identify Rust 1.96.0. `verification.json` records source and integrity checks. Core
identity excludes this host bridge: retain binary and host-source hashes too.
Cross-machine reproducible compilation is not established. The unchanged core's
previous 421-test suite is not counted as a new run here.

## Repeat and limitations

Use the example build procedure for both toolchains. Serve this directory on
loopback port 8902, open its index with Playwright CLI and `browser-config.json`,
then run `browser-check.js` using `run-code --filename`. Adjust its absolute
screenshot paths when moving the checkpoint. Inspect returned JSON for failures
even if the CLI exits successfully. Copy the checkpoint first to retain separate
results; the harness overwrites its screenshots.

The first harness completed both corpus comparisons and controls, then incorrectly
read collapsed evidence with `innerText`. The corrected check uses `textContent`
and separately asserts the visible total. The final result is a complete rerun;
no application fix was needed for that issue. The console log records a local
favicon 404.

Other browsers/targets, production policy and memory/load qualification, a more
usable facts editor/evidence presentation, and human review remain open. This
experiment provides no offline reload, browser scenario execution, deployment, or
external pilot. These checks are local; no hosted CI result is claimed.

Run `python evaluations/native_browser/2026-10-16/verify.py` from the repository
to recheck source hashes, captured origins, corpus equality, browser-result
coverage, and selected build inputs. This integrity check requires the recorded
local build directories; it does not rerun browser execution.
