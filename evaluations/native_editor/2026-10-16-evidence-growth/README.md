# Append evidence growth checkpoint

The preceding goal turn added typed local records and removed allocation template
plumbing. This turn profiles the remaining evidence cost and changes native
append events to record the inserted item and index, with source and operand
references, instead of complete before/after list snapshots. The public event
operation is now `append item`; see its [payload contract](../../../docs/native-append-evidence.md).

## Measurements and scope

The [initial allocation profile](profile.json), using the previous engine,
shows that values occupy 212,578 of 818,588 event bytes on the tested
16-recipient case. Metadata occupies the other roughly 74%; repeated exact values
account for about 15% of the total. In the incomplete 64-recipient trace, append
snapshots alone occupy 426,451 bytes. These observations distinguish append
prefix duplication from the cost of repeated remainder scans.

The [paired collector profiles](qualification/collector-profiles.json) use identical
source, input, and default limits on the retained previous and new engines:

| 200-character labels | Old event bytes | New event bytes | Outcome |
| --- | ---: | ---: | --- |
| 8 | 26,926 | 15,565 | Same result/state |
| 16 | 78,025 | 29,326 | Same result/state |
| 32 | 258,241 | 56,918 | Same result/state |
| 64 | 930,561 | 112,182 | Same result/state; 266 events on each engine |
| 128 | 1,042,450, incomplete | 222,823, complete | Old evidence refusal becomes success |

These are sums of compact UTF-8 event JSON bytes, matching the runtime budget
accounting. They exclude envelopes/array separators and do not measure runtime
speed or memory complexity. No evidence limit was raised. Append-only deltas
reconstruct the exact expected list, with every inserted item retained.

[Paired allocation probes](qualification/allocation-profiles.json) still refuse
the tested 32/64-recipient cases at the default evidence limit. Repeated scans,
per-event metadata, collection snapshots, and value copying remain. The copied
allocation entry is named `allocation.gwt`; its source-path metadata accounts
for byte differences from the initial `rules.gwt` profile. Each paired comparison
uses the same filename on both engines.

## Correctness, migration, and review

- [Rust results](rust-checks.json): **370 tests** and warning-free Clippy pass on
  Rust **1.85.0** and **1.96.0**, in development mode. Five new groups cover exact
  reconstruction, alias paths, destination normalization, optional null items,
  evidence refusal just before versus just after the event, bounded append-event
  growth, explanation validation, replay, and HTML escaping/default visibility.
- [Engine transitions](qualification/qualification.json): four successful
  collector outcomes/states remain identical; one old evidence refusal becomes
  success. All original bytes are unchanged, migrations are unapproved, and
  candidates replay. Separately, all **52 allocation outcomes and states** are
  preserved: **36** migrations change evidence and **16** preserve complete
  observations. All 1,004 independent allocation cases still pass in the Rust suite.
- A one-case [review](qualification/review.json) compares plain labels with a
  deliberate `!` suffix revision. It reports one changed outcome/state, with no
  unavailable cases or baseline mismatch. The [HTML](qualification/review.html)
  retains both trails and their append deltas. [Static HTML checks](html-checks.json)
  find all six append events in the default trail and no injected SVG element.
- [Browser validation](browser-validation.json) is **pending**: the browser
  runtime reported no available browser and discovery returned an empty list.
  No alternative browser-control mechanism or visual/interactive qualification
  is claimed. Automated HTML checks are narrower evidence.

## Other verification

[Reference checks](reference-checks.json) pass **629 Python tests**, **73 example
format checks**, 16 top-level checks, order/tour executions, extension syntax
checks, and **five JavaScript tests**. [The executable record](executable.json)
identifies the frozen development binary used for qualification. The previous
engine is the retained [local-record checkpoint](../2026-10-16-local-records/README.md).
No fresh release package, container run, or actual editor-host run is claimed.

[Final checks](final-checks.json) cover source/executable identity, fixture
reproduction, documented commands, local links, and diff whitespace.
[Source hashes](source-hashes.json) and [engine input hashes](engine-source-hashes.json)
identify the checkpoint.

## Reproduce

```sh
cargo test --locked --test append_evidence
python evaluations/native_editor/qualify_append_evidence.py --native /path/to/new/gwt-native --previous-engine /path/to/previous/gwt-native --output /tmp/gwt-append-evidence
```

The output directory must be new; the previous engine must own the retained
local-record allocation cases. The full project goal remains active. Remaining
evidence growth, language/tooling coverage, production qualification, and actual
human comprehension benefits are not closed by this change.
