from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import subprocess
import sys
from threading import Thread
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from gwtlang import (
    ExecutionCase,
    compare_execution_cases,
    render_workbench_html,
)


PILOT_DIR = Path(__file__).resolve().parent
REPO_ROOT = PILOT_DIR.parents[2]
RULES = PILOT_DIR / "rules.gwt"
CASES = PILOT_DIR / "conformance_cases.json"
FACT_PROVENANCE = PILOT_DIR / "evaluated-fact-provenance.json"
REQUEST_NAME = "select release from evaluated rules"
REQUEST_ROUTE = "/requests/select-release-from-evaluated-rules"
CASE_ID_PATTERN = re.compile(r"^sha256:([0-9a-f]{64})$")
MUTATION_BEFORE = "IF rank > result.release_rank"
MUTATION_AFTER = "IF rank < result.release_rank"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture the semantic-release pilot corpus through gwt serve, then "
            "compare and render the evidence against an intentional local mutation."
        )
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="New or empty directory for cases, comparison JSON, and workbench HTML.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    if output_dir.exists() and not output_dir.is_dir():
        parser.error(f"output path is not a directory: {output_dir}")
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    case_dir = output_dir / "cases"
    case_dir.mkdir()

    fixture = cast(dict[str, Any], json.loads(CASES.read_text()))
    fixture_cases = cast(list[dict[str, Any]], fixture["cases"])
    server = _start_server(case_dir)
    captured: list[ExecutionCase] = []
    case_manifest: list[dict[str, object]] = []
    try:
        for fixture_case in fixture_cases:
            pilot_case_id = cast(str, fixture_case["id"])
            request_input: dict[str, object] = {
                "evaluations": _snapshot_evaluations(fixture_case),
            }
            response, case_id = _post_decision(server.base_url, request_input)
            expected = cast(dict[str, str], fixture_case["expected"])["upstream"]
            actual = cast(dict[str, Any], response["result"])["release"]
            if actual != expected:
                raise RuntimeError(
                    f"{pilot_case_id}: served release {actual!r}, expected {expected!r}"
                )

            case_path = _case_path(case_dir, case_id)
            execution_case = ExecutionCase.load(case_path)
            payload = execution_case.as_payload()
            if payload["integrity"]["digest"] != case_id:
                raise RuntimeError(f"{pilot_case_id}: response case ID does not match artifact")
            if execution_case.input != request_input:
                raise RuntimeError(f"{pilot_case_id}: captured input does not match HTTP input")
            if execution_case.result != response:
                raise RuntimeError(f"{pilot_case_id}: captured result does not match HTTP response")
            if not execution_case.fact_provenance:
                raise RuntimeError(f"{pilot_case_id}: static fact provenance was not captured")

            captured.append(execution_case)
            case_manifest.append(
                {
                    "pilotCaseId": pilot_case_id,
                    "executionCaseId": case_id,
                    "artifact": str(case_path.relative_to(output_dir)),
                    "release": cast(str, actual),
                }
            )
    finally:
        _stop_server(server)

    candidate = output_dir / "candidate-rules.gwt"
    candidate.write_text(_mutated_candidate_source())
    comparison = compare_execution_cases(RULES, candidate, captured)
    comparison_payload = comparison.as_payload()
    for manifest_item, compared_item in zip(
        case_manifest,
        comparison_payload["cases"],
        strict=True,
    ):
        manifest_item["classification"] = compared_item["classification"]
        manifest_item["outputDifferencePaths"] = [
            difference["path"] for difference in compared_item["outputDifferences"]
        ]
    comparison_path = output_dir / "comparison.json"
    _write_json(comparison_path, comparison_payload)

    workbench_path = output_dir / "workbench.html"
    workbench_path.write_text(
        render_workbench_html(
            captured[0],
            comparison=comparison,
            review_notice=(
                "Local evidence lifecycle demo. The candidate intentionally inverts "
                "the named-release priority comparison and is not an upstream proposal."
            ),
            old_label="Pinned GWT semantic-release pilot",
            new_label="Intentional inverted-priority candidate",
        )
    )

    classifications = Counter(
        item["classification"] for item in comparison_payload["cases"]
    )
    changed = len(captured) - classifications["unchanged"]
    changed_pilot_ids = [
        cast(str, item["pilotCaseId"])
        for item in case_manifest
        if item["classification"] != "unchanged"
    ]
    if changed == 0:
        raise RuntimeError("intentional candidate mutation produced no comparison changes")

    manifest = {
        "kind": "gwt.external-pilot-served-evidence-demo",
        "source": fixture["source"],
        "request": REQUEST_NAME,
        "capture": {
            "values": "full",
            "factProvenance": str(FACT_PROVENANCE.relative_to(REPO_ROOT)),
        },
        "cases": case_manifest,
        "candidate": {
            "artifact": candidate.name,
            "mutation": f"{MUTATION_BEFORE} -> {MUTATION_AFTER}",
        },
        "comparison": {
            "artifact": comparison_path.name,
            "totals": comparison_payload["totals"],
        },
        "workbench": workbench_path.name,
    }
    _write_json(output_dir / "manifest.json", manifest)

    print(f"served Execution Cases captured: {len(captured)}/{len(fixture_cases)}")
    print(f"candidate comparisons changed: {changed}/{len(captured)}")
    print(f"changed pilot cases: {', '.join(changed_pilot_ids)}")
    print(f"evidence manifest: {output_dir / 'manifest.json'}")
    print(f"review workbench: {workbench_path}")
    return 0


