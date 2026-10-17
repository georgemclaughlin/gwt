# Browser qualification of retained adaptation reviews — 2026-10-16

Playwright CLI checks now cover four reports whose original checkpoints left
interactive browser validation pending. The copied HTML and comparison JSON are
byte-identical to the retained originals; `manifest.json` records their paths,
hashes, classifications, and expected rendered values. This checks historical
artifacts. It does not rerun their engines or regenerate their approvals.

**173 browser checks pass** in Playwright CLI 0.1.13 with isolated Chromium
153.0.8010.12. The reports represent **40 cases**: 32 changed cases have selectable
detail panels, and eight unchanged feature-flag cases appear in the summary.

| Workflow | Retained comparison | Browser evidence |
| --- | --- | --- |
| Underwriting | Six native outcome changes; four successful scalar-ratio baselines and two recurring-division failures become successful exact-ratio results | Every exact before/after result and changed path matches the report; candidate results also match the independent retained expectations. Failures stay visible, operand links reveal evidence, and the downloaded JSON matches exactly |
| Feature flags | Eight unchanged Python comparisons | All classification totals match and the unchanged summary is visible without inventing changed-case panels |
| Contact input normalization | Ten incompatible inputs, one changed failure, five path-only changes | Every selected case, exact error message, evaluated predicate, truth value, and source location matches the comparison; category filters and empty-search handling work |
| Subscription entitlements | Ten Python path-only changes with preserved output | The path queue starts collapsed; every case can be selected and its predicates/source locations match; filtering and search retain the intended distinctions |

All four pages have no horizontal document overflow at desktop 1440×1100 and
mobile 390×844. They emit no browser script errors or external page requests.
Eight screenshots were visually inspected:

| Workflow | Desktop | Mobile |
| --- | --- | --- |
| Underwriting | [Desktop](underwriting/desktop.png) | [Mobile](underwriting/mobile.png) |
| Feature flags | [Desktop](feature_flags/desktop.png) | [Mobile](feature_flags/mobile.png) |
| Contact normalization | [Desktop](input_normalization/desktop.png) | [Mobile](input_normalization/mobile.png) |
| Subscription | [Desktop](subscription/desktop.png) | [Mobile](subscription/mobile.png) |

The screenshots also expose a remaining presentation issue. On a 390×844 viewport,
the Python comparison's expanded identity hashes occupy **251 pixels**; the first
predicate starts about **743 pixels** below the selected panel's top. In the
selected incompatible contact case, the actual rejection message starts about
**1,332 pixels** below it. `layout-result.json` retains those DOM measurements.
An appropriate next change is to make identity details expandable and put failure
messages before lower-priority evidence. Functional correctness and lack of
overflow do not establish readable prioritization or human comprehension benefit.

`browser-check.js` contains the interaction checks, `browser-result.json` the final
CLI result, and `measure-layout.js` the separate layout measurements. Two initial
harness errors are retained: object-key order was incorrectly treated as a result
difference, and an operand test selected an intentionally hidden low-level event.
The corrected checks compare JSON structurally and follow an operand from a visible
event. An initial passing run preceded improved screenshot positioning; the final
run also passes all 173 checks.

The reports preserve their original formats. In particular, the underwriting HTML
is native review schema 1; this visual qualification does not add the complete
capture identity required by [current native decisions](../../../docs/native-review-decisions.md).
No choices were accepted or saved during this rehearsal. The historical approval
contract is not promoted into the current one.

To repeat the UI check, serve this checkpoint on loopback in one terminal:

```sh
python -m http.server 8898 --bind 127.0.0.1 --directory evaluations/workbench/2026-10-16-adaptations
```

Then run:

```sh
playwright-cli -s=gwt-adaptation-reviews open http://127.0.0.1:8898/subscription/review.html --config evaluations/workbench/2026-10-16-adaptations/browser-config.json
playwright-cli -s=gwt-adaptation-reviews run-code --filename evaluations/workbench/2026-10-16-adaptations/browser-check.js --json
playwright-cli -s=gwt-adaptation-reviews close
```

The retained configuration selects the installed local Chromium executable; the
check script uses this workspace's absolute artifact paths. Stop the local server
after the check. Source/runtime/editor code is unchanged, so the prior full suites
were not repeated. `verification.json` records checks and file identities. Actual
human evidence and live native model comparison remain outstanding, and external
pilots remain deferred.
