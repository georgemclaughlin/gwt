from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import shlex
import textwrap
from typing import Any

from .errors import GwtError
from .expressions import evaluate_expression

CONNECTORS = {"from", "into", "to", "with", "by", "for", "using", "as"}
DTO_TYPES = {"number", "text", "boolean", "list", "any"}
LIST_TYPE_PATTERN = re.compile(r"^list<([A-Za-z_][A-Za-z0-9_]*)>$")


@dataclass(frozen=True)
class Line:
    number: int
    text: str
    filename: str | None = None
    column: int = 1
    length: int = 1


@dataclass(frozen=True)
class PathRef:
    path: str


@dataclass
class BehaviorContract:
    inputs: dict[str, str] = field(default_factory=dict)
    input_lines: dict[str, Line] = field(default_factory=dict)
    return_type: str | None = None
    return_line: Line | None = None


@dataclass
class Action:
    name: str
    signature: list[str]
    body: list[Any]
    line: int
    filename: str | None = None
    column: int = 1
    length: int = 1
    signature_text: str = ""
    contract: BehaviorContract = field(default_factory=BehaviorContract)


@dataclass
class IfBlock:
    condition: Line
    then_body: list[Any]
    else_body: list[Any]


@dataclass
class ForBlock:
    name: str
    iterable: Line
    body: list[Any]
    name_line: Line | None = None
    header_line: Line | None = None


@dataclass(frozen=True)
class DtoDefinition:
    name: str
    fields: dict[str, str]
    line: int
    filename: str | None = None
    column: int = 1
    length: int = 1
    field_lines: dict[str, Line] = field(default_factory=dict)


@dataclass(frozen=True)
class DtoValidation:
    path: str
    dto_name: str
    line: Line


@dataclass(frozen=True)
class ContractBinding:
    kind: str
    path: str
    value_type: str
    line: Line


@dataclass(frozen=True)
class TableAssignment:
    path: str
    rows: list[dict[str, str]]
    line: Line
    item_type: str | None = None


@dataclass(frozen=True)
class BehaviorReturn:
    value: Any


@dataclass
class Scenario:
    name: str
    line: int
    filename: str | None = None
    column: int = 1
    length: int = 1
    givens: list[Any] = field(default_factory=list)
    whens: list[Line] = field(default_factory=list)
    thens: list[Line] = field(default_factory=list)
    examples: list[dict[str, str]] = field(default_factory=list)


@dataclass
class Program:
    name: str | None = None
    background: Scenario = field(default_factory=lambda: Scenario("Background", 0))
    inputs: dict[str, ContractBinding] = field(default_factory=dict)
    outputs: dict[str, ContractBinding] = field(default_factory=dict)
    dtos: dict[str, DtoDefinition] = field(default_factory=dict)
    actions: list[Action] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)


@dataclass
class ScenarioResult:
    name: str
    state: dict[str, Any]
    output: list[str]
    returned_state: dict[str, Any] | None = None


@dataclass
class RunResult:
    scenarios: list[ScenarioResult]

    @property
    def state(self) -> dict[str, Any]:
        if len(self.scenarios) != 1:
            raise GwtError("state is only available when exactly one scenario runs")
        return self.scenarios[0].state

    @property
    def output(self) -> list[str]:
        if len(self.scenarios) != 1:
            raise GwtError("output is only available when exactly one scenario runs")
        return self.scenarios[0].output


@dataclass
class CallFrame:
    name: str
    call_line: Line
    caller_env: dict[str, Any]


@dataclass
class StackFrame:
    name: str
    line: Line
    locals: dict[str, Any]


def run_source(source: str, filename: str = "<source>") -> RunResult:
    program = parse_program(source, filename)
    runtime = Runtime(program)
    return runtime.run()


def run_request(
    program_source: str,
    request_source: str,
    *,
    filename: str = "<program>",
    request_filename: str = "<request>",
) -> RunResult:
    program = parse_program(program_source, filename)
    request = parse_program(request_source, request_filename, initial_dtos=program.dtos)
    combined = Program(
        name=program.name,
        background=Scenario(
            name="Background",
            line=request.background.line or program.background.line,
            filename=request.background.filename or program.background.filename,
            column=request.background.column or program.background.column,
            length=request.background.length or program.background.length,
            givens=[*program.background.givens, *request.background.givens],
            whens=[*program.background.whens, *request.background.whens],
            thens=[*program.background.thens, *request.background.thens],
        ),
        inputs={**program.inputs, **request.inputs},
        outputs={**program.outputs, **request.outputs},
        dtos={**program.dtos, **request.dtos},
        actions=[*program.actions, *request.actions],
        scenarios=request.scenarios,
    )
    runtime = Runtime(combined)
    return runtime.run()


