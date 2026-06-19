from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re
from pathlib import Path
from typing import Any, TypeAlias, TypeGuard, cast

from .runtime import ImportPolicy, Runtime, parse_program
from .tracing import GwtTraceRecorder, OtlpSpan

JsonScalar: TypeAlias = str | int | float | bool | None | Decimal
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


@dataclass(frozen=True)
class ExplainResult:
    request: str
    status: str
    subject: str
    reason: str | None
    input_lines: list[str]
    result_lines: list[str]
    bullets: list[str]
    outcome_line: int | None
    outcome_rule: str | None
    change_lines: list[str]

    def as_text(self) -> str:
        lines = [f"{self.request} returned {self.status}", ""]
        if self.input_lines:
            lines.append("Input:")
            lines.extend(self.input_lines)
            lines.append("")
        if self.result_lines:
            lines.append("Result:")
            lines.extend(self.result_lines)
            lines.append("")
        if self.bullets:
            lines.append(f"{self.subject} {human_outcome(self.status)} because:")
            lines.extend(f"- {bullet}" for bullet in self.bullets)
            lines.append("")
        if self.outcome_rule:
            lines.append("Outcome rule:")
            if self.outcome_line is not None:
                lines.append(f"line {self.outcome_line}")
            lines.extend(_wrap_condition(self.outcome_rule))
            lines.append("")
        if self.change_lines:
            lines.append("Changed values:")
            lines.extend(f"- {line}" for line in self.change_lines)
        return "\n".join(lines).rstrip() + "\n"


def explain_json_file(
    path: str | Path,
    json_state: dict[str, Any],
    *,
    request: str,
    json_file: str | Path | None = None,
    import_policy: ImportPolicy | None = None,
) -> ExplainResult:
    program_path = Path(path)
    source = program_path.read_text()
    program = parse_program(source, filename=str(program_path), import_policy=import_policy)
    recorder = GwtTraceRecorder(
        program_file=str(program_path),
        program_name=program.name,
        program_hash=f"sha256:{hashlib.sha256(source.encode('utf-8')).hexdigest()}",
        request_name=request,
        include_values=True,
    )
    result = Runtime(program, tracer=recorder).run_json(
        json_state,
        request,
        request_filename="<request>",
        json_filename=str(json_file) if json_file is not None else None,
    )
    recorder.finish()
    input_state = cast(JsonObject, json_state)
    state = cast(JsonObject, result.state)
    output_state = cast(JsonObject, result.scenarios[0].returned_state or {})
    outcome = _primary_outcome(output_state, state)
    decision: JsonObject = outcome if outcome is not None else {}
    status_value = decision.get("status")
    reason_value = decision.get("reason")
    status = str(status_value or "completed")
    reason = str(reason_value) if reason_value is not None else None
    outcome_branch = _selected_decide_branch(recorder.spans)
    outcome_rule = _clean_condition(outcome_branch.get("condition")) if outcome_branch else None
    outcome_line = outcome_branch.get("line") if outcome_branch else None
    return ExplainResult(
        request=request,
        status=status,
        subject=_subject(input_state),
        reason=reason,
        input_lines=_summary_lines(input_state, max_lines=12),
        result_lines=_summary_lines(output_state, max_lines=10, priority_fields=("status", "reason")),
        bullets=_explanation_bullets(input_state, decision, outcome_rule),
        outcome_line=_int_value(outcome_line),
        outcome_rule=outcome_rule,
        change_lines=_state_change_lines(recorder.spans, output_state, max_lines=10),
    )


def _selected_decide_branch(spans: list[OtlpSpan]) -> dict[str, object] | None:
    selected: dict[str, object] | None = None
    for span in spans:
        for event in span.events:
            attributes = dict(event.attributes)
            if (
                event.name == "gwt.branch.selected"
                and attributes.get("gwt.branch.kind") == "DECIDE"
                and attributes.get("gwt.branch.selected") is True
            ):
                selected = {
                    "line": attributes.get("code.line.number"),
                    "condition": attributes.get("gwt.branch.condition"),
                }
    return selected


def _primary_outcome(output_state: JsonObject, state: JsonObject) -> JsonObject | None:
    for root in (output_state, state):
        decision = _object_field(root, "decision")
        if decision is not None and "status" in decision:
            return decision
        for value in root.values():
            if isinstance(value, dict) and "status" in value:
                return cast(JsonObject, value)
    return None


def _explanation_bullets(
    json_state: JsonObject,
    decision: JsonObject,
    outcome_rule: str | None,
) -> list[str]:
    vendor: JsonObject = _object_field(json_state, "vendor") or {}
    bullets: list[str] = []

    missing_requirements = decision.get("missing_requirements")
    if isinstance(missing_requirements, list):
        for requirement_value in missing_requirements:
            text = str(requirement_value)
            if text.endswith("_expired"):
                bullets.append(f"{text.removesuffix('_expired')} is expired")
            else:
                bullets.append(f"{text} is missing")

    reasons_value = decision.get("reasons")
    reasons: set[str] = set()
    if isinstance(reasons_value, list):
        reasons = {str(reason_value) for reason_value in reasons_value}
    annual_spend = vendor.get("annual_spend")
    if "high_annual_spend" in reasons and annual_spend is not None:
        bullets.append(f"annual_spend is {annual_spend}, which adds inherent risk")
    if vendor.get("handles_customer_data") is True:
        bullets.append("the vendor handles customer data")
    if vendor.get("stores_payment_data") is True:
        bullets.append("the vendor stores payment data")
    high_signal_count = decision.get("high_signal_count")
    if _is_number(high_signal_count) and high_signal_count > 0:
        bullets.append(f"{_number_text(high_signal_count)} high-severity risk signal was present")

    risk_points = decision.get("risk_points")
    threshold = _risk_threshold(outcome_rule)
    if threshold is not None and _is_number(risk_points) and risk_points >= threshold:
        bullets.append(
            f"risk score {_number_text(risk_points)} crossed the review threshold {_number_text(threshold)}"
        )

    return _unique(bullets)