def _snapshot_evaluations(case: dict[str, Any]) -> list[dict[str, object]]:
    rules = cast(list[dict[str, Any]], case["rules"])
    matches = cast(list[bool], case["host_matches"])
    if len(rules) != len(matches):
        raise ValueError(f"{case['id']}: host match snapshot has the wrong length")
    return [
        {
            "id": f"rule-{index}",
            "matched": matched,
            "release": _release_token(rule.get("release")),
        }
        for index, (rule, matched) in enumerate(zip(rules, matches), start=1)
    ]


def _release_token(value: object) -> str:
    if value is None:
        return "null"
    if value is False:
        return "false"
    if isinstance(value, str):
        return value
    raise ValueError(f"unsupported release outcome: {value!r}")


class _ServerProcess:
    def __init__(self, process: subprocess.Popen[str], base_url: str) -> None:
        self.process = process
        self.base_url = base_url


def _start_server(case_dir: Path) -> _ServerProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (str(REPO_ROOT), env.get("PYTHONPATH", ""))
        if part
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "gwtlang",
            "serve",
            str(RULES),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--import-root",
            str(PILOT_DIR),
            "--no-absolute-imports",
            "--capture-dir",
            str(case_dir),
            "--capture-request",
            REQUEST_NAME,
            "--capture-values",
            "--fact-provenance",
            str(FACT_PROVENANCE),
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout = process.stdout
    if stdout is None:
        raise RuntimeError("gwt serve did not expose its startup output")
    startup: Queue[str] = Queue()
    Thread(target=lambda: startup.put(stdout.readline()), daemon=True).start()
    try:
        line = startup.get(timeout=10)
    except Empty as exc:
        _terminate(process)
        detail = process.stderr.read() if process.stderr is not None else ""
        raise RuntimeError(f"timed out waiting for gwt serve startup: {detail}") from exc
    match = re.search(r" at (http://\S+)$", line.strip())
    if match is None:
        _terminate(process)
        detail = process.stderr.read() if process.stderr is not None else ""
        raise RuntimeError(f"gwt serve failed to start: {line.strip()} {detail}".strip())
    return _ServerProcess(process, match.group(1))


def _stop_server(server: _ServerProcess) -> None:
    _terminate(server.process)
    if server.process.stdout is not None:
        server.process.stdout.close()
    if server.process.stderr is not None:
        server.process.stderr.close()


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _post_decision(base_url: str, request_input: dict[str, object]) -> tuple[dict[str, Any], str]:
    request = Request(
        f"{base_url}{REQUEST_ROUTE}",
        data=json.dumps(request_input).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            payload = cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
            case_id = response.headers.get("x-gwt-case-id")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"served decision failed with HTTP {exc.code}: {detail}") from exc
    if case_id is None:
        raise RuntimeError("served decision did not return x-gwt-case-id")
    return payload, case_id


def _case_path(case_dir: Path, case_id: str) -> Path:
    match = CASE_ID_PATTERN.fullmatch(case_id)
    if match is None:
        raise RuntimeError(f"invalid x-gwt-case-id: {case_id!r}")
    case_path = case_dir / f"{match.group(1)}.execution-case.json"
    if not case_path.is_file():
        raise RuntimeError(f"x-gwt-case-id artifact is missing: {case_path}")
    return case_path


def _mutated_candidate_source() -> str:
    source = RULES.read_text()
    if source.count(MUTATION_BEFORE) != 1:
        raise RuntimeError("pilot rule source no longer has the expected mutation seam")
    return source.replace(MUTATION_BEFORE, MUTATION_AFTER)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
