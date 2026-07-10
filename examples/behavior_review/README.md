# Local Behavior Review

This example shows the complete local review loop with a compact library hold
routing rule. The baseline promotes a waiting hold after seven days. The
candidate promotes it after five days. Two captured inputs make the impact
concrete: a hold with an available copy is unchanged, while a five-day wait
changes from the standard queue to the priority queue.

Both programs carry their own executable `SCENARIO` coverage. Start by checking
and running those authored expectations:

```sh
python -m gwtlang check examples/behavior_review/baseline.gwt
python -m gwtlang check examples/behavior_review/candidate.gwt
python -m gwtlang test examples/behavior_review/baseline.gwt
python -m gwtlang test examples/behavior_review/candidate.gwt
```

## Capture And Explain What Actually Happened

Create a temporary directory so full-value Execution Cases and rendered output
stay out of the repository:

```sh
CASE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gwt-behavior-review.XXXXXX")"
python -m gwtlang capture examples/behavior_review/baseline.gwt \
  --json-input examples/behavior_review/available-copy.json \
  --request "route hold" \
  --output "$CASE_DIR/available-copy.execution-case.json"
python -m gwtlang capture examples/behavior_review/baseline.gwt \
  --json-input examples/behavior_review/five-day-wait.json \
  --request "route hold" \
  --output "$CASE_DIR/five-day-wait.execution-case.json"
python -m gwtlang explain examples/behavior_review/baseline.gwt \
  --json-input examples/behavior_review/five-day-wait.json \
  --request "route hold"
```

`explain` reports the branch and values observed during execution. The captured
case preserves that same baseline run as source-linked evidence; it does not
claim that the baseline outcome is the desired future behavior.

## Turn The Run Into A Reviewable Example

Generate a replay-verified scenario from the five-day case:

```sh
python -m gwtlang scenario-from-run \
  "$CASE_DIR/five-day-wait.execution-case.json" \
  --program examples/behavior_review/baseline.gwt \
  --name "captured five day hold" \
  --output "$CASE_DIR/captured-five-day-hold.gwt"
```

That generated scenario states what the baseline actually did: it routed the
hold to `standard`. The authored candidate scenario states the intended change:
the same input should route to `priority`. Reviewers should decide whether that
difference expresses the desired behavior before accepting the candidate;
generated actual behavior is evidence, not automatic intent.

## Compare And Review Locally

Compare both cases, then render the same evidence as a self-contained local
workbench page:

```sh
python -m gwtlang compare \
  --old examples/behavior_review/baseline.gwt \
  --new examples/behavior_review/candidate.gwt \
  "$CASE_DIR/five-day-wait.execution-case.json" \
  "$CASE_DIR/available-copy.execution-case.json"
python -m gwtlang workbench \
  "$CASE_DIR/five-day-wait.execution-case.json" \
  "$CASE_DIR/available-copy.execution-case.json" \
  --old examples/behavior_review/baseline.gwt \
  --new examples/behavior_review/candidate.gwt \
  --program examples/behavior_review/baseline.gwt \
  --name "captured five day hold" \
  --output "$CASE_DIR/behavior-review.html"
```

The comparison should report one `output_changed` case and one `unchanged`
case. Open the path printed for `behavior-review.html` in a local browser to
review the case, output diff, source-linked evidence, and generated scenario.
The workbench is a local renderer; it does not approve the change or establish
an audit history.

## Value Sensitivity

The commands above intentionally use full input and output values. These
samples use fictional hold IDs, but real library data could identify a patron
or reveal reading activity. Use `--omit-values` when shape-only evidence is
useful, while remembering that source text, field paths, request names, and
branch structure remain. Do not commit generated cases or HTML, and store or
share them only where the original input data is allowed.