def parse_program(
    source: str,
    filename: str = "<source>",
    importing: set[Path] | None = None,
    initial_dtos: dict[str, DtoDefinition] | None = None,
) -> Program:
    lines = _logical_lines(textwrap.dedent(source), filename)
    program = Program()
    if initial_dtos:
        program.dtos.update(initial_dtos)
    importing = set() if importing is None else importing
    current = Scenario("Main", 0)
    in_background = False
    saw_explicit_scenario = False
    index = 0
    last_top_keyword: str | None = None

    while index < len(lines):
        line = lines[index]
        text = line.text

        if text.startswith("BACKGROUND"):
            if text != "BACKGROUND":
                raise GwtError(f"{filename}:{line.number}: BACKGROUND does not take a name")
            if saw_explicit_scenario:
                raise GwtError(f"{filename}:{line.number}: BACKGROUND must appear before SCENARIO")
            current = program.background
            current.line = line.number
            current.filename = line.filename
            current.column = line.column
            current.length = len("BACKGROUND")
            in_background = True
            last_top_keyword = None
            index += 1
            continue

        if text.startswith("SCENARIO "):
            scenario_name = text.removeprefix("SCENARIO ").strip()
            if not scenario_name:
                raise GwtError(f"{filename}:{line.number}: SCENARIO requires a name")
            current = Scenario(
                scenario_name,
                line.number,
                line.filename,
                line.column + len("SCENARIO "),
                max(1, len(scenario_name)),
            )
            program.scenarios.append(current)
            in_background = False
            saw_explicit_scenario = True
            last_top_keyword = None
            index += 1
            continue

        if text.startswith("USE "):
            imported = _parse_import(text, line, filename, importing)
            program.dtos.update(imported.dtos)
            program.actions.extend(imported.actions)
            index += 1
            continue

        if text.startswith("DTO "):
            dto, index = _parse_dto(lines, index, filename)
            if dto.name in program.dtos:
                raise GwtError(f"{filename}:{line.number}: DTO already defined: {dto.name}")
            program.dtos[dto.name] = dto
            last_top_keyword = None
            continue

        if text == "EXAMPLES":
            if in_background:
                raise GwtError(f"{filename}:{line.number}: EXAMPLES cannot appear in BACKGROUND")
            examples, index = _parse_examples_table(lines, index + 1, filename, line.number)
            current.examples.extend(examples)
            last_top_keyword = None
            continue

        if text.startswith("AND "):
            if last_top_keyword is None:
                raise GwtError(f"{filename}:{line.number}: AND has no previous GIVEN, WHEN, THEN, REQUEST, or OUTPUT")
            text = f"{last_top_keyword} {text.removeprefix('AND ').strip()}"

        if text.startswith("PROGRAM "):
            program.name = text.removeprefix("PROGRAM ").strip()
            if not program.name:
                raise GwtError(f"{filename}:{line.number}: PROGRAM requires a name")
            index += 1
        elif text.startswith("REQUEST "):
            binding = _parse_contract_binding("REQUEST", text, filename, line)
            if binding.path in program.inputs:
                raise GwtError(f"{filename}:{line.number}: REQUEST already declares: {binding.path}")
            program.inputs[binding.path] = binding
            index += 1
            last_top_keyword = "REQUEST"
        elif text.startswith("OUTPUT "):
            binding = _parse_contract_binding("OUTPUT", text, filename, line)
            if binding.path in program.outputs:
                raise GwtError(f"{filename}:{line.number}: OUTPUT already declares: {binding.path}")
            program.outputs[binding.path] = binding
            index += 1
            last_top_keyword = "OUTPUT"
        elif text.startswith("GIVEN "):
            statement = text.removeprefix("GIVEN ").strip()
            if _is_table_header(statement):
                index += 1
                table, index = _parse_table_assignment(statement, lines, index, filename, line)
                current.givens.append(table)
            elif _is_typed_record_header(statement):
                index += 1
                expanded, index, validation = _expand_typed_record_block(statement, lines, index, filename, program.dtos)
                current.givens.extend(expanded)
                current.givens.append(validation)
            elif _is_record_header(statement):
                index += 1
                expanded, index = _expand_record_block(statement, lines, index, filename)
                current.givens.extend(expanded)
            else:
                current.givens.append(_derived_line(line, statement, len("GIVEN ")))
                index += 1
            last_top_keyword = "GIVEN"
        elif text.startswith("WHEN "):
            signature_text = text.removeprefix("WHEN ").strip()
            index += 1
            if index < len(lines) and lines[index].text.startswith("  ") and not in_background:
                signature = _tokens(signature_text, filename, line.number)
                if not signature:
                    raise GwtError(f"{filename}:{line.number}: WHEN requires a behavior signature")
                body, index, contract = _parse_action_block(lines, index, filename)
                if not body:
                    raise GwtError(f"{filename}:{line.number}: behavior '{signature[0]}' has no body")
                program.actions.append(
                    Action(
                        signature[0],
                        signature,
                        body,
                        line.number,
                        line.filename,
                        line.column + len("WHEN "),
                        max(1, len(signature_text)),
                        signature_text,
                        contract,
                    )
                )
            elif index < len(lines) and lines[index].text.startswith("  "):
                raise GwtError(f"{filename}:{line.number}: BACKGROUND cannot define WHEN behavior")
            else:
                current.whens.append(_derived_line(line, signature_text, len("WHEN ")))
            last_top_keyword = "WHEN"
        elif text.startswith("THEN "):
            statement = text.removeprefix("THEN ").strip()
            if _is_record_header(statement):
                index += 1
                expanded, index = _expand_record_block(statement, lines, index, filename)
                current.thens.extend(expanded)
            else:
                current.thens.append(_derived_line(line, statement, len("THEN ")))
                index += 1
            last_top_keyword = "THEN"
        elif text.startswith("  "):
            raise GwtError(f"{filename}:{line.number}: indented line outside a block")
        else:
            raise GwtError(f"{filename}:{line.number}: unknown top-level form: {text}")

    if not program.scenarios:
        program.scenarios.append(current)

    return program


