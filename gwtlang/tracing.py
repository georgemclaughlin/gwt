from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import json
import os
import secrets
import time
from typing import Any, cast
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .version import PACKAGE_VERSION

SPAN_KIND_INTERNAL = 1
SPAN_KIND_SERVER = 2
SPAN_KIND_CLIENT = 3

STATUS_CODE_UNSET = 0
STATUS_CODE_OK = 1
STATUS_CODE_ERROR = 2


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    parent_span_id: str
    trace_flags: str = "01"


@dataclass
class OtlpEvent:
    name: str
    time_unix_nano: int
    attributes: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


@dataclass
class OtlpSpan:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    name: str
    kind: int
    start_time_unix_nano: int
    end_time_unix_nano: int | None = None
    attributes: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    events: list[OtlpEvent] = field(default_factory=lambda: list[OtlpEvent]())
    status_code: int = STATUS_CODE_UNSET
    status_message: str | None = None

    def finish(self, *, error: str | None = None) -> None:
        if self.end_time_unix_nano is None:
            self.end_time_unix_nano = now_unix_nano()
        if error is None:
            self.status_code = STATUS_CODE_OK
            return
        self.status_code = STATUS_CODE_ERROR
        self.status_message = error


@dataclass(frozen=True)
class OtlpMetric:
    name: str
    description: str
    unit: str
    kind: str
    value: int | float
    attributes: dict[str, Any]
    start_time_unix_nano: int
    time_unix_nano: int


@dataclass(frozen=True)
class StateChange:
    patch: list[dict[str, Any]]
    operation: str
    pointer: str
    new_value: Any
    old_value: Any = None
    has_old_value: bool = False


class OtlpExportError(Exception):
    pass


