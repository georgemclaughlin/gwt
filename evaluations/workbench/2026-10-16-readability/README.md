# Prioritize failures in comparison review — 2026-10-16

The Python workbench now shows baseline/candidate errors immediately after the
selected case summary. Capture identities and evidence hashes live in a native
HTML disclosure after the supporting evidence. All identities remain available
with a click or keyboard activation; the focused summary has a visible outline.

This addresses the measured issue in the
[previous browser checkpoint](../2026-10-16-adaptations/README.md).
The renderer change is in [workbench.py](../../../gwtlang/workbench.py).

`render.py` reconstructs typed comparison objects from three retained dossiers
and calls the real production renderer. It checks original HTML/report hashes,
comparison round trips, and equality of the entire embedded dossier before and
after rendering. It does not replay language behavior. The historical originals
remain unchanged, and no review decisions are created.

**310 Playwright CLI checks pass**, covering 34 recorded cases: eight unchanged
feature-flag cases in the summary, sixteen contact comparisons, and ten
subscription comparisons. All 26 changed-case panels preserve their exact
errors, predicates, source locations, and identity values. Enter opens each
identity disclosure, Space closes it, and keyboard focus remains visible.
Classification counts, filters, search, and the initially collapsed path queue
also pass. Pages make no external requests and emit no browser script errors.

The separate layout check measures the first incompatible contact case and first
path-only subscription case, aligning the selected panel with the viewport top.
At **390×844**, the results are:

| Measurement | Previous layout | Updated layout |
| --- | ---: | ---: |
| First contact error, pixels from panel top | 1,332.03 | 183.31 |
| Entire first contact error visible without scrolling | No | Yes |
| First contact predicate, pixels from panel top | 742.75 | 640.75 |
| First subscription predicate, pixels from panel top | 742.75 | 491.75 |

The 251-pixel hash block no longer precedes the domain evidence. Expanded
identities and collapsed panels have no horizontal document overflow at either
390×844 or 1440×1100. These measurements establish presentation behavior, not
participant comprehension, error detection, or review-time improvement.

Twelve screenshots were inspected. Representative views:

| Workflow | Desktop | Mobile | Expanded identities |
| --- | --- | --- | --- |
| Feature flags | [Summary](feature_flags/desktop.png) | [Summary](feature_flags/mobile.png) | No changed cases |
| Contact normalization | [Rejection](input_normalization/selected-desktop.png) | [Rejection](input_normalization/selected-mobile.png) | [Hashes](input_normalization/identities-mobile.png) |
| Subscription | [Predicates](subscription/selected-desktop.png) | [Predicates](subscription/selected-mobile.png) | [Hashes](subscription/identities-mobile.png) |

`browser-result.json` contains the 310 checks; `layout-result.json` contains the
four desktop/mobile measurements. Both are Playwright CLI envelopes whose
`result` field is JSON text. The final checks ran sequentially in one isolated
Chromium 153.0.8010.12 session via Playwright CLI 0.1.13. An initial harness lacked
the identity fields in its expectation manifest; reconstruction now supplies the
full comparison rows. An overlapping measurement run was discarded and both
checks were repeated sequentially.

The eight existing workbench renderer/interaction tests pass:

```sh
python -m unittest tests.test_workbench tests.test_workbench_interactions
git diff --check
```

To regenerate the reports and serve them in a separate terminal:

```sh
python evaluations/workbench/2026-10-16-readability/render.py
python -m http.server 8899 --bind 127.0.0.1 --directory evaluations/workbench/2026-10-16-readability
```

Run the browser commands sequentially, waiting for each to finish:

```sh
playwright-cli -s=gwt-readability open http://127.0.0.1:8899/input_normalization/review.html --config evaluations/workbench/2026-10-16-readability/browser-config.json
playwright-cli -s=gwt-readability run-code --filename evaluations/workbench/2026-10-16-readability/browser-check.js --json
playwright-cli -s=gwt-readability run-code --filename evaluations/workbench/2026-10-16-readability/measure-layout.js --json
playwright-cli -s=gwt-readability close
```

The browser configuration and screenshot destinations use this workspace's local
paths. Check the returned `isError` field as well as the process exit status.
Stop the loopback server afterward. Language/runtime and Rust sources are
unchanged by this checkpoint; their full suites were not repeated. Actual human
evidence and live native model comparison remain outstanding, and external
pilots remain deferred.