class Runtime:
    def __init__(self, program: Program, debugger: Any | None = None) -> None:
        self.program = program
        self.state: dict[str, Any] = {}
        self.output: list[str] = []
        self.actions = self._index_actions(program.actions)
        self.debugger = debugger
        self.call_stack: list[CallFrame] = []
        self.base_path_types = self._base_path_types()
        self.path_types: dict[str, str] = {}

    def run(self) -> RunResult:
        results: list[ScenarioResult] = []
        for scenario in self.program.scenarios:
            if scenario.examples:
                for index, example in enumerate(scenario.examples, start=1):
                    results.append(self._run_scenario(scenario, example, f"{scenario.name} example {index}"))
            else:
                results.append(self._run_scenario(scenario))
        return RunResult(results)

    def _run_scenario(
        self, scenario: Scenario, example: dict[str, str] | None = None, result_name: str | None = None
    ) -> ScenarioResult:
        self.state = {}
        self.output = []
        self.path_types = dict(self.base_path_types)
        givens = [*self.program.background.givens, *_substitute_lines(scenario.givens, example)]
        whens = [*self.program.background.whens, *_substitute_lines(scenario.whens, example)]
        thens = [*self.program.background.thens, *_substitute_lines(scenario.thens, example)]
        for line in givens:
            if isinstance(line, DtoValidation):
                self._before_line(line.line, {})
                self._validate_dto(line)
            elif isinstance(line, TableAssignment):
                self._run_table_assignment(line)
            else:
                self._run_given(line)
        self._validate_contract_bindings(self.program.inputs, "REQUEST")
        for line in whens:
            self._run_command_or_action(line, {})
        self._validate_contract_bindings(self.program.outputs, "OUTPUT")
        for line in thens:
            self._before_line(line, {})
            try:
                assertion_passed = self._evaluate_condition(line.text, {})
            except GwtError as exc:
                raise _with_line_context(line, exc) from exc
            if not assertion_passed:
                raise GwtError(f"{scenario.name}: line {line.number}: assertion failed: {line.text}")
        return ScenarioResult(result_name or scenario.name, self.state, self.output, self._declared_output_state())

    def _index_actions(self, actions: list[Action]) -> dict[str, list[Action]]:
        indexed: dict[str, list[Action]] = {}
        for action in actions:
            indexed.setdefault(action.name, []).append(action)
        return indexed

    def _base_path_types(self) -> dict[str, str]:
        path_types: dict[str, str] = {}
        for binding in [*self.program.inputs.values(), *self.program.outputs.values()]:
            self._register_path_type(binding.path, binding.value_type, path_types)
        return path_types

    def _register_path_type(self, path: str, value_type: str, path_types: dict[str, str] | None = None) -> None:
        target = self.path_types if path_types is None else path_types
        target[path] = value_type

        dto = self.program.dtos.get(value_type)
        if dto is None:
            return
        for field, field_type in dto.fields.items():
            target[f"{path}.{field}"] = field_type
            if field_type in self.program.dtos:
                self._register_path_type(f"{path}.{field}", field_type, target)

    def _apply_action_contract(self, action: Action, env: dict[str, Any], line: Line) -> None:
        for name, value_type in action.contract.inputs.items():
            if name not in env:
                continue
            value = env[name]
            if isinstance(value, PathRef):
                resolved = self._resolve_path(value.path, {})
                self._register_path_type(resolved, value_type)
                self._validate_value_type(resolved, self._get_path(resolved, {}), value_type, line)
            else:
                self._validate_value_type(name, value, value_type, line)

    def _validate_assignment(self, path: str, value: Any, line: Line | None) -> None:
        expected_type = self.path_types.get(path)
        if expected_type is None:
            return
        validation_line = line or Line(0, path)
        self._validate_value_type(path, value, expected_type, validation_line)

    def _validate_dto(self, validation: DtoValidation) -> None:
        dto = self.program.dtos.get(validation.dto_name)
        if dto is None:
            raise GwtError(f"line {validation.line.number}: unknown DTO: {validation.dto_name}")
        try:
            value = self._get_path(validation.path, {})
            if not isinstance(value, dict):
                raise GwtError(f"expected {validation.path} to be a record")
            self._validate_dto_fields(validation.path, value, dto, validation.line)
            self._register_path_type(validation.path, validation.dto_name)
        except GwtError as exc:
            raise _with_line_context(validation.line, exc) from exc

    def _validate_dto_fields(self, base_path: str, value: dict[str, Any], dto: DtoDefinition, line: Line) -> None:
        flat_value = _flatten_record(value)
        expected_fields = set(dto.fields)
        actual_fields = set(flat_value)

        missing = sorted(expected_fields - actual_fields)
        if missing:
            raise GwtError(f"DTO {dto.name} missing field: {base_path}.{missing[0]}")

        extra = sorted(actual_fields - expected_fields)
        if extra:
            raise GwtError(f"DTO {dto.name} unknown field: {base_path}.{extra[0]}")

        for field, expected_type in dto.fields.items():
            field_value = flat_value[field]
            self._validate_value_type(f"{base_path}.{field}", field_value, expected_type, line)

    def _validate_value_type(self, path: str, value: Any, expected_type: str, line: Line) -> None:
        if expected_type == "any":
            return
        if expected_type in DTO_TYPES:
            if not _value_matches_primitive_type(value, expected_type):
                raise GwtError(
                    f"expected {path} to be {expected_type}, got {_value_type_name(value)}"
                )
            return

        item_type = _list_item_type(expected_type)
        if item_type is not None:
            if not isinstance(value, list):
                raise GwtError(f"expected {path} to be {expected_type}, got {_value_type_name(value)}")
            for index, item in enumerate(value, start=1):
                self._validate_value_type(f"{path}[{index}]", item, item_type, line)
            return

        dto = self.program.dtos.get(expected_type)
        if dto is None:
            raise GwtError(f"unknown DTO type: {expected_type}")
        if not isinstance(value, dict):
            raise GwtError(f"expected {path} to be {expected_type}, got {_value_type_name(value)}")
        self._validate_dto_fields(path, value, dto, line)

    def _validate_contract_bindings(self, bindings: dict[str, ContractBinding], label: str) -> None:
        for binding in bindings.values():
            try:
                value = self._get_path(binding.path, {})
                self._validate_value_type(binding.path, value, binding.value_type, binding.line)
            except GwtError as exc:
                raise _with_line_context(binding.line, GwtError(f"{label} contract failed for {binding.path}: {exc}")) from exc

    def _declared_output_state(self) -> dict[str, Any] | None:
        if not self.program.outputs:
            return None

        returned: dict[str, Any] = {}
        for binding in self.program.outputs.values():
            _set_nested_output(returned, binding.path, self._get_path(binding.path, {}))
        return returned

    def _run_given(self, line: Line) -> None:
        self._before_line(line, {})
        try:
            left, right = _split_required(line.text, " is ", line.number)
            self._set_path(left.strip(), self._eval_expression(right.strip(), {}), {}, line)
        except GwtError as exc:
            raise _with_line_context(line, exc) from exc

    def _run_table_assignment(self, table: TableAssignment) -> None:
        self._before_line(table.line, {})
        try:
            rows = [
                {
                    field: self._eval_expression(value, {})
                    for field, value in row.items()
                }
                for row in table.rows
            ]
            if table.item_type is not None:
                dto = self.program.dtos.get(table.item_type)
                if dto is None:
                    raise GwtError(f"unknown DTO: {table.item_type}")
                for index, row in enumerate(rows, start=1):
                    self._validate_dto_fields(f"{table.path}[{index}]", row, dto, table.line)
                self._register_path_type(table.path, f"list<{table.item_type}>")
            self._set_path(table.path, rows, {}, table.line)
        except GwtError as exc:
            raise _with_line_context(table.line, exc) from exc

    def _run_command_or_action(self, line: Line, env: dict[str, Any], *, allow_let: bool = False) -> BehaviorReturn | None:
        self._before_line(line, env)
        try:
            return self._run_command_or_action_inner(line, env, allow_let=allow_let)
        except GwtError as exc:
            raise _with_line_context(line, exc) from exc

    def _run_command_or_action_inner(
        self, line: Line, env: dict[str, Any], *, allow_let: bool = False
    ) -> BehaviorReturn | None:
        tokens = _tokens(line.text, "<source>", line.number)
        if not tokens:
            return

        command = tokens[0]
        if command == "RETURN":
            if not allow_let:
                raise GwtError(f"line {line.number}: RETURN is only allowed inside behavior")
            expression = line.text[len("RETURN") :].strip()
            if not expression:
                raise GwtError(f"line {line.number}: RETURN requires a value")
            return BehaviorReturn(self._eval_expression_or_returning_action(expression, line, env))
        if command == "LET":
            if not allow_let:
                raise GwtError(f"line {line.number}: LET is only allowed inside behavior")
            self._run_let(line, env)
            return
        if command == "REQUIRE":
            condition = line.text.removeprefix("REQUIRE ").strip()
            if not self._evaluate_condition(condition, env):
                raise GwtError(f"line {line.number}: requirement failed: {condition}")
            return
        if command in {"set", "add", "subtract", "print"}:
            self._run_builtin(tokens, line, env)
            return

        self._call_action(tokens, line, env)
        return None

    def _run_let(self, line: Line, env: dict[str, Any]) -> None:
        binding = line.text.removeprefix("LET ").strip()
        name, expression = _split_required(binding, " be ", line.number)
        name = name.strip()
        if not _is_local_name(name):
            raise GwtError(f"line {line.number}: LET requires a simple local name")
        if name in env or self._path_exists(name):
            raise GwtError(f"line {line.number}: LET cannot overwrite an existing name")
        env[name] = self._eval_expression_or_returning_action(expression.strip(), line, env)

    def _run_builtin(self, tokens: list[str], line: Line, env: dict[str, Any]) -> None:
        if tokens[0] == "set":
            if len(tokens) < 4 or tokens[2] != "to":
                raise GwtError(f"line {line.number}: expected 'set path to value'")
            self._set_path(tokens[1], self._eval_expression(_after_keyword(line.text, " to "), env), env, line)
        elif tokens[0] == "add":
            if len(tokens) < 4 or "to" not in tokens:
                raise GwtError(f"line {line.number}: expected 'add value to path'")
            value_text, path = _split_required(line.text.removeprefix("add ").strip(), " to ", line.number)
            value = self._eval_expression(value_text, env)
            try:
                new_value = self._get_path(path, env) + value
            except TypeError as exc:
                current_type = _value_type_name(self._get_path(path, env))
                raise GwtError(f"line {line.number}: cannot add {_value_type_name(value)} to {current_type}") from exc
            self._set_path(path, new_value, env, line)
        elif tokens[0] == "subtract":
            if len(tokens) < 4 or "from" not in tokens:
                raise GwtError(f"line {line.number}: expected 'subtract value from path'")
            value_text, path = _split_required(
                line.text.removeprefix("subtract ").strip(), " from ", line.number
            )
            value = self._eval_expression(value_text, env)
            try:
                new_value = self._get_path(path, env) - value
            except TypeError as exc:
                current_type = _value_type_name(self._get_path(path, env))
                raise GwtError(
                    f"line {line.number}: cannot subtract {_value_type_name(value)} from {current_type}"
                ) from exc
            self._set_path(path, new_value, env, line)
        elif tokens[0] == "print":
            value = self._eval_expression(line.text.removeprefix("print ").strip(), env)
            self.output.append(str(value))

    def _call_action(self, call: list[str], line: Line, caller_env: dict[str, Any]) -> BehaviorReturn | None:
        candidates = self.actions.get(call[0], [])
        for action in reversed(candidates):
            env = self._match_action(action, call, caller_env)
            if env is not None:
                self._apply_action_contract(action, env, line)
                frame = CallFrame(
                    action.signature_text or " ".join(action.signature),
                    line,
                    caller_env,
                )
                self.call_stack.append(frame)
                try:
                    return self._run_body(action.body, env)
                finally:
                    self.call_stack.pop()
        raise GwtError(f"line {line.number}: no action matches: {' '.join(call)}")

    def _run_body(self, body: list[Any], env: dict[str, Any]) -> BehaviorReturn | None:
        for statement in body:
            if isinstance(statement, IfBlock):
                self._before_line(statement.condition, env)
                try:
                    condition_result = self._evaluate_condition(statement.condition.text, env)
                except GwtError as exc:
                    raise _with_line_context(statement.condition, exc) from exc
                branch = statement.then_body if condition_result else statement.else_body
                result = self._run_body(branch, env)
            elif isinstance(statement, ForBlock):
                self._before_line(statement.header_line or statement.name_line or statement.iterable, env)
                result = self._run_for(statement, env)
            else:
                result = self._run_command_or_action(statement, env, allow_let=True)
            if isinstance(result, BehaviorReturn):
                return result
        return None

    def _before_line(self, line: Line, env: dict[str, Any]) -> None:
        if self.debugger is not None:
            self.debugger.before_line(line, self.state, env, self._stack_frames(line, env))

    def _stack_frames(self, line: Line, env: dict[str, Any]) -> list[StackFrame]:
        if not self.call_stack:
            return [StackFrame("Main", line, env)]

        frames = [StackFrame(self.call_stack[-1].name, line, env)]
        for index in range(len(self.call_stack) - 1, -1, -1):
            active = self.call_stack[index]
            caller_name = self.call_stack[index - 1].name if index > 0 else "Main"
            frames.append(StackFrame(caller_name, active.call_line, active.caller_env))
        return frames

    def _run_for(self, statement: ForBlock, env: dict[str, Any]) -> BehaviorReturn | None:
        if statement.name in env or self._path_exists(statement.name):
            raise GwtError(f"line {statement.iterable.number}: FOR cannot overwrite an existing name")
        try:
            values = self._eval_expression(statement.iterable.text, env)
        except GwtError as exc:
            raise _with_line_context(statement.iterable, exc) from exc
        if not isinstance(values, list):
            raise GwtError(f"line {statement.iterable.number}: FOR requires a list")

        for value in values:
            loop_env = dict(env)
            loop_env[statement.name] = value
            result = self._run_body(statement.body, loop_env)
            if isinstance(result, BehaviorReturn):
                return result
        return None

    def _match_action(self, action: Action, call: list[str], caller_env: dict[str, Any]) -> dict[str, Any] | None:
        if len(action.signature) != len(call):
            return None

        env: dict[str, Any] = {}
        for pattern, actual in zip(action.signature, call):
            if pattern == action.name:
                if pattern != actual:
                    return None
            elif pattern in CONNECTORS:
                if pattern != actual:
                    return None
            else:
                env[pattern] = self._argument_value(actual, caller_env)
        return env

    def _argument_value(self, token: str, env: dict[str, Any]) -> Any:
        if token in env:
            return env[token]
        if self._path_exists(self._resolve_path(token, env)):
            return PathRef(token)
        try:
            return self._eval_expression(token, env)
        except GwtError:
            pass
        return token

    def _evaluate_condition(self, text: str, env: dict[str, Any]) -> bool:
        expression = _condition_to_expression(text)
        value = self._eval_expression(expression, env)
        if not isinstance(value, bool):
            raise GwtError(f"condition must evaluate to a boolean: {text}")
        return value

    def _eval_expression(self, text: str, env: dict[str, Any]) -> Any:
        return evaluate_expression(text, ExpressionScope(self, env))

    def _eval_expression_or_returning_action(self, text: str, line: Line, env: dict[str, Any]) -> Any:
        try:
            return self._eval_expression(text, env)
        except GwtError as expression_error:
            tokens = _tokens(text, "<source>", line.number)
            if not tokens or tokens[0] not in self.actions:
                raise expression_error
            result = self._call_action(tokens, line, env)
            if isinstance(result, BehaviorReturn):
                return result.value
            raise GwtError(f"line {line.number}: behavior did not return a value: {text}")

    def _resolve_name(self, name: str, env: dict[str, Any]) -> Any:
        if name in env:
            value = env[name]
            if isinstance(value, PathRef):
                return self._get_path(value.path, {})
            return value
        if "." in name:
            env_value = self._get_env_path(name, env)
            if env_value is not None:
                return env_value
        if self._path_exists(self._resolve_path(name, env)):
            return self._get_path(name, env)
        raise GwtError(f"unknown name: {name}")

    def _resolve_path(self, path: str, env: dict[str, Any]) -> str:
        parts = path.split(".")
        if parts[0] in env and isinstance(env[parts[0]], PathRef):
            parts[0] = env[parts[0]].path
        return ".".join(parts)

    def _get_path(self, path: str, env: dict[str, Any]) -> Any:
        resolved = self._resolve_path(path, env)
        current: Any = self.state
        for part in resolved.split("."):
            if not isinstance(current, dict) or part not in current:
                raise GwtError(f"unknown path: {resolved}")
            current = current[part]
        return current

    def _set_path(self, path: str, value: Any, env: dict[str, Any], line: Line | None = None) -> None:
        resolved = self._resolve_path(path, env)
        parts = resolved.split(".")
        if not all(parts):
            raise GwtError(f"invalid path: {path}")
        self._validate_assignment(resolved, value, line)

        current = self.state
        for part in parts[:-1]:
            next_value = current.setdefault(part, {})
            if not isinstance(next_value, dict):
                raise GwtError(f"cannot create nested path under scalar: {part}")
            current = next_value
        current[parts[-1]] = value

    def _path_exists(self, path: str) -> bool:
        current: Any = self.state
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        return True

    def _get_env_path(self, path: str, env: dict[str, Any]) -> Any:
        parts = path.split(".")
        if not parts or parts[0] not in env:
            return None
        current = env[parts[0]]
        if isinstance(current, PathRef):
            current = self._get_path(current.path, {})
        for part in parts[1:]:
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return current


