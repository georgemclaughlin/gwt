from __future__ import annotations

import argparse
import json
from pathlib import Path
from queue import Empty, Queue
import re
import subprocess
import sys
import tempfile
from threading import Thread
import time
from typing import IO, Any, cast
from urllib.error import URLError
from urllib.request import urlopen


PILOT_DIR = Path(__file__).resolve().parent
ROOT = PILOT_DIR.parents[2]
RULES = PILOT_DIR / "rules.gwt"
SLICE = PILOT_DIR / "oracle_slice.json"
ORACLE = PILOT_DIR / "ruby_oracle.rb"
RUBY_CLIENT = PILOT_DIR / "openapi_ruby_client.rb"
UPSTREAM_COMMIT = "249dbf3c68461288f8444d754bcf27d0fa962250"
RUBY_IMAGE = "ruby:3.4.9-alpine"
OPENAPI_GENERATOR = "@openapitools/openapi-generator-cli@2.38.0"


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
    cwd: Path = ROOT,
) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}"
        )
    return completed.stdout


def _ruby_oracle(
    upstream_root: Path,
    cases: list[dict[str, Any]],
) -> dict[str, dict[str, object]]:
    oracle_input = [{"id": case["id"], **case["facts"]} for case in cases]
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
        input_text=json.dumps(oracle_input),
    )
    values = cast(list[dict[str, object]], json.loads(output))
    return {
        cast(str, item["id"]): {
            "eligible": item["eligible"],
            "first_error": item["first_error"],
            "error_count": item["error_count"],
        }
        for item in values
    }


def _assert_openapi(openapi_path: Path) -> None:
    document = cast(dict[str, Any], json.loads(openapi_path.read_text()))
    operation = document["paths"]["/requests/assess-item-total-eligibility"]["post"]
    if operation["operationId"] != "assessItemTotalEligibility":
        raise ValueError("unexpected Spree OpenAPI operation")
    facts = document["components"]["schemas"]["ItemTotalFacts"]
    if "amount_max" in facts["required"]:
        raise ValueError("optional amount_max must not be required")
    amount_max = facts["properties"]["amount_max"]
    if {"type": "null"} not in amount_max["anyOf"]:
        raise ValueError("optional amount_max must accept JSON null")


def _assert_generated_decimal_mapping(client_dir: Path) -> None:
    source = (
        client_dir
        / "lib/gwt_spree_client/models/item_total_facts_amount_min.rb"
    ).read_text()
    if ":'String'" not in source or ":'Float'" in source:
        raise ValueError(
            "generated Ruby decimal mapping must be String|Integer, not Float|Integer"
        )


def _read_startup_line(stream: IO[str], output: Queue[str]) -> None:
    output.put(stream.readline())


def _start_server() -> tuple[subprocess.Popen[str], int]:
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
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.stdout is None:
        raise RuntimeError("expected gwt serve stdout")
    output: Queue[str] = Queue()
    Thread(target=_read_startup_line, args=(process.stdout, output), daemon=True).start()
    try:
        line = output.get(timeout=10)
    except Empty as exc:
        process.terminate()
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise RuntimeError(f"gwt serve did not report startup URL\n{stderr}") from exc
    match = re.search(r"http://[^:]+:(\d+)", line)
    if match is None:
        process.terminate()
        raise RuntimeError(f"unexpected gwt serve startup output: {line!r}")
    port = int(match.group(1))
    for _ in range(50):
        try:
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                if response.status == 200:
                    return process, port
        except URLError:
            time.sleep(0.1)
    process.terminate()
    raise RuntimeError("gwt serve did not become healthy")


def _stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Spree oracle and GWT through a generated Ruby OpenAPI client"
    )
    parser.add_argument("upstream_root", type=Path, help="pinned local Spree checkout")
    args = parser.parse_args()
    upstream_root = args.upstream_root.resolve()
    commit = _run(["git", "-C", str(upstream_root), "rev-parse", "HEAD"]).strip()
    if commit != UPSTREAM_COMMIT:
        parser.error(f"upstream checkout must be pinned at {UPSTREAM_COMMIT}")

    fixture = cast(dict[str, Any], json.loads(SLICE.read_text()))
    cases = cast(list[dict[str, Any]], fixture["cases"])
    ruby_results = _ruby_oracle(upstream_root, cases)
    http_cases = [
        {
            "id": case["id"],
            "facts": case["facts"],
            "expected": ruby_results[cast(str, case["id"])],
        }
        for case in cases
    ]

    with tempfile.TemporaryDirectory(prefix="gwt-spree-openapi-") as temp:
        temp_dir = Path(temp)
        openapi_path = temp_dir / "openapi.json"
        client_dir = temp_dir / "client"
        _run(
            [
                sys.executable,
                "-m",
                "gwtlang",
                "openapi",
                str(RULES),
                "--output",
                str(openapi_path),
            ]
        )
        _assert_openapi(openapi_path)
        _run(
            [
                "npx",
                "--yes",
                OPENAPI_GENERATOR,
                "generate",
                "-i",
                str(openapi_path),
                "-g",
                "ruby",
                "-o",
                str(client_dir),
                "--additional-properties=gemName=gwt_spree_client,moduleName=GwtSpreeClient",
                "--global-property=apiDocs=false,modelDocs=false",
                "--type-mappings",
                "decimal=String",
            ],
            cwd=temp_dir,
        )
        _assert_generated_decimal_mapping(client_dir)

        server, port = _start_server()
        try:
            output = _run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-i",
                    "--network",
                    "host",
                    "-v",
                    f"{client_dir}:/client:ro",
                    "-v",
                    f"{PILOT_DIR}:/pilot:ro",
                    "-e",
                    f"GWT_BASE_URL=http://127.0.0.1:{port}",
                    RUBY_IMAGE,
                    "sh",
                    "-c",
                    (
                        "apk add --no-cache libcurl >/dev/null && "
                        "gem install typhoeus -v '~> 1.0' --no-document >/dev/null && "
                        "ruby -I/client/lib /pilot/openapi_ruby_client.rb \"$GWT_BASE_URL\""
                    ),
                ],
                input_text=json.dumps(http_cases),
            )
        finally:
            _stop_server(server)

    results = cast(list[dict[str, object]], json.loads(output))
    print(f"generated Ruby OpenAPI client/gwt serve parity: {len(results)}/{len(cases)}")
    print(f"upstream: spree/spree@{UPSTREAM_COMMIT}")
    print("decimal mapping: String|Integer; amount_max: optional|null")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
