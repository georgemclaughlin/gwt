from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from queue import Queue
import signal
import sys
from threading import Lock, Thread, current_thread, main_thread
from types import FrameType
from typing import Any, BinaryIO, cast
from urllib.parse import urlparse

from .api import CompiledProgram, compile_text, generate_openapi_text, run_result_payload
from .errors import GwtError
from .execution_case import (
    ExecutionCaseCapturePolicy,
    FactProvenanceInput,
    _execution_case_from_completed_trace,
    _normalize_fact_provenance,
    _validate_fact_provenance_paths,
)
from .program_identity import LoadedProgramSnapshot, load_program_snapshot
from .runtime import (
    DEFAULT_EXECUTION_BUDGET,
    DEFAULT_MAX_CALL_DEPTH,
    ContractBinding,
    ImportPolicy,
    Runtime,
)
from .tracing import (
    GwtTraceRecorder,
    OtlpExportError,
    OtlpHttpExporter,
    OtlpMetric,
    OtlpMetricsExporter,
    OtlpSpan,
    now_unix_nano,
    otlp_metrics_endpoint as resolve_otlp_metrics_endpoint,
    parse_traceparent,
    otlp_trace_endpoint,
)


DEFAULT_MAX_REQUEST_BODY_BYTES = 1024 * 1024


@dataclass(frozen=True)
class HttpRequestRoute:
    path: str
    request_name: str
    operation_id: str

    def as_payload(self, program: CompiledProgram) -> dict[str, Any]:
        request = program.program.requests[self.request_name]
        return {
            "name": self.request_name,
            "method": "POST",
            "path": self.path,
            "operationId": self.operation_id,
            "inputs": _contract_payloads(request.inputs.values()),
            "outputs": _contract_payloads(request.outputs.values()),
        }


@dataclass
class _ContractPathNode:
    value_type: str | None = None
    children: dict[str, "_ContractPathNode"] = field(
        default_factory=lambda: dict[str, _ContractPathNode]()
    )


@dataclass(frozen=True)
class HttpExecutionCaseConfig:
    """Opt-in local Execution Case recording for served named requests."""

    directory: Path
    request_names: frozenset[str] | None = None
    fact_provenance: FactProvenanceInput | None = None
    include_values: bool = False

    def captures(self, request_name: str) -> bool:
        return self.request_names is None or request_name in self.request_names

    @property
    def policy(self) -> ExecutionCaseCapturePolicy:
        return ExecutionCaseCapturePolicy(
            on_error="record",
            values="full" if self.include_values else "omit",
        )


