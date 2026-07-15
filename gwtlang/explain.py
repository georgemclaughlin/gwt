from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import cast

from .execution_case import (
    ExecutionCase,
    ExecutionCaseCapturePolicy,
    FactProvenanceInput,
    capture_execution_case,
)
from .payloads import ExecutionCasePayload, JsonObject, JsonValue
from .runtime import (
    DEFAULT_EXECUTION_BUDGET,
    DEFAULT_MAX_CALL_DEPTH,
    ImportPolicy,
)


@dataclass(frozen=True)
class ExplainResult:
    """Human and machine-readable views of one execution case."""

    case: ExecutionCase

    @property
    def request(self) -> str:
        return self.case.request_name

    @property
    def status(self) -> str:
        status = self.case.as_payload()["execution"]["status"]
        if status is None:
            return self.case.outcome
        if "value" in status:
            return str(status["value"])
        return str(status["availability"])

    @property
    def reason(self) -> str | None:
        reason = self.case.as_payload()["execution"]["reason"]
        if reason is None:
            return None
        if "value" in reason:
            return str(reason["value"])
        return str(reason["availability"])

    def as_payload(self) -> ExecutionCasePayload:
        return self.case.as_payload()

    def as_text(self) -> str:
        payload = self.case.as_payload()
        execution = payload["execution"]
        if execution["outcome"] == "failed":
            lines = [f"{self.request} failed", ""]
        else:
            lines = [f"{self.request} completed", ""]

        if payload["redaction"]["mode"] == "omit-values":
            lines.extend(("Captured values: omitted by capture policy", ""))
        else:
            input_lines = _summary_lines(payload["request"]["input"], max_lines=12)
            if input_lines:
                lines.append("Input:")
                lines.extend(input_lines)
                lines.append("")

            if execution["outcome"] == "completed":
                result_lines = _summary_lines(
                    payload["result"],
                    max_lines=10,
                )
                if result_lines:
                    lines.append("Result:")
                    lines.extend(result_lines)
                    lines.append("")

        error = execution.get("error")
        if error is not None:
            lines.append("Failure:")
            lines.append(error["message"])
            source = error["source"]
            if source is not None:
                lines.append(
                    f"source: {source['file']}:{source['line']}:{source['column']}"
                )
            lines.append("")

        selected_branches = [
            item
            for item in payload["evidence"]
            if item["kind"] == "branch" and item.get("selected") is True
        ]
        if selected_branches:
            lines.append("Selected branches:")
            for branch in selected_branches:
                branch_kind = branch.get("branchKind", "branch")
                branch_label = branch.get("branchLabel", "")
                expression = branch.get("expression", "") or "ELSE"
                source = branch["source"]
                location = (
                    f" at {source['file']}:{source['line']}:{source['column']}"
                    if source is not None
                    else ""
                )
                lines.append(
                    f"- {branch_kind} {branch_label}: {expression}{location}"
                )
                operand_lines = _selected_operand_lines(payload, expression)
                lines.extend(f"  observed: {line}" for line in operand_lines)
            lines.append("")

        behavior_lines = _behavior_call_lines(payload, max_lines=10)
        if behavior_lines:
            lines.append("Behavior calls:")
            lines.extend(f"- {line}" for line in behavior_lines)
            lines.append("")

        change_lines = _state_change_lines(payload, max_lines=10)
        if change_lines:
            lines.append("Changed values:")
            lines.extend(f"- {line}" for line in change_lines)
        return "\n".join(lines).rstrip() + "\n"


