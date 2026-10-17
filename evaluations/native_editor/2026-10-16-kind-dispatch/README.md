# Exhaustive kind dispatch checkpoint

Native `DEPENDING ON path` now checks declared kinds, requires complete coverage
or a final `ELSE`, and exposes the selected payload inside each branch. Runtime
address guards prevent aliases or ancestor replacements from changing an active
subject's kind. Payload edits and same-kind replacements remain possible. Guards
are released on normal completion, return, and failure; completed earlier writes
are not rolled back.

## Verification

- Rust 1.85.0 and 1.96.0 each pass all 256 workspace tests (252 integration and
  four unit tests) and Clippy with warnings denied (`test-*.log`, `clippy-*.log`).
  The eleven new `tests/depending.rs` tests cover independent routing results,
  replay/explanations, malformed and nonexhaustive branches, scoped fields,
  return guarantees, nested subjects, alias/ancestor writes, copied arguments,
  collection items, caught failures, step limits, and Unicode/CRLF source evidence
  from expanded scenarios.
- All 614 Python tests pass (`python-tests.log`). The delivery example's explicit
  native kind initializer is assigned to the Rust suite; all examples retain
  Python formatter checks. All top-level Python examples, both reference request
  workflows, formatting, and whitespace pass (`final-checks.log`, `python-*.json`).
  JavaScript syntax and all five JavaScript unit tests also pass.
- Actual VS Code 1.137.0 passes 21 checks with the workspace and installed
  executables (`native/extension-host.json`, `native-packaged/extension-host.json`).
  The added check accepts unsaved exhaustive branches reading private payload
  fields, reports an unknown kind at the branch's exact source span, and clears
  the diagnostic after correction without writing the source buffer.
- Package qualification verifies independent identity/dependency checks, 18 host
  observations, 288 concurrent executions, and 18 relocated replays
  (`package-1.96.0/qualification.json`). The packaged source identity is
  `sha256:47fe818db31bfd48eb4a7f1f92ae1c2ff60aa2965c4161b2e591bf557e30f52b`.
  All 47 implementation/build inputs match the current workspace byte for byte,
  accounting for Cargo's original manifest filename. Executable/archive hashes
  are recorded separately.

## Packaged behavior and review

[Delivery validation](delivery-validation.html) passes three scenarios and six
expectations. Independent email, SMS, and pickup inputs produce their expected
channel and payload; all three captured cases replay exactly (`*.run.json`,
`*.case.json`, `*.replay.json`).

[The revision review](delivery-review.html) detects an intentionally incorrect
email destination in `candidate.gwt`. All three cases compare successfully; only
email changes outcome. SMS and pickup retain their outputs while source/evidence
changes are reported. The candidate is a fault-detection fixture, not an accepted
rule revision.

The review displays `kind branch` events by default, showing the selected flag
and linking to the single subject read. Offline Chromium 153.0.8010.12 checks at
1440 and 390 pixels select all three cases, verify visible kind decisions, and
follow operand links without script errors, external requests, or horizontal
overflow. Both screenshots were visually inspected (`browser/`). The initial
browser harness used a Python workbench selector; that failed check is recorded
in `browser-before-selector-fix/`. Correcting the harness required no renderer
change. The repeatable script is [check_kind_review.py](../check_kind_review.py).

`source-hashes.json` records the source, tests, examples, and supporting docs.
Scalar-value dispatch, `IF` narrowing, branch-specific field provenance, broader
domain pressure tests, deployment work, and comparative human evidence remain
open. These results establish the documented native behavior, not a demonstrated
human readability benefit. No external pilot or publication occurred.
