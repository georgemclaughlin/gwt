# Native GWT and Python maintenance evaluation

This research corpus extends the refund-only maintenance experiment to five
policy domains and the current Rust GWT implementation. It prepares paired tasks
and qualifies trusted references against independent expectations. The
[Codex CLI comparison](2026-10-16-codex-cli/README.md) records the subsequent live
model experiment separately from fixture qualification. Human sessions remain
pending; there are no participant results.

Four smaller tasks reuse the human-review kit's refund, delivery, expenses, and
inventory policies. The new allocation task changes a larger policy involving
exact decimals, eligibility, fallback, ordering, rejections, and output metadata.
Existing human-study materials and public allocation examples remain unchanged.

## Allocation change

When eligible weights sum to zero, give every eligible recipient effective weight
one and every ineligible recipient zero. Apply this even at zero total so that
participation metadata reflects the fallback. If any eligible weight is positive,
retain the original effective weights. Positive total with no eligible recipients
remains invalid; zero total with none remains valid. Negative weights remain
invalid even on excluded recipients. Preserve output shape, exact-cent conservation,
input-order ties, duplicate-label handling, and at most one extra cent per row.

The GWT reference changes the helper contract and constructs shares using
effective weights. Python uses integer-cent base shares and repeated winner
selection. The independent oracle uses rational quotas and one stable ranking;
it does not execute either implementation or duplicate their award loop.

Baseline, correct, and faulty fixtures are retained. The faulty allocation
implementation uses equal weights even when eligible positive weights exist.
It passes both public examples but fails mixed-weight withheld cases.

## Qualification

From the repository root, select a frozen native executable and a new directory:

```sh
python -m evaluations.native_maintenance.study --native /path/to/gwt --output /path/to/new-qualification
python -m unittest tests.test_native_maintenance
```

Every GWT reference is checked and formatted through native validation with an
explicit no-scenarios allowance. These isolated request fixtures intentionally
omit embedded tests in both conditions. Independent host probes establish behavior;
declaration-only validation does not count as scenario coverage.

The worker receives request names and input values; expected outcomes stay in
the parent. Native `assertion_failed` and Python's explicit
`ValueError("policy_rejected")` normalize to `{"rejected":true}`. Other failures
are errors, not expected rejections. Successful output is wrapped in `result`
for scoring. Shapes, decimal strings, integer/boolean distinctions, row order,
and missing fields compare strictly. This corpus does not score cross-language
state/evidence equality, malformed input contracts, runtime speed, or memory.

`study.py` qualifies **trusted fixtures**, not arbitrary generated code in a
sandbox. Its subprocesses have timeouts and normal account permissions. Use the
separate [isolated scorer](scoring.md) for candidate responses. It runs native
GWT and Python in bounded disposable containers, keeps expected answers in the
parent, and provides public-only repair feedback. The
[model experiment runner](experiment.md) connects that loop to either tool-free
API requests or a separately labeled Codex CLI protocol. Live Responses API
qualification remains pending; CLI evidence is recorded independently.

Artifacts contain the exact corpus, observations for both languages and three
revisions, partitioned scores, commands, source/executable hashes, and 30 task
records: five domains × two languages × three repeats. Language order alternates
within pairs across trials. Inputs are deduplicated; each domain's two public
examples occur once in its scoring corpus.

## Future experiment boundary

Each task supplies baseline source, intent, a language guide, request name, and
two public probes. Correct/faulty source and withheld expectations are omitted.
The repository is public; withholding describes the prompt boundary, not secrecy
or training-data contamination.

Use the isolated scorer's public-only mode for repair feedback. The older
`gwtlang.maintenance_evaluation` worker runs Python GWT and cannot score native
allocation syntax. Its repair/scoring path must not be used for this corpus.
Prepared records follow the existing response convention; that alone does not
qualify a model integration.

Before live calls, freeze model/settings, full tasks and guides, repair policy,
order, candidate execution environment, and scoring rules. Retain missing trials,
failed attempts, public feedback, exact responses, and reported usage. Separate
first/final success and changed/preserved/public/withheld results. Record context
sizes: declaration-rich GWT source and its guide differ from Python, so this is
guided use rather than matched prompt lengths. This extension has no clarification
tasks.

[Fixture evidence](2026-10-16/README.md) establishes agreement and fault sensitivity.
[Scorer qualification](2026-10-16-isolated/README.md) records synthetic repairs,
missing trials, withheld failures, and actual container boundary checks.
Prepared repeats are not model executions. Reference passes establish neither AI
maintenance performance nor human comprehension or adoption.
