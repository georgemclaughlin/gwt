from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass, field
from decimal import Decimal
import re
from typing import Any, cast

from .errors import GwtError
from .expressions import Binary, Expr, ListLiteral, Literal, Name, Unary, parse_expression
from .runtime import (
    Action,
    ContractBinding,
    DecisionBlock,
    RecordValidation,
    RECORD_TYPES,
    FindBlock,
    ForBlock,
    IfBlock,
    Line,
    MatchBlock,
    NamedRequest,
    Program,
    RESERVED_BEHAVIOR_NAMES,
    RequestCall,
    Scenario,
    TableAssignment,
    VariantAssignment,
    VariantDefinition,
    _condition_to_expression,
    _is_local_name,
    _is_type_syntax,
    _is_builtin_statement,
    _literal_value_text,
    _literal_union_base_type,
    _literal_union_values,
    _list_item_type,
    _parse_exists_statement,
    _parse_find_statement,
    _parse_sum_projection,
    _resolve_type_alias,
    _action_mismatch_message,
    _signature_matches as _runtime_signature_matches,
    _signature_has_explicit_parameters,
    _signature_parameter_name,
    _signature_parameters as _runtime_signature_parameters,
    _signature_shape as _runtime_signature_shape,
    _split_required,
    _tokens,
    _unknown_request_message,
    _value_matches_literal,
    _variant_kind_type,
)
from .symbols import SourceRange
from .payloads import DiagnosticPayload

PLACEHOLDER_PATTERN = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*)>")
PATH_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


@dataclass(frozen=True)
class Diagnostic:
    filename: str | None
    line: int
    message: str
    code: str = "GWT000"
    severity: str = "error"
    column: int = 1
    length: int = 1
    category: str | None = None
    expected: str | None = None
    actual: str | None = None
    help: str | None = None

    def as_error_message(self, fallback_filename: str) -> str:
        filename = self.filename or fallback_filename
        return f"{filename}:{self.line}:{self.column}: {self.code} {self.message}"

    def as_payload(self, fallback_filename: str) -> DiagnosticPayload:
        source_range = SourceRange(self.filename, self.line, self.column, self.length).as_payload(fallback_filename)
        filename = self.filename or fallback_filename
        payload: DiagnosticPayload = {
            **source_range,
            "code": self.code,
            "severity": self.severity,
            "source": "gwt",
            "path": filename,
            "category": self.category or _diagnostic_category(self.code, self.message),
            "message": self.message,
        }
        if self.expected is not None:
            payload["expected"] = self.expected
        if self.actual is not None:
            payload["actual"] = self.actual
        if self.help is not None:
            payload["help"] = self.help
        return payload


def _diagnostic_category(code: str, message: str) -> str:
    if code == "GWT900":
        if message.startswith("USE ") or message.startswith("circular USE import"):
            return "import"
        return "parse"
    if code == "GWT901":
        return "format"
    if code == "GWT800":
        return "runtime"
    if code.startswith("GWT1"):
        return "lint"
    if code.startswith("GWT"):
        return "check"
    return "unknown"


@dataclass
class Scope:
    names: set[str]
    types: dict[str, str] = field(default_factory=lambda: {})

    def copy(self) -> Scope:
        return Scope(set(self.names), dict(self.types))


def check_program(program: Program, *, lint: bool = False) -> list[Diagnostic]:
    checker = Checker(program, lint=lint)
    return checker.check()


