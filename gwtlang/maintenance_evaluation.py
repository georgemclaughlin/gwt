"""Paired GWT/Python maintenance tasks with independent acceptance probes.

Research tooling, separate from the language and its stable payload contract.
Candidates run with the current account's permissions. Use a disposable
container without secrets when scoring untrusted model output.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from statistics import median
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence, TypedDict, cast

from .agent_evaluation import read_jsonl, write_jsonl


LANGUAGES = ("gwt", "python")


class CandidateAssessment(TypedDict):
    passed: list[bool]
    error: str | None


def _manifest(path: str | Path) -> dict[str, Any]:
    raw: object = json.loads(Path(path).read_text())
    if not isinstance(raw, dict):
        raise ValueError("expected maintenance manifest version 1")
    value = cast(dict[str, Any], raw)
    if value.get("schemaVersion") != 1 or not isinstance(value.get("cases"), list) or not value["cases"]:
        raise ValueError("expected nonempty maintenance manifest version 1")
    for case in value["cases"]:
        if case.get("kind") not in {"maintain", "clarify"}:
            raise ValueError("case kind must be maintain or clarify")
        if case["kind"] == "maintain":
            probes = case.get("probes", [])
            if not probes or {probe.get("kind") for probe in probes} != {"changed", "preserved"}:
                raise ValueError("maintenance cases require changed and preserved probes")
            if any("input" not in probe or "expected" not in probe for probe in probes):
                raise ValueError("probes require input and expected values")
        elif not case.get("requiredConcepts") or any(not concepts for concepts in case["requiredConcepts"]):
            raise ValueError("clarification cases require nonempty concepts")
    ids = [case["id"] for case in value["cases"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate maintenance case ID")
    return value


def prepare_maintenance(
    manifest_path: str | Path, *, language: str, repeats: int = 3,
) -> list[dict[str, Any]]:
    if language not in LANGUAGES or type(repeats) is not int or repeats < 1:
        raise ValueError("choose gwt or python and a positive repeat count")
    path = Path(manifest_path)
    manifest = _manifest(path)
    guide = (path.parent / manifest["guides"][language]).read_text()
    tasks: list[dict[str, Any]] = []
    for trial in range(1, repeats + 1):
        for case in manifest["cases"]:
            tasks.append({
                "schemaVersion": 1,
                "caseId": f"{case['id']}-{language}-{trial}",
                "pairId": case["id"], "trial": trial, "language": language,
                "kind": case["kind"], "task": case["task"],
                "contextVariant": "maintenance-guide",
                "context": {
                    "source": (path.parent / case["starter"][language]).read_text(),
                    "guide": guide, "publicProbes": case.get("publicProbes", []),
                    "request": case["request"],
                },
                "responseContract": {
                    "action": "code or clarify", "source": "complete replacement source",
                    "clarifications": "questions about missing domain policy, if needed",
                },
            })
    return tasks


def evaluate_candidate(
    source: str, language: str, request: str, probes: Sequence[Mapping[str, Any]],
    *, timeout: float = 10,
) -> CandidateAssessment:
    """Evaluate each input without exposing expected outputs to the worker."""
    if language not in LANGUAGES or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("invalid language or timeout")
    worker = Path(__file__).with_name("maintenance_worker.py").resolve()
    with tempfile.TemporaryDirectory(prefix="gwt-maintenance-") as directory:
        candidate = Path(directory) / ("candidate.gwt" if language == "gwt" else "candidate.py")
        candidate.write_text(source)
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(worker), language, str(candidate)],
                input=json.dumps({"request": request, "inputs": [probe["input"] for probe in probes]}),
                text=True, capture_output=True, cwd=directory, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"passed": [False] * len(probes), "error": "candidate timed out"}
    if completed.returncode:
        return {"passed": [False] * len(probes), "error": completed.stderr[-2000:]}
    try:
        raw_values: object = json.loads(completed.stdout)
        if not isinstance(raw_values, list):
            raise ValueError("expected result array")
        values = cast(list[object], raw_values)
        if len(values) != len(probes):
            raise ValueError("incorrect result count")
        passed = [
            isinstance(value, dict) and cast(dict[str, Any], value).get("ok") is True
            and _exact_json(cast(dict[str, Any], value).get("result")) == _exact_json(probe["expected"])
            for value, probe in zip(values, probes)
        ]
    except (ValueError, TypeError):
        return {"passed": [False] * len(probes), "error": "invalid worker response"}
    return {"passed": passed, "error": None}


def public_feedback(task: Mapping[str, Any], response: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Repair feedback is derived exclusively from model-visible acceptance cases."""
    if task["kind"] == "clarify":
        return []
    source = response.get("source")
    if response.get("action") != "code" or not isinstance(source, str) or not source.strip():
        return [{"gate": "response", "message": "return the complete replacement source"}]
    context = task["context"]
    probes = context["publicProbes"]
    result = evaluate_candidate(source, task["language"], context["request"], probes)
    if result["error"]:
        return [{"gate": "execution", "message": result["error"]}]
    return [
        {"gate": "public-probe", "input": probe["input"], "expected": probe["expected"]}
        for probe, passed in zip(probes, result["passed"]) if not passed
    ]


