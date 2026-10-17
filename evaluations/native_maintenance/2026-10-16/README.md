# Five-domain fixture qualification

The final [qualification](final/qualification.json) covers 1,138 distinct inputs
per revision, 6,828 trusted reference executions, and 30 prepared paired tasks.
There were **zero model calls and zero human participants**.

| Domain | Inputs | Changed | Preserved | Faulty candidate failures |
| --- | ---: | ---: | ---: | ---: |
| Refund | 33 | 3 | 30 | 1 |
| Delivery | 13 | 5 | 8 | 2 |
| Expenses | 74 | 14 | 60 | 31 |
| Inventory | 20 | 6 | 14 | 10 |
| Allocation | 998 | 158 | 840 | 380 |

Counts apply to each language. Correct references pass every probe; unchanged
baselines fail every changed probe and pass every preserved one. Baselines also
match independent old-policy expectations. Baseline, correct, and faulty
observations agree exactly across languages. Faulty agreement establishes that
the intended defect exists in both arms, not that its policy is acceptable.

Two inputs per domain are public. The other 1,128 are withheld from task records.
The allocation fault passes its public probes and fails 380 withheld probes.
Allocation inputs derive from exhaustive small weight/eligibility combinations,
seeded broader values, rejection boundaries, and public fallback examples,
deduplicated before scoring. Every output field and canonical decimal counts.

The retained static release comes from the
[CLI-budget checkpoint](../../native_editor/2026-10-16-cli-limits/README.md).
No engine code or public example policy changed. GWT fixtures validate with an
explicit no-scenarios allowance; independent request probes establish behavior.

The [task file](final/tasks.jsonl) contains three paired repeats per domain and
language, with alternating language order. The complete [corpus](final/corpus.json),
[observations](final/observations.json), [scores](final/checks.json), native
commands, and source/executable hashes are retained. Hashes are checked unchanged
across qualification. The initial run remains at this directory's top level;
final qualification includes explicit unknown-language rejection and freezes
tooling hashes before execution.

Four new unit groups cover prompt boundaries, distinct changed/preserved inputs,
public subsets, independently specified fallback/rejection examples, strict JSON
comparison, and missing-observation refusal. The full Python suite result is in
`python-tests.log`.

This prepares a harder experiment. A native-aware isolated candidate scorer and
repair loop, actual model trials, and representative human review evidence remain
open. The older Python-GWT worker must not judge these native tasks.