class Checker:
    def __init__(self, program: Program, *, lint: bool = False) -> None:
        self.program = program
        self.lint = lint
        self.diagnostics: list[Diagnostic] = []
        self.actions_by_name = self._index_actions(program.actions)

    def check(self) -> list[Diagnostic]:
        self._check_record_field_types()
        self._check_type_aliases()
        self._check_behavior_signatures()
        for action in self.program.actions:
            self._check_action(action)
        for request in self.program.requests.values():
            self._check_named_request(request)
        self._check_background()
        for scenario in self.program.scenarios:
            self._check_scenario(scenario)
        if self.lint:
            self._check_lints()
        return self.diagnostics

    def _check_record_field_types(self) -> None:
        for record in self.program.records.values():
            self._check_record_field_path_overlaps(record.name, record.fields, record.field_lines)
            for field, value_type in record.fields.items():
                if not self._is_known_type(value_type):
                    self._add_line(
                        record.field_lines[field],
                        f"unknown record field type: {value_type}",
                        "GWT014",
                    )
        for variant in self.program.variants.values():
            for case in variant.cases.values():
                for field, value_type in case.fields.items():
                    if not self._is_known_type(value_type):
                        self._add_line(
                            case.field_lines[field],
                            f"unknown record field type: {value_type}",
                            "GWT014",
                        )

    def _check_type_aliases(self) -> None:
        for alias in self.program.type_aliases.values():
            try:
                resolved_type = self._resolve_type(alias.name)
            except GwtError as exc:
                self._add(
                    alias.filename,
                    alias.line,
                    str(exc),
                    "GWT014",
                    alias.column,
                    alias.length,
                )
                continue
            if not self._is_known_resolved_type(resolved_type):
                self._add(
                    alias.filename,
                    alias.line,
                    f"unknown TYPE target: {alias.value_type}",
                    "GWT014",
                    alias.column,
                    alias.length,
                )

    def _check_lints(self) -> None:
        request_calls = self._scenario_request_calls()
        for request in self.program.requests.values():
            if request.name not in request_calls:
                self._add_line_warning(
                    request.line,
                    f"public REQUEST has no scenario evidence: {request.name}",
                    "GWT101",
                )
            if request.outputs and not request.thens:
                self._add_line_warning(
                    request.line,
                    f"REQUEST {request.name} declares OUTPUT but no request-level THEN invariant",
                    "GWT103",
                )
            for binding in [*request.inputs.values(), *request.outputs.values()]:
                if binding.value_type == "list":
                    self._add_line_warning(
                        binding.line,
                        f"{binding.kind.upper()} contract uses bare list; prefer list<Type>",
                        "GWT102",
                    )

        for record in self.program.records.values():
            for field, value_type in record.fields.items():
                if value_type == "list":
                    self._add_line_warning(
                        record.field_lines[field],
                        f"record field {record.name}.{field} uses bare list; prefer list<Type>",
                        "GWT102",
                    )
        for variant in self.program.variants.values():
            for case in variant.cases.values():
                for field, value_type in case.fields.items():
                    if value_type == "list":
                        self._add_line_warning(
                            case.field_lines[field],
                            f"one-of field {variant.name}.{case.name}.{field} uses bare list; prefer list<Type>",
                            "GWT102",
                        )
        for alias in self.program.type_aliases.values():
            if alias.value_type == "list":
                self._add(
                    alias.filename,
                    alias.line,
                    f"TYPE {alias.name} aliases bare list; prefer list<Type>",
                    "GWT102",
                    alias.column,
                    alias.length,
                    severity="warning",
                )

        for action in self.program.actions:
            for parameter in _signature_parameters(action.signature):
                if parameter not in action.contract.inputs:
                    self._add(
                        action.filename,
                        action.line,
                        f"behavior parameter <{parameter}> has no GIVEN contract",
                        "GWT104",
                        action.column,
                        action.length,
                        severity="warning",
                    )
            for name, value_type in action.contract.inputs.items():
                if value_type == "list":
                    line = action.contract.input_lines[name]
                    self._add_line_warning(
                        line,
                        f"behavior contract {name} uses bare list; prefer list<Type>",
                        "GWT102",
                    )

    def _scenario_request_calls(self) -> set[str]:
        calls: set[str] = set()
        for step in self.program.background.whens:
            if isinstance(step, RequestCall):
                calls.add(step.name)
        for scenario in self.program.scenarios:
            for step in scenario.whens:
                if isinstance(step, RequestCall):
                    calls.add(step.name)
        return calls

    def _check_record_field_path_overlaps(
        self,
        record_name: str,
        fields: dict[str, str],
        field_lines: dict[str, Line],
    ) -> None:
        ordered = list(fields)
        for index, field in enumerate(ordered):
            for previous in ordered[:index]:
                overlap = _contract_path_overlap(previous, field)
                if overlap is not None:
                    ancestor, descendant = overlap
                    self._add_line(
                        field_lines[field],
                        f"record {record_name} field path {descendant} overlaps {ancestor}; "
                        f"declare {ancestor} or {descendant}, not both",
                        "GWT014",
                    )
                    break

    def _check_named_request(self, request: NamedRequest) -> None:
        self._check_contract_path_overlaps("REQUEST", request.inputs)
        self._check_contract_path_overlaps("OUTPUT", request.outputs)
        for binding in [*request.inputs.values(), *request.outputs.values()]:
            if not self._is_known_type(binding.value_type):
                keyword = binding.kind.upper()
                self._add_line(
                    binding.line,
                    f"unknown {keyword} contract type: {binding.value_type}",
                    "GWT014",
                )

        for line in request.givens:
            if isinstance(line, TableAssignment):
                self._check_table_placeholders(line, set())
            elif isinstance(line, VariantAssignment):
                self._check_variant_placeholders(line, set())
            elif isinstance(line, Line):
                self._check_placeholders(line, set())
        for line in request.whens:
            self._check_placeholders(line, set())
        for line in request.thens:
            self._check_placeholders(line, set())

        for line in request.givens:
            self._check_given(line)
        scope = self._request_scope(request)
        for line in request.whens:
            self._check_command_or_action(line, scope, allow_let=False)
        for line in request.thens:
            self._check_condition_with_scope(line, scope)

    def _request_scope(self, request: NamedRequest) -> Scope:
        scope = Scope(set())
        for binding in [*request.inputs.values(), *request.outputs.values()]:
            self._add_typed_name(scope, binding.path, binding.value_type)
        return self._scope_from_givens(request.givens, scope)

    def _check_request_call(self, call: RequestCall, scope: Scope) -> None:
        request = self.program.requests.get(call.name)
        if request is None:
            self._add_line(
                call.line,
                _unknown_request_message(call.name, self.program.requests.keys()),
                "GWT001",
            )
            return
        for binding in request.inputs.values():
            actual_type = scope.types.get(binding.path)
            if actual_type is None:
                if self._check_request_input_descendants(call, scope, binding):
                    continue
                self._add_line(
                    call.line,
                    f"request input {binding.path} is missing; expected {binding.value_type}",
                    "GWT016",
                )
            elif not self._assignable(actual_type, binding.value_type):
                self._add_line(
                    call.line,
                    f"request input {binding.path} expected {binding.value_type}, got {actual_type}",
                    "GWT016",
                )

    def _check_request_input_descendants(self, call: RequestCall, scope: Scope, binding: ContractBinding) -> bool:
        if binding.value_type == "any" and _has_descendant_path(scope, binding.path):
            return True

        record = self.program.records.get(self._resolve_type_or_original(binding.value_type))
        if record is None:
            return False

        saw_descendant = False
        for field, expected_type in record.fields.items():
            field_path = f"{binding.path}.{field}"
            actual_type = scope.types.get(field_path)
            if actual_type is None:
                if saw_descendant:
                    self._add_line(
                        call.line,
                        f"request input {binding.path} expected {binding.value_type} but is missing {field_path}",
                        "GWT016",
                    )
                    return True
                return False
            saw_descendant = True
            if not self._assignable(actual_type, expected_type):
                self._add_line(
                    call.line,
                    f"request input {field_path} expected {expected_type}, got {actual_type}",
                    "GWT016",
                )
                return True
        return saw_descendant

    def _add_request_outputs_to_scope(self, scope: Scope, request_name: str) -> None:
        request = self.program.requests.get(request_name)
        if request is None:
            return
        for binding in request.outputs.values():
            self._add_typed_name(scope, binding.path, binding.value_type)

    def _check_contract_path_overlaps(self, keyword: str, bindings: dict[str, ContractBinding]) -> None:
        ordered = list(bindings.values())
        for index, binding in enumerate(ordered):
            for previous in ordered[:index]:
                overlap = _contract_path_overlap(previous.path, binding.path)
                if overlap is not None:
                    ancestor, descendant = overlap
                    self._add_line(
                        binding.line,
                        f"{keyword} contract path {descendant} overlaps {ancestor}; "
                        f"declare {ancestor} or {descendant}, not both",
                        "GWT014",
                    )
                    break

    def _check_behavior_signatures(self) -> None:
        seen: dict[tuple[str | None, tuple[str, ...]], Action] = {}
        for action in self.program.actions:
            if action.name in RESERVED_BEHAVIOR_NAMES:
                self._add(
                    action.filename,
                    action.line,
                    f"behavior name is reserved: {action.name}",
                    "GWT003",
                    action.column,
                    len(action.name),
                )

            parameters = _signature_parameters(action.signature)
            duplicate_parameter = _first_duplicate(parameters)
            if duplicate_parameter is not None:
                self._add(
                    action.filename,
                    action.line,
                    f"duplicate behavior parameter: {duplicate_parameter}",
                    "GWT004",
                    action.column,
                    action.length,
                )

            for parameter in parameters:
                if not _is_local_name(parameter):
                    self._add(
                        action.filename,
                        action.line,
                        f"behavior parameter must be a simple name: {parameter}",
                        "GWT005",
                        action.column,
                        action.length,
                    )

            if parameters and not _signature_has_explicit_parameters(action.signature):
                self._add(
                    action.filename,
                    action.line,
                    "implicit behavior parameters are deprecated; write parameters as <name>",
                    "GWT018",
                    action.column,
                    action.length,
                    severity="warning",
                )

            key = (action.filename, _signature_shape(action.signature))
            previous = seen.get(key)
            if previous is not None:
                self._add(
                    action.filename,
                    action.line,
                    f"duplicate behavior signature: {_format_signature_shape(key[1])} "
                    f"(previously line {previous.line})",
                    "GWT002",
                    action.column,
                    action.length,
                )
            else:
                seen[key] = action

    def _check_action(self, action: Action) -> None:
        self._check_action_contract(action)
        scope = Scope(set(_signature_parameters(action.signature)), {})
        for name, value_type in action.contract.inputs.items():
            self._add_typed_name(scope, name, value_type)
        self._check_body(action.body, scope, action.contract.return_type)
        if action.contract.return_type is not None and not _body_has_return(action.body):
            line = action.contract.return_line
            if line is not None:
                self._add_line(line, f"behavior declares {action.contract.return_type} but does not return a value", "GWT017")

    def _check_action_contract(self, action: Action) -> None:
        parameters = set(_signature_parameters(action.signature))
        for name, value_type in action.contract.inputs.items():
            line = action.contract.input_lines[name]
            if name not in parameters:
                self._add_line(line, f"contract refers to unknown behavior parameter: {name}", "GWT015")
            if not self._is_known_type(value_type):
                self._add_line(line, f"unknown contract type: {value_type}", "GWT014")

        if action.contract.return_type is not None and not self._is_known_type(action.contract.return_type):
            line = action.contract.return_line
            if line is not None:
                self._add_line(line, f"unknown return type: {action.contract.return_type}", "GWT014")

    def _check_background(self) -> None:
        background_lines = [
            *self.program.background.givens,
            *self.program.background.whens,
            *self.program.background.thens,
        ]
        for line in background_lines:
            if isinstance(line, TableAssignment):
                self._check_table_placeholders(line, set())
            elif isinstance(line, VariantAssignment):
                self._check_variant_placeholders(line, set())
            elif isinstance(line, RequestCall):
                self._check_placeholders(line.line, set())
            elif isinstance(line, Line):
                self._check_placeholders(line, set())

        for line in self.program.background.givens:
            self._check_given(line)
        background_scope = self._scope_from_givens(self.program.background.givens)
        for line in self.program.background.whens:
            if isinstance(line, RequestCall):
                self._check_request_call(line, background_scope)
                self._add_request_outputs_to_scope(background_scope, line.name)
            else:
                self._check_command_or_action(line, background_scope, allow_let=False)
        for line in self.program.background.thens:
            self._check_condition_with_scope(line, background_scope)

    def _check_scenario(self, scenario: Scenario) -> None:
        example_headers: set[str] = set(scenario.examples[0]) if scenario.examples else set()
        for line in scenario.givens:
            if isinstance(line, TableAssignment):
                self._check_table_placeholders(line, example_headers)
            elif isinstance(line, VariantAssignment):
                self._check_variant_placeholders(line, example_headers)
            elif isinstance(line, Line):
                self._check_placeholders(line, example_headers)
        for line in scenario.whens:
            if isinstance(line, RequestCall):
                self._check_placeholders(line.line, example_headers)
            else:
                self._check_placeholders(line, example_headers)
        for line in scenario.thens:
            self._check_placeholders(line, example_headers)

        for line in scenario.givens:
            self._check_given(line)
        scenario_scope = self._scope_from_givens([*self.program.background.givens, *scenario.givens])
        for line in scenario.whens:
            if isinstance(line, RequestCall):
                self._check_request_call(line, scenario_scope)
                self._add_request_outputs_to_scope(scenario_scope, line.name)
            else:
                self._check_command_or_action(line, scenario_scope, allow_let=False)
        for line in scenario.thens:
            self._check_condition_with_scope(line, scenario_scope)

    def _scope_from_givens(self, givens: list[Any], base: Scope | None = None) -> Scope:
        scope = base.copy() if base is not None else Scope(set())
        for given in givens:
            if isinstance(given, RecordValidation):
                self._add_typed_name(scope, given.path, given.record_name)
            elif isinstance(given, TableAssignment):
                scope.names.add(given.path)
                scope.types[given.path] = f"list<{given.item_type}>" if given.item_type is not None else "list"
            elif isinstance(given, VariantAssignment):
                scope.names.add(given.path)
                scope.types[given.path] = f"list<{given.variant_name}>"
            elif isinstance(given, Line) and " is " in given.text:
                path, expression = given.text.split(" is ", 1)
                path = path.strip()
                scope.names.add(path)
                try:
                    expression_type = parse_expression(expression.strip())
                except GwtError:
                    expression_type = None
                inferred_type = _infer_expression_type(expression_type, scope) if expression_type is not None else None
                if inferred_type is not None:
                    self._add_typed_name(scope, path, inferred_type)
        return scope

    def _add_typed_name(self, scope: Scope, name: str, value_type: str) -> None:
        scope.names.add(name)
        scope.types[name] = value_type
        resolved_type = self._resolve_type_or_original(value_type)
        record = self.program.records.get(resolved_type)
        if record is not None:
            for field_name, field_type in record.fields.items():
                scope.types[f"{name}.{field_name}"] = field_type
            return
        variant = self.program.variants.get(resolved_type)
        if variant is not None:
            scope.types[f"{name}.kind"] = _variant_kind_type(variant)

    def _check_body(self, body: list[Any], scope: Scope, expected_return: str | None = None) -> None:
        for statement in body:
            if isinstance(statement, IfBlock):
                self._check_condition(statement.condition)
                self._check_body(statement.then_body, scope.copy(), expected_return)
                self._check_body(statement.else_body, scope.copy(), expected_return)
            elif isinstance(statement, ForBlock):
                self._check_for(statement, scope, expected_return)
            elif isinstance(statement, FindBlock):
                self._check_find_block(statement, scope, expected_return)
            elif isinstance(statement, DecisionBlock):
                self._check_decision_block(statement, scope, expected_return)
            elif isinstance(statement, MatchBlock):
                self._check_match_block(statement, scope, expected_return)
            else:
                self._check_command_or_action(statement, scope, allow_let=True, expected_return=expected_return)

    def _check_for(self, statement: ForBlock, scope: Scope, expected_return: str | None = None) -> None:
        if statement.name in scope.names:
            self._add_line(statement.name_line or statement.iterable, f"FOR cannot overwrite: {statement.name}", "GWT008")

        expression = self._check_expression(statement.iterable.text, statement.iterable)
        iterable_type = _infer_expression_type(expression, scope) if expression is not None else None
        if isinstance(expression, Literal) and not isinstance(expression.value, list):
            self._add_line(statement.iterable, "FOR requires a list", "GWT013")
        elif iterable_type is not None and not self._is_collection_type(iterable_type):
            self._add_line(statement.iterable, "FOR requires a list", "GWT013")

        loop_scope = scope.copy()
        item_type = self._list_item_type(iterable_type) if iterable_type is not None else None
        if item_type is not None:
            self._add_typed_name(loop_scope, statement.name, item_type)
        else:
            loop_scope.names.add(statement.name)
            loop_scope.types[statement.name] = "any"
        if statement.where is not None:
            self._check_condition_with_scope(statement.where, loop_scope)
        self._check_body(statement.body, loop_scope, expected_return)

    def _check_find_block(self, statement: FindBlock, scope: Scope, expected_return: str | None = None) -> None:
        if statement.name in scope.names:
            self._add_line(statement.name_line or statement.iterable, f"FIND cannot overwrite: {statement.name}", "GWT008")

        expression = self._check_expression(statement.iterable.text, statement.iterable)
        iterable_type = _infer_expression_type(expression, scope) if expression is not None else None
        if isinstance(expression, Literal) and not isinstance(expression.value, list):
            self._add_line(statement.iterable, "FIND requires a list", "GWT013")
        elif iterable_type is not None and not self._is_collection_type(iterable_type):
            self._add_line(statement.iterable, "FIND requires a list", "GWT013")

        find_scope = scope.copy()
        item_type = self._list_item_type(iterable_type) if iterable_type is not None else None
        if item_type is not None:
            self._add_typed_name(find_scope, statement.name, item_type)
        else:
            find_scope.names.add(statement.name)
            find_scope.types[statement.name] = "any"
        self._check_condition_with_scope(statement.condition, find_scope)
        self._check_body(statement.body, find_scope, expected_return)
        self._check_body(statement.else_body, scope.copy(), expected_return)

    def _check_decision_block(
        self,
        statement: DecisionBlock,
        scope: Scope,
        expected_return: str | None = None,
    ) -> None:
        for branch in statement.branches:
            self._check_condition_with_scope(branch.condition, scope)
            self._check_body(branch.body, scope.copy(), expected_return)
        self._check_body(statement.else_body, scope.copy(), expected_return)

    def _check_match_block(self, statement: MatchBlock, scope: Scope, expected_return: str | None = None) -> None:
        expression = self._check_expression(statement.expression.text, statement.expression)
        expression_type = _infer_expression_type(expression, scope) if expression is not None else None
        selector = statement.cases[0].selector if statement.cases else "kind"
        if any(case.selector != selector for case in statement.cases):
            self._add_line(statement.expression, "DEPENDING ON cannot mix kind and value branches", "GWT014")
            selector = "kind"
        if selector == "value":
            self._check_scalar_match_block(statement, scope, expected_return, expression_type)
            return

        resolved_expression_type = (
            self._resolve_type_or_original(expression_type)
            if expression_type is not None
            else None
        )
        variant = self.program.variants.get(resolved_expression_type) if resolved_expression_type is not None else None
        if expression_type is not None and variant is None and expression_type != "any":
            self._add_line(statement.expression, f"DEPENDING ON expected one-of record, got {expression_type}", "GWT016")

        seen: set[str] = set()
        for case in statement.cases:
            if case.name in seen:
                self._add_line(case.line, f"duplicate kind branch: {case.name}", "GWT014")
            seen.add(case.name)
            if variant is not None and case.name not in variant.cases:
                self._add_line(case.line, f"unknown kind for {variant.name}: {case.name}", "GWT014")

            branch_scope = scope.copy()
            if variant is not None and case.name in variant.cases and isinstance(expression, Name):
                self._add_variant_case_fields(branch_scope, expression.value, variant, case.name)
            self._check_body(case.body, branch_scope, expected_return)

        if variant is not None:
            missing = sorted(set(variant.cases) - seen)
            if missing and not statement.else_body:
                self._add_line(
                    statement.expression,
                    f"DEPENDING ON requires ELSE unless all kinds are covered; missing {missing[0]}",
                    "GWT014",
                )
        elif not statement.else_body:
            self._add_line(statement.expression, "DEPENDING ON requires ELSE for unknown one-of records", "GWT014")

        self._check_body(statement.else_body, scope.copy(), expected_return)

    def _check_scalar_match_block(
        self,
        statement: MatchBlock,
        scope: Scope,
        expected_return: str | None = None,
        expression_type: str | None = None,
        ) -> None:
        if expression_type is not None and not self._is_scalar_match_type(expression_type):
            self._add_line(
                statement.expression,
                f"DEPENDING ON value expected scalar, got {expression_type}",
                "GWT016",
            )

        seen: set[tuple[type[object], Hashable]] = set()
        for case in statement.cases:
            literal: object = case.literal
            key = (type(literal), cast(Hashable, literal))
            if key in seen:
                self._add_line(case.line, f"duplicate value branch: {_literal_value_text(literal)}", "GWT014")
            seen.add(key)

            literal_type = _literal_type_name(literal)
            if (
                expression_type is not None
                and not self._case_literal_matches_expression_type(literal, literal_type, expression_type)
            ):
                self._add_line(
                    case.line,
                    f"branch value {_literal_value_text(literal)} cannot match {expression_type}",
                    "GWT016",
                )
            self._check_body(case.body, scope.copy(), expected_return)

        literal_values = self._literal_union_values(expression_type) if expression_type is not None else None
        if literal_values is not None:
            missing = [
                literal
                for literal in literal_values
                if not any(_value_matches_literal(case.literal, literal) for case in statement.cases)
            ]
            if missing and not statement.else_body:
                self._add_line(
                    statement.expression,
                    "DEPENDING ON value requires ELSE unless all values are covered; "
                    f"missing {_literal_value_text(missing[0])}",
                    "GWT014",
                )
        elif not statement.else_body:
            self._add_line(
                statement.expression,
                "DEPENDING ON value requires ELSE unless all values are covered",
                "GWT014",
            )

        self._check_body(statement.else_body, scope.copy(), expected_return)

    def _add_variant_case_fields(
        self, scope: Scope, name: str, variant: VariantDefinition, case_name: str
    ) -> None:
        case = variant.cases[case_name]
        scope.types[name] = variant.name
        scope.types[f"{name}.kind"] = f'"{case_name}"'
        for field, value_type in case.fields.items():
            scope.types[f"{name}.{field}"] = value_type

    def _check_given(self, statement: Any) -> None:
        if isinstance(statement, RecordValidation):
            record_name = self._resolve_type_or_original(statement.record_name)
            if record_name not in self.program.records and record_name not in self.program.variants:
                self._add_line(statement.line, f"unknown record: {statement.record_name}", "GWT014")
            return
        if isinstance(statement, TableAssignment):
            self._check_path(statement.path, statement.line)
            if statement.item_type is not None:
                self._check_table_type(statement)
            else:
                for row in statement.rows:
                    for value in row.values():
                        self._check_expression(value, statement.line)
            return
        if isinstance(statement, VariantAssignment):
            self._check_variant_assignment(statement)
            return
        if not isinstance(statement, Line):
            return

        try:
            path, expression = _split_required(statement.text, " is ", statement.number)
        except GwtError as exc:
            self._add_line(statement, str(exc), "GWT010")
            return

        self._check_path(path.strip(), statement)
        self._check_expression(expression.strip(), statement)

    def _check_table_type(self, statement: TableAssignment) -> None:
        if statement.item_type is None:
            return
        record = self.program.records.get(self._resolve_type_or_original(statement.item_type))
        if record is None:
            if statement.item_type in self.program.variants:
                self._add_line(
                    statement.line,
                    f"GIVEN table cannot construct one-of record: {statement.item_type}",
                    "GWT014",
                )
                return
            self._add_line(statement.line, f"unknown record: {statement.item_type}", "GWT014")
            return
        if not statement.rows:
            return

        actual_fields = set(statement.rows[0])
        expected_fields = set(record.fields)
        missing = sorted(expected_fields - actual_fields)
        if missing:
            self._add_line(statement.line, f"GIVEN table for {statement.item_type} missing field: {missing[0]}", "GWT014")
        extra = sorted(actual_fields - expected_fields)
        if extra:
            self._add_line(statement.line, f"GIVEN table for {statement.item_type} has unknown field: {extra[0]}", "GWT014")

        for row_index, row in enumerate(statement.rows, start=1):
            for field, value in row.items():
                expected_type = record.fields.get(field)
                if expected_type is None or _has_placeholder(value):
                    continue
                expression = self._check_expression(value, statement.line)
                actual_type = _infer_expression_type(expression, Scope(set())) if expression is not None else None
                literal_values = self._literal_union_values(expected_type)
                if literal_values is not None and isinstance(expression, Literal):
                    if not any(_value_matches_literal(expression.value, literal) for literal in literal_values):
                        self._add_line(
                            statement.line,
                            f"GIVEN table row {row_index} field '{field}' expected {expected_type}, got {actual_type}",
                            "GWT016",
                        )
                    continue
                if actual_type is not None and not self._assignable(actual_type, expected_type):
                    self._add_line(
                        statement.line,
                        f"GIVEN table row {row_index} field '{field}' expected {expected_type}, got {actual_type}",
                        "GWT016",
                    )

    def _check_variant_assignment(self, statement: VariantAssignment) -> None:
        self._check_path(statement.path, statement.line)
        variant = self.program.variants.get(self._resolve_type_or_original(statement.variant_name))
        if variant is None:
            self._add_line(statement.line, f"unknown one-of record: {statement.variant_name}", "GWT014")
            return
        case = variant.cases.get(statement.case_name)
        if case is None:
            self._add_line(statement.line, f"unknown kind for {variant.name}: {statement.case_name}", "GWT014")
            return

        actual_fields = set(statement.fields)
        expected_fields = set(case.fields)
        missing = sorted(expected_fields - actual_fields)
        if missing:
            self._add_line(statement.line, f"GIVEN {variant.name} kind {case.name} missing field: {missing[0]}", "GWT014")
        extra = sorted(actual_fields - expected_fields)
        if extra:
            self._add_line(statement.line, f"GIVEN {variant.name} kind {case.name} has unknown field: {extra[0]}", "GWT014")

        for field, value in statement.fields.items():
            expected_type = case.fields.get(field)
            if expected_type is None or _has_placeholder(value):
                continue
            expression = self._check_expression(value, statement.field_lines.get(field, statement.line))
            actual_type = _infer_expression_type(expression, Scope(set())) if expression is not None else None
            literal_values = self._literal_union_values(expected_type)
            if literal_values is not None and isinstance(expression, Literal):
                if not any(_value_matches_literal(expression.value, literal) for literal in literal_values):
                    self._add_line(
                        statement.field_lines.get(field, statement.line),
                        f"GIVEN {variant.name} field '{field}' expected {expected_type}, got {actual_type}",
                        "GWT016",
                    )
                continue
            if actual_type is not None and not self._assignable(actual_type, expected_type):
                self._add_line(
                    statement.field_lines.get(field, statement.line),
                    f"GIVEN {variant.name} field '{field}' expected {expected_type}, got {actual_type}",
                    "GWT016",
                )

    def _check_command_or_action(
        self,
        line: Line,
        scope: Scope,
        *,
        allow_let: bool,
        expected_return: str | None = None,
    ) -> None:
        try:
            tokens = _tokens(line.text, line.filename or "<source>", line.number)
        except GwtError as exc:
            self._add_line(line, _strip_location(str(exc)), "GWT010")
            return
        if not tokens:
            return

        command = tokens[0]
        if command == "RETURN":
            if not allow_let:
                self._add_line(line, "RETURN is only allowed inside behavior", "GWT007")
                return
            expression = line.text.removeprefix("RETURN").strip()
            if not expression:
                self._add_line(line, "RETURN requires a value", "GWT009")
                return
            actual_type = self._check_expression_or_action(expression, line, scope, require_return_value=True)
            if expected_return is not None and actual_type is not None and not self._assignable(actual_type, expected_return):
                self._add_line(line, f"RETURN expected {expected_return}, got {actual_type}", "GWT016")
            return

        if command == "PASS":
            if not allow_let:
                self._add_line(line, "PASS is only allowed inside behavior", "GWT007")
                return
            if len(tokens) != 1:
                self._add_line(line, "PASS does not take arguments", "GWT006")
            return

        if command == "LET":
            if not allow_let:
                self._add_line(line, "LET is only allowed inside behavior", "GWT007")
                return
            self._check_let(line, scope)
            return

        if command == "REQUIRE":
            condition = line.text.removeprefix("REQUIRE").strip()
            if not condition:
                self._add_line(line, "REQUIRE requires a condition", "GWT010")
                return
            self._check_condition_with_scope(
                Line(line.number, condition, line.filename, line.column + len("REQUIRE "), len(condition)),
                scope,
            )
            return

        if _is_builtin_statement(tokens, line.text):
            self._check_builtin(tokens, line, scope)
            return

        self._check_behavior_call(tokens, line, scope, require_return_value=False)

    def _check_let(self, line: Line, scope: Scope) -> None:
        binding = line.text.removeprefix("LET").strip()
        try:
            name, expression = _split_required(binding, " be ", line.number)
        except GwtError as exc:
            self._add_line(line, str(exc), "GWT010")
            return

        name = name.strip()
        if not _is_local_name(name):
            self._add_line(line, "LET requires a simple local name", "GWT005")
            return
        if name in scope.names:
            self._add_line(line, f"LET cannot overwrite an existing name: {name}", "GWT008")
            return

        value_type = self._check_expression_or_action(expression.strip(), line, scope, require_return_value=True)
        scope.names.add(name)
        if value_type is not None:
            scope.types[name] = value_type

    def _check_builtin(self, tokens: list[str], line: Line, scope: Scope) -> None:
        command = tokens[0]
        if command == "set":
            if len(tokens) < 4 or tokens[2] != "to":
                self._add_line(line, "expected 'set path to value'", "GWT006")
                return
            path = tokens[1]
            self._check_path(path, line)
            expression = line.text.split(" to ", 1)[1].strip() if " to " in line.text else ""
            parsed = self._check_expression(expression, line)
            actual_type = _infer_expression_type(parsed, scope) if parsed is not None else None
            self._check_assignment_type("set", path, actual_type, line, scope, parsed)
            return

        if command == "add":
            if len(tokens) < 4 or "to" not in tokens:
                self._add_line(line, "expected 'add value to path'", "GWT006")
                return
            try:
                value, path = _split_required(line.text.removeprefix("add").strip(), " to ", line.number)
            except GwtError as exc:
                self._add_line(line, str(exc), "GWT006")
                return
            path = path.strip()
            parsed = self._check_expression(value.strip(), line)
            actual_type = _infer_expression_type(parsed, scope) if parsed is not None else None
            self._check_path(path, line)
            self._check_add_type(path, actual_type, line, scope)
            return

        if command == "subtract":
            if len(tokens) < 4 or "from" not in tokens:
                self._add_line(line, "expected 'subtract value from path'", "GWT006")
                return
            try:
                value, path = _split_required(line.text.removeprefix("subtract").strip(), " from ", line.number)
            except GwtError as exc:
                self._add_line(line, str(exc), "GWT006")
                return
            path = path.strip()
            parsed = self._check_expression(value.strip(), line)
            actual_type = _infer_expression_type(parsed, scope) if parsed is not None else None
            self._check_path(path, line)
            self._check_subtract_type(path, actual_type, line, scope)
            return

        if command == "append":
            if len(tokens) < 4 or "to" not in tokens:
                self._add_line(line, "expected 'append value to path'", "GWT006")
                return
            try:
                value, path = _split_required(line.text.removeprefix("append").strip(), " to ", line.number)
            except GwtError as exc:
                self._add_line(line, str(exc), "GWT006")
                return
            path = path.strip()
            parsed = self._check_expression(value.strip(), line)
            actual_type = _infer_expression_type(parsed, scope) if parsed is not None else None
            self._check_path(path, line)
            self._check_append_type(path, actual_type, line, scope)
            return

        if command == "count":
            if len(tokens) < 4 or "into" not in tokens:
                self._add_line(line, "expected 'count list into path'", "GWT006")
                return
            try:
                value, path = _split_required(line.text.removeprefix("count").strip(), " into ", line.number)
            except GwtError as exc:
                self._add_line(line, str(exc), "GWT006")
                return
            path = path.strip()
            parsed = self._check_expression(value.strip(), line)
            value_type = _infer_expression_type(parsed, scope) if parsed is not None else None
            if value_type is not None and not self._is_collection_type(value_type):
                self._add_line(line, f"count requires a list, got {value_type}", "GWT016")
            self._check_path(path, line)
            self._check_assignment_type("count into", path, "integer", line, scope)
            return

        if command == "sum":
            if len(tokens) < 4 or "into" not in tokens:
                self._add_line(line, "expected 'sum list into path'", "GWT006")
                return
            projection = _parse_sum_projection(line.text)
            if projection is not None:
                self._check_sum_projection(projection, line, scope)
                return
            try:
                value, path = _split_required(line.text.removeprefix("sum").strip(), " into ", line.number)
            except GwtError as exc:
                self._add_line(line, str(exc), "GWT006")
                return
            path = path.strip()
            parsed = self._check_expression(value.strip(), line)
            value_type = _infer_expression_type(parsed, scope) if parsed is not None else None
            if value_type is not None and not self._is_collection_type(value_type):
                self._add_line(line, f"sum requires a list, got {value_type}", "GWT016")
            elif value_type is not None:
                self._check_sum_item_type(value_type, line)
            self._check_path(path, line)
            self._check_assignment_type("sum into", path, _sum_result_type(value_type), line, scope)
            return

        if command == "find":
            self._check_find(line, scope)
            return

        if command == "exists":
            self._check_exists(line, scope)
            return

        if command == "print":
            expression = line.text.removeprefix("print").strip()
            if not expression:
                self._add_line(line, "print requires a value", "GWT006")
                return
            self._check_expression(expression, line)

    def _check_assignment_type(
        self,
        command: str,
        path: str,
        actual_type: str | None,
        line: Line,
        scope: Scope,
        expression: Expr | None = None,
    ) -> None:
        expected_type = scope.types.get(path)
        if expected_type is None or actual_type is None:
            return
        literal_values = self._literal_union_values(expected_type)
        if literal_values is not None and isinstance(expression, Literal):
            if not any(_value_matches_literal(expression.value, literal) for literal in literal_values):
                self._add_line(line, f"{command} {path} expected {expected_type}, got {actual_type}", "GWT016")
            return
        if not self._assignable(actual_type, expected_type):
            self._add_line(line, f"{command} {path} expected {expected_type}, got {actual_type}", "GWT016")

    def _check_add_type(self, path: str, actual_type: str | None, line: Line, scope: Scope) -> None:
        expected_type = scope.types.get(path)
        if expected_type is None or actual_type is None:
            return
        if not self._assignable(actual_type, expected_type):
            self._add_line(line, f"add to {path} expected {expected_type}, got {actual_type}", "GWT016")

    def _check_append_type(self, path: str, actual_type: str | None, line: Line, scope: Scope) -> None:
        expected_type = scope.types.get(path)
        if expected_type is None:
            return
        item_type = self._list_item_type(expected_type)
        if expected_type != "list" and item_type is None:
            self._add_line(line, f"append to {path} expected list, got {expected_type}", "GWT016")
            return
        if item_type is not None and actual_type is not None and not self._assignable(actual_type, item_type):
            self._add_line(line, f"append to {path} expected {item_type}, got {actual_type}", "GWT016")

    def _check_subtract_type(self, path: str, actual_type: str | None, line: Line, scope: Scope) -> None:
        expected_type = scope.types.get(path)
        if expected_type is not None and not self._is_numeric_type(expected_type) and expected_type != "any":
            self._add_line(line, f"subtract from {path} expected numeric, got {expected_type}", "GWT016")
            return
        if actual_type is not None and not self._is_numeric_type(actual_type) and actual_type != "any":
            self._add_line(line, f"subtract value expected numeric, got {actual_type}", "GWT016")

    def _check_sum_item_type(self, value_type: str, line: Line) -> None:
        item_type = self._list_item_type(value_type)
        if item_type is None or item_type == "any" or self._is_numeric_type(item_type):
            return
        self._add_line(line, f"sum requires a list of numbers, got {value_type}", "GWT016")

    def _check_sum_projection(
        self,
        projection: tuple[str, str, str, str],
        line: Line,
        scope: Scope,
    ) -> None:
        projection_text, name, iterable_text, path = projection
        expression = self._check_expression(iterable_text.strip(), line)
        iterable_type = _infer_expression_type(expression, scope) if expression is not None else None
        if iterable_type is not None and not self._is_collection_type(iterable_type):
            self._add_line(line, f"sum requires a list, got {iterable_type}", "GWT016")

        projection_scope = scope.copy()
        item_type = self._list_item_type(iterable_type) if iterable_type is not None else None
        if item_type is not None:
            self._add_typed_name(projection_scope, name, item_type)
        else:
            projection_scope.names.add(name)
            projection_scope.types[name] = "any"

        projected = self._check_expression(projection_text, line)
        projected_type = _infer_expression_type(projected, projection_scope) if projected is not None else None
        if projected_type is not None and projected_type != "any" and not self._is_numeric_type(projected_type):
            self._add_line(line, f"sum projection expected number, got {projected_type}", "GWT016")
        self._check_path(path, line)
        result_type = _sum_result_type(f"list<{projected_type}>") if projected_type is not None else None
        self._check_assignment_type("sum into", path, result_type, line, scope)

    def _check_find(self, line: Line, scope: Scope) -> None:
        parsed = _parse_find_statement(line.text)
        if parsed is None:
            self._add_line(line, "expected 'find [optional] name in list where condition into path'", "GWT006")
            return
        _optional, name, iterable_text, condition, path = parsed
        expression = self._check_expression(iterable_text.strip(), line)
        iterable_type = _infer_expression_type(expression, scope) if expression is not None else None
        if iterable_type is not None and not self._is_collection_type(iterable_type):
            self._add_line(line, f"find requires a list, got {iterable_type}", "GWT016")

        find_scope = scope.copy()
        item_type = self._list_item_type(iterable_type) if iterable_type is not None else None
        if item_type is not None:
            self._add_typed_name(find_scope, name, item_type)
        else:
            find_scope.names.add(name)
            find_scope.types[name] = "any"
        self._check_condition_with_scope(Line(line.number, condition.strip(), line.filename, line.column, len(condition.strip())), find_scope)
        self._check_path(path, line)
        if item_type is not None:
            self._check_assignment_type("find into", path, item_type, line, scope)

    def _check_exists(self, line: Line, scope: Scope) -> None:
        parsed = _parse_exists_statement(line.text)
        if parsed is None:
            self._add_line(line, "expected 'exists name in list where condition into path'", "GWT006")
            return
        name, iterable_text, condition, path = parsed
        expression = self._check_expression(iterable_text.strip(), line)
        iterable_type = _infer_expression_type(expression, scope) if expression is not None else None
        if iterable_type is not None and not self._is_collection_type(iterable_type):
            self._add_line(line, f"exists requires a list, got {iterable_type}", "GWT016")

        exists_scope = scope.copy()
        item_type = self._list_item_type(iterable_type) if iterable_type is not None else None
        if item_type is not None:
            self._add_typed_name(exists_scope, name, item_type)
        else:
            exists_scope.names.add(name)
            exists_scope.types[name] = "any"
        self._check_condition_with_scope(Line(line.number, condition.strip(), line.filename, line.column, len(condition.strip())), exists_scope)
        self._check_path(path, line)
        self._check_assignment_type("exists into", path, "boolean", line, scope)

    def _check_condition(self, line: Line) -> None:
        self._check_condition_with_scope(line, Scope(set()))

    def _check_condition_with_scope(self, line: Line, scope: Scope) -> None:
        if _has_placeholder(line.text):
            return
        try:
            expression_text = _condition_to_expression(line.text)
        except GwtError as exc:
            self._add_line(line, str(exc), "GWT010")
            return
        expression = self._check_expression(expression_text, line)
        if isinstance(expression, Literal) and not isinstance(expression.value, bool):
            self._add_line(line, "condition must evaluate to a boolean", "GWT010")
        elif (
            expression_type := _infer_expression_type(expression, scope) if expression is not None else None
        ) is not None and expression_type != "boolean":
            self._add_line(line, "condition must evaluate to a boolean", "GWT010")

    def _check_expression_or_action(
        self,
        text: str,
        line: Line,
        scope: Scope,
        *,
        require_return_value: bool,
    ) -> str | None:
        if _has_placeholder(text):
            return None
        try:
            expression = parse_expression(text)
            if isinstance(expression, Name):
                matches = self._matching_actions([expression.value])
                if matches and require_return_value and not any(_body_has_return(action.body) for action in matches):
                    self._add_line(line, f"behavior does not return a value: {expression.value}", "GWT009")
                if matches:
                    return _common_return_type(matches)
            return _infer_expression_type(expression, scope)
        except GwtError:
            pass

        try:
            tokens = _tokens(text, line.filename or "<source>", line.number)
        except GwtError as exc:
            self._add_line(line, _strip_location(str(exc)), "GWT010")
            return None
        return self._check_behavior_call(tokens, line, scope, require_return_value=require_return_value)

    def _check_behavior_call(
        self,
        tokens: list[str],
        line: Line,
        scope: Scope,
        *,
        require_return_value: bool,
    ) -> str | None:
        if not tokens:
            self._add_line(line, "expected behavior call", "GWT001")
            return None
        matches = self._matching_actions(tokens)
        if not matches:
            self._add_line(
                line,
                _action_mismatch_message("no behavior matches", tokens, self.actions_by_name),
                "GWT001",
            )
            return None
        type_errors = [self._behavior_call_type_errors(action, tokens, line, scope) for action in matches]
        if type_errors and all(errors for errors in type_errors):
            self._add_line(line, type_errors[0][0], "GWT016")
        if require_return_value and not any(_body_has_return(action.body) for action in matches):
            self._add_line(line, f"behavior does not return a value: {' '.join(tokens)}", "GWT009")
            return None
        return _common_return_type(matches)

    def _matching_actions(self, call: list[str]) -> list[Action]:
        matches: list[Action] = []
        for action in self.actions_by_name.get(call[0], []):
            if _signature_matches(action.signature, call):
                matches.append(action)
        return matches

    def _behavior_call_type_errors(self, action: Action, call: list[str], line: Line, scope: Scope) -> list[str]:
        errors: list[str] = []
        for index, (pattern, actual) in enumerate(zip(action.signature, call)):
            parameter_name = _signature_parameter_name(action.signature, index, pattern)
            if parameter_name is None:
                continue
            expected_type = action.contract.inputs.get(parameter_name)
            if expected_type is None:
                continue
            actual_type = self._argument_type(actual, line, scope)
            if actual_type is not None and not self._assignable(actual_type, expected_type):
                errors.append(f"behavior argument '{parameter_name}' expected {expected_type}, got {actual_type}")
        return errors

    def _argument_type(self, token: str, line: Line, scope: Scope) -> str | None:
        if token in scope.types:
            return scope.types[token]
        if _has_placeholder(token):
            return None
        try:
            return _infer_expression_type(parse_expression(token), scope)
        except GwtError:
            return None

    def _is_known_type(self, value_type: str) -> bool:
        if not _is_type_syntax(value_type):
            return False
        try:
            resolved_type = self._resolve_type(value_type)
        except GwtError:
            return False
        return self._is_known_resolved_type(resolved_type)

    def _is_known_resolved_type(self, value_type: str) -> bool:
        if (
            value_type in RECORD_TYPES
            or value_type in self.program.records
            or value_type in self.program.variants
            or _literal_union_values(value_type) is not None
        ):
            return True
        item_type = _list_item_type(value_type)
        if item_type is None:
            return False
        return self._is_known_resolved_type(item_type)

    def _resolve_type(self, value_type: str) -> str:
        return _resolve_type_alias(value_type, self.program.type_aliases)

    def _resolve_type_or_original(self, value_type: str) -> str:
        try:
            return self._resolve_type(value_type)
        except GwtError:
            return value_type

    def _literal_union_values(self, value_type: str) -> tuple[Any, ...] | None:
        return _literal_union_values(self._resolve_type_or_original(value_type))

    def _list_item_type(self, value_type: str | None) -> str | None:
        if value_type is None:
            return None
        return _list_item_type(self._resolve_type_or_original(value_type))

    def _is_collection_type(self, value_type: str) -> bool:
        resolved_type = self._resolve_type_or_original(value_type)
        return _is_collection_type(resolved_type)

    def _is_numeric_type(self, value_type: str | None) -> bool:
        if value_type is None:
            return False
        return _is_numeric_type(self._resolve_type_or_original(value_type))

    def _assignable(self, actual_type: str, expected_type: str) -> bool:
        return _assignable(
            self._resolve_type_or_original(actual_type),
            self._resolve_type_or_original(expected_type),
        )

    def _is_scalar_match_type(self, value_type: str) -> bool:
        return _is_scalar_match_type(self._resolve_type_or_original(value_type))

    def _case_literal_matches_expression_type(
        self,
        literal: Any,
        literal_type: str | None,
        expression_type: str,
    ) -> bool:
        return _case_literal_matches_expression_type(
            literal,
            literal_type,
            self._resolve_type_or_original(expression_type),
        )

    def _check_expression(self, text: str, line: Line) -> Expr | None:
        if _has_placeholder(text):
            return None
        try:
            return parse_expression(text)
        except GwtError as exc:
            self._add_line(line, f"invalid expression: {exc}", "GWT010")
            return None

    def _check_path(self, path: str, line: Line) -> None:
        if not PATH_PATTERN.match(path):
            self._add_line(line, f"invalid path: {path}", "GWT011")

    def _check_placeholders(self, line: Line, example_headers: set[str]) -> None:
        for placeholder in PLACEHOLDER_PATTERN.findall(line.text):
            if placeholder not in example_headers:
                self._add_line(line, f"EXAMPLES has no value for <{placeholder}>", "GWT012")

    def _check_table_placeholders(self, table: TableAssignment, example_headers: set[str]) -> None:
        for row in table.rows:
            for value in row.values():
                for placeholder in PLACEHOLDER_PATTERN.findall(value):
                    if placeholder not in example_headers:
                        self._add_line(table.line, f"EXAMPLES has no value for <{placeholder}>", "GWT012")

    def _check_variant_placeholders(self, assignment: VariantAssignment, example_headers: set[str]) -> None:
        for value in assignment.fields.values():
            for placeholder in PLACEHOLDER_PATTERN.findall(value):
                if placeholder not in example_headers:
                    self._add_line(assignment.line, f"EXAMPLES has no value for <{placeholder}>", "GWT012")

    def _index_actions(self, actions: list[Action]) -> dict[str, list[Action]]:
        indexed: dict[str, list[Action]] = {}
        for action in actions:
            indexed.setdefault(action.name, []).append(action)
        return indexed

    def _add(
        self,
        filename: str | None,
        line: int,
        message: str,
        code: str = "GWT000",
        column: int = 1,
        length: int = 1,
        severity: str = "error",
    ) -> None:
        self.diagnostics.append(Diagnostic(filename, line, message, code, severity, column, max(1, length)))

    def _add_line(self, line: Line, message: str, code: str = "GWT000") -> None:
        self._add(line.filename, line.number, message, code, line.column, line.length)

    def _add_line_warning(self, line: Line, message: str, code: str) -> None:
        self._add(line.filename, line.number, message, code, line.column, line.length, severity="warning")