class OtlpHttpExporter:
    def __init__(self, endpoint: str, *, timeout: float = 2.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def export(self, spans: list[OtlpSpan]) -> None:
        if not spans:
            return
        payload = otlp_traces_payload(spans)
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            request = Request(
                self.endpoint,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=self.timeout) as response:
                if response.status >= 300:
                    raise OtlpExportError(f"OTLP export failed with HTTP {response.status}")
        except OtlpExportError:
            raise
        except Exception as exc:
            raise OtlpExportError(f"OTLP export failed: {exc}") from exc


class OtlpMetricsExporter:
    def __init__(self, endpoint: str, *, timeout: float = 2.0) -> None:
        self.endpoint = endpoint
        self.timeout = timeout

    def export(self, metrics: list[OtlpMetric], *, service_name: str) -> None:
        if not metrics:
            return
        payload = otlp_metrics_payload(metrics, service_name=service_name)
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        try:
            request = Request(
                self.endpoint,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=self.timeout) as response:
                if response.status >= 300:
                    raise OtlpExportError(f"OTLP metric export failed with HTTP {response.status}")
        except OtlpExportError:
            raise
        except Exception as exc:
            raise OtlpExportError(f"OTLP metric export failed: {exc}") from exc


class GwtTraceRecorder:
    def __init__(
        self,
        *,
        program_file: str,
        program_name: str | None,
        program_hash: str,
        request_name: str,
        route_path: str | None = None,
        context: TraceContext | None = None,
        service_name: str = "gwt-serve",
        include_values: bool = True,
    ) -> None:
        self.trace_id = context.trace_id if context is not None else new_trace_id()
        self.trace_flags = context.trace_flags if context is not None else "01"
        self.include_values = include_values
        self.root_span_id = new_span_id()
        self._sequence = 0
        self._spans: list[OtlpSpan] = []
        self._span_stack: list[OtlpSpan] = []

        root_name = f"POST {route_path}" if route_path else f"GWT REQUEST {request_name}"
        root = OtlpSpan(
            trace_id=self.trace_id,
            span_id=self.root_span_id,
            parent_span_id=context.parent_span_id if context is not None else None,
            name=root_name,
            kind=SPAN_KIND_SERVER if route_path else SPAN_KIND_INTERNAL,
            start_time_unix_nano=now_unix_nano(),
            attributes={
                "service.name": service_name,
                "gwt.program.file": program_file,
                "gwt.program.hash": program_hash,
                "gwt.request.name": request_name,
                "gwt.trace.values": "full" if include_values else "redacted",
            },
        )
        if program_name is not None:
            root.attributes["gwt.program.name"] = program_name
        if route_path is not None:
            root.attributes["http.route"] = route_path
            root.attributes["http.request.method"] = "POST"
        self._push_span(root)

    @property
    def traceparent(self) -> str:
        return make_traceparent(self.trace_id, self.root_span_id, self.trace_flags)

    @property
    def spans(self) -> list[OtlpSpan]:
        return self._spans

    def before_line(
        self,
        line: Any,
        state: dict[str, Any],
        env: dict[str, Any],
        stack: list[Any] | None = None,
    ) -> None:
        del state, env
        attributes = self._line_attributes(line)
        if stack:
            attributes["gwt.stack.depth"] = len(stack)
            attributes["gwt.stack"] = " > ".join(
                str(getattr(frame, "name", "Main")) for frame in stack
            )
        attributes["gwt.statement.text"] = str(getattr(line, "text", ""))
        self._event("gwt.statement.executed", attributes)

    def enter_request(self, name: str, line: Any) -> None:
        self._push_child_span(
            f"GWT REQUEST {name}",
            attributes={
                "gwt.request.name": name,
                **self._line_attributes(line),
            },
        )

    def exit_request(self, *, error: str | None = None) -> None:
        self._pop_span(error=error)

    def enter_behavior(self, signature: str, line: Any) -> None:
        self._push_child_span(
            f"GWT WHEN {signature}",
            attributes={
                "gwt.behavior.signature": signature,
                **self._line_attributes(line),
            },
        )

    def exit_behavior(self, *, error: str | None = None) -> None:
        self._pop_span(error=error)

    def record_contract(
        self,
        *,
        label: str,
        path: str,
        value_type: str,
        passed: bool,
        line: Any,
        error: str | None = None,
    ) -> None:
        attributes: dict[str, Any] = {
            "gwt.contract.label": label,
            "gwt.contract.path": path,
            "gwt.contract.type": value_type,
            "gwt.contract.passed": passed,
            **self._line_attributes(line),
        }
        if error is not None:
            attributes["error.message"] = error if self.include_values else "GWT contract failed"
            if not self.include_values:
                attributes["error.message.redacted"] = True
        attributes["gwt.contract.summary"] = (
            f"{label} {path} is {value_type} {'passed' if passed else 'failed'}"
        )
        self._event("gwt.contract.checked", attributes)

    def record_condition(self, *, text: str, result: bool, line: Any | None = None) -> None:
        attributes: dict[str, Any] = {
            "gwt.condition.text": text,
            "gwt.condition.result": result,
            "gwt.condition.summary": f"{text} -> {_result_text(result)}",
        }
        if line is not None:
            attributes.update(self._line_attributes(line))
        self._event("gwt.condition.evaluated", attributes)

    def record_branch(
        self,
        *,
        kind: str,
        condition: str,
        selected: bool,
        line: Any,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> None:
        attributes: dict[str, Any] = {
            "gwt.branch.kind": kind,
            "gwt.branch.condition": condition,
            "gwt.branch.selected": selected,
            "gwt.branch.summary": _branch_summary(kind, condition, selected, start_line, end_line),
            **self._line_attributes(line),
        }
        if start_line is not None:
            attributes["gwt.branch.start_line"] = start_line
        if end_line is not None:
            attributes["gwt.branch.end_line"] = end_line
        self._event("gwt.branch.selected" if selected else "gwt.branch.skipped", attributes)

    def record_assertion(self, *, text: str, result: bool, line: Any | None = None) -> None:
        attributes: dict[str, Any] = {
            "gwt.assertion.text": text,
            "gwt.assertion.result": result,
            "gwt.assertion.summary": f"THEN {text} {'passed' if result else 'failed'}",
        }
        if line is not None:
            attributes.update(self._line_attributes(line))
        self._event("gwt.assertion.checked", attributes)

    def record_state_change(
        self,
        *,
        path: str,
        change: StateChange,
        line: Any | None = None,
    ) -> None:
        attributes: dict[str, Any] = {
            "gwt.state.path": path,
            "gwt.state.operation": change.operation,
            "gwt.state.pointer": change.pointer,
        }
        if self.include_values:
            attributes["gwt.state.new"] = _attribute_value(change.new_value)
            attributes["gwt.state.patch"] = json.dumps(_jsonable(change.patch), separators=(",", ":"), sort_keys=True)
            if change.has_old_value:
                attributes["gwt.state.old"] = _attribute_value(change.old_value)
            attributes["gwt.state.summary"] = _state_summary(path, change)
        else:
            attributes["gwt.state.values.redacted"] = True
            attributes["gwt.state.summary"] = _state_summary(path, change, include_values=False)
        if line is not None:
            attributes.update(self._line_attributes(line))
        self._event("gwt.state.changed", attributes)

    def record_local_change(self, *, path: str, line: Any | None = None) -> None:
        attributes: dict[str, Any] = {"gwt.local.path": path}
        if line is not None:
            attributes.update(self._line_attributes(line))
        self._event("gwt.local.changed", attributes)

    def record_output(self, *, value: str, line: Any | None = None) -> None:
        if self.include_values:
            attributes: dict[str, Any] = {"gwt.output": value}
        else:
            attributes = {"gwt.output.redacted": True}
        if line is not None:
            attributes.update(self._line_attributes(line))
        self._event("gwt.output", attributes)

    def record_request_completed(self, *, output: dict[str, Any], output_paths: list[str] | None = None) -> None:
        output_fields = _flatten_scalar_paths(output)
        request_name = self._span_stack[-1].attributes.get("gwt.request.name")
        redacted_output_fields = {path: None for path in (output_paths or output_fields)}
        attributes: dict[str, Any] = {
            "gwt.request.outcome": "completed",
            "gwt.request.summary": _request_summary(
                request_name,
                output_fields if self.include_values else redacted_output_fields,
                include_values=self.include_values,
            ),
        }
        self._span_stack[-1].attributes["gwt.request.summary"] = attributes["gwt.request.summary"]
        if self.include_values:
            attributes["gwt.output"] = json.dumps(_jsonable(output), separators=(",", ":"), sort_keys=True)
            for path, value in output_fields.items():
                key = f"gwt.output.{path}"
                attributes[key] = _attribute_value(value)
                self._span_stack[-1].attributes[key] = _attribute_value(value)
        else:
            attributes["gwt.output.redacted"] = True
            if redacted_output_fields:
                attributes["gwt.output.fields"] = ", ".join(redacted_output_fields)
        self._event("gwt.request.completed", attributes)

    def record_error(self, error: str) -> None:
        if self.include_values:
            self._event("exception", {"exception.type": "GwtError", "exception.message": error})
            return
        self._event(
            "exception",
            {
                "exception.type": "GwtError",
                "exception.message": "GWT error",
                "exception.message.redacted": True,
            },
        )

    def finish(self, *, error: str | None = None) -> None:
        if error is not None:
            self.record_error(error)
        while self._span_stack:
            self._pop_span(error=error)

    def _push_child_span(self, name: str, *, attributes: dict[str, Any]) -> None:
        parent = self._span_stack[-1]
        span = OtlpSpan(
            trace_id=self.trace_id,
            span_id=new_span_id(),
            parent_span_id=parent.span_id,
            name=name,
            kind=SPAN_KIND_INTERNAL,
            start_time_unix_nano=now_unix_nano(),
            attributes=attributes,
        )
        self._push_span(span)

    def _push_span(self, span: OtlpSpan) -> None:
        self._spans.append(span)
        self._span_stack.append(span)

    def _pop_span(self, *, error: str | None = None) -> None:
        span = self._span_stack.pop()
        span.finish(error=self._error_message(error))

    def _error_message(self, error: str | None) -> str | None:
        if error is None or self.include_values:
            return error
        return "GWT error"

    def _event(self, name: str, attributes: dict[str, Any]) -> None:
        self._sequence += 1
        event_attributes = {
            "gwt.event.sequence": self._sequence,
            "gwt.event.summary": _event_summary(name, attributes),
            **attributes,
        }
        self._span_stack[-1].events.append(
            OtlpEvent(name, now_unix_nano(), event_attributes)
        )

    def _line_attributes(self, line: Any) -> dict[str, Any]:
        return {
            "code.file.path": str(getattr(line, "filename", None) or "<source>"),
            "code.line.number": int(getattr(line, "number", 0) or 0),
            "code.column.number": int(getattr(line, "column", 0) or 0),
            "gwt.source.text": str(getattr(line, "text", "")),
        }


def now_unix_nano() -> int:
    return time.time_ns()


def new_trace_id() -> str:
    return secrets.token_hex(16)


def new_span_id() -> str:
    return secrets.token_hex(8)


def parse_traceparent(value: str | None) -> TraceContext | None:
    if value is None:
        return None
    parts = value.strip().split("-")
    if len(parts) != 4:
        return None
    version, trace_id, span_id, trace_flags = parts
    if (
        len(version) != 2
        or len(trace_id) != 32
        or len(span_id) != 16
        or len(trace_flags) != 2
        or trace_id == "0" * 32
        or span_id == "0" * 16
        or not all(_is_lower_hex(part) for part in parts)
    ):
        return None
    return TraceContext(trace_id, span_id, trace_flags)


def make_traceparent(trace_id: str, span_id: str, trace_flags: str = "01") -> str:
    return f"00-{trace_id}-{span_id}-{trace_flags}"


def otlp_trace_endpoint(explicit_endpoint: str | None = None) -> str | None:
    if explicit_endpoint:
        return _with_trace_path(explicit_endpoint)
    trace_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    if trace_endpoint:
        return trace_endpoint
    base_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if base_endpoint:
        return _with_trace_path(base_endpoint)
    return None


def otlp_metrics_endpoint(explicit_endpoint: str | None = None) -> str | None:
    if explicit_endpoint:
        return _with_metrics_path(explicit_endpoint)
    metrics_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")
    if metrics_endpoint:
        return metrics_endpoint
    base_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if base_endpoint:
        return _with_metrics_path(base_endpoint)
    return None


def json_patch_for_set(root: dict[str, Any], path: str, value: Any) -> list[dict[str, Any]]:
    parts = path.split(".")
    current: Any = root
    pointer_parts: list[str] = []
    for index, part in enumerate(parts[:-1]):
        if not isinstance(current, dict) or part not in current:
            return _patch_for_missing_parent(pointer_parts, parts[index:], value)
        current = cast(dict[str, Any], current)[part]
        pointer_parts.append(part)

    final = parts[-1]
    op = "replace" if isinstance(current, dict) and final in current else "add"
    return [
        {
            "op": op,
            "path": _json_pointer([*pointer_parts, final]),
            "value": _jsonable(value),
        }
    ]


def state_change_for_set(root: dict[str, Any], path: str, value: Any) -> StateChange | None:
    old_exists, old_value = _value_at_path(root, path)
    if old_exists and _jsonable(old_value) == _jsonable(value):
        return None
    patch = json_patch_for_set(root, path, value)
    last = patch[-1]
    return StateChange(
        patch=patch,
        operation=str(last["op"]),
        pointer=str(last["path"]),
        new_value=value,
        old_value=old_value if old_exists else None,
        has_old_value=old_exists,
    )


def otlp_traces_payload(spans: list[OtlpSpan]) -> dict[str, Any]:
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _otlp_attribute("service.name", _service_name(spans)),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "gwtlang",
                            "version": PACKAGE_VERSION,
                        },
                        "spans": [_otlp_span(span) for span in spans],
                    }
                ],
            }
        ]
    }


