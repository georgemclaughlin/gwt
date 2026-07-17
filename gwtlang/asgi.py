"""Optional ASGI transport for the transport-neutral GWT HTTP application."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import importlib
import math
from pathlib import Path
import socket
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


class _UvicornServer(Protocol):
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
        scope_type = scope.get("type")
        if scope_type == "lifespan":
            await self._lifespan(receive, send)
            return
        if scope_type == "http":
            await self._http(scope, receive, send)
            return
        raise RuntimeError(f"unsupported ASGI scope type: {scope_type!r}")

    async def _http(
        self,
        scope: dict[str, Any],
        receive: AsgiReceive,
        send: AsgiSend,
    ) -> None:
        method = str(scope.get("method", "GET")).upper()
        body = bytearray()
        too_large = False
        more_body = True
        while more_body:
            message = await receive()
            if message.get("type") == "http.disconnect":
                return
            if message.get("type") != "http.request":
                continue
            chunk = message.get("body", b"")
            if isinstance(chunk, bytes) and not too_large:
                if len(body) + len(chunk) > self.application.service.max_request_body_bytes:
                    too_large = True
                else:
                    body.extend(chunk)
            more_body = bool(message.get("more_body", False))

        if too_large:
            raw_headers = scope.get("headers", [])
            headers = {
                bytes(key).decode("latin-1"): bytes(value).decode("latin-1")
                for key, value in raw_headers
            }
            response = self.application.body_too_large_response(
                HttpApplicationRequest(method, str(scope.get("path", "/")), headers)
            )
        else:
            raw_headers = scope.get("headers", [])
            headers = {
                bytes(key).decode("latin-1"): bytes(value).decode("latin-1")
                for key, value in raw_headers
            }
            path = str(scope.get("raw_path", b"").decode("ascii", "surrogateescape"))
            if not path:
                path = str(scope.get("path", "/"))
            query_string = scope.get("query_string", b"")
            if query_string:
                path = f"{path}?{bytes(query_string).decode('ascii', 'surrogateescape')}"
            response = await asyncio.to_thread(
                self.application.handle,
                HttpApplicationRequest(method, path, headers, bytes(body)),
            )
        await _send_response(response, send)

    async def _lifespan(self, receive: AsgiReceive, send: AsgiSend) -> None:
        while True:
            message = await receive()
            message_type = message.get("type")
            if message_type == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
                continue
            if message_type == "lifespan.shutdown":
                self.application.begin_draining()
                finished = await asyncio.to_thread(
                    self.application.wait_for_idle,
                    self.shutdown_grace_seconds,
                )
                self.application.close()
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
    try:
        uvicorn.Server(config).run(sockets=[listener])
    finally:
        application.application.begin_draining()
        application.application.wait_for_idle(shutdown_grace_seconds)
        application.application.close()
        listener.close()
    return 0


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
