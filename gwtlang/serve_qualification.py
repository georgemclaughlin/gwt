"""Repeatable qualification of a served GWT decision boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import signal
import subprocess
import sys
import tempfile
from threading import Thread
import time
from typing import TextIO, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .case_corpus import CaseCorpus, load_case_corpus
from .program_identity import load_program_snapshot
from .runtime import ImportPolicy


SERVE_QUALIFICATION_SCHEMA_VERSION = 1
_STARTUP_PATTERN = re.compile(r" at (http://\S+)$")


@dataclass(frozen=True)
class QualificationCheck:
    name: str
    ok: bool
    detail: str
    evidence: dict[str, object]

    def as_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class QualificationCaseResult:
    reference: str
    case_id: str
    request: str
    status: int
    ok: bool
    detail: str

    def as_payload(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "caseId": self.case_id,
            "request": self.request,
            "status": self.status,
            "ok": self.ok,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ServeQualificationResult:
    program_file: str
    program_digest: str
    program_identity_algorithm: str
    corpus_file: str
    corpus: CaseCorpus
    engine: str
    checks: tuple[QualificationCheck, ...]
    cases: tuple[QualificationCaseResult, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks) and all(
            case.ok for case in self.cases
        )

    def as_payload(self) -> dict[str, object]:
        corpus_payload = self.corpus.as_payload()
        return {
            "schemaVersion": SERVE_QUALIFICATION_SCHEMA_VERSION,
            "kind": "gwt.serve-qualification",
            "ok": self.ok,
            "engine": self.engine,
            "program": {
                "file": self.program_file,
                "digest": self.program_digest,
                "identityAlgorithm": self.program_identity_algorithm,
            },
            "corpus": {
                "file": self.corpus_file,
                "name": self.corpus.name,
                "digest": corpus_payload["integrity"]["digest"],
                "cases": len(self.corpus.entries),
            },
            "checks": [check.as_payload() for check in self.checks],
            "cases": [case.as_payload() for case in self.cases],
        }


@dataclass
class _ServerProcess:
    process: subprocess.Popen[str]
    base_url: str
    diagnostic: TextIO


@dataclass(frozen=True)
class _HttpResponse:
    status: int
    payload: object
    headers: dict[str, str]


def qualify_served_program(
    program: str | Path,
    corpus_path: str | Path,
    *,
    engine: str = "asgi",
    import_roots: tuple[str | Path, ...] = (),
    allow_absolute_imports: bool = True,
    timeout_seconds: float = 10.0,
) -> ServeQualificationResult:
    """Run the complete local served-decision qualification workflow."""

    if engine != "asgi":
        raise ValueError("serve qualification currently supports only the ASGI engine")
    if timeout_seconds <= 0:
        raise ValueError("qualification timeout must be positive")

    displayed_program = str(program)
    displayed_corpus = str(corpus_path)
    program_path = Path(program).resolve()
    roots = tuple(Path(root).resolve() for root in import_roots)
    policy = ImportPolicy(roots, allow_absolute_imports)
    snapshot = load_program_snapshot(program_path, import_policy=policy)
    corpus = load_case_corpus(Path(corpus_path).resolve())
    _validate_corpus(corpus)

    checks: list[QualificationCheck] = []
    case_results: list[QualificationCaseResult] = []
    server: _ServerProcess | None = None
    routes: dict[str, str] = {}
    try:
        server = _start_server(
            _serve_command(
                program_path,
                engine=engine,
                import_roots=roots,
                allow_absolute_imports=allow_absolute_imports,
            ),
            timeout_seconds=timeout_seconds,
        )
        checks.append(
            QualificationCheck(
                "startup",
                True,
                "gwt serve started the ASGI process",
                {"engine": engine},
            )
        )
        ready = _wait_for_ready(server, timeout_seconds)
        checks.append(_readiness_check(ready))

        openapi = _request_json(f"{server.base_url}/openapi.json", timeout_seconds)
        requests = _request_json(f"{server.base_url}/requests", timeout_seconds)
        checks.append(
            _identity_check(
                snapshot.identity.digest,
                ready,
                openapi,
                requests,
            )
        )
        routes, openapi_check = _openapi_routes(openapi, requests, corpus)
        checks.append(openapi_check)
        case_results = _run_corpus(
            server.base_url,
            corpus,
            routes,
            snapshot.identity.digest,
            timeout_seconds,
        )
        passed = sum(result.ok for result in case_results)
        checks.append(
            QualificationCheck(
                "corpus",
                passed == len(case_results),
                f"served corpus replay passed {passed}/{len(case_results)} cases",
                {"passed": passed, "failed": len(case_results) - passed},
            )
        )
    except Exception as exc:
        checks.append(
            QualificationCheck(
                "runtime_boundary",
                False,
                f"served qualification stopped: {_safe_error(exc)}",
                {},
            )
        )
    finally:
        if server is not None:
            exit_code = _terminate(server.process, timeout_seconds)
            accepted_exit_codes = {0, -signal.SIGTERM}
            checks.append(
                QualificationCheck(
                    "process_shutdown",
                    exit_code in accepted_exit_codes,
                    f"ordinary ASGI process shutdown exited with status {exit_code}",
                    {"exitCode": exit_code},
                )
            )
            _close_server(server)

    first_entry = corpus.entries[0]
    overload, active_shutdown = _controlled_lifecycle_checks(
        program_path,
        first_entry.execution_case.request_name,
        cast(dict[str, object], first_entry.execution_case.input),
        first_entry.execution_case.result,
        import_roots=roots,
        allow_absolute_imports=allow_absolute_imports,
        timeout_seconds=timeout_seconds,
    )
    checks.extend((overload, active_shutdown))

    return ServeQualificationResult(
        program_file=displayed_program,
        program_digest=snapshot.identity.digest,
        program_identity_algorithm=snapshot.identity.algorithm,
        corpus_file=displayed_corpus,
        corpus=corpus,
        engine=engine,
        checks=tuple(checks),
        cases=tuple(case_results),
    )


def _validate_corpus(corpus: CaseCorpus) -> None:
    for entry in corpus.entries:
        execution_case = entry.execution_case
        if execution_case.outcome != "completed":
            raise ValueError(
                f"qualification corpus case {entry.reference!r} did not complete"
            )
        payload = execution_case.as_payload()
        if payload["execution"]["capturePolicy"]["values"] != "full":
            raise ValueError(
                f"qualification corpus case {entry.reference!r} omits replay values"
            )


def _serve_command(
    program: Path,
    *,
    engine: str,
    import_roots: tuple[Path, ...],
    allow_absolute_imports: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "gwtlang",
        "serve",
        str(program),
        "--engine",
        engine,
        "--host",
        "127.0.0.1",
        "--port",
        "0",
    ]
    return _append_import_policy(command, import_roots, allow_absolute_imports)


def _start_server(command: list[str], *, timeout_seconds: float) -> _ServerProcess:
    diagnostic = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=diagnostic,
            text=True,
            env=dict(os.environ),
        )
    except Exception:
        diagnostic.close()
        raise
    stdout = process.stdout
    if stdout is None:
        _terminate(process, timeout_seconds)
        diagnostic.close()
        raise RuntimeError("serve process did not expose startup output")
    startup: Queue[str] = Queue()
    Thread(target=lambda: startup.put(stdout.readline()), daemon=True).start()
    try:
        line = startup.get(timeout=timeout_seconds)
    except Empty as exc:
        _terminate(process, timeout_seconds)
        detail = _process_error(process, diagnostic)
        stdout.close()
        diagnostic.close()
        raise RuntimeError(
            f"timed out waiting for serve process startup: {detail}"
        ) from exc
    match = _STARTUP_PATTERN.search(line.strip())
    if match is None:
        _terminate(process, timeout_seconds)
        detail = _process_error(process, diagnostic)
        stdout.close()
        diagnostic.close()
        raise RuntimeError(
            f"serve process failed to start: {line.strip()} {detail}".strip()
        )
    return _ServerProcess(process, match.group(1), diagnostic)


def _wait_for_ready(server: _ServerProcess, timeout_seconds: float) -> _HttpResponse:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if server.process.poll() is not None:
            raise RuntimeError(
                "serve process exited before readiness: "
                f"{_process_error(server.process, server.diagnostic)}"
            )
        try:
            response = _request_json(
                f"{server.base_url}/ready",
                min(1.0, timeout_seconds),
            )
            if response.status == 200:
                return response
        except (OSError, URLError) as exc:
            last_error = exc
        time.sleep(0.02)
    detail = f": {_safe_error(last_error)}" if last_error is not None else ""
    raise RuntimeError(f"timed out waiting for readiness{detail}")


def _readiness_check(response: _HttpResponse) -> QualificationCheck:
    payload = _object_payload(response.payload)
    ok = (
        response.status == 200
        and payload.get("ready") is True
        and payload.get("accepting") is True
        and payload.get("inFlight") == 0
    )
    return QualificationCheck(
        "readiness",
        ok,
        "readiness reports an accepting process with no active evaluations",
        {
            "status": response.status,
            "ready": payload.get("ready"),
            "accepting": payload.get("accepting"),
            "inFlight": payload.get("inFlight"),
        },
    )


def _identity_check(
    expected_digest: str,
    ready: _HttpResponse,
    openapi: _HttpResponse,
    requests: _HttpResponse,
) -> QualificationCheck:
    ready_payload = _object_payload(ready.payload)
    openapi_payload = _object_payload(openapi.payload)
    requests_payload = _object_payload(requests.payload)
    extension = _object_payload(openapi_payload.get("x-gwt"))
    extension_digest = extension.get("programDigest")
    observed = (
        ready_payload.get("programDigest"),
        ready.headers.get("x-gwt-program-digest"),
        openapi.headers.get("x-gwt-program-digest"),
        requests.headers.get("x-gwt-program-digest"),
        requests_payload.get("programDigest"),
        extension_digest,
    )
    matching = sum(value == expected_digest for value in observed)
    ok = openapi.status == 200 and requests.status == 200 and matching == len(observed)
    return QualificationCheck(
        "program_identity",
        ok,
        "local closure, operator endpoints, OpenAPI, and response headers agree",
        {
            "digest": expected_digest,
            "observations": len(observed),
            "matching": matching,
        },
    )


def _openapi_routes(
    openapi: _HttpResponse,
    requests: _HttpResponse,
    corpus: CaseCorpus,
) -> tuple[dict[str, str], QualificationCheck]:
    routes: dict[str, str] = {}
    openapi_payload = _object_payload(openapi.payload)
    paths = _object_payload(openapi_payload.get("paths"))
    for path, path_item_value in paths.items():
        path_item = _object_payload(path_item_value)
        post = path_item.get("post")
        post_payload = _object_payload(post)
        request_name = post_payload.get("x-gwt-request-name")
        if isinstance(request_name, str):
            routes[request_name] = path

    listed: dict[str, str] = {}
    requests_payload = _object_payload(requests.payload)
    request_items = requests_payload.get("requests")
    if isinstance(request_items, list):
        for item_value in cast(list[object], request_items):
            item = _object_payload(item_value)
            name = item.get("name")
            path = item.get("path")
            if isinstance(name, str) and isinstance(path, str):
                listed[name] = path

    needed = {entry.execution_case.request_name for entry in corpus.entries}
    missing = sorted(needed - routes.keys())
    disagreements = sorted(
        name for name in routes.keys() | listed.keys() if routes.get(name) != listed.get(name)
    )
    ok = openapi.status == 200 and requests.status == 200 and not missing and not disagreements
    detail = (
        f"OpenAPI and /requests agree for {len(needed)} corpus request(s)"
        if ok
        else "served route discovery is incomplete or inconsistent"
    )
    return routes, QualificationCheck(
        "openapi",
        ok,
        detail,
        {
            "discoveredRoutes": len(routes),
            "corpusRequests": len(needed),
            "missing": missing,
            "disagreements": disagreements,
        },
    )


def _run_corpus(
    base_url: str,
    corpus: CaseCorpus,
    routes: dict[str, str],
    expected_digest: str,
    timeout_seconds: float,
) -> list[QualificationCaseResult]:
    results: list[QualificationCaseResult] = []
    for entry in corpus.entries:
        execution_case = entry.execution_case
        route = routes.get(execution_case.request_name)
        if route is None:
            results.append(
                QualificationCaseResult(
                    entry.reference,
                    entry.case_id,
                    execution_case.request_name,
                    0,
                    False,
                    "OpenAPI route is missing",
                )
            )
            continue
        try:
            response = _request_json(
                f"{base_url}{route}",
                timeout_seconds,
                payload=cast(dict[str, object], execution_case.input),
            )
            digest_matches = (
                response.headers.get("x-gwt-program-digest") == expected_digest
            )
            ok = response.status == 200 and response.payload == execution_case.result and digest_matches
            if response.status != 200:
                detail = f"served request returned HTTP {response.status}"
            elif not digest_matches:
                detail = "served response program digest did not match"
            elif response.payload != execution_case.result:
                detail = "served result did not match the recorded result"
            else:
                detail = "served result matched the recorded result"
            results.append(
                QualificationCaseResult(
                    entry.reference,
                    entry.case_id,
                    execution_case.request_name,
                    response.status,
                    ok,
                    detail,
                )
            )
        except Exception as exc:
            results.append(
                QualificationCaseResult(
                    entry.reference,
                    entry.case_id,
                    execution_case.request_name,
                    0,
                    False,
                    f"served request failed: {_safe_error(exc)}",
                )
            )
    return results


def _controlled_lifecycle_checks(
    program: Path,
    request_name: str,
    request_input: dict[str, object],
    expected_result: Mapping[str, object],
    *,
    import_roots: tuple[Path, ...],
    allow_absolute_imports: bool,
    timeout_seconds: float,
) -> tuple[QualificationCheck, QualificationCheck]:
    with tempfile.TemporaryDirectory(prefix="gwt-serve-qualification-") as temp_dir:
        root = Path(temp_dir)
        marker = root / "admitted"
        release = root / "release"
        command = [
            sys.executable,
            "-m",
            "gwtlang.serve_qualification_probe",
            str(program),
            "--host",
            "127.0.0.1",
            "--port",
            "0",
            "--marker",
            str(marker),
            "--release",
            str(release),
            "--hold-timeout",
            str(timeout_seconds),
        ]
        command = _append_import_policy(command, import_roots, allow_absolute_imports)
        server: _ServerProcess | None = None
        first_response: list[_HttpResponse] = []
        first_error: list[Exception] = []
        first_thread: Thread | None = None
        try:
            server = _start_server(command, timeout_seconds=timeout_seconds)
            ready = _wait_for_ready(server, timeout_seconds)
            openapi = _request_json(f"{server.base_url}/openapi.json", timeout_seconds)
            routes, route_check = _openapi_routes_for_names(openapi, {request_name})
            if not route_check.ok:
                raise RuntimeError(route_check.detail)
            route = routes[request_name]

            def run_first() -> None:
                try:
                    first_response.append(
                        _request_json(
                            f"{server.base_url}{route}",
                            timeout_seconds + 2,
                            payload=request_input,
                        )
                    )
                except Exception as exc:
                    first_error.append(exc)

            first_thread = Thread(target=run_first, daemon=True)
            first_thread.start()
            _wait_for_file(marker, server, timeout_seconds)
            during = _request_json(f"{server.base_url}/ready", timeout_seconds)
            overloaded = _request_json(
                f"{server.base_url}{route}",
                timeout_seconds,
                payload=request_input,
            )
            overloaded_payload = _object_payload(overloaded.payload)
            error = _object_payload(overloaded_payload.get("error"))
            code = error.get("code")
            during_payload = _object_payload(during.payload)
            overload_ok = (
                ready.status == 200
                and during_payload.get("inFlight") == 1
                and overloaded.status == 503
                and overloaded.headers.get("retry-after") == "1"
                and code == "GWT_HTTP_UNAVAILABLE"
            )
            overload_check = QualificationCheck(
                "overload",
                overload_ok,
                "a second request was rejected while one evaluation held the only slot",
                {
                    "inFlight": during_payload.get("inFlight"),
                    "status": overloaded.status,
                    "retryAfter": overloaded.headers.get("retry-after"),
                    "errorCode": code,
                },
            )

            server.process.send_signal(signal.SIGTERM)
            release.write_text("continue\n", encoding="utf-8")
            first_thread.join(timeout_seconds + 2)
            exit_code = _wait_process(server.process, timeout_seconds + 2)
            response = first_response[0] if first_response else None
            active_ok = (
                not first_thread.is_alive()
                and not first_error
                and response is not None
                and response.status == 200
                and response.payload == expected_result
                and exit_code in {0, -signal.SIGTERM}
            )
            shutdown_check = QualificationCheck(
                "active_shutdown",
                active_ok,
                "SIGTERM allowed the admitted evaluation to return before ASGI exit",
                {
                    "requestStatus": response.status if response is not None else 0,
                    "exitCode": exit_code,
                    "requestCompleted": response is not None and not first_thread.is_alive(),
                },
            )
            return overload_check, shutdown_check
        except Exception as exc:
            detail = _safe_error(exc)
            return (
                QualificationCheck("overload", False, f"overload probe failed: {detail}", {}),
                QualificationCheck(
                    "active_shutdown",
                    False,
                    f"active shutdown probe failed: {detail}",
                    {},
                ),
            )
        finally:
            release.write_text("continue\n", encoding="utf-8")
            if first_thread is not None:
                first_thread.join(timeout=1)
            if server is not None:
                _terminate(server.process, timeout_seconds)
                _close_server(server)


def _openapi_routes_for_names(
    openapi: _HttpResponse,
    names: set[str],
) -> tuple[dict[str, str], QualificationCheck]:
    routes: dict[str, str] = {}
    payload = _object_payload(openapi.payload)
    paths = _object_payload(payload.get("paths"))
    for path, path_item_value in paths.items():
        path_item = _object_payload(path_item_value)
        post = _object_payload(path_item.get("post"))
        name = post.get("x-gwt-request-name")
        if isinstance(name, str):
            routes[name] = path
    missing = sorted(names - routes.keys())
    return routes, QualificationCheck(
        "openapi",
        openapi.status == 200 and not missing,
        "controlled probe discovered its route through OpenAPI",
        {"missing": missing},
    )


def _request_json(
    url: str,
    timeout_seconds: float,
    *,
    payload: Mapping[str, object] | None = None,
) -> _HttpResponse:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            return _HttpResponse(
                response.status,
                json.loads(body.decode("utf-8")),
                {key.lower(): value for key, value in response.headers.items()},
            )
    except HTTPError as exc:
        try:
            body = exc.read()
            return _HttpResponse(
                exc.code,
                json.loads(body.decode("utf-8")),
                {key.lower(): value for key, value in exc.headers.items()},
            )
        finally:
            exc.close()


def _append_import_policy(
    command: list[str],
    import_roots: tuple[Path, ...],
    allow_absolute_imports: bool,
) -> list[str]:
    result = list(command)
    for root in import_roots:
        result.extend(("--import-root", str(root)))
    if not allow_absolute_imports:
        result.append("--no-absolute-imports")
    return result


def _wait_for_file(path: Path, server: _ServerProcess, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return
        if server.process.poll() is not None:
            raise RuntimeError(
                "controlled probe exited early: "
                f"{_process_error(server.process, server.diagnostic)}"
            )
        time.sleep(0.01)
    raise RuntimeError("timed out waiting for controlled evaluation admission")


def _terminate(process: subprocess.Popen[str], timeout_seconds: float) -> int:
    if process.poll() is None:
        process.terminate()
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        return process.wait(timeout=timeout_seconds)


def _wait_process(process: subprocess.Popen[str], timeout_seconds: float) -> int:
    try:
        return process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("serve process did not exit after SIGTERM") from exc


def _process_error(process: subprocess.Popen[str], diagnostic: TextIO) -> str:
    if process.poll() is None:
        return "no process diagnostic"
    diagnostic.flush()
    diagnostic.seek(0)
    text = diagnostic.read().strip()
    if not text:
        return f"exit status {process.returncode}"
    return text.splitlines()[-1]


def _close_server(server: _ServerProcess) -> None:
    if server.process.stdout is not None:
        server.process.stdout.close()
    server.diagnostic.close()


def _safe_error(error: object) -> str:
    text = str(error).strip()
    return text.splitlines()[0] if text else type(error).__name__


def _object_payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, object], value)
