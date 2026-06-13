from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any, BinaryIO, cast
from urllib.parse import urlparse

from .api import CompiledProgram, compile_text, generate_openapi_text, run_result_payload
from .errors import GwtError
from .runtime import ContractBinding, Runtime
from .tracing import (
    GwtTraceRecorder,
    OtlpExportError,
    OtlpHttpExporter,
    parse_traceparent,
    otlp_trace_endpoint,
)


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
class GwtHttpService:
    compiled: CompiledProgram
    openapi_document: dict[str, Any]
    routes: dict[str, HttpRequestRoute]
    trace_config: HttpTraceConfig | None = None

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        import_roots: Iterable[str | Path] | None = None,
        allow_absolute_imports: bool = True,
        trace_config: HttpTraceConfig | None = None,
    ) -> GwtHttpService:
        file_path = Path(path)
        source = file_path.read_text()
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
        return cls(compiled, openapi_document, _routes_from_openapi(openapi_document), trace_config)

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

    def run_route(
        self,
        path: str,
        json_state: dict[str, Any],
        *,
        traceparent: str | None = None,
    ) -> HttpRouteResult:
        route = self.routes.get(path)
        if route is None:
            raise HttpServiceError(404, f"unknown GWT request route: {path}", "GWT_HTTP_ROUTE_NOT_FOUND")

        recorder = self._trace_recorder(route, traceparent)
        try:
            self._validate_declared_input_keys(route, json_state)
        except HttpServiceError as exc:
            self._finish_trace(recorder, error=exc.message)
            raise _with_traceparent(exc, recorder) from exc
        return self._execute_route(route, json_state, recorder)

    def run_http_route(
        self,
        path: str,
        content_length: str | None,
        body: BinaryIO,
        *,
        traceparent: str | None = None,
    ) -> HttpRouteResult:
        route = self.routes.get(path)
        if route is None:
            raise HttpServiceError(404, f"unknown GWT request route: {path}", "GWT_HTTP_ROUTE_NOT_FOUND")

        recorder = self._trace_recorder(route, traceparent)
        try:
            json_state = _read_json_body(body, content_length)
            self._validate_declared_input_keys(route, json_state)
        except HttpServiceError as exc:
            self._finish_trace(recorder, error=exc.message)
            raise _with_traceparent(exc, recorder) from exc
        return self._execute_route(route, json_state, recorder)

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
            self._finish_trace(recorder, error=str(exc))
            raise HttpServiceError(
                _status_for_gwt_error(str(exc)),
                str(exc),
                "GWT_REQUEST_FAILED",
                traceparent=recorder.traceparent if recorder is not None else None,
            ) from exc

        result = run_result_payload(run_result, file=self.compiled.file)["result"]
        if result is None:
            self._finish_trace(recorder)
            return HttpRouteResult({}, traceparent=recorder.traceparent if recorder is not None else None)
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
        return HttpRouteResult(
            cast(dict[str, Any], result),
            traceparent=recorder.traceparent if recorder is not None else None,
        )

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
        if self.trace_config is None:
            return None
        return GwtTraceRecorder(
            program_file=self.compiled.file,
            program_name=self.program_name,
            program_hash=f"sha256:{self.compiled.source_hash}",
            request_name=route.request_name,
            route_path=route.path,
            context=parse_traceparent(traceparent),
            service_name=self.trace_config.service_name,
            include_values=self.trace_config.include_values,
        )

    def _export_trace(self, recorder: GwtTraceRecorder) -> None:
        if self.trace_config is None:
            return
        try:
            OtlpHttpExporter(self.trace_config.otlp_endpoint).export(recorder.spans)
        except OtlpExportError as exc:
            print(f"gwt: OTLP trace export failed: {exc}", file=sys.stderr)

    def _finish_trace(self, recorder: GwtTraceRecorder | None, *, error: str | None = None) -> None:
        if recorder is None:
            return
        recorder.finish(error=error)
        self._export_trace(recorder)


@dataclass(frozen=True)
class HttpTraceConfig:
    otlp_endpoint: str
    service_name: str = "gwt-serve"
    include_values: bool = False


@dataclass(frozen=True)
class HttpRouteResult:
    body: dict[str, Any]
    traceparent: str | None = None


class HttpServiceError(Exception):
    def __init__(self, status: int, message: str, code: str, *, traceparent: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code
        self.traceparent = traceparent


class GwtHttpServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        service: GwtHttpService,
    ) -> None:
        super().__init__(server_address, _GwtHttpRequestHandler)
        self.service = service


def create_http_server(
    service: GwtHttpService,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
) -> GwtHttpServer:
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
) -> int:
    resolved_otlp_endpoint = otlp_trace_endpoint(otlp_endpoint)
    service = GwtHttpService.from_file(
        path,
        import_roots=import_roots,
        allow_absolute_imports=allow_absolute_imports,
        trace_config=(
            HttpTraceConfig(resolved_otlp_endpoint, include_values=trace_values)
            if resolved_otlp_endpoint is not None
            else None
        ),
    )
    server = create_http_server(service, host=host, port=port)
    actual_host, actual_port = server.server_address[:2]
    print(f"Serving {path} at http://{actual_host}:{actual_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
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
                traceparent=self.headers.get("traceparent"),
            )
        except HttpServiceError as exc:
            self._write_error(exc)
            return
        self._write_json(200, result.body, headers=_trace_headers(result.traceparent))

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
            headers=_trace_headers(error.traceparent),
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


def _read_json_body(body: BinaryIO, content_length: str | None) -> dict[str, Any]:
    try:
        length = int(content_length or "0")
    except ValueError as exc:
        raise HttpServiceError(400, "invalid Content-Length header", "GWT_HTTP_BAD_REQUEST") from exc
    if length < 0:
        raise HttpServiceError(400, "invalid Content-Length header", "GWT_HTTP_BAD_REQUEST")
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


def _trace_headers(traceparent: str | None) -> dict[str, str]:
    if traceparent is None:
        return {}
    parts = traceparent.split("-")
    trace_id = parts[1] if len(parts) == 4 else ""
    return {
        "traceparent": traceparent,
        "x-gwt-trace-id": trace_id,
    }


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
    )