def _signature_parameters(signature: list[str]) -> list[str]:
    return _runtime_signature_parameters(signature)


def _signature_shape(signature: list[str]) -> tuple[str, ...]:
    return _runtime_signature_shape(signature)


def _signature_matches(signature: list[str], call: list[str]) -> bool:
    return _runtime_signature_matches(signature, call)


def _format_signature_shape(shape: tuple[str, ...]) -> str:
    return " ".join(shape)


def _first_duplicate(values: list[str]) -> str | None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None


def _is_ancestor_path(ancestor: str, descendant: str) -> bool:
    return descendant.startswith(f"{ancestor}.")


def _contract_path_overlap(left: str, right: str) -> tuple[str, str] | None:
    if _is_ancestor_path(left, right):
        return left, right
    if _is_ancestor_path(right, left):
        return right, left
    return None


def _body_has_return(body: list[Any]) -> bool:
    for statement in body:
        if isinstance(statement, Line):
            try:
                tokens = _tokens(statement.text, statement.filename or "<source>", statement.number)
            except GwtError:
                continue
            if tokens and tokens[0] == "RETURN":
                return True
        elif isinstance(statement, IfBlock):
            if _body_has_return(statement.then_body) or _body_has_return(statement.else_body):
                return True
        elif isinstance(statement, ForBlock) and _body_has_return(statement.body):
            return True
        elif isinstance(statement, FindBlock):
            if _body_has_return(statement.body) or _body_has_return(statement.else_body):
                return True
        elif isinstance(statement, DecisionBlock):
            if any(_body_has_return(branch.body) for branch in statement.branches) or _body_has_return(
                statement.else_body
            ):
                return True
        elif isinstance(statement, MatchBlock):
            if any(_body_has_return(case.body) for case in statement.cases) or _body_has_return(statement.else_body):
                return True
    return False


