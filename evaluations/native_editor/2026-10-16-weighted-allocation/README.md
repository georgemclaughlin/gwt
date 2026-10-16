# Weighted allocation checkpoint

This pressure test implements [weighted cent allocation](../../../examples/native_weighted_allocation/README.md)
in the existing native language. No parser, checker, runtime, editor, or numeric
semantics changed. The preceding recovery turn verified the saved source and
executable checkpoint; this turn adds an executable domain policy, independent
acceptance evidence, and specific language/tooling findings.

## Correctness and meaningful policy limits

- [Rust results](rust-checks.json): **358 tests** pass on Rust **1.85.0** and
  **1.96.0**, with warning-free Clippy and canonical Rust formatting. Two new
  integration tests execute the public example and compare **1,004 inputs** with
  the independent [Fraction quota/sort oracle](../weighted_allocation_oracle.py).
  The engine uses rounded decimal arithmetic and repeated scans. Expectations
  cover complete result records and domain rejections before allocation writes.
- [Validation](policy/validation.json): **11 scenarios**, **18 top-level
  expectations**, all passing. In addition to ordinary boundary cases, two
  examples demonstrate that increasing the total from three to four cents can
  reduce one recipient's share. This is an explicit consequence of the selected
  policy, not a guarantee of individual monotonicity.
- [Inspection](policy/inspection.json) exposes only the budget as caller input;
  the typed result template and output record are request-local setup. Template
  copying works but adds authoring plumbing. Local typed construction is an
  open design opportunity grounded in this example.
- [Resource probes](resource-probes/results.json) preserve inputs and commands.
  Equal-weight inputs requiring many bonus awards succeed for 1/3/8/16 recipients.
  The tested 32/64-recipient inputs return `evidence_limit` and no result under
  default limits. This does not establish a universal capacity threshold. The
  implementation has quadratic worst-case scanning, and growing-state evidence
  consumes the byte budget. Earlier partial state may remain on failure.

## Captured faulty revision

The [qualifier](../qualify_weighted_allocation.py) changes one selection condition
from equality with the largest remainder to `<=`. The checker still accepts
the program, but it selects the first eligible recipient instead of the largest
remainder. [Embedded scenario validation rejects it](policy/candidate-validation.json).

The [52-case review](policy/qualification.json) finds exactly **12 changed
outcomes/states**, as independently predicted. The **15 failures** are unchanged
invalid-input rejections, not newly broken valid allocations. All cases compare,
with **zero baseline mismatches and zero unavailable cases**. All **104 baseline
and candidate captures replay**, and baseline file hashes remain unchanged.
Source and evidence changes remain visible for all 52 cases.

[Review JSON](policy/review.json) and [offline HTML](policy/review.html) are retained.
No review approval, browser qualification, external pilot, or human comprehension
benefit is claimed. The HTML renderer itself did not change.

## Reference and package checks

[Reference checks](reference-checks.json) include **627 Python tests**, all **73
example formatting checks**, 16 top-level checks, order/tour executions, extension
syntax checks, and **five JavaScript tests**. The Python runtime does not implement
native rounded division; this example is explicitly registered as native-only.

The policy qualification uses the retained static release executable from the
[rounded-division checkpoint](../2026-10-16-rounded-division/README.md).
[Engine source verification](engine-source-verification.json) checks all 54 prior
archive source/build hashes against the current tree. No new package, container,
or actual editor-host run is claimed. Native library tests exercise the new
example on both supported Rust toolchains.

The oracle fixture reproduces byte-for-byte; documented inspect/validate/run
commands, local documentation links, and `git diff --check` pass. See
[final checks](final-checks.json) and [source hashes](source-hashes.json).
The earliest authoring attempts required corrections to table setup and the
test harness API; the retained results describe the final source, not first-pass
authoring success.

## Reproduce

```sh
cargo test --locked --test weighted_allocation
python evaluations/native_editor/weighted_allocation_oracle.py --output /tmp/gwt-allocation-oracle.json
python evaluations/native_editor/qualify_weighted_allocation.py --native /path/to/gwt-native --output /tmp/gwt-allocation-review
```

The output directory must be new. The qualifier includes resource probes; this
checkpoint also retains a separate run of the same probe function. The full
project goal remains active. Human benefit is unproven, and the broader language,
authoring, resource-management, and production qualification work remains open.