@dataclass(frozen=True)
class GwtHttpService:
    """Compiled HTTP view of a GWT file's named REQUEST contracts.

    Use `run_route` when the caller already has a decoded JSON object. Use
    `run_http_route` when the caller has raw HTTP body bytes and wants the same
    content-type, size, JSON parsing, and strict input checks as `gwt serve`.
    """

    compiled: CompiledProgram
    openapi_document: dict[str, Any]
    routes: dict[str, HttpRequestRoute]
    program_snapshot: LoadedProgramSnapshot
    trace_config: HttpTraceConfig | None = None
    metrics_config: HttpMetricsConfig | None = None
    capture_config: HttpExecutionCaseConfig | None = None
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES
    background_exporter: _BackgroundOtlpExporter | None = None

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        import_roots: Iterable[str | Path] | None = None,
        allow_absolute_imports: bool = True,
        trace_config: HttpTraceConfig | None = None,
        metrics_config: HttpMetricsConfig | None = None,
        capture_config: HttpExecutionCaseConfig | None = None,
        max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
        background_exports: bool = False,
    ) -> GwtHttpService:
        """Compile a GWT file and build its OpenAPI-backed HTTP route table."""

        file_path = Path(path)
        import_policy = _http_import_policy(import_roots, allow_absolute_imports)
        snapshot = load_program_snapshot(file_path, import_policy=import_policy)
        source = snapshot.entry_source
        filename = str(file_path)
        compiled = compile_text(
            source,
            filename=filename,
            import_roots=import_roots,
            allow_absolute_imports=allow_absolute_imports,
        )
        openapi_document = generate_openapi_text(
            source,
            filename=filename,
            import_roots=import_roots,
            allow_absolute_imports=allow_absolute_imports,
        ).as_payload()
        _prepare_capture_config(
            capture_config,
            compiled=compiled,
            trace_config=trace_config,
        )
        return cls(
            compiled=compiled,
            openapi_document=openapi_document,
            routes=_routes_from_openapi(openapi_document),
            program_snapshot=snapshot,
            trace_config=trace_config,
            metrics_config=metrics_config,
            capture_config=capture_config,
            max_request_body_bytes=max_request_body_bytes,
            background_exporter=(
                _BackgroundOtlpExporter()
                if background_exports and (trace_config is not None or metrics_config is not None)
                else None
            ),
        )

    @property
    def program_name(self) -> str | None:
        return self.compiled.program.name

    def health_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "file": self.compiled.file,
            "program": self.program_name,
            "requests": len(self.routes),
        }

    def requests_payload(self) -> dict[str, Any]:
        return {
            "file": self.compiled.file,
            "program": self.program_name,
            "requests": [
                route.as_payload(self.compiled)
                for route in self.routes.values()
            ],
        }

    def close(self) -> None:
        if self.background_exporter is not None:
            self.background_exporter.close()

    def run_route(
        self,
        path: str,
        json_state: dict[str, Any],
        *,
        traceparent: str | None = None,
    ) -> HttpRouteResult:
        """Run a route with an already-decoded JSON object.

        This path is for embedded callers and does not apply HTTP content-type
        or request-body size checks.
        """

        route = self.routes.get(path)
        if route is None:
            raise HttpServiceError(404, f"unknown GWT request route: {path}", "GWT_HTTP_ROUTE_NOT_FOUND")

        start_time = now_unix_nano()
        status = 200
        error_code: str | None = None
        error_message: str | None = None
        recorder = self._trace_recorder(route, traceparent)
        try:
            self._validate_declared_input_keys(route, json_state)
            return self._execute_route(route, json_state, recorder)
        except HttpServiceError as exc:
            status = exc.status
            error_code = exc.code
            error_message = exc.message
            if exc.traceparent is None:
                self._finish_trace(recorder, error=exc.message)
                raise _with_traceparent(exc, recorder) from exc
            raise
        except Exception:
            status = 500
            error_code = "GWT_HTTP_UNEXPECTED_ERROR"
            error_message = "unexpected GWT HTTP service error"
            self._finish_trace(recorder, error=error_message)
            raise
        finally:
            self._export_route_metrics(
                route,
                status=status,
                error_code=error_code,
                error_message=error_message,
                start_time_unix_nano=start_time,
            )
            self._export_trace(recorder)

    def run_http_route(
        self,
        path: str,
        content_length: str | None,
        body: BinaryIO,
        *,
        content_type: str | None = "application/json",
        traceparent: str | None = None,
    ) -> HttpRouteResult:
        """Run a route from raw HTTP request body bytes.

        `content_type` defaults to `application/json` to preserve the original
        embedded call shape. Real HTTP handlers should pass the request header;
        missing or non-JSON content types are rejected with `415`.
        """

        route = self.routes.get(path)
        if route is None:
            raise HttpServiceError(404, f"unknown GWT request route: {path}", "GWT_HTTP_ROUTE_NOT_FOUND")

        start_time = now_unix_nano()
        status = 200
        error_code: str | None = None
        error_message: str | None = None
        recorder = self._trace_recorder(route, traceparent)
        try:
            _validate_json_content_type(content_type)
            json_state = _read_json_body(body, content_length, self.max_request_body_bytes)
            self._validate_declared_input_keys(route, json_state)
            return self._execute_route(route, json_state, recorder)
        except HttpServiceError as exc:
            status = exc.status
            error_code = exc.code
            error_message = exc.message
            if exc.traceparent is None:
                self._finish_trace(recorder, error=exc.message)
                raise _with_traceparent(exc, recorder) from exc
            raise
        except Exception:
            status = 500
            error_code = "GWT_HTTP_UNEXPECTED_ERROR"
            error_message = "unexpected GWT HTTP service error"
            self._finish_trace(recorder, error=error_message)
            raise
        finally:
            self._export_route_metrics(
                route,
                status=status,
                error_code=error_code,
                error_message=error_message,
                start_time_unix_nano=start_time,
            )
            self._export_trace(recorder)

    def _execute_route(
        self,
        route: HttpRequestRoute,
        json_state: dict[str, Any],
        recorder: GwtTraceRecorder | None,
    ) -> HttpRouteResult:
        try:
            runtime = Runtime(self.compiled.program, tracer=recorder)
            run_result = runtime.run_json(json_state, request=route.request_name)
        except GwtError as exc:
            error_status = _status_for_gwt_error(str(exc))
            self._finish_trace(recorder, error=str(exc))
            case_id = self._capture_execution_case(
                route,
                json_state,
                recorder,
                failure=exc,
            )
            raise HttpServiceError(
                error_status,
                str(exc),
                "GWT_REQUEST_FAILED",
                traceparent=recorder.traceparent if recorder is not None else None,
                case_id=case_id,
            ) from exc

        result = run_result_payload(run_result, file=self.compiled.file)["result"]
        if result is None:
            self._finish_trace(recorder)
            declared_result: dict[str, Any] = {}
            case_id = self._capture_execution_case(
                route,
                json_state,
                recorder,
                declared_result=declared_result,
            )
            return HttpRouteResult(
                declared_result,
                traceparent=recorder.traceparent if recorder is not None else None,
                case_id=case_id,
            )
        if not isinstance(result, dict):
            error = "GWT request returned a non-object response"
            self._finish_trace(recorder, error=error)
            raise HttpServiceError(
                500,
                error,
                "GWT_RESPONSE_INVALID",
                traceparent=recorder.traceparent if recorder is not None else None,
            )
        self._finish_trace(recorder)
        declared_result = cast(dict[str, Any], result)
        case_id = self._capture_execution_case(
            route,
            json_state,
            recorder,
            declared_result=declared_result,
        )
        return HttpRouteResult(
            declared_result,
            traceparent=recorder.traceparent if recorder is not None else None,
            case_id=case_id,
        )

    def _capture_execution_case(
        self,
        route: HttpRequestRoute,
        json_state: dict[str, Any],
        recorder: GwtTraceRecorder | None,
        *,
        declared_result: dict[str, Any] | None = None,
        failure: GwtError | None = None,
    ) -> str | None:
        config = self.capture_config
        if config is None or not config.captures(route.request_name):
            return None
        if recorder is None:
            print(
                f"gwt: execution case capture skipped for {route.request_name!r}: missing trace recorder",
                file=sys.stderr,
            )
            return None
        try:
            execution_case = _execution_case_from_completed_trace(
                self.program_snapshot,
                self.compiled.program,
                json_state,
                request=route.request_name,
                recorder=recorder,
                program_file=self.compiled.file,
                fact_provenance=config.fact_provenance,
                policy=config.policy,
                declared_result=declared_result,
                failure=failure,
                execution_budget=DEFAULT_EXECUTION_BUDGET,
                max_call_depth=DEFAULT_MAX_CALL_DEPTH,
            )
            payload = execution_case.as_payload()
            case_id = payload["integrity"]["digest"]
            filename = f"{case_id.removeprefix('sha256:')}.execution-case.json"
            execution_case.write(config.directory / filename)
            return case_id
        except Exception as exc:
            print(
                f"gwt: execution case capture failed for {route.request_name!r}: {exc}",
                file=sys.stderr,
            )
            return None

    def _validate_declared_input_keys(
        self,
        route: HttpRequestRoute,
        json_state: dict[str, Any],
    ) -> None:
        request = self.compiled.program.requests[route.request_name]
        root = _contract_path_tree(request.inputs.values())
        _validate_contract_object(root, json_state)

    def _trace_recorder(
        self,
        route: HttpRequestRoute,
        traceparent: str | None,
    ) -> GwtTraceRecorder | None:
        capture_enabled = (
            self.capture_config is not None
            and self.capture_config.captures(route.request_name)
        )
        if self.trace_config is None and not capture_enabled:
            return None
        include_values = (
            (self.trace_config.include_values if self.trace_config is not None else False)
            or (
                self.capture_config.include_values
                if capture_enabled and self.capture_config is not None
                else False
            )
        )
        return GwtTraceRecorder(
            program_file=self.compiled.file,
            program_name=self.program_name,
            program_hash=f"sha256:{self.compiled.source_hash}",
            request_name=route.request_name,
            route_path=route.path,
            context=parse_traceparent(traceparent),
            service_name=(
                self.trace_config.service_name
                if self.trace_config is not None
                else "gwt-serve"
            ),
            include_values=include_values,
        )

    def _export_trace(self, recorder: GwtTraceRecorder | None) -> None:
        if self.trace_config is None or recorder is None:
            return
        if self.background_exporter is not None:
            self.background_exporter.export_trace(
                self.trace_config.otlp_endpoint,
                recorder.spans,
            )
            return
        try:
            OtlpHttpExporter(self.trace_config.otlp_endpoint).export(recorder.spans)
        except OtlpExportError as exc:
            print(f"gwt: OTLP trace export failed: {exc}", file=sys.stderr)

    def _finish_trace(self, recorder: GwtTraceRecorder | None, *, error: str | None = None) -> None:
        if recorder is None:
            return
        recorder.finish(error=error)

    def _export_route_metrics(
        self,
        route: HttpRequestRoute,
        *,
        status: int,
        error_code: str | None,
        error_message: str | None,
        start_time_unix_nano: int,
    ) -> None:
        if self.metrics_config is None:
            return
        end_time = now_unix_nano()
        attributes: dict[str, Any] = {
            "gwt.request.name": route.request_name,
            "http.route": route.path,
            "http.request.method": "POST",
            "http.response.status_code": status,
        }
        if error_code is not None:
            attributes["gwt.error.code"] = error_code
        duration_ms = max((end_time - start_time_unix_nano) / 1_000_000, 0.0)
        metrics = [
            OtlpMetric(
                name="gwt.request.count",
                description="GWT HTTP request executions.",
                unit="{request}",
                kind="sum",
                value=1,
                attributes=attributes,
                start_time_unix_nano=start_time_unix_nano,
                time_unix_nano=end_time,
            ),
            OtlpMetric(
                name="gwt.request.duration_ms",
                description="GWT HTTP request execution duration.",
                unit="ms",
                kind="histogram",
                value=duration_ms,
                attributes=attributes,
                start_time_unix_nano=start_time_unix_nano,
                time_unix_nano=end_time,
            ),
        ]
        if status >= 400:
            metrics.append(
                OtlpMetric(
                    name="gwt.request.failure.count",
                    description="Failed GWT HTTP request executions.",
                    unit="{request}",
                    kind="sum",
                    value=1,
                    attributes=attributes,
                    start_time_unix_nano=start_time_unix_nano,
                    time_unix_nano=end_time,
                )
            )
        for metric_name, description in _failure_metric_specs(error_message):
            metrics.append(
                OtlpMetric(
                    name=metric_name,
                    description=description,
                    unit="{failure}",
                    kind="sum",
                    value=1,
                    attributes=attributes,
                    start_time_unix_nano=start_time_unix_nano,
                    time_unix_nano=end_time,
                )
            )
        if self.background_exporter is not None:
            self.background_exporter.export_metrics(
                self.metrics_config.otlp_endpoint,
                metrics,
                service_name=self.metrics_config.service_name,
            )
            return
        try:
            OtlpMetricsExporter(self.metrics_config.otlp_endpoint).export(
                metrics,
                service_name=self.metrics_config.service_name,
            )
        except OtlpExportError as exc:
            print(f"gwt: OTLP metric export failed: {exc}", file=sys.stderr)