class ExpressionScope:
    def __init__(self, runtime: Runtime, env: dict[str, Any]) -> None:
        self.runtime = runtime
        self.env = env

    def resolve_name(self, name: str) -> Any:
        return self.runtime._resolve_name(name, self.env)


def _logical_lines(source: str, filename: str) -> list[Line]:
    lines: list[Line] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        without_comment = raw.split("#", 1)[0].rstrip()
        if without_comment.strip():
            column = len(without_comment) - len(without_comment.lstrip(" ")) + 1
            lines.append(Line(number, without_comment, filename, column, len(without_comment.strip())))
    return lines


def _derived_line(source: Line, text: str, column_offset: int = 0) -> Line:
    return Line(source.number, text, source.filename, source.column + column_offset, max(1, len(text)))


def _parse_action_block(lines: list[Line], index: int, filename: str) -> tuple[list[Any], int, BehaviorContract]:
    contract = BehaviorContract()
    last_contract_keyword: str | None = None

    while index < len(lines):
        line = lines[index]
        if _indent_width(line.text) != 2:
            break
        text = line.text.strip()
        if text.startswith("AND "):
            if last_contract_keyword != "GIVEN":
                break
            text = f"GIVEN {text.removeprefix('AND ').strip()}"
        if text.startswith("GIVEN "):
            name, value_type = _parse_contract_input(text, filename, line.number)
            if name in contract.inputs:
                raise GwtError(f"{filename}:{line.number}: behavior contract already defines: {name}")
            contract.inputs[name] = value_type
            contract.input_lines[name] = _derived_line(line, text, 0)
            index += 1
            last_contract_keyword = "GIVEN"
            continue
        if text.startswith("THEN returns "):
            if contract.return_type is not None:
                raise GwtError(f"{filename}:{line.number}: behavior contract already defines a return type")
            return_type = text.removeprefix("THEN returns ").strip()
            if not return_type:
                raise GwtError(f"{filename}:{line.number}: THEN returns requires a type")
            contract.return_type = return_type
            contract.return_line = _derived_line(line, text, 0)
            index += 1
            last_contract_keyword = "THEN"
            continue
        break

    body, index = _parse_behavior_block(lines, index, filename)
    return body, index, contract