def otlp_metrics_payload(
    metrics: list[OtlpMetric],
    *,
    service_name: str,
) -> dict[str, Any]:
    return {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        _otlp_attribute("service.name", service_name),
                    ]
                },
                "scopeMetrics": [
                    {
                        "scope": {
                            "name": "gwtlang",
                            "version": PACKAGE_VERSION,
                        },
                        "metrics": [_otlp_metric(metric) for metric in metrics],
                    }
                ],
            }
        ]
    }


def _otlp_metric(metric: OtlpMetric) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": metric.name,
        "description": metric.description,
        "unit": metric.unit,
    }
    data_point = _otlp_metric_data_point(metric)
    if metric.kind == "sum":
        payload["sum"] = {
            "dataPoints": [data_point],
            "aggregationTemporality": 1,
            "isMonotonic": True,
        }
        return payload
    if metric.kind == "histogram":
        payload["histogram"] = {
            "dataPoints": [
                {
                    **data_point,
                    "count": "1",
                    "sum": float(metric.value),
                    "bucketCounts": ["1"],
                    "explicitBounds": [],
                }
            ],
            "aggregationTemporality": 1,
        }
        return payload
    raise OtlpExportError(f"unknown OTLP metric kind: {metric.kind}")


def _otlp_metric_data_point(metric: OtlpMetric) -> dict[str, Any]:
    data_point: dict[str, Any] = {
        "attributes": [
            _otlp_attribute(key, value)
            for key, value in metric.attributes.items()
        ],
        "startTimeUnixNano": str(metric.start_time_unix_nano),
        "timeUnixNano": str(metric.time_unix_nano),
    }
    if metric.kind == "sum":
        if isinstance(metric.value, int):
            data_point["asInt"] = str(metric.value)
        else:
            data_point["asDouble"] = float(metric.value)
    return data_point


