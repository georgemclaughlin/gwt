"""Optional ASGI transport for the transport-neutral GWT HTTP application."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
import importlib
import math
from pathlib import Path
import socket
from types import FrameType
from typing import Any, Protocol, cast

from .http_server import (
    DEFAULT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_SHUTDOWN_GRACE_SECONDS,
    GwtHttpApplication,
    GwtHttpService,
    HttpApplicationRequest,
    HttpApplicationResponse,
)


AsgiMessage = dict[str, Any]
AsgiReceive = Callable[[], Awaitable[AsgiMessage]]
AsgiSend = Callable[[AsgiMessage], Awaitable[None]]
SUPPORTED_ASGI_VERSION = "3.0"
SUPPORTED_ASGI_HTTP_SPEC_MAJOR = 2
SUPPORTED_ASGI_LIFESPAN_SPEC_VERSION = "2.0"


class GwtAsgiProtocolError(RuntimeError):
    """The ASGI server supplied a scope or event outside GWT's contract."""


class _UvicornServer(Protocol):
    def handle_exit(self, sig: int, frame: FrameType | None) -> None: ...

    def run(self, sockets: list[socket.socket] | None = None) -> None: ...


class _UvicornModule(Protocol):
    def Config(self, app: object, **kwargs: object) -> object: ...

    def Server(self, config: object) -> _UvicornServer: ...


class GwtAsgiApplication:
    """ASGI HTTP and lifespan adapter for :class:`GwtHttpApplication`."""

    def __init__(
        self,
        application: GwtHttpApplication,
        *,
        shutdown_grace_seconds: float = DEFAULT_SHUTDOWN_GRACE_SECONDS,
    ) -> None:
        if not math.isfinite(shutdown_grace_seconds) or shutdown_grace_seconds <= 0:
            raise ValueError("shutdown_grace_seconds must be a positive number")
        self.application = application
        self.shutdown_grace_seconds = shutdown_grace_seconds

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: AsgiReceive,
        send: AsgiSend,
    ) -> None:
        scope_type = _scope_type(scope)
        if scope_type == "lifespan":
            _validate_asgi_scope(
                scope,
                expected_type="lifespan",
            )
            lifespan_asgi = cast(dict[str, Any], scope["asgi"])
            lifespan_spec = lifespan_asgi.get("spec_version", "1.0")
            if lifespan_spec != SUPPORTED_ASGI_LIFESPAN_SPEC_VERSION:
                raise GwtAsgiProtocolError(
                    "unsupported ASGI lifespan spec version: "
                    f"{lifespan_spec!r}; expected "
                    f"{SUPPORTED_ASGI_LIFESPAN_SPEC_VERSION}"
                )
            await self._lifespan(receive, send)
            return
        if scope_type == "http":
            _validate_http_scope(scope)
            await self._http(scope, receive, send)
            return
        raise GwtAsgiProtocolError(f"unsupported ASGI scope type: {scope_type!r}")

    async def _http(
        self,
        scope: dict[str, Any],
        receive: AsgiReceive,
        send: AsgiSend,
    ) -> None:
        method = cast(str, scope["method"])
        body = bytearray()
        too_large = False
        more_body = True
        while more_body:
            message = await receive()
            message_type = _message_type(message)
            if message_type == "http.disconnect":
                return
            if message_type != "http.request":
                raise GwtAsgiProtocolError(
                    f"unexpected ASGI HTTP event: {message_type!r}"
                )
            chunk = message.get("body", b"")
            if not isinstance(chunk, bytes):
                raise GwtAsgiProtocolError("ASGI http.request body must be bytes")
            more_body_value = message.get("more_body", False)
            if not isinstance(more_body_value, bool):
                raise GwtAsgiProtocolError(
                    "ASGI http.request more_body must be a boolean"
                )
            if not too_large:
                if len(body) + len(chunk) > self.application.service.max_request_body_bytes:
                    too_large = True
                else:
                    body.extend(chunk)
            more_body = more_body_value

        headers = _http_headers(scope)
        path = _http_request_path(scope)
        if too_large:
            response = self.application.body_too_large_response(
                HttpApplicationRequest(method, path, headers)
            )
        else:
            response = await asyncio.to_thread(
                self.application.handle,
                HttpApplicationRequest(method, path, headers, bytes(body)),
            )
        await _send_response(response, send)

    async def _lifespan(self, receive: AsgiReceive, send: AsgiSend) -> None:
        started = False
        while True:
            message = await receive()
            message_type = _message_type(message)
            if message_type == "lifespan.startup":
                if started:
                    raise GwtAsgiProtocolError(
                        "received duplicate ASGI lifespan.startup event"
                    )
                await send({"type": "lifespan.startup.complete"})
                started = True
                continue
            if message_type == "lifespan.shutdown":
                if not started:
                    raise GwtAsgiProtocolError(
                        "received ASGI lifespan.shutdown before startup"
                    )
                self.application.begin_draining()
                finished = await asyncio.to_thread(
                    self.application.wait_for_idle,
                    self.shutdown_grace_seconds,
                )
                try:
                    self.application.close()
                except Exception:
                    await send(
                        {
                            "type": "lifespan.shutdown.failed",
                            "message": "GWT service cleanup failed",
                        }
                    )
                    return
                if finished:
                    await send({"type": "lifespan.shutdown.complete"})
                else:
                    await send(
                        {
                            "type": "lifespan.shutdown.failed",
                            "message": "active requests exceeded the GWT shutdown grace period",
                        }
                    )
                return
            raise GwtAsgiProtocolError(
                f"unexpected ASGI lifespan event: {message_type!r}"
            )