@dataclass(frozen=True)
class _TraceExportTask:
    endpoint: str
    spans: list[OtlpSpan]


@dataclass(frozen=True)
class _MetricsExportTask:
    endpoint: str
    metrics: list[OtlpMetric]
    service_name: str


_OtlpExportTask = _TraceExportTask | _MetricsExportTask


class _BackgroundOtlpExporter:
    def __init__(self) -> None:
        self._queue: Queue[_OtlpExportTask | None] = Queue()
        self._lock = Lock()
        self._closed = False
        self._thread = Thread(target=self._run, name="gwt-otlp-exporter", daemon=True)
        self._thread.start()

    def export_trace(self, endpoint: str, spans: list[OtlpSpan]) -> None:
        self._put(_TraceExportTask(endpoint, list(spans)))

    def export_metrics(
        self,
        endpoint: str,
        metrics: list[OtlpMetric],
        *,
        service_name: str,
    ) -> None:
        self._put(_MetricsExportTask(endpoint, list(metrics), service_name))

    def close(self, *, timeout: float = 10.0) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._queue.put(None)
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            print(
                "gwt: OTLP background exporter did not finish before shutdown timeout",
                file=sys.stderr,
            )

    def _put(self, task: _OtlpExportTask) -> None:
        with self._lock:
            if self._closed:
                return
            self._queue.put(task)

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            try:
                if task is None:
                    return
                if isinstance(task, _TraceExportTask):
                    OtlpHttpExporter(task.endpoint).export(task.spans)
                    continue
                OtlpMetricsExporter(task.endpoint).export(
                    task.metrics,
                    service_name=task.service_name,
                )
            except Exception as exc:
                label = "trace" if isinstance(task, _TraceExportTask) else "metric"
                print(f"gwt: OTLP {label} export failed: {exc}", file=sys.stderr)
            finally:
                self._queue.task_done()


