from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
import time
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from gwtlang import (
    QualificationCheck,
    ServedEndpointQualificationResult,
    ServeQualificationResult,
    qualify_served_endpoint,
)
from gwtlang.serve_qualification import _load_qualification_inputs


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DOCKERFILE = SCRIPT_DIR / "Dockerfile"
CONTAINER_PROGRAM_ROOT = Path("/qualification/program")
CONTAINER_CONTROL_ROOT = Path("/qualification/control")
DOCKER_AUXILIARY_TIMEOUT_SECONDS = 5.0
_PYTHON_EXECUTABLE = re.compile(r"python(?:\d+(?:\.\d+)*)?")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the deployable GWT image and qualify a program/corpus through "
            "Docker-managed readiness, ports, overload, and SIGTERM."
        )
    )
    parser.add_argument("program", type=Path)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--program-root",
        type=Path,
        help="Root mounted read-only into the container; defaults to the program directory.",
    )
    parser.add_argument(
        "--dockerfile",
        type=Path,
        default=DEFAULT_DOCKERFILE,
        help="Dockerfile to build (default: examples/deployable_api/Dockerfile).",
    )
    parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=20.0,
        metavar="SECONDS",
        help="Startup, request, and shutdown timeout (default: 20s).",
    )
    parser.add_argument(
        "--keep-image",
        action="store_true",
        help="Keep the temporary qualification image after the run.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if shutil.which("docker") is None:
        parser.error("docker is required for container qualification")
    program = args.program.resolve()
    corpus = args.corpus.resolve()
    program_root = (args.program_root or program.parent).resolve()
    try:
        relative_program = program.relative_to(program_root)
    except ValueError:
        parser.error(f"program must be beneath --program-root: {program_root}")
    if not program.is_file():
        parser.error(f"program does not exist: {program}")
    if not corpus.is_file():
        parser.error(f"corpus does not exist: {corpus}")

    try:
        _program_path, _roots, snapshot, loaded_corpus = _load_qualification_inputs(
            program,
            corpus,
            import_roots=(program_root,),
            allow_absolute_imports=False,
        )
    except Exception as exc:
        parser.error(_safe_error(exc))

    suffix = uuid4().hex[:12]
    image_tag = f"gwt-serve-qualification:{suffix}"
    production_name = f"gwt-serve-production-{suffix}"
    controlled_name = f"gwt-serve-controlled-{suffix}"
    checks: list[QualificationCheck] = []
    endpoint = None
    try:
        image_id, configured_user, healthcheck_configured = _build_image(
            image_tag,
            args.dockerfile.resolve(),
            args.timeout,
        )
        image_ok = (
            configured_user not in {"", "0", "root"} and healthcheck_configured
        )
        checks.append(
            QualificationCheck(
                "container_image",
                image_ok,
                "deployable Docker image built with a non-root user and healthcheck",
                {
                    "imageId": image_id,
                    "configuredUser": configured_user,
                    "healthcheckConfigured": healthcheck_configured,
                },
            )
        )

        production_url = _start_production_container(
            production_name,
            image_tag,
            program_root,
            relative_program,
            args.timeout,
        )
        health = _wait_for_healthy(production_name, args.timeout)
        pid1_executable, pid1_argv = _container_pid1_identity(
            production_name,
            _auxiliary_timeout(args.timeout),
        )
        pid1_is_gwt = _is_gwt_pid1(pid1_executable, pid1_argv)
        checks.append(
            QualificationCheck(
                "container_health",
                health == "healthy" and pid1_is_gwt,
                "Docker health reached healthy and GWT/Uvicorn owns PID 1",
                {
                    "status": health,
                    "pid1IsGwt": pid1_is_gwt,
                    "pid1Executable": pid1_executable,
                    "pid1Argv": list(pid1_argv),
                },
            )
        )
        endpoint = qualify_served_endpoint(
            program,
            corpus,
            production_url,
            import_roots=(program_root,),
            allow_absolute_imports=False,
            timeout_seconds=args.timeout,
        )
        checks.extend(endpoint.checks)
        checks.append(_stop_check(production_name, args.timeout))

        overload, active_shutdown = _controlled_container_checks(
            controlled_name,
            image_tag,
            program_root,
            relative_program,
            endpoint,
            args.timeout,
        )
        checks.extend((overload, active_shutdown))
    except Exception as exc:
        checks.append(
            QualificationCheck(
                "container_boundary",
                False,
                f"container qualification stopped: {_safe_error(exc)}",
                {},
            )
        )
    finally:
        cleanup_timeout = _auxiliary_timeout(args.timeout)
        _remove_container(production_name, timeout=cleanup_timeout)
        _remove_container(controlled_name, timeout=cleanup_timeout)
        if not args.keep_image:
            _remove_image(image_tag, timeout=cleanup_timeout)

    result = ServeQualificationResult(
        program_file=str(args.program),
        program_digest=snapshot.identity.digest,
        program_identity_algorithm=snapshot.identity.algorithm,
        corpus_file=str(args.corpus),
        corpus=loaded_corpus,
        engine="asgi",
        checks=tuple(checks),
        cases=endpoint.cases if endpoint is not None else (),
    )
    if args.json:
        print(json.dumps(result.as_payload(), indent=2, sort_keys=True))
    else:
        for check in result.checks:
            print(f"{'PASS' if check.ok else 'FAIL'} {check.name}: {check.detail}")
        for case in result.cases:
            if not case.ok:
                print(f"FAIL case {case.reference}: {case.detail}")
        print(
            f"{'PASS' if result.ok else 'FAIL'} container qualification: "
            f"{len(result.cases)} corpus case(s)"
        )
    return 0 if result.ok else 1


def _build_image(
    image_tag: str,
    dockerfile: Path,
    timeout: float,
) -> tuple[str, str, bool]:
    completed = _run(
        [
            "docker",
            "build",
            "--quiet",
            "--file",
            str(dockerfile),
            "--tag",
            image_tag,
            str(REPO_ROOT),
        ],
        timeout=timeout * 6,
    )
    image_id = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    inspected = _docker_inspect(image_tag, image=True)
    if not image_id.startswith("sha256:"):
        image_id = cast(str, inspected.get("Id", ""))
    if not image_id.startswith("sha256:"):
        raise RuntimeError("Docker build did not return an image ID")
    config = _mapping(inspected.get("Config"))
    configured_user = config.get("User")
    healthcheck = _mapping(config.get("Healthcheck"))
    healthcheck_test = healthcheck.get("Test")
    healthcheck_configured = (
        isinstance(healthcheck_test, list)
        and len(cast(list[object], healthcheck_test)) > 0
    )
    return (
        image_id,
        configured_user if isinstance(configured_user, str) else "",
        healthcheck_configured,
    )


def _start_production_container(
    name: str,
    image_tag: str,
    program_root: Path,
    relative_program: Path,
    timeout: float,
) -> str:
    container_program = CONTAINER_PROGRAM_ROOT / relative_program
    serve_args = (
        "--import-root /qualification/program --no-absolute-imports "
        f"--shutdown-grace-seconds {timeout:g}"
    )
    _run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            name,
            "--label",
            "gwt.qualification=true",
            "--publish",
            "127.0.0.1::8080",
            "--mount",
            _bind_mount(program_root, CONTAINER_PROGRAM_ROOT, readonly=True),
            "--env",
            f"GWT_RULES={container_program.as_posix()}",
            "--env",
            "GWT_ENGINE=asgi",
            "--env",
            f"GWT_SERVE_ARGS={serve_args}",
            image_tag,
        ],
        timeout=timeout,
    )
    return _container_url(name)