async def _send_response(response: HttpApplicationResponse, send: AsgiSend) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": response.status,
            "headers": [
                (key.lower().encode("ascii"), value.encode("latin-1"))
                for key, value in response.headers.items()
            ],
        }
    )
    await send({"type": "http.response.body", "body": response.body})


def _scope_type(scope: dict[str, Any]) -> str:
    scope_type = scope.get("type")
    if not isinstance(scope_type, str):
        raise GwtAsgiProtocolError("ASGI scope type must be a string")
    return scope_type


def _validate_asgi_scope(
    scope: dict[str, Any],
    *,
    expected_type: str,
) -> None:
    if _scope_type(scope) != expected_type:
        raise GwtAsgiProtocolError(
            f"expected ASGI {expected_type!r} scope"
        )
    asgi_value = scope.get("asgi")
    if not isinstance(asgi_value, dict):
        raise GwtAsgiProtocolError("ASGI scope must include an asgi mapping")
    asgi = cast(dict[str, Any], asgi_value)
    version = asgi.get("version")
    if version != SUPPORTED_ASGI_VERSION:
        raise GwtAsgiProtocolError(
            f"unsupported ASGI version: {version!r}; expected {SUPPORTED_ASGI_VERSION}"
        )
    spec_version = asgi.get("spec_version")
    if spec_version is not None and not isinstance(spec_version, str):
        raise GwtAsgiProtocolError("ASGI spec_version must be a string")


def _validate_http_scope(scope: dict[str, Any]) -> None:
    _validate_asgi_scope(
        scope,
        expected_type="http",
    )
    asgi = cast(dict[str, Any], scope["asgi"])
    spec_version = cast(str, asgi.get("spec_version", "2.0"))
    major, separator, minor = spec_version.partition(".")
    if (
        not separator
        or not major.isdigit()
        or not minor.isdigit()
        or int(major) != SUPPORTED_ASGI_HTTP_SPEC_MAJOR
    ):
        raise GwtAsgiProtocolError(
            f"unsupported ASGI HTTP spec version: {spec_version!r}"
        )
    http_version = scope.get("http_version")
    if http_version not in {"1.0", "1.1", "2"}:
        raise GwtAsgiProtocolError(
            f"invalid ASGI HTTP version: {http_version!r}"
        )
    method = scope.get("method")
    if not isinstance(method, str):
        raise GwtAsgiProtocolError("ASGI HTTP method must be a string")
    if not method or method != method.upper():
        raise GwtAsgiProtocolError("ASGI HTTP method must be non-empty and uppercase")
    if not isinstance(scope.get("path"), str):
        raise GwtAsgiProtocolError("ASGI HTTP path must be a string")
    raw_path = scope.get("raw_path")
    if raw_path is not None and not isinstance(raw_path, bytes):
        raise GwtAsgiProtocolError("ASGI HTTP raw_path must be bytes or None")
    if not isinstance(scope.get("query_string"), bytes):
        raise GwtAsgiProtocolError("ASGI HTTP query_string must be bytes")
    _http_header_items(scope)


def _http_headers(scope: dict[str, Any]) -> dict[str, str]:
    raw_headers = _http_header_items(scope)
    headers: dict[str, str] = {}
    for raw_item in raw_headers:
        if not isinstance(raw_item, (list, tuple)):
            raise GwtAsgiProtocolError("ASGI HTTP header entries must be pairs")
        item = cast(list[object] | tuple[object, ...], raw_item)
        if len(item) != 2:
            raise GwtAsgiProtocolError("ASGI HTTP header entries must be pairs")
        key, value = item
        if not isinstance(key, bytes) or not isinstance(value, bytes):
            raise GwtAsgiProtocolError("ASGI HTTP header names and values must be bytes")
        headers[key.decode("latin-1")] = value.decode("latin-1")
    return headers


