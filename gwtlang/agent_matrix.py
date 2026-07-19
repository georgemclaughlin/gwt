"""Run prepared GWT agent-evaluation tasks through an isolated Codex CLI.

This optional live-model harness is deliberately separate from
``agent_evaluation``. The evaluator stays provider-neutral and deterministic;
this module records one provider's raw outputs for later scoring.
"""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
from typing import Any, Mapping, Sequence, cast

from .agent_evaluation import read_jsonl, write_jsonl
from .formatter import format_text
from .runtime import GwtError, run_source
from .service import analyze_source


RESPONSE_SCHEMA = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "schemas"
    / "agent-evaluation-response.schema.json"
)
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ModelRun:
    index: int
    case_id: str
    response: dict[str, Any] | None
    stdout: str
    stderr: str
    duration_seconds: float
    error: str | None = None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run prepared GWT evaluation JSONL through isolated Codex CLI calls."
    )
    parser.add_argument("tasks")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--repair-responses",
        help="Run the next attempt only for responses that fail public deterministic gates.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.jobs <= 0:
        parser.error("--jobs must be positive")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")

    tasks_path = Path(args.tasks)
    tasks = read_jsonl(tasks_path)
    if args.limit is not None:
        tasks = tasks[: args.limit]
    _validate_tasks(tasks)

    work_items: list[
        tuple[Mapping[str, Any], int, Mapping[str, Any] | None, list[dict[str, Any]]]
    ] = []
    prior_responses: list[dict[str, Any]] = []
    if args.repair_responses is None:
        work_items = [(task, 1, None, []) for task in tasks]
    else:
        prior_responses = read_jsonl(args.repair_responses)
        previous_by_case = _latest_responses(prior_responses)
        for task in tasks:
            case_id = str(task["caseId"])
            previous = previous_by_case.get(case_id)
            if previous is None:
                continue
            feedback = _public_repair_feedback(task, previous)
            if feedback:
                attempt = _positive_attempt(previous) + 1
                work_items.append((task, attempt, previous, feedback))
    if not work_items:
        raise ValueError("no tasks require a model call")
    selected_tasks = [item[0] for item in work_items]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "logs").mkdir()

    started = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    cli_version = _codex_version()
    results: dict[int, ModelRun] = {}
    metadata = {
        "schemaVersion": 1,
        "status": "running",
        "provider": "openai-codex-cli",
        "requestedModel": args.model,
        "reasoningEffort": args.reasoning_effort,
        "cliVersion": cli_version,
        "startedAt": started.isoformat(),
        "taskFile": str(tasks_path),
        "taskDigest": f"sha256:{hashlib.sha256(tasks_path.read_bytes()).hexdigest()}",
        "contextVariants": sorted(
            {
                str(task.get("contextVariant"))
                for task in selected_tasks
                if task.get("contextVariant") is not None
            }
        ),
        "caseCount": len(selected_tasks),
        "jobs": args.jobs,
        "timeoutSeconds": args.timeout,
        "mode": "repair" if args.repair_responses is not None else "first-pass",
        "repairResponses": args.repair_responses,
    }
    _write_checkpoint(
        output_dir,
        selected_tasks,
        results,
        metadata,
        prior_responses=prior_responses,
    )

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures: dict[Future[ModelRun], int] = {}
        for index, (task, attempt, previous, feedback) in enumerate(work_items):
            future = executor.submit(
                _run_codex_task,
                index,
                task,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
                timeout=args.timeout,
                attempt=attempt,
                previous=previous,
                feedback=feedback,
            )
            futures[future] = index

        for future in as_completed(futures):
            index = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - subprocess/platform boundary
                result = ModelRun(
                    index,
                    str(selected_tasks[index]["caseId"]),
                    None,
                    "",
                    "",
                    0.0,
                    f"runner failure: {exc}",
                )
            results[index] = result
            _write_log(output_dir, result)
            _write_checkpoint(
                output_dir,
                selected_tasks,
                results,
                metadata,
                prior_responses=prior_responses,
            )
            state = "ok" if result.error is None else "failed"
            print(
                f"[{len(results)}/{len(selected_tasks)}] {result.case_id}: {state}",
                flush=True,
            )

    finished = datetime.now(timezone.utc)
    final_metadata = {
        **metadata,
        "status": "complete",
        "finishedAt": finished.isoformat(),
        "durationSeconds": round(time.monotonic() - started_monotonic, 3),
    }
    _write_checkpoint(
        output_dir,
        selected_tasks,
        results,
        final_metadata,
        prior_responses=prior_responses,
    )
    return 1 if any(result.error is not None for result in results.values()) else 0