@dataclass(frozen=True)
class HttpTraceConfig:
    """OpenTelemetry export settings for served or embedded HTTP request runs."""

    otlp_endpoint: str
    service_name: str = "gwt-serve"
    include_values: bool = False


@dataclass(frozen=True)
class HttpMetricsConfig:
    """OpenTelemetry metrics export settings for served or embedded HTTP request runs."""

    otlp_endpoint: str
    service_name: str = "gwt-serve"


@dataclass(frozen=True)
class HttpRouteResult:
    body: dict[str, Any]
    traceparent: str | None = None
    case_id: str | None = None


class HttpServiceError(Exception):
    def __init__(
        self,
        status: int,
        message: str,
        code: str,
        *,
        traceparent: str | None = None,
        case_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.traceparent = traceparent
        self.case_id = case_id


class GwtHttpServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: GwtHttpService,
    ) -> None:
        super().__init__(server_address, _GwtHttpRequestHandler)
        self.service = service

    def server_close(self) -> None:
        super().server_close()
        self.service.close()


def create_http_server(
    service: GwtHttpService,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> GwtHttpServer:
    """Create a ThreadingHTTPServer for a precompiled `GwtHttpService`."""

    return GwtHttpServer((host, port), service)


def run_http_server(
    path: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    import_roots: Iterable[str | Path] | None = None,
    allow_absolute_imports: bool = True,
    otlp_endpoint: str | None = None,
    trace_values: bool = False,
    otlp_metrics_endpoint: str | None = None,
    max_request_body_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES,
    capture_directory: str | Path | None = None,
    capture_request_names: Iterable[str] | None = None,
    capture_values: bool = False,
    fact_provenance: FactProvenanceInput | None = None,
) -> int:
    if capture_directory is None and (
        capture_request_names is not None
        or capture_values
        or fact_provenance is not None
    ):
        raise ValueError(
            "capture request selection, values, and fact provenance require "
            "a capture directory"
        )
    resolved_otlp_endpoint = otlp_trace_endpoint(otlp_endpoint)
    resolved_otlp_metrics_endpoint = resolve_otlp_metrics_endpoint(otlp_metrics_endpoint)
    service = GwtHttpService.from_file(
        path,
        import_roots=import_roots,
        allow_absolute_imports=allow_absolute_imports,
        trace_config=(
            HttpTraceConfig(resolved_otlp_endpoint, include_values=trace_values)
            if resolved_otlp_endpoint is not None
            else None
        ),
        metrics_config=(
            HttpMetricsConfig(resolved_otlp_metrics_endpoint)
            if resolved_otlp_metrics_endpoint is not None
            else None
        ),
        capture_config=(
            HttpExecutionCaseConfig(
                directory=Path(capture_directory),
                request_names=(
                    frozenset(capture_request_names)
                    if capture_request_names is not None
                    else None
                ),
                fact_provenance=fact_provenance,
                include_values=capture_values,
            )
            if capture_directory is not None
            else None
        ),
        max_request_body_bytes=max_request_body_bytes,
        background_exports=True,
    )
    server = create_http_server(service, host=host, port=port)
    actual_host, actual_port = server.server_address[:2]
    print(f"Serving {path} at http://{actual_host}:{actual_port}", flush=True)
    previous_sigterm = _install_sigterm_handler()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        _restore_sigterm_handler(previous_sigterm)
        server.server_close()
    return 0


class _GwtHttpRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = _request_path(self.path)
        if path == "/health":
            self._write_json(200, self._service().health_payload())
            return
        if path == "/openapi.json":
            self._write_json(200, self._service().openapi_document)
            return
        if path == "/requests":
            self._write_json(200, self._service().requests_payload())
            return
        self._write_error(HttpServiceError(404, f"unknown route: {path}", "GWT_HTTP_ROUTE_NOT_FOUND"))

    def do_POST(self) -> None:
        path = _request_path(self.path)
        try:
            result = self._service().run_http_route(
                path,
                self.headers.get("Content-Length", "0"),
                cast(BinaryIO, self.rfile),
                content_type=self.headers.get("Content-Type"),
                traceparent=self.headers.get("traceparent"),
            )
        except HttpServiceError as exc:
            self._write_error(exc)
            return
        self._write_json(
            200,
            result.body,
            headers=_response_headers(result.traceparent, result.case_id),
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _service(self) -> GwtHttpService:
        return cast(GwtHttpServer, self.server).service

    def _write_json(
        self,
        status: int,
        payload: object,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        rendered = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(rendered)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(rendered)

    def _write_error(self, error: HttpServiceError) -> None:
        self._write_json(
            error.status,
            {
                "ok": False,
                "error": {
                    "code": error.code,
                    "message": error.message,
                },
            },
            headers=_response_headers(error.traceparent, error.case_id),
        )


def _routes_from_openapi(document: dict[str, Any]) -> dict[str, HttpRequestRoute]:
    routes: dict[str, HttpRequestRoute] = {}
    paths_object = document.get("paths", {})
    if not isinstance(paths_object, dict):
        return routes
    paths = cast(dict[object, object], paths_object)
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        post_object = cast(dict[object, object], path_item).get("post")
        if not isinstance(post_object, dict):
            continue
        post = cast(dict[object, object], post_object)
        request_name = post.get("x-gwt-request-name")
        operation_id = post.get("operationId")
        if isinstance(request_name, str) and isinstance(operation_id, str):
            routes[path] = HttpRequestRoute(path, request_name, operation_id)
    return routes


def _http_import_policy(
    import_roots: Iterable[str | Path] | None,
    allow_absolute_imports: bool,
) -> ImportPolicy | None:
    if import_roots is None and allow_absolute_imports:
        return None
    roots = tuple(Path(root).resolve() for root in import_roots or ())
    return ImportPolicy(roots, allow_absolute_imports)


def _prepare_capture_config(
    config: HttpExecutionCaseConfig | None,
    *,
    compiled: CompiledProgram,
    trace_config: HttpTraceConfig | None,
) -> None:
    if config is None:
        return
    if config.include_values and trace_config is not None and not trace_config.include_values:
        raise ValueError(
            "full Execution Case capture cannot share a redacted OTLP trace; "
            "also enable trace values or omit captured values"
        )
    available = set(compiled.program.requests)
    selected = set(config.request_names) if config.request_names is not None else available
    if not selected:
        raise ValueError("execution case capture requires at least one named REQUEST")
    unknown = sorted(selected - available)
    if unknown:
        raise ValueError(f"unknown capture request: {unknown[0]}")
    normalized_provenance = _normalize_fact_provenance(config.fact_provenance)
    for request_name in sorted(selected):
        _validate_fact_provenance_paths(
            normalized_provenance,
            compiled.program,
            request_name,
        )
    config.directory.mkdir(parents=True, exist_ok=True)


def _contract_path_tree(bindings: Iterable[ContractBinding]) -> _ContractPathNode:
    root = _ContractPathNode()
    for binding in bindings:
        current = root
        for part in binding.path.split("."):
            current = current.children.setdefault(part, _ContractPathNode())
        current.value_type = binding.value_type
    return root


def _validate_contract_object(node: _ContractPathNode, value: object, *, path: str = "") -> None:
    if node.value_type is not None:
        return
    if not isinstance(value, dict):
        return
    item = cast(dict[object, object], value)
    for key in item:
        if not isinstance(key, str):
            return
        if key not in node.children:
            input_path = f"{path}.{key}" if path else key
            raise HttpServiceError(
                400,
                f"request body contains undeclared input: {input_path}",
                "GWT_HTTP_UNDECLARED_INPUT",
            )
    for key, child in node.children.items():
        if key in item:
            input_path = f"{path}.{key}" if path else key
            _validate_contract_object(child, item[key], path=input_path)


def _contract_payloads(bindings: Iterable[ContractBinding]) -> list[dict[str, str]]:
    return [
        {
            "path": binding.path,
            "type": binding.value_type,
        }
        for binding in bindings
    ]


def _request_path(raw_path: str) -> str:
    return urlparse(raw_path).path


def _validate_json_content_type(content_type: str | None) -> None:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise HttpServiceError(
            415,
            "request Content-Type must be application/json",
            "GWT_HTTP_UNSUPPORTED_MEDIA_TYPE",
        )


def _read_json_body(
    body: BinaryIO,
    content_length: str | None,
    max_body_bytes: int,
) -> dict[str, Any]:
    try:
        length = int(content_length or "0")
    except ValueError as exc:
        raise HttpServiceError(400, "invalid Content-Length header", "GWT_HTTP_BAD_REQUEST") from exc
    if length < 0:
        raise HttpServiceError(400, "invalid Content-Length header", "GWT_HTTP_BAD_REQUEST")
    if length > max_body_bytes:
        raise HttpServiceError(
            413,
            f"request body exceeds {max_body_bytes} byte limit",
            "GWT_HTTP_BODY_TOO_LARGE",
        )
    raw = body.read(length) if length > 0 else b""
    return _json_body_from_raw(raw)


def _json_body_from_raw(raw: bytes) -> dict[str, Any]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise HttpServiceError(400, "request body must be UTF-8 JSON", "GWT_HTTP_INVALID_JSON") from exc
    except json.JSONDecodeError as exc:
        message = f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        raise HttpServiceError(400, message, "GWT_HTTP_INVALID_JSON") from exc
    if not isinstance(payload, dict):
        raise HttpServiceError(400, "request body must be a JSON object", "GWT_HTTP_INVALID_JSON")
    return cast(dict[str, Any], payload)


def _status_for_gwt_error(message: str) -> int:
    if (
        "REQUEST contract failed" in message
        or "JSON input" in message
        or "JSON input key" in message
        or message.startswith("<json-input>:")
        or message.startswith("<request>:")
    ):
        return 400
    return 500


def _failure_metric_specs(error_message: str | None) -> list[tuple[str, str]]:
    if error_message is None:
        return []
    specs: list[tuple[str, str]] = []
    if "REQUEST contract failed" in error_message or "OUTPUT contract failed" in error_message:
        specs.append(("gwt.contract.failure.count", "GWT request or output contract failures."))
    if "assertion failed:" in error_message:
        specs.append(("gwt.assertion.failure.count", "GWT request assertion failures."))
    return specs


def _response_headers(
    traceparent: str | None,
    case_id: str | None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if traceparent is not None:
        parts = traceparent.split("-")
        trace_id = parts[1] if len(parts) == 4 else ""
        headers.update(
            {
                "traceparent": traceparent,
                "x-gwt-trace-id": trace_id,
            }
        )
    if case_id is not None:
        headers["x-gwt-case-id"] = case_id
    return headers


def _with_traceparent(
    error: HttpServiceError,
    recorder: GwtTraceRecorder | None,
) -> HttpServiceError:
    if recorder is None:
        return error
    return HttpServiceError(
        error.status,
        error.message,
        error.code,
        traceparent=recorder.traceparent,
        case_id=error.case_id,
    )


def _install_sigterm_handler() -> Any:
    if current_thread() is not main_thread():
        return None
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    return previous


def _restore_sigterm_handler(previous: Any) -> None:
    if previous is None or current_thread() is not main_thread():
        return
    signal.signal(signal.SIGTERM, previous)


def _raise_keyboard_interrupt(signum: int, frame: FrameType | None) -> None:
    del signum, frame
    raise KeyboardInterrupt
