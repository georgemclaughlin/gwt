from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from .errors import GwtError
from .expressions import Expr, Literal, Name, parse_expression
from .runtime import (
    CONNECTORS,
    Action,
    DtoValidation,
    ForBlock,
    IfBlock,
    Line,
    Program,
    Scenario,
    _condition_to_expression,
    _is_local_name,
    _split_required,
    _tokens,
)


BUILTINS = {"set", "add", "subtract", "print"}
RESERVED_BEHAVIOR_NAMES = BUILTINS | {"LET", "REQUIRE", "RETURN"}
PLACEHOLDER_PATTERN = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*)>")
PATH_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


@dataclass(frozen=True)
class Diagnostic:
    filename: str | None
    line: int
    message: str

    def as_error_message(self, fallback_filename: str) -> str:
        filename = self.filename or fallback_filename
        return f"{filename}:{self.line}: {self.message}"

    def as_payload(self, fallback_filename: str) -> dict[str, object]:
        return {
            "file": self.filename or fallback_filename,
            "line": self.line,
            "message": self.message,
        }


@dataclass
class Scope:
    names: set[str]

    def copy(self) -> Scope:
        return Scope(set(self.names))


def check_program(program: Program) -> list[Diagnostic]:
    checker = Checker(program)
    return checker.check()