def _common_return_type(actions: list[Action]) -> str | None:
    return_types = {action.contract.return_type for action in actions if action.contract.return_type is not None}
    if len(return_types) == 1:
        return next(iter(return_types))
    return None


def _infer_expression_type(expression: Expr, scope: Scope) -> str | None:
    if isinstance(expression, Literal):
        value = expression.value
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, Decimal):
            return "decimal"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "text"
        if isinstance(value, list):
            return "list"
        return None
    if isinstance(expression, ListLiteral):
        return "list"
    if isinstance(expression, Name):
        return scope.types.get(expression.value)
    if isinstance(expression, Unary):
        if expression.operator == "not":
            return "boolean"
        if expression.operator == "-":
            return _infer_expression_type(expression.right, scope)
    if isinstance(expression, Binary):
        if expression.operator in {"==", "!=", ">", "<", ">=", "<=", "contains", "and", "or"}:
            return "boolean"
        if expression.operator in {"+", "-", "*", "/"}:
            left_type = _infer_expression_type(expression.left, scope)
            right_type = _infer_expression_type(expression.right, scope)
            if (
                left_type is not None
                and right_type is not None
                and _is_numeric_type(left_type)
                and _is_numeric_type(right_type)
            ):
                return _numeric_result_type(left_type, right_type, expression.operator)
            if expression.operator == "+" and left_type == right_type == "text":
                return "text"
    return None