def _parse_contract_input(text: str, filename: str, line_number: int) -> tuple[str, str]:
    statement = text.removeprefix("GIVEN ").strip()
    if " is " not in statement:
        raise GwtError(f"{filename}:{line_number}: behavior contract expects 'GIVEN name is Type'")
    name, value_type = statement.split(" is ", 1)
    name = name.strip()
    value_type = value_type.strip()
    if not _is_local_name(name):
        raise GwtError(f"{filename}:{line_number}: behavior contract requires a simple parameter name")
    if not value_type:
        raise GwtError(f"{filename}:{line_number}: behavior contract requires a type")
    return name, value_type


def _parse_contract_binding(keyword: str, text: str, filename: str, line: Line) -> ContractBinding:
    statement = text.removeprefix(f"{keyword} ").strip()
    if " is " not in statement:
        raise GwtError(f"{filename}:{line.number}: {keyword} expects '{keyword} path is Type'")
    path, value_type = statement.split(" is ", 1)
    path = path.strip()
    value_type = value_type.strip()
    if not _is_path(path):
        raise GwtError(f"{filename}:{line.number}: {keyword} requires a state path")
    if not value_type:
        raise GwtError(f"{filename}:{line.number}: {keyword} requires a type")
    if not _is_type_syntax(value_type):
        raise GwtError(f"{filename}:{line.number}: invalid {keyword} type: {value_type}")
    return ContractBinding(keyword.lower(), path, value_type, _derived_line(line, text, 0))