def _controlled_container_checks(
    name: str,
    image_tag: str,
    program_root: Path,
    relative_program: Path,
    endpoint: ServedEndpointQualificationResult,
    timeout: float,
) -> tuple[QualificationCheck, QualificationCheck]:
    first_entry = endpoint.corpus.entries[0]
    execution_case = first_entry.execution_case
    request_input = cast(dict[str, object], execution_case.input)
    expected_result = execution_case.result
    with tempfile.TemporaryDirectory(prefix="gwt-container-control-") as temp_dir:
        control_root = Path(temp_dir)
        control_root.chmod(0o777)
        marker = control_root / "admitted"
        release = control_root / "release"
        container_program = CONTAINER_PROGRAM_ROOT / relative_program
        _run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--label",
                "gwt.qualification=true",
                "--publish",
                "127.0.0.1::8080",
                "--mount",
                _bind_mount(program_root, CONTAINER_PROGRAM_ROOT, readonly=True),
                "--mount",
                _bind_mount(control_root, CONTAINER_CONTROL_ROOT),
                image_tag,
                "python",
                "-m",
                "gwtlang.serve_qualification_probe",
                container_program.as_posix(),
                "--host",
                "0.0.0.0",
                "--port",
                "8080",
                "--marker",
                (CONTAINER_CONTROL_ROOT / "admitted").as_posix(),
                "--release",
                (CONTAINER_CONTROL_ROOT / "release").as_posix(),
                "--hold-timeout",
                str(timeout),
                "--import-root",
                CONTAINER_PROGRAM_ROOT.as_posix(),
                "--no-absolute-imports",
            ],
            timeout=timeout,
        )
        base_url = _container_url(name)
        _wait_for_healthy(name, timeout)
        route = _route_for_request(base_url, execution_case.request_name, timeout)
        first_response: list[_HttpResponse] = []
        first_error: list[Exception] = []

        def send_first() -> None:
            try:
                first_response.append(
                    _http_json(
                        f"{base_url}{route}",
                        timeout + 2,
                        payload=request_input,
                    )
                )
            except Exception as exc:
                first_error.append(exc)

        request_thread = Thread(target=send_first, daemon=True)
        request_thread.start()
        _wait_for_path(marker, name, timeout)
        during = _http_json(f"{base_url}/ready", timeout)
        overloaded = _http_json(
            f"{base_url}{route}",
            timeout,
            payload=request_input,
        )
        during_payload = _mapping(during.payload)
        error_payload = _mapping(_mapping(overloaded.payload).get("error"))
        overload_ok = (
            during_payload.get("inFlight") == 1
            and overloaded.status == 503
            and overloaded.headers.get("retry-after") == "1"
            and error_payload.get("code") == "GWT_HTTP_UNAVAILABLE"
        )
        overload = QualificationCheck(
            "container_overload",
            overload_ok,
            "Docker-published ASGI endpoint rejected work above its one-slot limit",
            {
                "inFlight": during_payload.get("inFlight"),
                "status": overloaded.status,
                "retryAfter": overloaded.headers.get("retry-after"),
                "errorCode": error_payload.get("code"),
            },
        )

        _run(["docker", "kill", "--signal", "TERM", name], timeout=timeout)
        release.write_text("continue\n", encoding="utf-8")
        request_thread.join(timeout + 2)
        state = _wait_for_stopped(name, timeout + 2)
        response = first_response[0] if first_response else None
        exit_code = state.get("ExitCode")
        oom_killed = state.get("OOMKilled")
        active_ok = (
            not request_thread.is_alive()
            and not first_error
            and response is not None
            and response.status == 200
            and response.payload == expected_result
            and exit_code == 0
            and oom_killed is False
        )
        active_shutdown = QualificationCheck(
            "container_active_shutdown",
            active_ok,
            "Docker-delivered SIGTERM preserved the admitted response and exited cleanly",
            {
                "signal": "SIGTERM",
                "requestStatus": response.status if response is not None else 0,
                "requestCompleted": response is not None and not request_thread.is_alive(),
                "exitCode": exit_code,
                "oomKilled": oom_killed,
            },
        )
        return overload, active_shutdown


