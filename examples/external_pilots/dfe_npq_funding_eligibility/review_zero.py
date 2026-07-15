from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from gwtlang import GwtClient

from compare_corpus import normalize


PILOT_DIR = Path(__file__).resolve().parent
RULES = PILOT_DIR / "rules.gwt"
RUBY_ORACLE = PILOT_DIR / "ruby_oracle.rb"
REQUEST_NAME = "assess funding eligibility"
UPSTREAM_COMMIT = "f3601047213660121a5b8e0850c8ecef798f8e03"
RUBY_IMAGE = "ruby:3.4.9-alpine"

SELECTORS: tuple[tuple[str, dict[str, str]], ...] = (
    (
        "unfunded-and-outside-catchment",
        {
            "Cohort": "2026 spring",
            "Works in England": "no",
            "Work setting": "school",
            "NPQ": "headship",
            "Already registered for this course": "no",
        },
    ),
    (
        "funded-cohort-outside-catchment",
        {
            "Cohort": "2026 autumn",
            "Works in England": "no",
            "Work setting": "school",
            "NPQ": "headship",
            "Already registered for this course": "no",
        },
    ),
    (
        "previously-funded",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "school",
            "NPQ": "headship",
            "Already registered for this course": "yes",
        },
    ),
    (
        "rise-overrides-pp50",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "school",
            "NPQ": "executive leadership",
            "Already registered for this course": "no",
            "RISE list?": "yes",
            "PP50": "no",
        },
    ),
    (
        "specialist-course-without-pp50",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "school",
            "NPQ": "leading literacy",
            "Already registered for this course": "no",
            "RISE list?": "no",
            "PP50": "no",
        },
    ),
    (
        "specialist-course-with-pp50",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "school",
            "NPQ": "leading literacy",
            "Already registered for this course": "no",
            "RISE list?": "no",
            "PP50": "yes",
        },
    ),
    (
        "unlisted-childminder",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "early years or childcare - childminder",
            "NPQ": "early years leadership",
            "Already registered for this course": "no",
        },
    ),
    (
        "preschool-class",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "early years or childcare - pre-school class or nursery that's part of a school",
            "NPQ": "early years leadership",
            "Already registered for this course": "no",
        },
    ),
    (
        "local-authority-nursery",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "early years or childcare - local authority maintained nursery",
            "NPQ": "headship",
            "Already registered for this course": "no",
        },
    ),
    (
        "another-setting-review",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "another setting - independent hospital education organisation",
            "NPQ": "headship",
            "Already registered for this course": "no",
        },
    ),
    (
        "approved-lead-mentor",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "another setting - lead mentor for an accredited ITT provider",
            "NPQ": "leading teacher development",
            "Already registered for this course": "no",
        },
    ),
    (
        "return-to-teaching-referral",
        {
            "Cohort": "2026 autumn",
            "Works in England": "yes",
            "Work setting": "other - referred by a RTTA",
            "NPQ": "headship",
            "Already registered for this course": "no",
        },
    ),
)


def _run(command: list[str], *, input_text: str | None = None) -> str:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}")
    return completed.stdout


def _value(row: dict[str, str], name: str) -> str:
    return (row.get(name) or "").strip()


def _upstream_commit(upstream_root: Path) -> str:
    return _run(["git", "-C", str(upstream_root), "rev-parse", "HEAD"]).strip()


def _select_rows(csv_path: Path) -> list[dict[str, Any]]:
    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))

    selected: list[dict[str, Any]] = []
    for case_id, selector in SELECTORS:
        matches = [
            (index, row)
            for index, row in enumerate(rows, start=2)
            if all(_value(row, key) == expected for key, expected in selector.items())
        ]
        if len(matches) != 1:
            raise ValueError(f"selector {case_id!r} matched {len(matches)} rows; expected exactly one")
        fixture_row, row = matches[0]
        request = normalize(row)
        selected.append(
            {
                "id": case_id,
                "fixture_row": fixture_row,
                "fixture_expectation": _value(row, "Expected eligibility value"),
                "request": request,
                "source": {key: _value(row, key) for key in row},
            }
        )
    return selected


def _ruby_results(upstream_root: Path, cases: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    payload = [{"id": case["id"], **case["request"]} for case in cases]
    output = _run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            f"{upstream_root}:/upstream:ro",
            "-v",
            f"{PILOT_DIR}:/pilot:ro",
            RUBY_IMAGE,
            "ruby",
            "/pilot/ruby_oracle.rb",
            "/upstream",
        ],
        input_text=json.dumps(payload),
    )
    values = json.loads(output)
    return {
        item["id"]: {
            "outcome": item["outcome"],
            "status_code": item["status_code"],
            "description": item["description"],
        }
        for item in values
    }