def _parse_behavior_block(lines: list[Line], index: int, filename: str, indent: int = 2) -> tuple[list[Any], int]:
    body: list[Any] = []
    last_body_keyword: str | None = None

    while index < len(lines):
        line = lines[index]
        line_indent = _indent_width(line.text)
        text = line.text.strip()

        if line_indent < indent:
            break
        if line_indent > indent:
            raise GwtError(f"{filename}:{line.number}: behavior statement is indented too far")
        if text == "ELSE":
            break
        if text.startswith("ELSE "):
            raise GwtError(f"{filename}:{line.number}: ELSE does not take a condition")
        if text.startswith("GIVEN ") or text.startswith("THEN returns "):
            raise GwtError(f"{filename}:{line.number}: behavior contracts must appear before executable statements")

        if text.startswith("AND "):
            if last_body_keyword is None:
                raise GwtError(f"{filename}:{line.number}: AND has no previous behavior statement")
            text = f"{last_body_keyword} {text.removeprefix('AND ').strip()}"

        if text.startswith("IF "):
            condition = text.removeprefix("IF ").strip()
            if not condition:
                raise GwtError(f"{filename}:{line.number}: IF requires a condition")
            index += 1
            then_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
            if not then_body:
                raise GwtError(f"{filename}:{line.number}: IF requires a body")

            else_body: list[Any] = []
            if index < len(lines) and _indent_width(lines[index].text) == indent and lines[index].text.strip() == "ELSE":
                else_line = lines[index]
                index += 1
                else_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
                if not else_body:
                    raise GwtError(f"{filename}:{else_line.number}: ELSE requires a body")

            body.append(IfBlock(_derived_line(line, condition, len("IF ")), then_body, else_body))
            last_body_keyword = None
            continue

        if text.startswith("FOR "):
            name, expression = _parse_for_header(text, filename, line.number)
            index += 1
            loop_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
            if not loop_body:
                raise GwtError(f"{filename}:{line.number}: FOR requires a body")
            body.append(
                ForBlock(
                    name,
                    _derived_line(line, expression, text.find(expression)),
                    loop_body,
                    _derived_line(line, name, len("FOR ")),
                    _derived_line(line, text, 0),
                )
            )
            last_body_keyword = None
            continue

        tokens = _tokens(text, filename, line.number)
        if tokens:
            last_body_keyword = tokens[0]
        body.append(_derived_line(line, text, 0))
        index += 1

    return body, index


def _parse_dto(lines: list[Line], index: int, filename: str) -> tuple[DtoDefinition, int]:
    header = lines[index]
    tokens = _tokens(header.text, filename, header.number)
    if len(tokens) != 2:
        raise GwtError(f"{filename}:{header.number}: DTO expects one name")
    name = tokens[1]
    if not _is_dto_name(name):
        raise GwtError(f"{filename}:{header.number}: DTO name must start with an uppercase letter")
    fields, field_lines, index = _parse_dto_fields(lines, index + 1, filename, header.number)
    return DtoDefinition(name, fields, header.number, header.filename, header.column + len("DTO "), len(name), field_lines), index


def _parse_dto_fields(
    lines: list[Line], index: int, filename: str, dto_line: int
) -> tuple[dict[str, str], dict[str, Line], int]:
    if index >= len(lines) or not lines[index].text.startswith("  "):
        raise GwtError(f"{filename}:{dto_line}: DTO requires fields")

    fields: dict[str, str] = {}
    field_lines: dict[str, Line] = {}
    parents: list[str] = []

    while index < len(lines) and lines[index].text.startswith("  "):
        line = lines[index]
        indent = _indent_width(line.text)
        if indent % 2 != 0:
            raise GwtError(f"{filename}:{line.number}: DTO indentation must use two spaces")

        depth = indent // 2 - 1
        if depth < 0:
            break
        if depth > len(parents):
            raise GwtError(f"{filename}:{line.number}: DTO field is indented too far")

        field_text = line.text.strip()
        if ":" not in field_text:
            raise GwtError(f"{filename}:{line.number}: DTO field must use 'name: type'")
        field, value_type = field_text.split(":", 1)
        field = field.strip()
        value_type = value_type.strip()
        if not field:
            raise GwtError(f"{filename}:{line.number}: DTO field requires a name")

        parent = "" if depth == 0 else parents[depth - 1]
        path = field if parent == "" else f"{parent}.{field}"
        parents = parents[:depth]
        parents.append(path)

        if value_type:
            if not _is_type_syntax(value_type):
                raise GwtError(f"{filename}:{line.number}: invalid DTO field type: {value_type}")
            if path in fields:
                raise GwtError(f"{filename}:{line.number}: DTO field already defined: {path}")
            fields[path] = value_type
            field_lines[path] = _derived_line(line, field, 0)
        elif index + 1 >= len(lines) or _indent_width(lines[index + 1].text) <= indent:
            raise GwtError(f"{filename}:{line.number}: nested DTO field requires fields")
        index += 1

    if not fields:
        raise GwtError(f"{filename}:{dto_line}: DTO requires typed fields")
    return fields, field_lines, index