def explain_json_file(
    path: str | Path,
    json_state: JsonObject,
    *,
    request: str,
    fact_provenance: FactProvenanceInput | None = None,
    json_file: str | Path | None = None,
    import_policy: ImportPolicy | None = None,
    policy: ExecutionCaseCapturePolicy | None = None,
    execution_budget: int | None = DEFAULT_EXECUTION_BUDGET,
    max_call_depth: int | None = DEFAULT_MAX_CALL_DEPTH,
) -> ExplainResult:
    return ExplainResult(
        capture_execution_case(
            path,
            json_state,
            request=request,
            fact_provenance=fact_provenance,
            json_file=json_file,
            import_policy=import_policy,
            policy=policy,
            execution_budget=execution_budget,
            max_call_depth=max_call_depth,
        )
    )


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
            for key, nested in _ordered_items(cast(JsonObject, item), priority_fields):
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
    priority = [item for item in value.items() if item[0] in priority_fields]
    rest = [item for item in value.items() if item[0] not in priority_fields]
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
        return json.dumps(items, separators=(",", ":"))
    return f"{len(items)} items"


def _state_change_lines(payload: ExecutionCasePayload, *, max_lines: int) -> list[str]:
    if payload["redaction"]["mode"] == "omit-values":
        paths = [change["path"] for change in payload["stateChanges"]]
        lines = [f"{path}: values redacted" for path in paths[:max_lines]]
        if len(paths) > max_lines:
            lines.append(f"... {len(paths) - max_lines} more")
        return lines
    output_roots = set(payload["result"].keys())
    changes: dict[str, tuple[JsonValue, JsonValue]] = {}
    order: list[str] = []
    for change in payload["stateChanges"]:
        path = change["path"]
        if not _is_output_path(path, output_roots):
            continue
        before = change["before"]
        after = change["after"]
        if "present" not in before or "present" not in after:
            continue
        if not before["present"] or not after["present"]:
            continue
        old_value = before.get("value")
        new_value = after.get("value")
        if path not in changes:
            changes[path] = (old_value, new_value)
            order.append(path)
        else:
            changes[path] = (changes[path][0], new_value)

    lines = [
        f"{path}: {_display_value(changes[path][0])} -> {_display_value(changes[path][1])}"
        for path in order
        if changes[path][0] != changes[path][1]
    ]
    if len(lines) > max_lines:
        return [*lines[:max_lines], f"... {len(lines) - max_lines} more"]
    return lines


def _is_output_path(path: str, roots: set[str]) -> bool:
    return any(path == root or path.startswith(f"{root}.") for root in roots)


def _selected_operand_lines(
    payload: ExecutionCasePayload,
    condition: str,
) -> list[str]:
    matching = [
        item
        for item in payload["evidence"]
        if item["kind"] == "condition"
        and item.get("expression") == condition
        and item.get("result") is True
    ]
    if not matching:
        return []
    operands = matching[-1].get("operands")
    if operands is None:
        return []
    if operands["availability"] == "redacted":
        return ["redacted by capture policy"]
    if operands["availability"] == "unavailable":
        return [f"unavailable: {operands.get('reason', 'not recorded')}"]
    return [
        f"{operand['name']} = {_display_value(operand['value'])} "
        f"({operand['valueType']})"
        for operand in operands.get("values", [])
    ]


def _behavior_call_lines(
    payload: ExecutionCasePayload,
    *,
    max_lines: int,
) -> list[str]:
    entered = [
        item
        for item in payload["evidence"]
        if item["kind"] == "behavior" and item.get("phase") == "enter"
    ]
    exits = {
        str(item.get("callId")): item.get("behaviorOutcome")
        for item in payload["evidence"]
        if item["kind"] == "behavior" and item.get("phase") == "exit"
    }
    lines: list[str] = []
    for item in entered[:max_lines]:
        indent = "  " * int(item.get("depth", 0))
        source = item["source"]
        location = (
            f" at {source['file']}:{source['line']}:{source['column']}"
            if source is not None
            else ""
        )
        outcome = exits.get(str(item.get("callId")))
        suffix = " [failed]" if outcome == "failed" else ""
        lines.append(
            f"{indent}{item.get('signature', 'unknown')}{location}{suffix}"
        )
    if len(entered) > max_lines:
        lines.append(f"... {len(entered) - max_lines} more")
    return lines


def _display_value(value: JsonValue) -> str:
    return json.dumps(value, separators=(",", ":"))


def _is_scalar(value: JsonValue) -> bool:
    return value is None or isinstance(value, str | int | float | bool)