def _gwt_results(cases: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    compiled = GwtClient(RULES).compile(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    results: dict[str, dict[str, str]] = {}
    for case in cases:
        execution = compiled.run_json(case["request"], request=REQUEST_NAME)
        decision = execution.as_payload()["result"]["decision"]
        results[case["id"]] = {
            "outcome": decision["outcome"],
            "status_code": decision["status_code"],
            "description": decision["description"],
        }
    return results


def _candidate_source() -> str:
    source = RULES.read_text()
    original = """    WHEN facts.cohort_funded == false
      record status \"unfunded_cohort\" outcome \"not_funded\" description \"unfunded_cohort\" into decision
    WHEN facts.inside_catchment == false
      record status \"not_in_england\" outcome \"not_funded\" description \"outside_catchment\" into decision
"""
    mutated = """    WHEN facts.inside_catchment == false
      record status \"not_in_england\" outcome \"not_funded\" description \"outside_catchment\" into decision
    WHEN facts.cohort_funded == false
      record status \"unfunded_cohort\" outcome \"not_funded\" description \"unfunded_cohort\" into decision
"""
    if source.count(original) != 1:
        raise ValueError("could not locate the precedence block to mutate")
    source = source.replace(
        "PROGRAM DfE NPQ funding eligibility pilot",
        "PROGRAM DfE NPQ funding eligibility seeded wrong precedence",
        1,
    )
    return source.replace(original, mutated, 1)


def _write_review_artifacts(
    output_dir: Path,
    cases: list[dict[str, Any]],
    ruby_results: dict[str, dict[str, str]],
    gwt_results: dict[str, dict[str, str]],
) -> dict[str, Any]:
    inputs_dir = output_dir / "inputs"
    cases_dir = output_dir / "cases"
    inputs_dir.mkdir()
    cases_dir.mkdir()

    candidate = output_dir / "candidate-wrong-precedence.gwt"
    candidate.write_text(_candidate_source())
    _run([sys.executable, "-m", "gwtlang", "format", str(candidate), "--check"])
    _run([sys.executable, "-m", "gwtlang", "check", str(candidate)])

    case_paths: list[Path] = []
    manifest_cases: list[dict[str, Any]] = []
    for case in cases:
        case_id = case["id"]
        input_path = inputs_dir / f"{case_id}.json"
        case_path = cases_dir / f"{case_id}.execution-case.json"
        input_path.write_text(json.dumps(case["request"], indent=2, sort_keys=True) + "\n")
        _run(
            [
                sys.executable,
                "-m",
                "gwtlang",
                "capture",
                str(RULES),
                "--json-input",
                str(input_path),
                "--request",
                REQUEST_NAME,
                "--output",
                str(case_path),
            ]
        )
        case_paths.append(case_path)
        manifest_cases.append(
            {
                "id": case_id,
                "fixture_row": case["fixture_row"],
                "fixture_expectation": case["fixture_expectation"],
                "ruby": ruby_results[case_id],
                "gwt": gwt_results[case_id],
            }
        )

    comparison_json = output_dir / "comparison.json"
    comparison_text = output_dir / "comparison.txt"
    comparison_command = [
        sys.executable,
        "-m",
        "gwtlang",
        "compare",
        "--old",
        str(RULES),
        "--new",
        str(candidate),
        *[str(path) for path in case_paths],
    ]
    comparison_text.write_text(_run(comparison_command))
    comparison_json.write_text(_run([*comparison_command, "--json"]))

    scenario = output_dir / "captured-unfunded-and-outside.gwt"
    _run(
        [
            sys.executable,
            "-m",
            "gwtlang",
            "scenario-from-run",
            str(case_paths[0]),
            "--program",
            str(RULES),
            "--name",
            "captured unfunded and outside catchment",
            "--output",
            str(scenario),
        ]
    )

    workbench = output_dir / "review.html"
    _run(
        [
            sys.executable,
            "-m",
            "gwtlang",
            "workbench",
            *[str(path) for path in case_paths],
            "--old",
            str(RULES),
            "--new",
            str(candidate),
            "--program",
            str(RULES),
            "--name",
            "captured unfunded and outside catchment",
            "--review-notice",
            (
                "Independent local evaluation against the pinned DfE service; "
                "the candidate contains a deliberate precedence error and is not upstream code."
            ),
            "--old-label",
            f"GWT parity baseline for DfE service @ {UPSTREAM_COMMIT[:12]}",
            "--new-label",
            "local seeded wrong-precedence candidate",
            "--output",
            str(workbench),
        ]
    )

    comparison = json.loads(comparison_json.read_text())
    classifications = Counter(item["classification"] for item in comparison["cases"])
    manifest = {
        "artifact": "gwt.local-pilot-zero",
        "upstream_commit": UPSTREAM_COMMIT,
        "ruby_image": RUBY_IMAGE,
        "exact_status_parity": len(cases),
        "case_count": len(cases),
        "comparison_classifications": dict(sorted(classifications.items())),
        "seeded_mutation": "inside-catchment rejection evaluated before unfunded-cohort rejection",
        "cases": manifest_cases,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local NPQ exact-status behavior-review experiment")
    parser.add_argument("upstream_root", type=Path, help="pinned local checkout of DFE-Digital/npq-registration")
    parser.add_argument("--output-dir", type=Path, help="new directory for sensitive local review artifacts")
    args = parser.parse_args()

    upstream_root = args.upstream_root.resolve()
    if _upstream_commit(upstream_root) != UPSTREAM_COMMIT:
        parser.error(f"upstream checkout must be pinned at {UPSTREAM_COMMIT}")

    csv_path = upstream_root / "spec/fixtures/scenarios/eligibility_testing_scenarios.csv"
    cases = _select_rows(csv_path)
    ruby_results = _ruby_results(upstream_root, cases)
    gwt_results = _gwt_results(cases)
    mismatches = [case_id for case_id in ruby_results if ruby_results[case_id] != gwt_results.get(case_id)]
    if mismatches:
        parser.error(f"exact Ruby/GWT status mismatch for: {', '.join(mismatches)}")

    if args.output_dir is None:
        output_dir = Path(tempfile.mkdtemp(prefix="gwt-npq-review-zero."))
    else:
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=False)

    manifest = _write_review_artifacts(output_dir, cases, ruby_results, gwt_results)
    print(f"exact Ruby/GWT status parity: {manifest['exact_status_parity']}/{manifest['case_count']}")
    print(f"candidate comparison: {json.dumps(manifest['comparison_classifications'], sort_keys=True)}")
    print(f"review artifacts: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