def _otlp_span(span: OtlpSpan) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "name": span.name,
        "kind": span.kind,
        "startTimeUnixNano": str(span.start_time_unix_nano),
        "endTimeUnixNano": str(span.end_time_unix_nano or now_unix_nano()),
        "attributes": [
            _otlp_attribute(key, value)
            for key, value in span.attributes.items()
        ],
        "events": [_otlp_event(event) for event in span.events],
        "status": {"code": span.status_code},
    }
    if span.parent_span_id is not None:
        payload["parentSpanId"] = span.parent_span_id
    if span.status_message is not None:
        cast(dict[str, Any], payload["status"])["message"] = span.status_message
    return payload


def _otlp_event(event: OtlpEvent) -> dict[str, Any]:
    return {
        "timeUnixNano": str(event.time_unix_nano),
        "name": event.name,
        "attributes": [
            _otlp_attribute(key, value)
            for key, value in event.attributes.items()
        ],
    }


def _otlp_attribute(key: str, value: Any) -> dict[str, Any]:
    return {"key": key, "value": _otlp_any_value(value)}


def _otlp_any_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if value is None:
        return {"stringValue": "null"}
    return {"stringValue": str(value)}


def _service_name(spans: list[OtlpSpan]) -> str:
    for span in spans:
        service_name = span.attributes.get("service.name")
        if isinstance(service_name, str):
            return service_name
    return "gwt"


