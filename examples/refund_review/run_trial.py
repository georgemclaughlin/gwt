"""Rehearse three successive rule changes with synthetic, independently scored cases."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import shutil

from gwtlang.case_corpus import CaseCorpusEntrySpec, write_case_corpus
from gwtlang.comparison import compare_execution_cases
from gwtlang.execution_case import capture_execution_case
from gwtlang.maintenance_evaluation import evaluate_candidate
from gwtlang.scenario_generation import generate_scenario
from gwtlang.workbench import render_workbench_html


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evaluations/maintenance/manifest.json"


def run_trial(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    programs = output / "programs"
    programs.mkdir()
    for source in Path(__file__).parent.glob("stage*.*"):
        shutil.copyfile(source, programs / source.name)
    manifest = json.loads(MANIFEST.read_text())
    shutil.copyfile(MANIFEST, output / "acceptance-manifest.json")
    rounds = []
    for stage, task in enumerate(manifest["cases"][:3], 1):
        directory = output / task["id"]
        directory.mkdir()
        # Keep a compact review queue, including both changed and preserved cases.
        changed = [probe for probe in task["probes"] if probe["kind"] == "changed"]
        preserved = [probe for probe in task["probes"] if probe["kind"] == "preserved"]
        probes = changed[:6] + preserved[::max(1, len(preserved) // 6)][:6]
        old = programs / f"stage{stage - 1}.gwt"
        new = programs / f"stage{stage}.gwt"
        # Full acceptance is separate from the smaller human review queue.
        parity = {}
        for language, extension in (("gwt", "gwt"), ("python", "py")):
            result = evaluate_candidate((programs / f"stage{stage}.{extension}").read_text(), language, task["request"], task["probes"])
            if not all(result["passed"]):
                raise ValueError(f"{task['id']}: {language} acceptance failed: {result['error']}")
            parity[language] = len(result["passed"])
        cases, references, entries = [], [], []
        expectations = []
        for index, probe in enumerate(probes, 1):
            reference = f"{probe['kind']}-{index:02d}"
            case = capture_execution_case(old, probe["input"], request=task["request"])
            filename = reference + ".execution-case.json"
            case.write(directory / filename)
            case_id = case.as_payload()["integrity"]["digest"]
            cases.append(case)
            references.append(reference)
            entries.append(CaseCorpusEntrySpec(reference, case_id, filename))
            expectations.append({"reference": reference, **probe})
        write_case_corpus(directory / "corpus.json", name=task["id"], entries=entries)
        comparison = compare_execution_cases(old, new, cases, case_references=references)
        expected_changes = sum(probe["kind"] == "changed" for probe in probes)
        if comparison.totals.output_changed != expected_changes:
            raise ValueError("comparison does not reconcile with independent expected changes")
        scenario = generate_scenario(cases[0].as_payload(), old, scenario_name="captured baseline refund").source
        (directory / "observed-baseline.gwt").write_text(scenario)
        (directory / "expected-candidate.json").write_text(json.dumps(expectations, indent=2) + "\n")
        (directory / "comparison.json").write_text(json.dumps(comparison.as_payload(), indent=2) + "\n")
        (directory / "review.html").write_text(render_workbench_html(
            cases[0], comparison, scenario,
            case_reference=references[0],
            review_notice="Synthetic rehearsal. Generated scenarios preserve observed baseline behavior. Candidate expectations are authored separately in expected-candidate.json; no human approval has been recorded.",
            old_label=f"Refund policy stage {stage - 1}", new_label=f"Refund policy stage {stage}",
        ))
        rounds.append({"task": task["id"], "acceptance": parity, "reviewCases": len(cases), "expectedOutputChanges": expected_changes, "comparison": comparison.totals.as_payload()})
    with (output / "human-review.csv").open("w", newline="") as stream:
        columns = ["task", "condition", "reviewer", "review_seconds", "identified_changes", "missed_changes", "interventions", "verdict", "would_use_again", "notes"]
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for item in rounds:
            for condition in ("gwt-workbench", "python-source-and-tests"):
                writer.writerow({"task": item["task"], "condition": condition})
    report = {"kind": "gwt.adoption-rehearsal", "externalPilot": False, "humanReviewCompleted": False, "rounds": rounds}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory for frozen programs and review evidence")
    args = parser.parse_args()
    print(json.dumps(run_trial(args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