def _parse_for_header(text: str, filename: str, line_number: int) -> tuple[str, str]:
    header = text.removeprefix("FOR ").strip()
    if " in " not in header:
        raise GwtError(f"{filename}:{line_number}: FOR expects 'name in expression'")
    name, expression = header.split(" in ", 1)
    name = name.strip()
    expression = expression.strip()
    if not _is_local_name(name):
        raise GwtError(f"{filename}:{line_number}: FOR requires a simple local name")
    if not expression:
        raise GwtError(f"{filename}:{line_number}: FOR requires an iterable expression")
    return name, expression


def _parse_import(text: str, line: Line, filename: str, importing: set[Path]) -> Program:
    tokens = _tokens(text, filename, line.number)
    if len(tokens) != 2:
        raise GwtError(f"{filename}:{line.number}: USE expects one quoted path")

    base_dir = Path.cwd() if filename == "<source>" else Path(filename).resolve().parent
    import_path = Path(tokens[1])
    if not import_path.is_absolute():
        import_path = base_dir / import_path
    import_path = import_path.resolve()

    if import_path in importing:
        raise GwtError(f"{filename}:{line.number}: circular USE import: {import_path}")
    if not import_path.exists():
        raise GwtError(f"{filename}:{line.number}: USE file not found: {import_path}")
    if not import_path.is_file():
        raise GwtError(f"{filename}:{line.number}: USE path is not a file: {import_path}")

    importing.add(import_path)
    try:
        return parse_program(import_path.read_text(), str(import_path), importing)
    finally:
        importing.remove(import_path)


def _parse_examples_table(
    lines: list[Line], index: int, filename: str, examples_line: int
) -> tuple[list[dict[str, str]], int]:
    rows, index = _parse_pipe_table(lines, index, filename, examples_line, "EXAMPLES")

    if len(rows) < 2:
        raise GwtError(f"{filename}:{examples_line}: EXAMPLES requires at least one data row")

    headers = rows[0]
    if len(set(headers)) != len(headers):
        raise GwtError(f"{filename}:{examples_line}: EXAMPLES headers must be unique")

    examples: list[dict[str, str]] = []
    for offset, row in enumerate(rows[1:], start=1):
        if len(row) != len(headers):
            raise GwtError(f"{filename}:{examples_line + offset}: EXAMPLES row has wrong number of cells")
        examples.append(dict(zip(headers, row)))
    return examples, index


def _parse_table_assignment(
    header: str,
    lines: list[Line],
    index: int,
    filename: str,
    header_line: Line,
) -> tuple[TableAssignment, int]:
    path, item_type = _parse_table_header(header, filename, header_line.number)
    if not path:
        raise GwtError(f"{filename}:{header_line.number}: table assignment requires a path")
    rows, index = _parse_pipe_table(lines, index, filename, header_line.number, "GIVEN table")

    if len(rows) < 2:
        raise GwtError(f"{filename}:{header_line.number}: GIVEN table requires at least one data row")
    headers = rows[0]
    if len(set(headers)) != len(headers):
        raise GwtError(f"{filename}:{header_line.number}: GIVEN table headers must be unique")
    for header_name in headers:
        if not _is_local_name(header_name):
            raise GwtError(f"{filename}:{header_line.number}: GIVEN table header must be a field name: {header_name}")

    records: list[dict[str, str]] = []
    for offset, row in enumerate(rows[1:], start=1):
        if len(row) != len(headers):
            raise GwtError(f"{filename}:{header_line.number + offset}: GIVEN table row has wrong number of cells")
        records.append(dict(zip(headers, row)))
    return TableAssignment(path, records, _derived_line(header_line, header, len("GIVEN ")), item_type), index


def _parse_table_header(header: str, filename: str, line_number: int) -> tuple[str, str | None]:
    match = re.match(
        r"^(?P<path>[A-Za-z_][A-Za-z0-9_.]*) are(?: (?P<item_type>[A-Za-z_][A-Za-z0-9_]*))?$",
        header,
    )
    if match is None:
        raise GwtError(f"{filename}:{line_number}: table assignment expects 'path are' or 'path are RowDto'")
    item_type = match.group("item_type")
    if item_type is not None and not _is_dto_name(item_type):
        raise GwtError(f"{filename}:{line_number}: GIVEN table type must be a DTO name")
    return match.group("path"), item_type


def _parse_pipe_table(
    lines: list[Line],
    index: int,
    filename: str,
    table_line: int,
    label: str,
) -> tuple[list[list[str]], int]:
    if index >= len(lines) or not lines[index].text.startswith("  "):
        raise GwtError(f"{filename}:{table_line}: {label} requires a table")

    rows: list[list[str]] = []
    while index < len(lines) and lines[index].text.startswith("  "):
        line = lines[index]
        if _indent_width(line.text) != 2:
            raise GwtError(f"{filename}:{line.number}: {label} rows must use two spaces")
        row_text = line.text.strip()
        if not (row_text.startswith("|") and row_text.endswith("|")):
            raise GwtError(f"{filename}:{line.number}: {label} rows must use table pipes")
        cells = [cell.strip() for cell in row_text.strip("|").split("|")]
        if not cells or any(cell == "" for cell in cells):
            raise GwtError(f"{filename}:{line.number}: {label} cells cannot be empty")
        rows.append(cells)
        index += 1
    return rows, index


def _substitute_lines(lines: list[Any], values: dict[str, str] | None) -> list[Any]:
    if values is None:
        return lines
    substituted: list[Any] = []
    for line in lines:
        if isinstance(line, DtoValidation):
            substituted.append(line)
        elif isinstance(line, TableAssignment):
            substituted.append(
                TableAssignment(
                    line.path,
                    [
                        {
                            field: _substitute_placeholders(value, values, line.line.number)
                            for field, value in row.items()
                        }
                        for row in line.rows
                    ],
                    line.line,
                    line.item_type,
                )
            )
        else:
            substituted.append(
                Line(
                    line.number,
                    _substitute_placeholders(line.text, values, line.number),
                    line.filename,
                    line.column,
                    line.length,
                )
            )
    return substituted


def _substitute_placeholders(text: str, values: dict[str, str], line_number: int) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise GwtError(f"line {line_number}: EXAMPLES has no value for <{name}>")
        return values[name]

    return re.sub(r"<([A-Za-z_][A-Za-z0-9_]*)>", replace, text)