def _http_header_items(scope: dict[str, Any]) -> Iterable[object]:
    raw_headers = scope.get("headers")
    if (
        not isinstance(raw_headers, Iterable)
        or isinstance(raw_headers, (bytes, str, dict))
    ):
        raise GwtAsgiProtocolError("ASGI HTTP headers must be an iterable of pairs")
    return cast(Iterable[object], raw_headers)


def _http_request_path(scope: dict[str, Any]) -> str:
    raw_path = scope.get("raw_path")
    path = (
        raw_path.decode("ascii", "surrogateescape")
        if isinstance(raw_path, bytes)
        else cast(str, scope["path"])
    )
    query_string = cast(bytes, scope["query_string"])
    if query_string:
        return f"{path}?{query_string.decode('ascii', 'surrogateescape')}"
    return path


def _message_type(message: AsgiMessage) -> str:
    message_type = message.get("type")
    if not isinstance(message_type, str):
        raise GwtAsgiProtocolError("ASGI event type must be a string")
    return message_type


def create_asgi_application(
    service: GwtHttpService,
    *,
    max_concurrent_requests: int = DEFAULT_MAX_CONCURRENT_REQUESTS,
    shutdown_grace_seconds: float = DEFAULT_SHUTDOWN_GRACE_SECONDS,
) -> GwtAsgiApplication:
    """Create an ASGI adapter without importing an ASGI server package."""

    return GwtAsgiApplication(
        GwtHttpApplication(
            service,
            max_concurrent_requests=max_concurrent_requests,
        ),
        shutdown_grace_seconds=shutdown_grace_seconds,
    )


def run_asgi_server(
    service: GwtHttpService,
    *,
    path: str | Path,
    host: str,
    port: int,
    max_concurrent_requests: int,
    shutdown_grace_seconds: float,
) -> int:
    """Run the optional Uvicorn transport used by ``gwt serve --engine asgi``."""

    try:
        uvicorn = cast(_UvicornModule, importlib.import_module("uvicorn"))
    except ModuleNotFoundError as exc:
        if exc.name != "uvicorn":
            raise
        service.close()
        raise ValueError(
            "the ASGI engine requires the optional serve dependency; "
            "install it with `python -m pip install 'gwtlang[serve]'`"
        ) from exc

    application = create_asgi_application(
        service,
        max_concurrent_requests=max_concurrent_requests,
        shutdown_grace_seconds=shutdown_grace_seconds,
    )
    try:
        listener = _bind_socket(host, port)
    except Exception:
        application.application.close()
        raise
    actual_port = int(listener.getsockname()[1])
    config = uvicorn.Config(
        application,
        host=host,
        port=actual_port,
        lifespan="on",
        timeout_graceful_shutdown=max(1, math.ceil(shutdown_grace_seconds)),
    )
    print(f"Serving {path} at http://{host}:{actual_port}", flush=True)
    server = uvicorn.Server(config)
    _install_uvicorn_exit_hook(server, application.application)
    try:
        server.run(sockets=[listener])
    finally:
        application.application.begin_draining()
        application.application.wait_for_idle(shutdown_grace_seconds)
        application.application.close()
        listener.close()
    return 0


def _install_uvicorn_exit_hook(
    server: _UvicornServer,
    application: GwtHttpApplication,
) -> None:
    original_handle_exit = server.handle_exit

    def handle_exit(sig: int, frame: FrameType | None) -> None:
        application.begin_draining()
        original_handle_exit(sig, frame)

    setattr(server, "handle_exit", handle_exit)


def _bind_socket(host: str, port: int) -> socket.socket:
    last_error: OSError | None = None
    addresses = socket.getaddrinfo(
        host,
        port,
        type=socket.SOCK_STREAM,
        flags=socket.AI_PASSIVE,
    )
    for family, socket_type, protocol, _, address in addresses:
        listener = socket.socket(family, socket_type, protocol)
        try:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(address)
            listener.listen(2048)
            listener.set_inheritable(True)
            return listener
        except OSError as exc:
            last_error = exc
            listener.close()
    if last_error is not None:
        raise last_error
    raise OSError(f"could not resolve ASGI bind address: {host}")