class Checker:
    def __init__(self, program: Program) -> None:
        self.program = program
        self.diagnostics: list[Diagnostic] = []
        self.actions_by_name = self._index_actions(program.actions)

    def check(self) -> list[Diagnostic]:
        self._check_behavior_signatures()
        for action in self.program.actions:
            self._check_action(action)
        self._check_background()
        for scenario in self.program.scenarios:
            self._check_scenario(scenario)
        return self.diagnostics

    def _check_behavior_signatures(self) -> None:
        seen: dict[tuple[str | None, tuple[str, ...]], Action] = {}
        for action in self.program.actions:
            if action.name in RESERVED_BEHAVIOR_NAMES:
                self._add(action.filename, action.line, f"behavior name is reserved: {action.name}")

            parameters = _signature_parameters(action.signature)
            duplicate_parameter = _first_duplicate(parameters)
            if duplicate_parameter is not None:
                self._add(action.filename, action.line, f"duplicate behavior parameter: {duplicate_parameter}")

            for parameter in parameters:
                if not _is_local_name(parameter):
                    self._add(action.filename, action.line, f"behavior parameter must be a simple name: {parameter}")

            key = (action.filename, _signature_shape(action.signature))
            previous = seen.get(key)
            if previous is not None:
                self._add(
                    action.filename,
                    action.line,
                    f"duplicate behavior signature: {_format_signature_shape(key[1])} "
                    f"(previously line {previous.line})",
                )
            else:
                seen[key] = action

    def _check_action(self, action: Action) -> None:
        scope = Scope(set(_signature_parameters(action.signature)))
        self._check_body(action.body, scope)

    def _check_background(self) -> None:
        background_lines = [
            *self.program.background.givens,
            *self.program.background.whens,
            *self.program.background.thens,
        ]
        for line in background_lines:
            if isinstance(line, Line):
                self._check_placeholders(line, set())

        for line in self.program.background.givens:
            self._check_given(line)
        for line in self.program.background.whens:
            self._check_command_or_action(line, Scope(set()), allow_let=False)
        for line in self.program.background.thens:
            self._check_condition(line)

    def _check_scenario(self, scenario: Scenario) -> None:
        example_headers = set(scenario.examples[0]) if scenario.examples else set()
        for line in scenario.givens:
            if isinstance(line, Line):
                self._check_placeholders(line, example_headers)
        for line in scenario.whens:
            self._check_placeholders(line, example_headers)
        for line in scenario.thens:
            self._check_placeholders(line, example_headers)

        for line in scenario.givens:
            self._check_given(line)
        for line in scenario.whens:
            self._check_command_or_action(line, Scope(set()), allow_let=False)
        for line in scenario.thens:
            self._check_condition(line)

    def _check_body(self, body: list[Any], scope: Scope) -> None:
        for statement in body:
            if isinstance(statement, IfBlock):
                self._check_condition(statement.condition)
                self._check_body(statement.then_body, scope.copy())
                self._check_body(statement.else_body, scope.copy())
            elif isinstance(statement, ForBlock):
                self._check_for(statement, scope)
            else:
                self._check_command_or_action(statement, scope, allow_let=True)

    def _check_for(self, statement: ForBlock, scope: Scope) -> None:
        if statement.name in scope.names:
            self._add(statement.iterable.filename, statement.iterable.number, f"FOR cannot overwrite: {statement.name}")

        expression = self._check_expression(statement.iterable.text, statement.iterable)
        if isinstance(expression, Literal) and not isinstance(expression.value, list):
            self._add(statement.iterable.filename, statement.iterable.number, "FOR requires a list")

        loop_scope = scope.copy()
        loop_scope.names.add(statement.name)
        self._check_body(statement.body, loop_scope)

    def _check_given(self, statement: Any) -> None:
        if isinstance(statement, DtoValidation):
            if statement.dto_name not in self.program.dtos:
                self._add(statement.line.filename, statement.line.number, f"unknown DTO: {statement.dto_name}")
            return
        if not isinstance(statement, Line):
            return

        try:
            path, expression = _split_required(statement.text, " is ", statement.number)
        except GwtError as exc:
            self._add(statement.filename, statement.number, str(exc))
            return

        self._check_path(path.strip(), statement)
        self._check_expression(expression.strip(), statement)

    def _check_command_or_action(self, line: Line, scope: Scope, *, allow_let: bool) -> None:
        try:
            tokens = _tokens(line.text, line.filename or "<source>", line.number)
        except GwtError as exc:
            self._add(line.filename, line.number, _strip_location(str(exc)))
            return
        if not tokens:
            return

        command = tokens[0]
        if command == "RETURN":
            if not allow_let:
                self._add(line.filename, line.number, "RETURN is only allowed inside behavior")
                return
            expression = line.text.removeprefix("RETURN").strip()
            if not expression:
                self._add(line.filename, line.number, "RETURN requires a value")
                return
            self._check_expression_or_action(expression, line, scope, require_return_value=True)
            return

        if command == "LET":
            if not allow_let:
                self._add(line.filename, line.number, "LET is only allowed inside behavior")
                return
            self._check_let(line, scope)
            return

        if command == "REQUIRE":
            condition = line.text.removeprefix("REQUIRE").strip()
            if not condition:
                self._add(line.filename, line.number, "REQUIRE requires a condition")
                return
            self._check_condition(Line(line.number, condition, line.filename))
            return

        if command in BUILTINS:
            self._check_builtin(tokens, line)
            return

        self._check_behavior_call(tokens, line, require_return_value=False)

    def _check_let(self, line: Line, scope: Scope) -> None:
        binding = line.text.removeprefix("LET").strip()
        try:
            name, expression = _split_required(binding, " be ", line.number)
        except GwtError as exc:
            self._add(line.filename, line.number, str(exc))
            return

        name = name.strip()
        if not _is_local_name(name):
            self._add(line.filename, line.number, "LET requires a simple local name")
            return
        if name in scope.names:
            self._add(line.filename, line.number, f"LET cannot overwrite an existing name: {name}")
            return

        self._check_expression_or_action(expression.strip(), line, scope, require_return_value=True)
        scope.names.add(name)

    def _check_builtin(self, tokens: list[str], line: Line) -> None:
        command = tokens[0]
        if command == "set":
            if len(tokens) < 4 or tokens[2] != "to":
                self._add(line.filename, line.number, "expected 'set path to value'")
                return
            self._check_path(tokens[1], line)
            expression = line.text.split(" to ", 1)[1].strip() if " to " in line.text else ""
            self._check_expression(expression, line)
            return

        if command == "add":
            if len(tokens) < 4 or "to" not in tokens:
                self._add(line.filename, line.number, "expected 'add value to path'")
                return
            try:
                value, path = _split_required(line.text.removeprefix("add").strip(), " to ", line.number)
            except GwtError as exc:
                self._add(line.filename, line.number, str(exc))
                return
            self._check_expression(value.strip(), line)
            self._check_path(path.strip(), line)
            return

        if command == "subtract":
            if len(tokens) < 4 or "from" not in tokens:
                self._add(line.filename, line.number, "expected 'subtract value from path'")
                return
            try:
                value, path = _split_required(line.text.removeprefix("subtract").strip(), " from ", line.number)
            except GwtError as exc:
                self._add(line.filename, line.number, str(exc))
                return
            self._check_expression(value.strip(), line)
            self._check_path(path.strip(), line)
            return

        if command == "print":
            expression = line.text.removeprefix("print").strip()
            if not expression:
                self._add(line.filename, line.number, "print requires a value")
                return
            self._check_expression(expression, line)

    def _check_condition(self, line: Line) -> None:
        if _has_placeholder(line.text):
            return
        try:
            expression_text = _condition_to_expression(line.text)
        except GwtError as exc:
            self._add(line.filename, line.number, str(exc))
            return
        expression = self._check_expression(expression_text, line)
        if isinstance(expression, Literal) and not isinstance(expression.value, bool):
            self._add(line.filename, line.number, "condition must evaluate to a boolean")

    def _check_expression_or_action(
        self,
        text: str,
        line: Line,
        scope: Scope,
        *,
        require_return_value: bool,
    ) -> None:
        if _has_placeholder(text):
            return
        try:
            expression = parse_expression(text)
            if isinstance(expression, Name):
                matches = self._matching_actions([expression.value])
                if matches and require_return_value and not any(_body_has_return(action.body) for action in matches):
                    self._add(line.filename, line.number, f"behavior does not return a value: {expression.value}")
            return
        except GwtError:
            pass

        try:
            tokens = _tokens(text, line.filename or "<source>", line.number)
        except GwtError as exc:
            self._add(line.filename, line.number, _strip_location(str(exc)))
            return
        self._check_behavior_call(tokens, line, require_return_value=require_return_value)

    def _check_behavior_call(self, tokens: list[str], line: Line, *, require_return_value: bool) -> None:
        if not tokens:
            self._add(line.filename, line.number, "expected behavior call")
            return
        matches = self._matching_actions(tokens)
        if not matches:
            self._add(line.filename, line.number, f"no behavior matches: {' '.join(tokens)}")
            return
        if require_return_value and not any(_body_has_return(action.body) for action in matches):
            self._add(line.filename, line.number, f"behavior does not return a value: {' '.join(tokens)}")

    def _matching_actions(self, call: list[str]) -> list[Action]:
        matches: list[Action] = []
        for action in self.actions_by_name.get(call[0], []):
            if _signature_matches(action.signature, call):
                matches.append(action)
        return matches

    def _check_expression(self, text: str, line: Line) -> Expr | None:
        if _has_placeholder(text):
            return None
        try:
            return parse_expression(text)
        except GwtError as exc:
            self._add(line.filename, line.number, f"invalid expression: {exc}")
            return None

    def _check_path(self, path: str, line: Line) -> None:
        if not PATH_PATTERN.match(path):
            self._add(line.filename, line.number, f"invalid path: {path}")

    def _check_placeholders(self, line: Line, example_headers: set[str]) -> None:
        for placeholder in PLACEHOLDER_PATTERN.findall(line.text):
            if placeholder not in example_headers:
                self._add(line.filename, line.number, f"EXAMPLES has no value for <{placeholder}>")

    def _index_actions(self, actions: list[Action]) -> dict[str, list[Action]]:
        indexed: dict[str, list[Action]] = {}
        for action in actions:
            indexed.setdefault(action.name, []).append(action)
        return indexed

    def _add(self, filename: str | None, line: int, message: str) -> None:
        self.diagnostics.append(Diagnostic(filename, line, message))


def _signature_parameters(signature: list[str]) -> list[str]:
    return [token for index, token in enumerate(signature) if index != 0 and token not in CONNECTORS]


def _signature_shape(signature: list[str]) -> tuple[str, ...]:
    return tuple(token if index == 0 or token in CONNECTORS else "_" for index, token in enumerate(signature))


def _signature_matches(signature: list[str], call: list[str]) -> bool:
    if len(signature) != len(call):
        return False
    for index, (pattern, actual) in enumerate(zip(signature, call)):
        if index == 0 and pattern != actual:
            return False
        if index != 0 and pattern in CONNECTORS and pattern != actual:
            return False
    return True


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


def _has_placeholder(text: str) -> bool:
    return PLACEHOLDER_PATTERN.search(text) is not None


def _strip_location(message: str) -> str:
    match = re.match(r"^.+:\d+:\s*(.+)$", message)
    if match:
        return match.group(1)
    return message