def _run_codex_task(
    index: int,
    task: Mapping[str, Any],
    *,
    model: str,
    reasoning_effort: str | None,
    timeout: int,
    attempt: int = 1,
    previous: Mapping[str, Any] | None = None,
    feedback: Sequence[Mapping[str, Any]] = (),
) -> ModelRun:
    case_id = str(task["caseId"])
    deterministic = _deterministic_format_repair(
        case_id,
        attempt,
        previous=previous,
        feedback=feedback,
    )
    if deterministic is not None:
        return ModelRun(index, case_id, deterministic, "", "", 0.0)
    prompt = _task_prompt(task, previous=previous, feedback=feedback)
    with tempfile.TemporaryDirectory(prefix=f"gwt-agent-{case_id}-") as temp_dir:
        root = Path(temp_dir)
        response_path = root / "response.json"
        command = [
            "codex",
            "exec",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--cd",
            str(root),
            "--model",
            model,
            "--output-schema",
            str(RESPONSE_SCHEMA),
            "--output-last-message",
            str(response_path),
        ]
        if reasoning_effort is not None:
            command.extend(["--config", f'model_reasoning_effort="{reasoning_effort}"'])
        command.append("-")

        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return ModelRun(
                index,
                case_id,
                None,
                _subprocess_text(exc.stdout),
                _subprocess_text(exc.stderr),
                time.monotonic() - started,
                f"timed out after {timeout} seconds",
            )

        duration = time.monotonic() - started
        if completed.returncode != 0:
            return ModelRun(
                index,
                case_id,
                None,
                completed.stdout,
                completed.stderr,
                duration,
                f"codex exited with status {completed.returncode}",
            )
        if not response_path.exists():
            return ModelRun(
                index,
                case_id,
                None,
                completed.stdout,
                completed.stderr,
                duration,
                "codex did not write a final response",
            )
        try:
            raw_response = json.loads(response_path.read_text())
            response = _normalize_response(case_id, raw_response, attempt=attempt)
        except (json.JSONDecodeError, ValueError) as exc:
            return ModelRun(
                index,
                case_id,
                None,
                completed.stdout,
                completed.stderr,
                duration,
                f"invalid structured response: {exc}",
            )
        return ModelRun(
            index,
            case_id,
            response,
            completed.stdout,
            completed.stderr,
            duration,
        )


