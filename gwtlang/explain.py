from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .runtime import ImportPolicy, Runtime, parse_program
from .tracing import GwtTraceRecorder


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
    state = result.state
    output_state = result.scenarios[0].returned_state or {}
    outcome = _primary_outcome(output_state, state)
    decision = outcome["value"] if outcome is not None else {}
    status = str(decision.get("status") or "completed")
    reason = str(decision.get("reason")) if decision.get("reason") is not None else None
    outcome_branch = _selected_decide_branch(recorder.spans)
    outcome_rule = _clean_condition(outcome_branch.get("condition")) if outcome_branch else None
    outcome_line = outcome_branch.get("line") if outcome_branch else None
    return ExplainResult(
        request=request,
        status=status,
        subject=_subject(json_state),
        reason=reason,
        input_lines=_summary_lines(json_state, max_lines=12),
        result_lines=_summary_lines(output_state, max_lines=10, priority_fields=("status", "reason")),
        bullets=_explanation_bullets(json_state, decision, outcome_rule),
        outcome_line=int(outcome_line) if outcome_line is not None else None,
        outcome_rule=outcome_rule,
        change_lines=_state_change_lines(recorder.spans, output_state, max_lines=10),
    )


def _selected_decide_branch(spans: list[Any]) -> dict[str, Any] | None:
    selected: dict[str, Any] | None = None
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


def _primary_outcome(output_state: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
    for root in (output_state, state):
        decision = root.get("decision") if isinstance(root.get("decision"), dict) else None
        if decision is not None and "status" in decision:
            return {"path": "decision", "value": decision}
        for path, value in root.items():
            if isinstance(value, dict) and "status" in value:
                return {"path": path, "value": value}
    return None


def _explanation_bullets(
    json_state: dict[str, Any],
    decision: dict[str, Any],
    outcome_rule: str | None,
) -> list[str]:
    vendor = json_state.get("vendor") if isinstance(json_state.get("vendor"), dict) else {}
    bullets: list[str] = []

    for requirement in decision.get("missing_requirements") or []:
        text = str(requirement)
        if text.endswith("_expired"):
            bullets.append(f"{text.removesuffix('_expired')} is expired")
        else:
            bullets.append(f"{text} is missing")

    reasons = set(str(reason) for reason in decision.get("reasons") or [])
    annual_spend = vendor.get("annual_spend")
    if "high_annual_spend" in reasons and annual_spend is not None:
        bullets.append(f"annual_spend is {annual_spend}, which adds inherent risk")
    if vendor.get("handles_customer_data") is True:
        bullets.append("the vendor handles customer data")
    if vendor.get("stores_payment_data") is True:
        bullets.append("the vendor stores payment data")
    high_signal_count = decision.get("high_signal_count")
    if isinstance(high_signal_count, int | float) and high_signal_count > 0:
        bullets.append(f"{high_signal_count:g} high-severity risk signal was present")

    risk_points = decision.get("risk_points")
    threshold = _risk_threshold(outcome_rule)
    if threshold is not None and isinstance(risk_points, int | float) and risk_points >= threshold:
        bullets.append(f"risk score {risk_points:g} crossed the review threshold {threshold:g}")

    return _unique(bullets)


def _summary_lines(
    value: Any,
    *,
    max_lines: int,
    priority_fields: tuple[str, ...] = (),
) -> list[str]:
    lines: list[str] = []

    def visit(path: str, item: Any) -> None:
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
    value: dict[str, Any],
    priority_fields: tuple[str, ...],
) -> list[tuple[str, Any]]:
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


def _summary_line_count(value: Any) -> int:
    if isinstance(value, dict):
        if not value:
            return 1
        return sum(_summary_line_count(item) for item in value.values())
    return 1


def _list_summary(items: list[Any]) -> str:
    if not items:
        return "[]"
    if len(items) <= 4 and all(_is_scalar(item) for item in items):
        return json.dumps([_jsonable(item) for item in items], separators=(",", ":"))
    return f"{len(items)} items"


def _state_change_lines(
    spans: list[Any],
    output_state: dict[str, Any],
    *,
    max_lines: int,
) -> list[str]:
    output_roots = set(output_state)
    if not output_roots:
        return []

    changes: dict[str, dict[str, Any]] = {}
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


def _change_value_text(value: Any) -> str:
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


def _clean_condition(condition: Any) -> str | None:
    if condition is None:
        return None
    return str(condition).removeprefix("DECIDE ").strip()


def _wrap_condition(condition: str) -> list[str]:
    parts = re.split(r"\s+or\s+", condition)
    if len(parts) == 1:
        return [condition]
    return [parts[0], *[f"or {part}" for part in parts[1:]]]


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _subject(json_state: dict[str, Any]) -> str:
    vendor = json_state.get("vendor") if isinstance(json_state.get("vendor"), dict) else {}
    if vendor.get("vendor_name") is not None:
        return str(vendor["vendor_name"])
    for key in ("order", "release", "incident", "request"):
        value = json_state.get(key)
        if isinstance(value, dict):
            for field in ("name", "order_id", "version", "id"):
                if value.get(field) is not None:
                    return str(value[field])
    return "This request"


def human_outcome(status: str) -> str:
    if status == "needs_review":
        return "needs review"
    if status == "approved":
        return "was approved"
    if status == "rejected":
        return "was rejected"
    return f"returned {status}"


def _display_value(value: Any) -> str:
    return json.dumps(_jsonable(value), separators=(",", ":"))


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool | Decimal)