def _with_trace_path(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.path.endswith("/v1/traces"):
        return endpoint
    return f"{endpoint}/v1/traces"


def _with_metrics_path(endpoint: str) -> str:
    endpoint = endpoint.rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.path.endswith("/v1/metrics"):
        return endpoint
    return f"{endpoint}/v1/metrics"


def _is_lower_hex(value: str) -> bool:
    return all(character in "0123456789abcdef" for character in value)


def _json_pointer(parts: list[str]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in parts)


def _patch_for_missing_parent(
    existing_parts: list[str],
    missing_parts: list[str],
    value: Any,
) -> list[dict[str, Any]]:
    patch: list[dict[str, Any]] = []
    pointer_parts = [*existing_parts]
    for part in missing_parts[:-1]:
        pointer_parts.append(part)
        patch.append({"op": "add", "path": _json_pointer(pointer_parts), "value": {}})
    pointer_parts.append(missing_parts[-1])
    patch.append({"op": "add", "path": _json_pointer(pointer_parts), "value": _jsonable(value)})
    return patch


def _value_at_path(root: dict[str, Any], path: str) -> tuple[bool, Any]:
    current: Any = root
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = cast(dict[str, Any], current)[part]
    return True, current


def _nested_object(parts: list[str], value: Any) -> Any:
    if not parts:
        return value
    return {parts[0]: _nested_object(parts[1:], value)}


def _attribute_value(value: Any) -> Any:
    if isinstance(value, dict | list):
        return json.dumps(_jsonable(value), separators=(",", ":"), sort_keys=True)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _flatten_scalar_paths(value: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}

    def visit(prefix: str, item: Any) -> None:
        if isinstance(item, dict):
            for key, nested in cast(dict[object, Any], item).items():
                visit(f"{prefix}.{key}" if prefix else str(key), nested)
            return
        if isinstance(item, list):
            return
        flattened[prefix] = item

    visit("", value)
    return flattened


def _result_text(result: bool) -> str:
    return "true" if result else "false"


def _branch_summary(
    kind: str,
    condition: str,
    selected: bool,
    start_line: int | None,
    end_line: int | None,
) -> str:
    action = "selected" if selected else "skipped"
    line_text = ""
    if start_line is not None and end_line is not None:
        line_text = f" lines {start_line}-{end_line}" if start_line != end_line else f" line {start_line}"
    return f"{kind} {condition} {action}{line_text}"


def _event_summary(name: str, attributes: dict[str, Any]) -> str:
    for key in (
        "gwt.request.summary",
        "gwt.contract.summary",
        "gwt.condition.summary",
        "gwt.branch.summary",
        "gwt.assertion.summary",
        "gwt.state.summary",
    ):
        value = attributes.get(key)
        if value is not None:
            return str(value)
    if name == "gwt.statement.executed":
        text = str(attributes.get("gwt.statement.text") or "").strip()
        return f"execute {text}" if text else "execute statement"
    if name == "gwt.local.changed":
        return f"local {attributes.get('gwt.local.path', 'value')} changed"
    if name == "gwt.output":
        if attributes.get("gwt.output.redacted") is True:
            return "print [redacted]"
        return f"print {attributes.get('gwt.output', '')}"
    if name == "exception":
        return str(attributes.get("exception.message") or "GWT error")
    return name


def _request_summary(request_name: Any, output_fields: dict[str, Any], *, include_values: bool) -> str:
    name = str(request_name or "request")
    if not include_values:
        fields = ", ".join(output_fields)
        if not fields:
            return f"{name} completed"
        return f"{name} completed: {fields} [values redacted]"
    fields = ", ".join(
        f"{path}={_summary_value(value)}"
        for path, value in output_fields.items()
    )
    if not fields:
        return f"{name} completed"
    return f"{name} completed: {fields}"


def _summary_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, int | float | bool):
        return json.dumps(value)
    return json.dumps(_jsonable(value), separators=(",", ":"), sort_keys=True)


def _state_summary(path: str, change: StateChange, *, include_values: bool = True) -> str:
    if not include_values:
        return f"{path} {change.operation} [values redacted]"
    new_value = _display_value(change.new_value)
    if change.has_old_value:
        return f"{path} {change.operation} {_display_value(change.old_value)} -> {new_value}"
    return f"{path} {change.operation} {new_value}"


def _display_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, int | float | bool):
        return json.dumps(value)
    return json.dumps(_jsonable(value), separators=(",", ":"), sort_keys=True)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in cast(list[Any], value)]
    if isinstance(value, dict):
        return {
            str(key): _jsonable(item)
            for key, item in cast(dict[object, Any], value).items()
        }
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
