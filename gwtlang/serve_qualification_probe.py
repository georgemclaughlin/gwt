"""Controlled subprocess used by the served-decision qualification harness.

This is intentionally not a public CLI.  It runs the same ASGI transport and
HTTP application as ``gwt serve`` while holding the first evaluation at a
known seam.  The parent harness can therefore verify overload and active
SIGTERM behavior without depending on machine speed or a deliberately slow GWT
program.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from threading import Lock
import time
from typing import Any

from .asgi import run_asgi_server
from .http_server import GwtHttpService, HttpRequestRoute, HttpRouteResult
from .runtime import ImportPolicy
from .tracing import GwtTraceRecorder


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("file", type=Path)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--hold-timeout", type=float, required=True)
    parser.add_argument("--import-root", type=Path, action="append", default=[])
    parser.add_argument("--no-absolute-imports", action="store_true")
    args = parser.parse_args(argv)

    import_policy = _import_policy(args.import_root, not args.no_absolute_imports)
    service = GwtHttpService.from_file(
        args.file,
        import_roots=import_policy.allowed_roots,
        allow_absolute_imports=import_policy.allow_absolute,
    )
    original_execute = GwtHttpService._execute_route
    lock = Lock()
    held = False

    def controlled_execute(
        self: GwtHttpService,
        route: HttpRequestRoute,
        json_state: dict[str, Any],
        recorder: GwtTraceRecorder | None,
    ) -> HttpRouteResult:
        nonlocal held
        with lock:
            should_hold = not held
            held = True
        if should_hold:
            args.marker.write_text("admitted\n", encoding="utf-8")
            deadline = time.monotonic() + args.hold_timeout
            while not args.release.exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("qualification hold timed out")
                time.sleep(0.01)
        return original_execute(self, route, json_state, recorder)

    GwtHttpService._execute_route = controlled_execute
    return run_asgi_server(
        service,
        path=args.file,
        host=args.host,
        port=args.port,
        max_concurrent_requests=1,
        shutdown_grace_seconds=args.hold_timeout,
    )


def _import_policy(roots: list[Path], allow_absolute: bool) -> ImportPolicy:
    return ImportPolicy(tuple(root.resolve() for root in roots), allow_absolute)


if __name__ == "__main__":
    raise SystemExit(main())