def _stop_check(name: str, timeout: float) -> QualificationCheck:
    _run(["docker", "stop", "--time", str(max(1, int(timeout))), name], timeout=timeout + 2)
    state = _container_state(name)
    exit_code = state.get("ExitCode")
    oom_killed = state.get("OOMKilled")
    ok = exit_code == 0 and oom_killed is False
    return QualificationCheck(
        "container_shutdown",
        ok,
        "docker stop delivered SIGTERM and the ordinary ASGI container exited cleanly",
        {"exitCode": exit_code, "oomKilled": oom_killed},
    )


def _wait_for_healthy(name: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    last_status = "starting"
    while time.monotonic() < deadline:
        state = _container_state(name)
        if state.get("Running") is not True:
            raise RuntimeError(
                "container exited before healthcheck: "
                f"{_container_log_tail(name, _auxiliary_timeout(timeout))}"
            )
        health = _mapping(state.get("Health"))
        status = health.get("Status")
        if isinstance(status, str):
            last_status = status
        if last_status == "healthy":
            return last_status
        if last_status == "unhealthy":
            raise RuntimeError(
                "container healthcheck failed: "
                f"{_container_log_tail(name, _auxiliary_timeout(timeout))}"
            )
        time.sleep(0.05)
    raise RuntimeError(f"timed out waiting for Docker healthcheck ({last_status})")


def _wait_for_stopped(name: str, timeout: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = _container_state(name)
        if state.get("Running") is False:
            return state
        time.sleep(0.02)
    raise RuntimeError("container did not stop after SIGTERM")


def _wait_for_path(path: Path, name: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if _container_state(name).get("Running") is not True:
            raise RuntimeError(
                "controlled container exited before admission: "
                f"{_container_log_tail(name, _auxiliary_timeout(timeout))}"
            )
        time.sleep(0.01)
    raise RuntimeError("timed out waiting for controlled container admission")


def _route_for_request(base_url: str, request_name: str, timeout: float) -> str:
    response = _http_json(f"{base_url}/openapi.json", timeout)
    paths = _mapping(_mapping(response.payload).get("paths"))
    for path, path_item_value in paths.items():
        post = _mapping(_mapping(path_item_value).get("post"))
        if post.get("x-gwt-request-name") == request_name:
            return path
    raise RuntimeError(f"controlled container OpenAPI omitted request: {request_name}")


class _HttpResponse:
    def __init__(self, status: int, payload: object, headers: dict[str, str]) -> None:
        self.status = status
        self.payload = payload
        self.headers = headers


def _http_json(
    url: str,
    timeout: float,
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
        with urlopen(request, timeout=timeout) as response:
            return _HttpResponse(
                response.status,
                json.loads(response.read().decode("utf-8")),
                {key.lower(): value for key, value in response.headers.items()},
            )
    except HTTPError as exc:
        try:
            return _HttpResponse(
                exc.code,
                json.loads(exc.read().decode("utf-8")),
                {key.lower(): value for key, value in exc.headers.items()},
            )
        finally:
            exc.close()


def _container_url(name: str) -> str:
    inspected = _docker_inspect(name)
    network = _mapping(inspected.get("NetworkSettings"))
    ports = _mapping(network.get("Ports"))
    bindings = ports.get("8080/tcp")
    if not isinstance(bindings, list) or not bindings:
        raise RuntimeError("container did not publish port 8080")
    binding = _mapping(cast(list[object], bindings)[0])
    host_port = binding.get("HostPort")
    if not isinstance(host_port, str) or not host_port.isdigit():
        raise RuntimeError("container published an invalid host port")
    return f"http://127.0.0.1:{host_port}"


def _container_state(name: str) -> dict[str, object]:
    return _mapping(_docker_inspect(name).get("State"))


def _docker_inspect(name: str, *, image: bool = False) -> dict[str, object]:
    command = ["docker", "image", "inspect", name] if image else ["docker", "inspect", name]
    completed = _run(command, timeout=10)
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"Docker inspect returned no object for {name}")
    return _mapping(cast(list[object], payload)[0])


def _container_log_tail(name: str, timeout: float) -> str:
    try:
        completed = subprocess.run(
            ["docker", "logs", "--tail", "5", name],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "timed out collecting container logs"
    except OSError as exc:
        return f"could not collect container logs: {_safe_error(exc)}"
    lines = (completed.stderr or completed.stdout).strip().splitlines()
    return lines[-1] if lines else "no container diagnostic"


def _container_pid1_identity(name: str, timeout: float) -> tuple[str, tuple[str, ...]]:
    completed = _run(
        [
            "docker",
            "exec",
            name,
            "python",
            "-c",
            (
                "import json, os; from pathlib import Path; "
                "raw = Path('/proc/1/cmdline').read_bytes(); "
                "argv = [part.decode('utf-8', 'replace') "
                "for part in raw.split(b'\\0') if part]; "
                "print(json.dumps({'executable': os.readlink('/proc/1/exe'), "
                "'argv': argv}))"
            ),
        ],
        timeout=timeout,
    )
    payload = json.loads(completed.stdout)
    identity = _mapping(payload)
    executable = identity.get("executable")
    argv = identity.get("argv")
    if not isinstance(executable, str) or not isinstance(argv, list):
        raise RuntimeError("container PID 1 inspection returned an invalid payload")
    argv_values = cast(list[object], argv)
    if not all(isinstance(value, str) for value in argv_values):
        raise RuntimeError("container PID 1 argv contained a non-string value")
    return executable, tuple(cast(list[str], argv_values))


def _is_gwt_pid1(executable: str, argv: Sequence[str]) -> bool:
    return (
        len(argv) >= 4
        and _PYTHON_EXECUTABLE.fullmatch(Path(executable).name) is not None
        and _PYTHON_EXECUTABLE.fullmatch(Path(argv[0]).name) is not None
        and tuple(argv[1:4]) == ("-m", "gwtlang", "serve")
    )


def _remove_container(name: str, *, timeout: float) -> None:
    _best_effort_docker(["docker", "rm", "--force", name], timeout=timeout)


def _remove_image(image_tag: str, *, timeout: float) -> None:
    _best_effort_docker(
        ["docker", "image", "rm", "--force", image_tag],
        timeout=timeout,
    )


def _best_effort_docker(command: Sequence[str], *, timeout: float) -> None:
    try:
        subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _bind_mount(source: Path, target: Path, *, readonly: bool = False) -> str:
    fields = ["type=bind", f"source={source}", f"target={target}"]
    if readonly:
        fields.append("readonly")
    return ",".join(fields)


def _run(command: Sequence[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip().splitlines()
        message = detail[-1] if detail else f"exit status {exc.returncode}"
        raise RuntimeError(f"{' '.join(command[:3])} failed: {message}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{' '.join(command[:3])} timed out") from exc


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return cast(dict[str, object], value)


def _safe_error(error: object) -> str:
    text = str(error).strip()
    return text.splitlines()[0] if text else type(error).__name__


def _auxiliary_timeout(timeout: float) -> float:
    return min(timeout, DOCKER_AUXILIARY_TIMEOUT_SECONDS)


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive number")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