def _summary_lines(
    value: JsonValue,
    *,
    max_lines: int,
    priority_fields: tuple[str, ...] = (),
) -> list[str]:
    lines: list[str] = []

    def visit(path: str, item: JsonValue) -> None:
        if len(lines) >= max_lines:
            return
        if isinstance(item, dict):
            if not item:
                lines.append(f"{path or 'value'}: {{}}")
                return
            for key, nested in _ordered_items(item, priority_fields):
                nested_path = f"{path}.{key}" if path else str(key)
                visit(nested_path, nested)
            return
        if isinstance(item, list):
            lines.append(f"{path or 'value'}: {_list_summary(item)}")
            return
        lines.append(f"{path or 'value'}: {_display_value(item)}")

    visit("", value)
    total = _summary_line_count(value)
    if total > len(lines):
        lines.append(f"... {total - len(lines)} more")
    return lines


def _ordered_items(
    value: JsonObject,
    priority_fields: tuple[str, ...],
) -> list[tuple[str, JsonValue]]:
    priority = [
        item
        for item in value.items()
        if item[0] in priority_fields
    ]
    rest = [
        item
        for item in value.items()
        if item[0] not in priority_fields
    ]
    return [*priority, *rest]


def _summary_line_count(value: JsonValue) -> int:
    if isinstance(value, dict):
        if not value:
            return 1
        return sum(_summary_line_count(item) for item in value.values())
    return 1


def _list_summary(items: list[JsonValue]) -> str:
    if not items:
        return "[]"
    if len(items) <= 4 and all(_is_scalar(item) for item in items):
        return json.dumps([_jsonable(item) for item in items], separators=(",", ":"))
    return f"{len(items)} items"


def _state_change_lines(
    spans: list[OtlpSpan],
    output_state: JsonObject,
    *,
    max_lines: int,
) -> list[str]:
    output_roots = set(output_state.keys())
    if not output_roots:
        return []

    changes: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for span in spans:
        for event in span.events:
            if event.name != "gwt.state.changed":
                continue
            attributes = dict(event.attributes)
            path = str(attributes.get("gwt.state.path") or "")
            if not _is_output_path(path, output_roots):
                continue
            if "gwt.state.old" not in attributes or "gwt.state.new" not in attributes:
                continue
            if path not in changes:
                changes[path] = {
                    "old": attributes["gwt.state.old"],
                    "new": attributes["gwt.state.new"],
                }
                order.append(path)
            else:
                changes[path]["new"] = attributes["gwt.state.new"]

    lines = [
        f"{path}: {_change_value_text(changes[path]['old'])} -> {_change_value_text(changes[path]['new'])}"
        for path in order
        if changes[path]["old"] != changes[path]["new"]
    ]
    if len(lines) > max_lines:
        return [*lines[:max_lines], f"... {len(lines) - max_lines} more"]
    return lines


def _is_output_path(path: str, roots: set[str]) -> bool:
    return any(path == root or path.startswith(f"{root}.") for root in roots)


def _change_value_text(value: object) -> str:
    if isinstance(value, str):
        if _looks_json(value):
            return value
        return json.dumps(value)
    return _display_value(value)


def _looks_json(value: str) -> bool:
    if not value or value[0] not in "[{":
        return False
    try:
        json.loads(value)
    except json.JSONDecodeError:
        return False
    return True


def _risk_threshold(condition: str | None) -> int | float | None:
    if not condition:
        return None
    match = re.search(r"\brisk_points\s*>=\s*(\d+(?:\.\d+)?)", condition)
    if not match:
        return None
    value = float(match.group(1))
    return int(value) if value.is_integer() else value


def _clean_condition(condition: object) -> str | None:
    if condition is None:
        return None
    return str(condition).removeprefix("DECIDE ").strip()


def _wrap_condition(condition: str) -> list[str]:
    parts = re.split(r"\s+or\s+", condition)
    if len(parts) == 1:
        return [condition]
    return [parts[0], *[f"or {part}" for part in parts[1:]]]


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _subject(json_state: JsonObject) -> str:
    vendor: JsonObject = _object_field(json_state, "vendor") or {}
    if vendor.get("vendor_name") is not None:
        return str(vendor["vendor_name"])
    for key in ("order", "release", "incident", "request"):
        value = json_state.get(key)
        if isinstance(value, dict):
            details = cast(JsonObject, value)
            for field in ("name", "order_id", "version", "id"):
                field_value = details.get(field)
                if field_value is not None:
                    return str(field_value)
    return "This request"


def human_outcome(status: str) -> str:
    if status == "needs_review":
        return "needs review"
    if status == "approved":
        return "was approved"
    if status == "rejected":
        return "was rejected"
    return f"returned {status}"


def _display_value(value: object) -> str:
    return json.dumps(_jsonable(value), separators=(",", ":"))


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in cast(list[object], value)]
    if isinstance(value, dict):
        return {
            str(key): _jsonable(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool | Decimal)


def _object_field(value: JsonObject, key: str) -> JsonObject | None:
    field = value.get(key)
    if isinstance(field, dict):
        return cast(JsonObject, field)
    return None


def _is_number(value: object) -> TypeGuard[int | float | Decimal]:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def _number_text(value: int | float | Decimal) -> str:
    return f"{value:g}"


def _int_value(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