def _assignable(actual_type: str, expected_type: str) -> bool:
    if expected_type == "any" or actual_type == "any" or actual_type == expected_type:
        return True
    expected_literal_base = _literal_union_base_type(expected_type)
    if expected_literal_base is not None:
        return actual_type == expected_literal_base
    actual_literal_base = _literal_union_base_type(actual_type)
    if actual_literal_base is not None:
        return _assignable(actual_literal_base, expected_type)
    if actual_type == "integer" and expected_type in {"decimal", "number"}:
        return True
    if actual_type == "decimal" and expected_type == "number":
        return True
    actual_item = _list_item_type(actual_type)
    expected_item = _list_item_type(expected_type)
    if expected_type == "list" and actual_item is not None:
        return True
    if actual_type == "list" and expected_item is not None:
        return True
    if actual_item is not None and expected_item is not None:
        return _assignable(actual_item, expected_item)
    return False


def _has_descendant_path(scope: Scope, path: str) -> bool:
    prefix = f"{path}."
    return any(name.startswith(prefix) for name in scope.names) or any(
        typed_path.startswith(prefix) for typed_path in scope.types
    )


def _is_numeric_type(value_type: str | None) -> bool:
    return value_type in {"number", "integer", "decimal"}


def _numeric_result_type(left_type: str, right_type: str, operator: str) -> str:
    if "number" in {left_type, right_type}:
        return "number"
    if "decimal" in {left_type, right_type}:
        return "decimal"
    if operator == "/":
        return "number"
    return "integer"


