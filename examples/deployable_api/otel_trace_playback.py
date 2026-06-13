from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen


DEFAULT_JAEGER_URL = "http://127.0.0.1:16686"


@dataclass(frozen=True)
class PlaybackEvent:
    sequence: int | None
    timestamp: int
    span_name: str
    name: str
    summary: str
    source: str | None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print GWT trace events from Jaeger as a linear playback.",
    )
    parser.add_argument("trace_id", help="Trace ID printed by otel_client_demo.py")
    parser.add_argument(
        "--jaeger-url",
        default=DEFAULT_JAEGER_URL,
        help=f"Jaeger base URL. Defaults to {DEFAULT_JAEGER_URL}.",
    )
    parser.add_argument(
        "--max-summary",
        type=int,
        default=180,
        help="Maximum summary characters per event line. Defaults to 180.",
    )
    parser.add_argument(
        "--show-span",
        action="store_true",
        help="Include the span name for each event.",
    )
    args = parser.parse_args(argv)

    try:
        trace = fetch_trace(args.jaeger_url, args.trace_id)
    except TracePlaybackError as exc:
        print(f"trace playback failed: {exc}", file=sys.stderr)
        return 1

    events = extract_gwt_events(trace)
    if not events:
        print(f"trace {args.trace_id} has no GWT events")
        return 1

    print(f"trace {args.trace_id}")
    for event in events:
        print(format_event(event, max_summary=args.max_summary, show_span=args.show_span))
    return 0


def fetch_trace(jaeger_url: str, trace_id: str) -> dict[str, Any]:
    url = f"{jaeger_url.rstrip('/')}/api/traces/{quote(trace_id)}"
    try:
        with urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise TracePlaybackError(f"Jaeger returned HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise TracePlaybackError(f"could not reach Jaeger at {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise TracePlaybackError(f"Jaeger returned invalid JSON from {url}") from exc

    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise TracePlaybackError(f"trace {trace_id} was not found in Jaeger")
    trace = data[0]
    if not isinstance(trace, dict):
        raise TracePlaybackError(f"trace {trace_id} has an unexpected Jaeger shape")
    return trace


def extract_gwt_events(trace: dict[str, Any]) -> list[PlaybackEvent]:
    spans = trace.get("spans")
    if not isinstance(spans, list):
        return []

    events: list[PlaybackEvent] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        span_name = str(span.get("operationName") or span.get("name") or "<span>")
        logs = span.get("logs")
        if not isinstance(logs, list):
            continue
        for log in logs:
            if not isinstance(log, dict):
                continue
            fields = _fields_by_key(log.get("fields"))
            sequence = _int_field(fields.get("gwt.event.sequence"))
            event_name = _str_field(fields.get("event"))
            if sequence is None or event_name is None:
                continue
            events.append(
                PlaybackEvent(
                    sequence=sequence,
                    timestamp=_int_value(log.get("timestamp")) or 0,
                    span_name=span_name,
                    name=event_name,
                    summary=_event_summary(fields),
                    source=_source(fields),
                )
            )

    return sorted(events, key=lambda event: (event.sequence or 0, event.timestamp))


def format_event(event: PlaybackEvent, *, max_summary: int, show_span: bool) -> str:
    sequence = f"{event.sequence:03}" if event.sequence is not None else "---"
    summary = _truncate(event.summary, max_summary)
    line = f"{sequence} {event.name}: {summary}"
    if event.source is not None:
        line = f"{line} ({event.source})"
    if show_span:
        line = f"{line} [{event.span_name}]"
    return line


def _fields_by_key(fields: object) -> dict[str, object]:
    if not isinstance(fields, list):
        return {}
    result: dict[str, object] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        key = field.get("key")
        if isinstance(key, str):
            result[key] = field.get("value")
    return result


def _event_summary(fields: dict[str, object]) -> str:
    for key in (
        "gwt.event.summary",
        "gwt.request.summary",
        "gwt.contract.summary",
        "gwt.condition.summary",
        "gwt.branch.summary",
        "gwt.assertion.summary",
        "gwt.state.summary",
        "exception.message",
        "gwt.statement.text",
    ):
        value = _str_field(fields.get(key))
        if value:
            return value
    return "GWT event"


def _source(fields: dict[str, object]) -> str | None:
    path = _str_field(fields.get("code.file.path"))
    line = _int_field(fields.get("code.line.number"))
    if path is None or line is None or line <= 0:
        return None
    return f"{path}:{line}"


def _str_field(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_field(value: object) -> int | None:
    parsed = _int_value(value)
    return parsed if parsed is not None else None


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _truncate(value: str, max_length: int) -> str:
    if max_length <= 0 or len(value) <= max_length:
        return value
    return value[: max_length - 1] + "..."


class TracePlaybackError(Exception):
    pass


if __name__ == "__main__":
    raise SystemExit(main())
