# Native language draft and review walkthrough qualification

The consolidated draft describes existing native behavior; it assigns no language
version and changes no runtime. The delivery candidate extends the low-fee band
from 1,000g to 1,500g, with 14 passing scenarios. Nine explicitly specified host
inputs produce exactly two outcome changes and one preserved zero-weight
rejection. Every baseline replays and compares. All nine choices remain pending;
there are zero human participants and no external pilot.

`summary.json` records source/executable hashes and exact review totals.
`pending-assessment.json` records zero accepted and nine pending decisions;
`assess-review` correctly exits 1. `browser.json` records Playwright CLI checks of
case selection, filtering, outcome/source evidence, operand navigation, preserved
failure, pending-decision download, and desktop/mobile layout. The two screenshots
were visually inspected. No browser console errors or warnings were reported.

The native helper, inputs and expectations are versioned under
`examples/native_review_walkthrough`. Run its documented command into a new output
directory to recreate the full HTML, frozen cases and comparison. The original
full generation is local at `/tmp/gwt-delivery-review-final`; retained hashes
identify it but do not make that temporary directory permanent. The browser was
served the byte-identical first successful generation from `/tmp/gwt-delivery-review`.
`check_browser.js` contains the interaction checks passed to Playwright CLI;
its download/screenshot destinations are local temporary files.

CI now executes the complete walkthrough on the current Rust development build.
The Python example inventory explicitly classifies the candidate as native-only
because Python does not implement `THEN fails with`; all example formatting is
still checked. Existing Python/native language defaults and historical evidence
remain separate. Human benefit and language-release commitments remain open.

Final validation: all 678 Python tests pass; the candidate and finite-contract
example pass native validation; candidate layout passes both formatters. Local
documentation links/anchors and staged whitespace checks pass. Downloaded pending
choices also re-assess as nine pending with exit status 1.