def _sum_result_type(value_type: str | None) -> str | None:
    if value_type is None:
        return None
    item_type = _list_item_type(value_type)
    if item_type is None:
        return None
    if item_type == "any":
        return "number"
    return item_type if _is_numeric_type(item_type) else "number"


def _literal_type_name(value: Any) -> str | None:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, Decimal):
        return "decimal"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "list"
    return None


def _is_scalar_match_type(value_type: str) -> bool:
    if value_type == "any":
        return True
    if value_type in {"text", "boolean", "number", "integer", "decimal"}:
        return True
    return _literal_union_values(value_type) is not None


def _case_literal_matches_expression_type(literal: Any, literal_type: str | None, expression_type: str) -> bool:
    if expression_type == "any":
        return True
    literal_values = _literal_union_values(expression_type)
    if literal_values is not None:
        return any(_value_matches_literal(literal, value) for value in literal_values)
    if expression_type == "number":
        return _is_numeric_type(literal_type)
    return literal_type == expression_type


def _is_collection_type(value_type: str) -> bool:
    return value_type == "list" or _list_item_type(value_type) is not None


def _has_placeholder(text: str) -> bool:
    return PLACEHOLDER_PATTERN.search(text) is not None


def _strip_location(message: str) -> str:
    match = re.match(r"^.+:\d+:\s*(.+)$", message)
    if match:
        return match.group(1)
    return message