def score_maintenance(
    manifest_path: str | Path, responses: Sequence[Mapping[str, Any]], *,
    language: str, repeats: int = 3, timeout: float = 10,
) -> dict[str, Any]:
    tasks = prepare_maintenance(manifest_path, language=language, repeats=repeats)
    manifest = _manifest(manifest_path)
    cases = {case["id"]: case for case in manifest["cases"]}
    task_ids = {task["caseId"] for task in tasks}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for response in responses:
        case_id = response.get("caseId")
        attempt = response.get("attempt")
        if not isinstance(case_id, str) or case_id not in task_ids:
            raise ValueError(f"unknown case ID: {case_id}")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise ValueError("attempt must be a positive integer")
        if response.get("action") not in {"code", "clarify"}:
            raise ValueError("action must be code or clarify")
        grouped[str(case_id)].append(response)

    details: list[dict[str, Any]] = []
    for task in tasks:
        case = cases[task["pairId"]]
        attempts = sorted(grouped[task["caseId"]], key=lambda item: int(item["attempt"]))
        if [item["attempt"] for item in attempts] != list(range(1, len(attempts) + 1)):
            raise ValueError("attempts must be contiguous from 1 without duplicates")
        assessments: list[dict[str, Any]] = []
        for attempt in attempts:
            if case["kind"] == "clarify":
                questions = attempt.get("clarifications", [])
                text = (
                    " ".join(cast(list[str], questions)).lower()
                    if isinstance(questions, list) and all(isinstance(q, str) for q in cast(list[object], questions))
                    else ""
                )
                passed = attempt["action"] == "clarify" and all(
                    any(term in text for term in alternatives) for alternatives in case["requiredConcepts"]
                )
                assessments.append({"attempt": attempt["attempt"], "success": passed})
                continue
            probes = case["probes"]
            source = attempt.get("source")
            result: CandidateAssessment = (
                evaluate_candidate(source, language, case["request"], probes, timeout=timeout)
                if attempt["action"] == "code" and isinstance(source, str) and source.strip()
                else {"passed": [False] * len(probes), "error": "missing code"}
            )
            changed = [passed for probe, passed in zip(probes, result["passed"]) if probe["kind"] == "changed"]
            preserved = [passed for probe, passed in zip(probes, result["passed"]) if probe["kind"] == "preserved"]
            assessments.append({
                "attempt": attempt["attempt"], "success": all(result["passed"]),
                "changedPassed": sum(changed), "changedCount": len(changed),
                "preservedPassed": sum(preserved), "preservedCount": len(preserved),
                "error": result["error"],
            })
        details.append({
            "caseId": task["caseId"], "pairId": task["pairId"], "trial": task["trial"],
            "kind": task["kind"], "attempts": assessments,
            "firstPassSuccess": bool(assessments and assessments[0]["success"]),
            "finalSuccess": bool(assessments and assessments[-1]["success"]),
        })
    code = [row for row in details if row["kind"] != "clarify"]
    clarify = [row for row in details if row["kind"] == "clarify"]
    repaired = [row for row in code if len(row["attempts"]) > 1]
    iterations = [len(row["attempts"]) - 1 for row in code if row["finalSuccess"]]
    return {
        "schemaVersion": 1, "kind": "gwt.maintenance-evaluation", "language": language,
        "manifestDigest": "sha256:" + hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest(),
        "taskDigest": "sha256:" + hashlib.sha256(_exact_json(tasks).encode()).hexdigest(),
        "repeats": repeats, "caseCount": len(tasks),
        "attemptedCaseCount": sum(bool(row["attempts"]) for row in details),
        "metrics": {
            "firstPassSuccessRate": _rate(code, "firstPassSuccess"),
            "finalSuccessRate": _rate(code, "finalSuccess"),
            "clarificationRate": _rate(clarify, "finalSuccess"),
            "repairRecoveryRate": _rate(repaired, "finalSuccess"),
            "medianSuccessfulRepairIterations": median(iterations) if iterations else None,
        },
        "cases": details,
    }


def _exact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _rate(rows: Sequence[Mapping[str, Any]], key: str) -> float | None:
    return sum(bool(row[key]) for row in rows) / len(rows) if rows else None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "score"):
        child = sub.add_parser(command)
        child.add_argument("manifest")
        child.add_argument("--language", choices=LANGUAGES, required=True)
        child.add_argument("--repeats", type=int, default=3)
        child.add_argument("--output", required=True)
        if command == "score":
            child.add_argument("responses")
            child.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        write_jsonl(prepare_maintenance(args.manifest, language=args.language, repeats=args.repeats), args.output)
    else:
        report = score_maintenance(args.manifest, read_jsonl(args.responses), language=args.language, repeats=args.repeats, timeout=args.timeout)
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