def _task_prompt(
    task: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None = None,
    feedback: Sequence[Mapping[str, Any]] = (),
) -> str:
    prompt = (
        "You are completing one blind evaluation of agent-authored GWT. "
        "Use only the supplied task record. Do not inspect the filesystem, use tools, "
        "or search for benchmark answers. For author and repair tasks, return action "
        "'code' and the complete canonical GWT source, including requested executable "
        "scenarios; set clarifications to an empty array. For a genuinely underspecified "
        "clarify task, return action 'clarify', an empty source, and explicit questions "
        "covering every missing domain decision. Do not return Markdown fences or prose.\n\n"
        f"TASK RECORD\n{json.dumps(task, indent=2, ensure_ascii=False, sort_keys=True)}"
    )
    if previous is not None:
        prompt += (
            "\n\nPREVIOUS RESPONSE\n"
            + json.dumps(previous, indent=2, ensure_ascii=False, sort_keys=True)
            + "\n\nPUBLIC DETERMINISTIC FEEDBACK\n"
            + json.dumps(list(feedback), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n\nReturn a complete repaired response. Preserve the supplied public domain "
            "vocabulary and requested semantics. Hidden behavioral probes are not "
            "included in this feedback."
        )
    return prompt


def _normalize_response(case_id: str, raw: object, *, attempt: int = 1) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("response must be an object")
    response = cast(dict[str, Any], raw)
    action = response.get("action")
    source = response.get("source")
    clarifications = response.get("clarifications")
    if action not in {"code", "clarify"}:
        raise ValueError("action must be code or clarify")
    if not isinstance(source, str):
        raise ValueError("source must be a string")
    if not isinstance(clarifications, list) or not all(
        isinstance(value, str) and value.strip()
        for value in cast(list[Any], clarifications)
    ):
        raise ValueError("clarifications must be a list of non-empty strings")
    if action == "code" and not source.strip():
        raise ValueError("a code response requires source")
    if action == "clarify" and not clarifications:
        raise ValueError("a clarification response requires questions")
    return {
        "caseId": case_id,
        "attempt": attempt,
        "action": action,
        "source": source,
        "clarifications": clarifications,
    }


def _latest_responses(
    responses: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    for response in responses:
        case_id = response.get("caseId")
        if not isinstance(case_id, str):
            raise ValueError("response requires caseId")
        attempt = _positive_attempt(response)
        existing = latest.get(case_id)
        if existing is None or attempt > _positive_attempt(existing):
            latest[case_id] = response
    return latest


def _positive_attempt(response: Mapping[str, Any]) -> int:
    attempt = response.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt <= 0:
        raise ValueError("response requires a positive attempt")
    return attempt


def _public_repair_feedback(
    task: Mapping[str, Any],
    response: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return public parser/checker/formatter/runtime feedback, never hidden probes."""

    if task.get("kind") == "clarify":
        return []
    action = response.get("action")
    source = response.get("source")
    if action != "code" or not isinstance(source, str) or not source.strip():
        return [
            {
                "gate": "response",
                "message": "author and repair tasks require a complete GWT code response",
            }
        ]

    filename = f"<agent-repair:{task['caseId']}>"
    analysis = analyze_source(source, filename=filename, lint=True)
    errors = [
        diagnostic.as_payload(filename)
        for diagnostic in analysis.diagnostics
        if diagnostic.severity == "error"
    ]
    if errors:
        return [{"gate": "check", "diagnostics": errors}]

    feedback: list[dict[str, Any]] = []
    canonical = format_text(source, filename=filename)
    if canonical != source:
        feedback.append(
            {
                "gate": "format",
                "message": "source is valid but not canonically formatted",
                "canonicalSource": canonical,
            }
        )
    try:
        result = run_source(source, filename=filename)
    except GwtError as exc:
        feedback.append({"gate": "scenarios", "message": str(exc)})
    else:
        if not result.scenarios:
            feedback.append(
                {
                    "gate": "scenarios",
                    "message": "author and repair responses must preserve executable scenarios",
                }
            )
    return feedback


def _deterministic_format_repair(
    case_id: str,
    attempt: int,
    *,
    previous: Mapping[str, Any] | None,
    feedback: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if previous is None or len(feedback) != 1 or feedback[0].get("gate") != "format":
        return None
    canonical = feedback[0].get("canonicalSource")
    if not isinstance(canonical, str) or not canonical:
        return None
    return {
        "caseId": case_id,
        "attempt": attempt,
        "action": "code",
        "source": canonical,
        "clarifications": [],
    }


def _validate_tasks(tasks: Sequence[Mapping[str, Any]]) -> None:
    if not tasks:
        raise ValueError("task JSONL is empty")
    seen: set[str] = set()
    for index, task in enumerate(tasks, start=1):
        case_id = task.get("caseId")
        if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(case_id):
            raise ValueError(f"task {index} has an unsafe caseId")
        if case_id in seen:
            raise ValueError(f"duplicate task caseId: {case_id}")
        seen.add(case_id)


def _write_log(output_dir: Path, result: ModelRun) -> None:
    payload = {
        "caseId": result.case_id,
        "durationSeconds": round(result.duration_seconds, 3),
        "error": result.error,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    (output_dir / "logs" / f"{result.case_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )


def _write_checkpoint(
    output_dir: Path,
    tasks: Sequence[Mapping[str, Any]],
    results: Mapping[int, ModelRun],
    metadata: Mapping[str, Any],
    *,
    prior_responses: Sequence[Mapping[str, Any]] = (),
) -> None:
    ordered = [results[index] for index in sorted(results)]
    new_responses = [result.response for result in ordered if result.response is not None]
    responses = [*prior_responses, *cast(list[Mapping[str, Any]], new_responses)]
    write_jsonl(responses, output_dir / "responses.jsonl")
    failures = [
        {"caseId": result.case_id, "error": result.error}
        for result in ordered
        if result.error is not None
    ]
    run = {
        **metadata,
        "completedCaseCount": len(results),
        "successfulCaseCount": len(new_responses),
        "failedCaseCount": len(failures),
        "totalResponseCount": len(responses),
        "failures": failures,
        "taskCaseIds": [str(task["caseId"]) for task in tasks],
    }
    (output_dir / "run.json").write_text(
        json.dumps(run, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    )


def _codex_version() -> str:
    completed = subprocess.run(
        ["codex", "--version"],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("codex --version failed")
    return completed.stdout.strip()


def _subprocess_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
