# Isolated scorer qualification — 2026-10-16

This checkpoint qualifies evaluation infrastructure with synthetic responses.
It contains **zero live model calls and zero human participants**.

## Retained evidence

- `fixtures/`: fresh trusted-fixture qualification with task and corpus digests;
  all 6,828 reference executions pass the qualification over 1,138 inputs per
  revision, with 30 prepared tasks across five domains and two languages.
- `boundaries-verified/qualification.json`: twelve real Docker checks pass,
  including 1,996 correct allocation executions, filesystem/network/environment
  boundaries, configured resource limits, noisy output, syntax errors, malformed
  worker responses, timeouts, output limits, and verified container removal.
- `score-recovered/report.json`: full scoring against the final scorer source.
- `public-initial-recovered/report.json`: initial public-only feedback against
  that source; `public-invalid/report.json` preserves useful syntax-error feedback.
- `python-tests-final.log`: all 641 Python tests pass. `scorer-tests-final.log`:
  all twelve focused corpus/scorer tests pass, including the final feedback edit.

The synthetic response set submits only the first repeat in each domain, leaving
twenty tasks missing. In both languages, refund starts with the unchanged source
and is repaired once, three domains use correct references, and allocation uses
the deliberately faulty reference. Per language the full report retains fifteen
trials, ten missing, three first-pass successes, four final successes, and one
repair that recovers. The faulty allocation passes public examples but fails
380 withheld probes. Initial public feedback requests the refund repair and
does not request an allocation repair. These outcomes check the scoring policy;
they are not model performance estimates.

The native executable SHA-256 is
`196484f5a1889b371b4e9cdd904d3b256c771061fb464e88cb9acd50ca8c3510`.
The immutable tested Docker image ID is
`sha256:b4acd70b6f4ca3e8fa68f11d4bc6831d141744654e62286f862b3c8ca7bd0467`.
Full metadata and per-attempt commands are in the reports. No native engine
implementation changes belong to this checkpoint.

## Recovery and limitations

An initial boundary run in `boundaries/` exposed a race between Docker automatic
removal and explicit cleanup. Cleanup now waits for verified absence when removal
is already in progress and rejects unrelated daemon failures. The initial
partial evidence is retained; the corrected complete run is `boundaries-verified/`.
Earlier `score*` and `public-feedback*` reports remain historical, with their own
source hashes. Recovery reruns use new directories and do not rewrite them.

The reported computer crash left the final unit-test logs and completed reports
present. No evaluation containers remained at recovery inspection. The recovered
scoring runs bind the final source hashes; unsaved editor buffers cannot be
checked from these artifacts.

These Linux container checks are local qualification, not a general security
proof. Python executes within the worker process, so the experiment assumes
cooperative candidates. Public repository fixtures are not secret or proven
absent from training data. Provider integration and live trials remain pending;
human comprehension and adoption remain unmeasured. See the
[scoring guide](../scoring.md) for commands and interpretation.
