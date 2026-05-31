from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from .errors import GwtError
from .expressions import Binary, Expr, ListLiteral, Literal, Name, Unary, parse_expression
from .runtime import (
    Action,
    DtoValidation,
    DTO_TYPES,
    ForBlock,
    IfBlock,
    Line,
    Program,
    Scenario,
    TableAssignment,
    _condition_to_expression,
    _is_local_name,
    _is_type_syntax,
    _is_builtin_statement,
    _list_item_type,
    _signature_matches as _runtime_signature_matches,
    _signature_parameter_name,
    _signature_parameters as _runtime_signature_parameters,
    _signature_shape as _runtime_signature_shape,
    _split_required,
    _tokens,
)
from .symbols import SourceRange


RESERVED_BEHAVIOR_NAMES = {"set", "add", "subtract", "print", "LET", "REQUIRE", "RETURN"}
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

    def as_error_message(self, fallback_filename: str) -> str:
        filename = self.filename or fallback_filename
        return f"{filename}:{self.line}:{self.column}: {self.code} {self.message}"

    def as_payload(self, fallback_filename: str) -> dict[str, object]:
        source_range = SourceRange(self.filename, self.line, self.column, self.length).as_payload(fallback_filename)
        return {
            **source_range,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class Scope:
    names: set[str]
    types: dict[str, str] = field(default_factory=dict)

    def copy(self) -> Scope:
        return Scope(set(self.names), dict(self.types))


def check_program(program: Program) -> list[Diagnostic]:
    checker = Checker(program)
    return checker.check()


class Checker:
    def __init__(self, program: Program) -> None:
        self.program = program
        self.diagnostics: list[Diagnostic] = []
        self.actions_by_name = self._index_actions(program.actions)

    def check(self) -> list[Diagnostic]:
        self._check_dto_field_types()
        self._check_program_contracts()
        self._check_behavior_signatures()
        for action in self.program.actions:
            self._check_action(action)
        self._check_background()
        for scenario in self.program.scenarios:
            self._check_scenario(scenario)
        return self.diagnostics

    def _check_dto_field_types(self) -> None:
        for dto in self.program.dtos.values():
            for field, value_type in dto.fields.items():
                if not self._is_known_type(value_type):
                    self._add_line(
                        dto.field_lines[field],
                        f"unknown DTO field type: {value_type}",
                        "GWT014",
                    )

    def _check_program_contracts(self) -> None:
        for binding in [*self.program.inputs.values(), *self.program.outputs.values()]:
            if not self._is_known_type(binding.value_type):
                keyword = binding.kind.upper()
                self._add_line(
                    binding.line,
                    f"unknown {keyword} contract type: {binding.value_type}",
                    "GWT014",
                )

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
            elif isinstance(line, Line):
                self._check_placeholders(line, set())

        for line in self.program.background.givens:
            self._check_given(line)
        background_scope = self._scope_from_givens(self.program.background.givens)
        for line in self.program.background.whens:
            self._check_command_or_action(line, background_scope, allow_let=False)
        for line in self.program.background.thens:
            self._check_condition(line)

    def _check_scenario(self, scenario: Scenario) -> None:
        example_headers = set(scenario.examples[0]) if scenario.examples else set()
        for line in scenario.givens:
            if isinstance(line, TableAssignment):
                self._check_table_placeholders(line, example_headers)
            elif isinstance(line, Line):
                self._check_placeholders(line, example_headers)
        for line in scenario.whens:
            self._check_placeholders(line, example_headers)
        for line in scenario.thens:
            self._check_placeholders(line, example_headers)

        for line in scenario.givens:
            self._check_given(line)
        scenario_scope = self._scope_from_givens([*self.program.background.givens, *scenario.givens])
        for line in scenario.whens:
            self._check_command_or_action(line, scenario_scope, allow_let=False)
        for line in scenario.thens:
            self._check_condition(line)

    def _scope_from_givens(self, givens: list[Any]) -> Scope:
        scope = self._scope_from_inputs()
        for given in givens:
            if isinstance(given, DtoValidation):
                self._add_typed_name(scope, given.path, given.dto_name)
            elif isinstance(given, TableAssignment):
                scope.names.add(given.path)
                scope.types[given.path] = f"list<{given.item_type}>" if given.item_type is not None else "list"
            elif isinstance(given, Line) and " is " in given.text:
                path, expression = given.text.split(" is ", 1)
                path = path.strip()
                if "." not in path:
                    scope.names.add(path)
                    try:
                        expression_type = parse_expression(expression.strip())
                    except GwtError:
                        expression_type = None
                    inferred_type = _infer_expression_type(expression_type, scope) if expression_type is not None else None
                    if inferred_type is not None:
                        self._add_typed_name(scope, path, inferred_type)
        return scope

    def _scope_from_inputs(self) -> Scope:
        scope = Scope(set())
        for binding in self.program.inputs.values():
            self._add_typed_name(scope, binding.path, binding.value_type)
        return scope

    def _add_typed_name(self, scope: Scope, name: str, value_type: str) -> None:
        scope.names.add(name)
        scope.types[name] = value_type
        dto = self.program.dtos.get(value_type)
        if dto is not None:
            for field_name, field_type in dto.fields.items():
                scope.types[f"{name}.{field_name}"] = field_type

    def _check_body(self, body: list[Any], scope: Scope, expected_return: str | None = None) -> None:
        for statement in body:
            if isinstance(statement, IfBlock):
                self._check_condition(statement.condition)
                self._check_body(statement.then_body, scope.copy(), expected_return)
                self._check_body(statement.else_body, scope.copy(), expected_return)
            elif isinstance(statement, ForBlock):
                self._check_for(statement, scope, expected_return)
            else:
                self._check_command_or_action(statement, scope, allow_let=True, expected_return=expected_return)

    def _check_for(self, statement: ForBlock, scope: Scope, expected_return: str | None = None) -> None:
        if statement.name in scope.names:
            self._add_line(statement.name_line or statement.iterable, f"FOR cannot overwrite: {statement.name}", "GWT008")

        expression = self._check_expression(statement.iterable.text, statement.iterable)
        iterable_type = _infer_expression_type(expression, scope) if expression is not None else None
        if isinstance(expression, Literal) and not isinstance(expression.value, list):
            self._add_line(statement.iterable, "FOR requires a list", "GWT013")
        elif iterable_type is not None and not _is_collection_type(iterable_type):
            self._add_line(statement.iterable, "FOR requires a list", "GWT013")

        loop_scope = scope.copy()
        item_type = _list_item_type(iterable_type) if iterable_type is not None else None
        if item_type is not None:
            self._add_typed_name(loop_scope, statement.name, item_type)
        else:
            loop_scope.names.add(statement.name)
            loop_scope.types[statement.name] = "any"
        if statement.where is not None:
            self._check_condition_with_scope(statement.where, loop_scope)
        self._check_body(statement.body, loop_scope, expected_return)

    def _check_given(self, statement: Any) -> None:
        if isinstance(statement, DtoValidation):
            if statement.dto_name not in self.program.dtos:
                self._add_line(statement.line, f"unknown DTO: {statement.dto_name}", "GWT014")
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
        dto = self.program.dtos.get(statement.item_type)
        if dto is None:
            self._add_line(statement.line, f"unknown DTO: {statement.item_type}", "GWT014")
            return
        if not statement.rows:
            return

        actual_fields = set(statement.rows[0])
        expected_fields = set(dto.fields)
        missing = sorted(expected_fields - actual_fields)
        if missing:
            self._add_line(statement.line, f"GIVEN table for {statement.item_type} missing field: {missing[0]}", "GWT014")
        extra = sorted(actual_fields - expected_fields)
        if extra:
            self._add_line(statement.line, f"GIVEN table for {statement.item_type} has unknown field: {extra[0]}", "GWT014")

        for row in statement.rows:
            for field, value in row.items():
                expected_type = dto.fields.get(field)
                if expected_type is None or _has_placeholder(value):
                    continue
                expression = self._check_expression(value, statement.line)
                actual_type = _infer_expression_type(expression, Scope(set())) if expression is not None else None
                if actual_type is not None and not _assignable(actual_type, expected_type):
                    self._add_line(
                        statement.line,
                        f"GIVEN table field '{field}' expected {expected_type}, got {actual_type}",
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
            if expected_return is not None and actual_type is not None and not _assignable(actual_type, expected_return):
                self._add_line(line, f"RETURN expected {expected_return}, got {actual_type}", "GWT016")
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
            self._check_condition(Line(line.number, condition, line.filename, line.column + len("REQUIRE "), len(condition)))
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
            self._check_assignment_type("set", path, actual_type, line, scope)
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
            if value_type is not None and not _is_collection_type(value_type):
                self._add_line(line, f"count requires a list, got {value_type}", "GWT016")
            self._check_path(path, line)
            self._check_assignment_type("count into", path, "number", line, scope)
            return

        if command == "sum":
            if len(tokens) < 4 or "into" not in tokens:
                self._add_line(line, "expected 'sum list into path'", "GWT006")
                return
            try:
                value, path = _split_required(line.text.removeprefix("sum").strip(), " into ", line.number)
            except GwtError as exc:
                self._add_line(line, str(exc), "GWT006")
                return
            path = path.strip()
            parsed = self._check_expression(value.strip(), line)
            value_type = _infer_expression_type(parsed, scope) if parsed is not None else None
            if value_type is not None and not _is_collection_type(value_type):
                self._add_line(line, f"sum requires a list, got {value_type}", "GWT016")
            self._check_path(path, line)
            self._check_assignment_type("sum into", path, "number", line, scope)
            return

        if command == "find":
            self._check_find(line, scope)
            return

        if command == "print":
            expression = line.text.removeprefix("print").strip()
            if not expression:
                self._add_line(line, "print requires a value", "GWT006")
                return
            self._check_expression(expression, line)

    def _check_assignment_type(self, command: str, path: str, actual_type: str | None, line: Line, scope: Scope) -> None:
        expected_type = scope.types.get(path)
        if expected_type is None or actual_type is None:
            return
        if not _assignable(actual_type, expected_type):
            self._add_line(line, f"{command} {path} expected {expected_type}, got {actual_type}", "GWT016")

    def _check_add_type(self, path: str, actual_type: str | None, line: Line, scope: Scope) -> None:
        expected_type = scope.types.get(path)
        if expected_type is None or actual_type is None:
            return
        if not _assignable(actual_type, expected_type):
            self._add_line(line, f"add to {path} expected {expected_type}, got {actual_type}", "GWT016")

    def _check_append_type(self, path: str, actual_type: str | None, line: Line, scope: Scope) -> None:
        expected_type = scope.types.get(path)
        if expected_type is None:
            return
        item_type = _list_item_type(expected_type)
        if expected_type != "list" and item_type is None:
            self._add_line(line, f"append to {path} expected list, got {expected_type}", "GWT016")
            return
        if item_type is not None and actual_type is not None and not _assignable(actual_type, item_type):
            self._add_line(line, f"append to {path} expected {item_type}, got {actual_type}", "GWT016")

    def _check_subtract_type(self, path: str, actual_type: str | None, line: Line, scope: Scope) -> None:
        expected_type = scope.types.get(path)
        if expected_type is not None and expected_type != "number" and expected_type != "any":
            self._add_line(line, f"subtract from {path} expected number, got {expected_type}", "GWT016")
            return
        if actual_type is not None and actual_type != "number" and actual_type != "any":
            self._add_line(line, f"subtract value expected number, got {actual_type}", "GWT016")

    def _check_find(self, line: Line, scope: Scope) -> None:
        match = re.match(
            r"^find ([A-Za-z_][A-Za-z0-9_]*) in (.+) where (.+) into ([A-Za-z_][A-Za-z0-9_.]*)$",
            line.text,
            re.IGNORECASE,
        )
        if match is None:
            self._add_line(line, "expected 'find name in list where condition into path'", "GWT006")
            return
        name, iterable_text, condition, path = match.groups()
        expression = self._check_expression(iterable_text.strip(), line)
        iterable_type = _infer_expression_type(expression, scope) if expression is not None else None
        if iterable_type is not None and not _is_collection_type(iterable_type):
            self._add_line(line, f"find requires a list, got {iterable_type}", "GWT016")

        find_scope = scope.copy()
        item_type = _list_item_type(iterable_type) if iterable_type is not None else None
        if item_type is not None:
            self._add_typed_name(find_scope, name, item_type)
        else:
            find_scope.names.add(name)
            find_scope.types[name] = "any"
        self._check_condition_with_scope(Line(line.number, condition.strip(), line.filename, line.column, len(condition.strip())), find_scope)
        self._check_path(path, line)
        if item_type is not None:
            self._check_assignment_type("find into", path, item_type, line, scope)

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
            self._add_line(line, f"no behavior matches: {' '.join(tokens)}", "GWT001")
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
            if actual_type is not None and not _assignable(actual_type, expected_type):
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
        if value_type in DTO_TYPES or value_type in self.program.dtos:
            return True
        item_type = _list_item_type(value_type)
        if item_type is None:
            return False
        return item_type in DTO_TYPES or item_type in self.program.dtos

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
    ) -> None:
        self.diagnostics.append(Diagnostic(filename, line, message, code, "error", column, max(1, length)))

    def _add_line(self, line: Line, message: str, code: str = "GWT000") -> None:
        self._add(line.filename, line.number, message, code, line.column, line.length)


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
        if isinstance(value, (int, float)):
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
        if expression.operator in {"==", "!=", ">", "<", ">=", "<=", "and", "or"}:
            return "boolean"
        if expression.operator in {"+", "-", "*", "/"}:
            left_type = _infer_expression_type(expression.left, scope)
            right_type = _infer_expression_type(expression.right, scope)
            if left_type == right_type == "number":
                return "number"
            if expression.operator == "+" and left_type == right_type == "text":
                return "text"
    return None


def _assignable(actual_type: str, expected_type: str) -> bool:
    if expected_type == "any" or actual_type == "any" or actual_type == expected_type:
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


def _is_collection_type(value_type: str) -> bool:
    return value_type == "list" or _list_item_type(value_type) is not None


def _has_placeholder(text: str) -> bool:
    return PLACEHOLDER_PATTERN.search(text) is not None


def _strip_location(message: str) -> str:
    match = re.match(r"^.+:\d+:\s*(.+)$", message)
    if match:
        return match.group(1)
    return message