def _with_line_context(line: Line, error: GwtError) -> GwtError:
    message = str(error)
    if _has_error_location(message):
        return error
    if line.filename:
        return GwtError(f"{line.filename}:{line.number}: {message}")
    return GwtError(f"line {line.number}: {message}")


def _has_error_location(message: str) -> bool:
    return (
        re.match(r"^.+:\d+:", message) is not None
        or re.match(r"^.+: line \d+:", message) is not None
        or re.match(r"^line \d+:", message) is not None
    )


def _is_record_header(text: str) -> bool:
    return text.endswith(" is")


def _is_table_header(text: str) -> bool:
    return re.match(r"^[A-Za-z_][A-Za-z0-9_.]* are(?: [A-Za-z_][A-Za-z0-9_]*)?$", text) is not None


def _is_typed_record_header(text: str) -> bool:
    return re.match(r"^[A-Za-z_][A-Za-z0-9_.]* is [A-Z][A-Za-z0-9_]*$", text) is not None


def _expand_typed_record_block(
    header: str,
    lines: list[Line],
    index: int,
    filename: str,
    dtos: dict[str, DtoDefinition],
) -> tuple[list[Line], int, DtoValidation]:
    header_line = lines[index - 1]
    path, dto_name = header.split(" is ", 1)
    path = path.strip()
    dto_name = dto_name.strip()
    if dto_name not in dtos:
        raise GwtError(f"{filename}:{header_line.number}: unknown DTO: {dto_name}")
    expanded, index = _expand_record_block(f"{path} is", lines, index, filename)
    return expanded, index, DtoValidation(path, dto_name, header_line)


def _expand_record_block(
    header: str, lines: list[Line], index: int, filename: str
) -> tuple[list[Line], int]:
    base_path = header.removesuffix(" is").strip()
    if not base_path:
        raise GwtError(f"{filename}: record block requires a path")
    if index >= len(lines) or not lines[index].text.startswith("  "):
        raise GwtError(f"{filename}: line {lines[index - 1].number}: record block requires fields")

    expanded: list[Line] = []
    parents: list[str] = []

    while index < len(lines) and lines[index].text.startswith("  "):
        line = lines[index]
        indent = _indent_width(line.text)
        if indent % 2 != 0:
            raise GwtError(f"{filename}:{line.number}: record indentation must use two spaces")

        depth = indent // 2 - 1
        if depth < 0:
            break
        if depth > len(parents):
            raise GwtError(f"{filename}:{line.number}: record field is indented too far")

        field_text = line.text.strip()
        if ":" not in field_text:
            raise GwtError(f"{filename}:{line.number}: record field must use 'name: value'")
        field, value = field_text.split(":", 1)
        field = field.strip()
        value = value.strip()
        if not field:
            raise GwtError(f"{filename}:{line.number}: record field requires a name")

        parent = base_path if depth == 0 else parents[depth - 1]
        path = f"{parent}.{field}"
        parents = parents[:depth]
        parents.append(path)

        if value:
            expanded.append(_derived_line(line, f"{path} is {value}", 0))
        index += 1

    if not expanded:
        raise GwtError(f"{filename}: line {lines[index - 1].number}: record block requires values")
    return expanded, index


def _indent_width(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


def _is_local_name(text: str) -> bool:
    if not text or "." in text:
        return False
    if not (text[0].isalpha() or text[0] == "_"):
        return False
    return all(char.isalnum() or char == "_" for char in text)


def _is_path(text: str) -> bool:
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$", text))


def _is_dto_name(text: str) -> bool:
    return bool(re.match(r"^[A-Z][A-Za-z0-9_]*$", text))


def _is_type_syntax(value_type: str) -> bool:
    if value_type in DTO_TYPES or _is_dto_name(value_type):
        return True
    item_type = _list_item_type(value_type)
    if item_type is None:
        return False
    return item_type in DTO_TYPES or _is_dto_name(item_type)


def _list_item_type(value_type: str) -> str | None:
    match = LIST_TYPE_PATTERN.match(value_type)
    if match is None:
        return None
    return match.group(1)


def _flatten_record(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, item in value.items():
        path = key if prefix == "" else f"{prefix}.{key}"
        if isinstance(item, dict):
            flattened.update(_flatten_record(item, path))
        else:
            flattened[path] = item
    return flattened


def _set_nested_output(target: dict[str, Any], path: str, value: Any) -> None:
    current = target
    parts = path.split(".")
    for part in parts[:-1]:
        next_value = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            raise GwtError(f"OUTPUT path collides with scalar: {path}")
        current = next_value
    current[parts[-1]] = value


def _value_matches_primitive_type(value: Any, expected_type: str) -> bool:
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "text":
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "list":
        return isinstance(value, list)
    if expected_type == "any":
        return True
    raise AssertionError(expected_type)


def _value_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "record"
    return type(value).__name__


def _tokens(text: str, filename: str, line_number: int) -> list[str]:
    try:
        return shlex.split(text)
    except ValueError as exc:
        raise GwtError(f"{filename}:{line_number}: {exc}") from exc


def _split_required(text: str, separator: str, line_number: int) -> tuple[str, str]:
    if separator not in text:
        raise GwtError(f"line {line_number}: expected '{separator.strip()}' in: {text}")
    left, right = text.split(separator, 1)
    return left, right


def _after_keyword(text: str, separator: str) -> str:
    if separator not in text:
        raise GwtError(f"expected '{separator.strip()}' in: {text}")
    return text.split(separator, 1)[1]


def _condition_to_expression(text: str) -> str:
    if " is " not in text:
        return text

    left, right_text = text.split(" is ", 1)
    right_text = right_text.strip()

    if right_text.startswith("not "):
        operator = "!="
        right = right_text.removeprefix("not ").strip()
    elif right_text.startswith("greater than "):
        operator = ">"
        right = right_text.removeprefix("greater than ").strip()
    elif right_text.startswith("less than "):
        operator = "<"
        right = right_text.removeprefix("less than ").strip()
    elif right_text.startswith("at least "):
        operator = ">="
        right = right_text.removeprefix("at least ").strip()
    elif right_text.startswith("at most "):
        operator = "<="
        right = right_text.removeprefix("at most ").strip()
    else:
        operator = "=="
        right = right_text

    if not left.strip() or not right:
        raise GwtError(f"invalid condition: {text}")
    return f"{left.strip()} {operator} {right}"
