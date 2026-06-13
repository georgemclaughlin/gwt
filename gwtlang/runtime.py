from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from difflib import get_close_matches
from pathlib import Path
import re
import shlex
import textwrap
from typing import Any, Iterable, TypeGuard, cast

from .errors import GwtError
from .expressions import Literal, evaluate_expression, parse_expression
from .tracing import GwtTraceRecorder, state_change_for_set

CONNECTORS = {"from", "into", "to", "with", "by", "for", "using", "as"}
RECORD_TYPES = {"number", "integer", "decimal", "text", "boolean", "list", "any"}
LIST_TYPE_PATTERN = re.compile(r"^list<(.+)>$")
SIGNATURE_PARAMETER_PATTERN = re.compile(r"^<([A-Za-z_][A-Za-z0-9_]*)>$")
RESERVED_BEHAVIOR_NAMES = {
    "set",
    "add",
    "subtract",
    "append",
    "count",
    "sum",
    "find",
    "exists",
    "print",
    "LET",
    "REQUIRE",
    "RETURN",
    "PASS",
    "IF",
    "ELSE",
    "FOR",
    "FIND",
    "DEPENDING",
    "DECIDE",
}
_MISSING = object()


@dataclass(frozen=True)
class ImportPolicy:
    allowed_roots: tuple[Path, ...] = ()
    allow_absolute: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "allowed_roots",
            tuple(Path(root).resolve() for root in self.allowed_roots),
        )

    def validate(
        self,
        raw_path: Path,
        resolved_path: Path,
        filename: str,
        line_number: int,
    ) -> None:
        if raw_path.is_absolute() and not self.allow_absolute:
            raise GwtError(
                f"{filename}:{line_number}: USE absolute import is not allowed: {raw_path}"
            )

        if not self.allowed_roots:
            return

        for root in self.allowed_roots:
            try:
                resolved_path.relative_to(root)
            except ValueError:
                continue
            return

        raise GwtError(
            f"{filename}:{line_number}: USE import is outside allowed roots: {resolved_path}"
        )


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
    inputs: dict[str, str] = field(default_factory=lambda: {})
    input_lines: dict[str, Line] = field(default_factory=lambda: {})
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
    where: Line | None = None


@dataclass
class FindBlock:
    name: str
    iterable: Line
    condition: Line
    body: list[Any]
    else_body: list[Any]
    name_line: Line | None = None
    header_line: Line | None = None


@dataclass
class DecisionBranch:
    condition: Line
    body: list[Any]


@dataclass
class DecisionBlock:
    branches: list[DecisionBranch]
    else_body: list[Any]
    header_line: Line
    else_line: Line


@dataclass
class MatchCase:
    name: str
    body: list[Any]
    line: Line
    selector: str = "kind"
    literal: Any = None


@dataclass
class MatchBlock:
    expression: Line
    cases: list[MatchCase]
    else_body: list[Any]
    header_line: Line | None = None
    else_line: Line | None = None


@dataclass(frozen=True)
class RecordDefinition:
    name: str
    fields: dict[str, str]
    line: int
    filename: str | None = None
    column: int = 1
    length: int = 1
    field_lines: dict[str, Line] = field(default_factory=lambda: {})


@dataclass(frozen=True)
class VariantCaseDefinition:
    name: str
    fields: dict[str, str]
    line: int
    filename: str | None = None
    column: int = 1
    length: int = 1
    field_lines: dict[str, Line] = field(default_factory=lambda: {})


@dataclass(frozen=True)
class VariantDefinition:
    name: str
    cases: dict[str, VariantCaseDefinition]
    line: int
    filename: str | None = None
    column: int = 1
    length: int = 1


@dataclass(frozen=True)
class TypeAliasDefinition:
    name: str
    value_type: str
    line: int
    filename: str | None = None
    column: int = 1
    length: int = 1


@dataclass(frozen=True)
class RecordValidation:
    path: str
    record_name: str
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
class VariantAssignment:
    path: str
    variant_name: str
    case_name: str
    fields: dict[str, str]
    line: Line
    field_lines: dict[str, Line] = field(default_factory=lambda: {})


@dataclass(frozen=True)
class BehaviorReturn:
    value: Any


@dataclass(frozen=True)
class RequestCall:
    name: str
    line: Line


@dataclass
class Scenario:
    name: str
    line: int
    filename: str | None = None
    column: int = 1
    length: int = 1
    givens: list[Any] = field(default_factory=lambda: [])
    whens: list[Any] = field(default_factory=lambda: [])
    thens: list[Line] = field(default_factory=lambda: [])
    examples: list[dict[str, str]] = field(default_factory=lambda: [])


@dataclass
class NamedRequest:
    name: str
    line: Line
    inputs: dict[str, ContractBinding] = field(default_factory=lambda: {})
    outputs: dict[str, ContractBinding] = field(default_factory=lambda: {})
    givens: list[Any] = field(default_factory=lambda: [])
    whens: list[Line] = field(default_factory=lambda: [])
    thens: list[Line] = field(default_factory=lambda: [])


@dataclass
class Program:
    name: str | None = None
    background: Scenario = field(default_factory=lambda: Scenario("Background", 0))
    records: dict[str, RecordDefinition] = field(default_factory=lambda: {})
    variants: dict[str, VariantDefinition] = field(default_factory=lambda: {})
    type_aliases: dict[str, TypeAliasDefinition] = field(default_factory=lambda: {})
    actions: list[Action] = field(default_factory=lambda: [])
    requests: dict[str, NamedRequest] = field(default_factory=lambda: {})
    scenarios: list[Scenario] = field(default_factory=lambda: [])


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


def run_source(
    source: str,
    filename: str = "<source>",
    *,
    import_policy: ImportPolicy | None = None,
) -> RunResult:
    program = parse_program(source, filename, import_policy=import_policy)
    runtime = Runtime(program)
    return runtime.run()


def run_request(
    program_source: str,
    request_source: str,
    *,
    filename: str = "<program>",
    request_filename: str = "<request>",
    import_policy: ImportPolicy | None = None,
) -> RunResult:
    program = parse_program(program_source, filename, import_policy=import_policy)
    request = parse_program(
        request_source,
        request_filename,
        initial_records=program.records,
        initial_variants=program.variants,
        initial_type_aliases=program.type_aliases,
        import_policy=import_policy,
    )
    _validate_external_request_file(request, request_filename)
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
        records={**program.records, **request.records},
        variants={**program.variants, **request.variants},
        type_aliases={**program.type_aliases, **request.type_aliases},
        actions=[*program.actions, *request.actions],
        requests={**program.requests, **request.requests},
        scenarios=request.scenarios,
    )
    runtime = Runtime(combined)
    return runtime.run()


def _validate_external_request_file(request: Program, filename: str) -> None:
    if request.name is not None:
        raise GwtError(
            f"{filename}:1: request files cannot declare PROGRAM; "
            "the program is provided by the run target"
        )

    if request.actions:
        action = request.actions[0]
        raise GwtError(
            f"{action.filename or filename}:{action.line}: "
            "request files cannot define WHEN behavior; define behavior in the program file"
        )

    if request.requests:
        named_request = next(iter(request.requests.values()))
        line = named_request.line
        raise GwtError(
            f"{line.filename or filename}:{line.number}: "
            "request files cannot define named REQUEST blocks; define public requests in the program file"
        )

    scenarios = request.scenarios or [Scenario("Main", 0)]
    background_has_request = _validate_request_file_steps(request.background.whens, filename)
    for scenario in scenarios:
        scenario_has_request = _validate_request_file_steps(scenario.whens, filename)
        if not background_has_request and not scenario_has_request:
            line = scenario.line or request.background.line or 1
            raise GwtError(
                f"{filename}:{line}: request files must invoke at least one named REQUEST"
            )


def _validate_request_file_steps(steps: list[Any], filename: str) -> bool:
    has_request = False
    for step in steps:
        if isinstance(step, RequestCall):
            has_request = True
            continue
        if isinstance(step, Line):
            raise GwtError(
                f"{step.filename or filename}:{step.number}: "
                f"request files must invoke named REQUESTs; direct WHEN is not allowed: {step.text}"
            )
    return has_request


def run_json_request(
    program_source: str,
    state: dict[str, Any],
    *,
    request: str,
    filename: str = "<program>",
    request_filename: str = "<request>",
    json_filename: str | None = None,
    import_policy: ImportPolicy | None = None,
    validate_contracts: bool = True,
) -> RunResult:
    program = parse_program(program_source, filename, import_policy=import_policy)
    runtime = Runtime(program)
    return runtime.run_json(
        state,
        request,
        request_filename=request_filename,
        json_filename=json_filename,
        validate_contracts=validate_contracts,
    )


def parse_program(
    source: str,
    filename: str = "<source>",
    importing: set[Path] | None = None,
    initial_records: dict[str, RecordDefinition] | None = None,
    initial_variants: dict[str, VariantDefinition] | None = None,
    initial_type_aliases: dict[str, TypeAliasDefinition] | None = None,
    allow_unknown_records: bool = False,
    import_policy: ImportPolicy | None = None,
) -> Program:
    lines = _logical_lines(textwrap.dedent(source), filename)
    program = Program()
    if initial_records:
        program.records.update(initial_records)
    if initial_variants:
        program.variants.update(initial_variants)
    if initial_type_aliases:
        program.type_aliases.update(initial_type_aliases)
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
            imported = _parse_import(text, line, filename, importing, import_policy)
            duplicate_types = sorted(
                (
                    set(program.records)
                    | set(program.variants)
                    | set(program.type_aliases)
                )
                & (
                    set(imported.records)
                    | set(imported.variants)
                    | set(imported.type_aliases)
                )
            )
            if duplicate_types:
                raise GwtError(f"{filename}:{line.number}: type already defined: {duplicate_types[0]}")
            program.records.update(imported.records)
            program.variants.update(imported.variants)
            program.type_aliases.update(imported.type_aliases)
            program.actions.extend(imported.actions)
            duplicate_requests = sorted(set(program.requests) & set(imported.requests))
            if duplicate_requests:
                raise GwtError(f"{filename}:{line.number}: REQUEST already declares: {duplicate_requests[0]}")
            program.requests.update(imported.requests)
            index += 1
            continue

        if text == "RECORD" or text.startswith("RECORD "):
            if _is_record_one_of_header(text):
                variant, index = _parse_variant(lines, index, filename)
                if variant.name in program.records or variant.name in program.variants or variant.name in program.type_aliases:
                    raise GwtError(f"{filename}:{line.number}: type already defined: {variant.name}")
                program.variants[variant.name] = variant
            else:
                record, index = _parse_record(lines, index, filename)
                if record.name in program.records or record.name in program.variants or record.name in program.type_aliases:
                    raise GwtError(f"{filename}:{line.number}: type already defined: {record.name}")
                program.records[record.name] = record
            last_top_keyword = None
            continue

        if text.startswith("TYPE "):
            alias = _parse_type_alias(line, filename)
            if alias.name in program.records or alias.name in program.variants or alias.name in program.type_aliases:
                raise GwtError(f"{filename}:{line.number}: type already defined: {alias.name}")
            program.type_aliases[alias.name] = alias
            index += 1
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
            last_top_keyword = None
        elif text.startswith("EXPORT "):
            raise GwtError(f"{filename}:{line.number}: EXPORT is no longer a public interface form; use REQUEST <name>")
        elif text.startswith("REQUEST "):
            if index + 1 < len(lines) and _indent_width(lines[index + 1].text) >= 2:
                named_request, index = _parse_named_request(
                    lines,
                    index,
                    filename,
                    program.records,
                    program.type_aliases,
                    allow_unknown_records=allow_unknown_records,
                )
                if named_request.name in program.requests:
                    raise GwtError(f"{filename}:{line.number}: REQUEST already declares: {named_request.name}")
                program.requests[named_request.name] = named_request
                last_top_keyword = None
            else:
                request_name = text.removeprefix("REQUEST ").strip()
                if not request_name:
                    raise GwtError(f"{filename}:{line.number}: REQUEST requires a name")
                if _looks_like_removed_request_contract(request_name):
                    raise GwtError(
                        f"{filename}:{line.number}: top-level REQUEST contracts were removed; "
                        "use REQUEST <name> with indented GIVEN bindings"
                    )
                current.whens.append(RequestCall(request_name, _derived_line(line, request_name, len("REQUEST "))))
                index += 1
                last_top_keyword = None
        elif text.startswith("OUTPUT "):
            raise GwtError(f"{filename}:{line.number}: OUTPUT must appear inside a named REQUEST block")
        elif text.startswith("GIVEN "):
            statement = text.removeprefix("GIVEN ").strip()
            if _is_table_header(statement):
                index += 1
                table, index = _parse_table_assignment(statement, lines, index, filename, line)
                current.givens.append(table)
            elif _is_variant_assignment_header(statement):
                index += 1
                assignment, index = _parse_variant_assignment(statement, lines, index, filename, line)
                current.givens.append(assignment)
            elif _is_typed_record_header(statement):
                index += 1
                expanded, index, validation = _expand_typed_record_block(
                    statement,
                    lines,
                    index,
                    filename,
                    program.records,
                    program.type_aliases,
                    allow_unknown_records=allow_unknown_records,
                )
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
                if signature[0] in RESERVED_BEHAVIOR_NAMES:
                    raise GwtError(f"{filename}:{line.number}: behavior name is reserved: {signature[0]}")
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
        elif text.startswith(" "):
            indent = _indent_width(text)
            if indent % 2 != 0:
                raise GwtError(
                    f"{filename}:{line.number}: invalid indentation: use two spaces per level"
                )
            raise GwtError(f"{filename}:{line.number}: indented line outside a block")
        else:
            raise GwtError(f"{filename}:{line.number}: unknown top-level form: {text}")

    if not program.scenarios:
        program.scenarios.append(current)

    return program


class Runtime:
    def __init__(
        self,
        program: Program,
        debugger: Any | None = None,
        tracer: GwtTraceRecorder | None = None,
    ) -> None:
        self.program = program
        self.state: dict[str, Any] = {}
        self.output: list[str] = []
        self.actions = self._index_actions(program.actions)
        self.debugger = debugger
        self.tracer = tracer
        self.call_stack: list[CallFrame] = []
        self.base_path_types = self._base_path_types()
        self.path_types: dict[str, str] = {}
        self._last_returned_state: dict[str, Any] | None = None

    def run(self) -> RunResult:
        results: list[ScenarioResult] = []
        for scenario in self.program.scenarios:
            if scenario.examples:
                for index, example in enumerate(scenario.examples, start=1):
                    results.append(self._run_scenario(scenario, example, f"{scenario.name} example {index}"))
            else:
                results.append(self._run_scenario(scenario))
        return RunResult(results)

    def run_json(
        self,
        state: object,
        request: str,
        *,
        request_filename: str = "<request>",
        json_filename: str | None = None,
        validate_contracts: bool = True,
    ) -> RunResult:
        if not isinstance(state, dict):
            raise GwtError("JSON input must be an object")
        json_state = cast(dict[object, object], state)
        request = request.strip()
        if not request:
            raise GwtError("request name is required for JSON input")

        self.state = {}
        self.output = []
        self.path_types = dict(self.base_path_types)
        self._last_returned_state = None

        self._run_givens(self.program.background.givens)

        json_line = Line(1, "<json-input>", json_filename or request_filename, 1, len("<json-input>"))
        declared_path_types = self.path_types
        try:
            self.path_types = {}
            for path, value in json_state.items():
                if not isinstance(path, str) or not _is_path(path):
                    raise GwtError(f"JSON input key must be a state path: {path}")
                self._set_path(path, deepcopy(value), {}, json_line)
        except GwtError as exc:
            raise _with_line_context(json_line, exc) from exc
        finally:
            self.path_types = declared_path_types

        for line in self.program.background.whens:
            self._run_when_step(line, {})

        request_line = Line(1, request, request_filename, 1, max(1, len(request)))
        self._run_request_call(request, request_line, validate_contracts=validate_contracts)

        for line in self.program.background.thens:
            self._before_line(line, {}, trace_statement=False)
            try:
                assertion_passed = self._evaluate_condition(line.text, {}, line, trace_kind="assertion")
            except GwtError as exc:
                raise _with_line_context(line, exc) from exc
            if not assertion_passed:
                raise GwtError(f"Main: line {line.number}: assertion failed: {line.text}")

        return RunResult([ScenarioResult("Main", self.state, self.output, self._last_returned_state)])

    def _run_scenario(
        self, scenario: Scenario, example: dict[str, str] | None = None, result_name: str | None = None
    ) -> ScenarioResult:
        self.state = {}
        self.output = []
        self.path_types = dict(self.base_path_types)
        self._last_returned_state = None
        givens = [*self.program.background.givens, *_substitute_lines(scenario.givens, example)]
        whens = [*self.program.background.whens, *_substitute_lines(scenario.whens, example)]
        thens = [*self.program.background.thens, *_substitute_lines(scenario.thens, example)]
        self._run_givens(givens)
        for line in whens:
            self._run_when_step(line, {})
        for line in thens:
            self._before_line(line, {}, trace_statement=False)
            try:
                assertion_passed = self._evaluate_condition(line.text, {}, line, trace_kind="assertion")
            except GwtError as exc:
                raise _with_line_context(line, exc) from exc
            if not assertion_passed:
                raise GwtError(f"{scenario.name}: line {line.number}: assertion failed: {line.text}")
        return ScenarioResult(result_name or scenario.name, self.state, self.output, self._last_returned_state)

    def _index_actions(self, actions: list[Action]) -> dict[str, list[Action]]:
        indexed: dict[str, list[Action]] = {}
        for action in actions:
            indexed.setdefault(action.name, []).append(action)
        return indexed

    def _base_path_types(self) -> dict[str, str]:
        return {}

    def _request_path_types(self, request: NamedRequest, current_path_types: dict[str, str] | None = None) -> dict[str, str]:
        path_types = dict(self.base_path_types if current_path_types is None else current_path_types)
        for binding in [*request.inputs.values(), *request.outputs.values()]:
            self._register_path_type(binding.path, binding.value_type, path_types)
        return path_types

    def _run_givens(self, givens: list[Any]) -> None:
        for line in givens:
            if isinstance(line, RecordValidation):
                self._before_line(line.line, {})
                self._validate_record(line)
            elif isinstance(line, TableAssignment):
                self._run_table_assignment(line)
            elif isinstance(line, VariantAssignment):
                self._run_variant_assignment(line)
            else:
                self._run_given(line)

    def _run_when_step(self, step: Any, env: dict[str, Any]) -> None:
        if isinstance(step, RequestCall):
            self._run_request_call(step.name, step.line)
            return
        self._run_command_or_action(step, env)

    def _run_request_call(
        self,
        name: str,
        line: Line,
        *,
        validate_contracts: bool = True,
    ) -> None:
        request = self.program.requests.get(name)
        if request is None:
            raise _with_line_context(
                line,
                GwtError(_unknown_request_message(name, self.program.requests.keys())),
            )

        self._before_line(line, {})
        if self.tracer is not None:
            self.tracer.enter_request(name, line)
        previous_path_types = self.path_types
        self.path_types = self._request_path_types(request, previous_path_types)
        try:
            if validate_contracts:
                self._validate_contract_bindings(request.inputs, "REQUEST")
            self._run_givens(request.givens)
            for when in request.whens:
                self._run_command_or_action(when, {})
            if validate_contracts:
                self._validate_contract_bindings(request.outputs, "OUTPUT")
            for then in request.thens:
                self._before_line(then, {}, trace_statement=False)
                try:
                    assertion_passed = self._evaluate_condition(then.text, {}, then, trace_kind="assertion")
                except GwtError as exc:
                    raise _with_line_context(then, exc) from exc
                if not assertion_passed:
                    raise GwtError(f"REQUEST {request.name}: line {then.number}: assertion failed: {then.text}")
            self._last_returned_state = self._declared_output_state(request)
            if self.tracer is not None:
                self.tracer.record_request_completed(
                    output=self._last_returned_state,
                    output_paths=[binding.path for binding in request.outputs.values()],
                )
        except GwtError as exc:
            if self.tracer is not None:
                self.tracer.exit_request(error=str(exc))
            raise
        finally:
            previous_path_types.update(self.path_types)
            self.path_types = previous_path_types
        if self.tracer is not None:
            self.tracer.exit_request()

    def _register_path_type(self, path: str, value_type: str, path_types: dict[str, str] | None = None) -> None:
        target = self.path_types if path_types is None else path_types
        target[path] = value_type

        resolved_type = self._resolve_type_alias(value_type)
        record = self.program.records.get(resolved_type)
        if record is not None:
            for field, field_type in record.fields.items():
                target[f"{path}.{field}"] = field_type
                resolved_field_type = self._resolve_type_alias(field_type)
                if resolved_field_type in self.program.records or resolved_field_type in self.program.variants:
                    self._register_path_type(f"{path}.{field}", field_type, target)
            return

        variant = self.program.variants.get(resolved_type)
        if variant is not None:
            target[f"{path}.kind"] = _variant_kind_type(variant)

    def _resolve_type_alias(self, value_type: str) -> str:
        return _resolve_type_alias(value_type, self.program.type_aliases)

    def _apply_action_contract(self, action: Action, env: dict[str, Any], line: Line) -> None:
        for name, value_type in action.contract.inputs.items():
            if name not in env:
                continue
            value = env[name]
            if isinstance(value, PathRef):
                resolved = self._resolve_path(value.path, {})
                self._register_path_type(resolved, value_type)
                normalized = self._validate_value_type(resolved, self._get_path(resolved, {}), value_type, line)
                self._set_path(resolved, normalized, {}, line)
            else:
                env[name] = self._validate_value_type(name, value, value_type, line)

    def _validate_assignment(self, path: str, value: Any, line: Line | None) -> Any:
        expected_type = self.path_types.get(path)
        if expected_type is None:
            return value
        validation_line = line or Line(0, path)
        return self._validate_value_type(path, value, expected_type, validation_line)

    def _validate_record(self, validation: RecordValidation) -> None:
        record_name = self._resolve_type_alias(validation.record_name)
        record = self.program.records.get(record_name)
        variant = self.program.variants.get(record_name)
        if record is None and variant is None:
            raise GwtError(f"line {validation.line.number}: unknown record: {validation.record_name}")
        try:
            value = self._get_path(validation.path, {})
            if variant is not None:
                self._validate_variant_value(validation.path, value, variant, validation.line)
                self._register_path_type(validation.path, validation.record_name)
                return
            if not isinstance(value, dict):
                raise GwtError(f"expected {validation.path} to be a record")
            assert record is not None
            record_value = cast(dict[str, Any], value)
            self._validate_record_fields(validation.path, record_value, record, validation.line)
            self._register_path_type(validation.path, validation.record_name)
        except GwtError as exc:
            raise _with_line_context(validation.line, exc) from exc

    def _validate_record_fields(self, base_path: str, value: dict[str, Any], record: RecordDefinition, line: Line) -> None:
        flat_value = _flatten_record(value)
        expected_fields = set(record.fields)
        actual_fields = set(flat_value)

        missing = sorted(expected_fields - actual_fields)
        if missing:
            raise GwtError(f"record {record.name} missing field: {base_path}.{missing[0]}")

        extra = sorted(actual_fields - expected_fields)
        if extra:
            raise GwtError(f"record {record.name} unknown field: {base_path}.{extra[0]}")

        for field, expected_type in record.fields.items():
            field_value = flat_value[field]
            normalized = self._validate_value_type(f"{base_path}.{field}", field_value, expected_type, line)
            _set_flat_record_value(value, field, normalized)

    def _validate_value_type(self, path: str, value: Any, expected_type: str, line: Line) -> Any:
        expected_type = self._resolve_type_alias(expected_type)
        if expected_type == "any":
            return value
        literal_values = _literal_union_values(expected_type)
        if literal_values is not None:
            candidate = value
            base_type = _value_type_name(literal_values[0])
            if base_type in RECORD_TYPES:
                normalized = _normalize_primitive_value(value, base_type)
                if normalized is not _INVALID_TYPE:
                    candidate = normalized
            if not any(_value_matches_literal(candidate, literal) for literal in literal_values):
                raise GwtError(
                    f"expected {path} to be one of {_format_literal_values(literal_values)}, "
                    f"got {_literal_value_text(value)}"
                )
            return candidate
        if expected_type in RECORD_TYPES:
            normalized = _normalize_primitive_value(value, expected_type)
            if normalized is _INVALID_TYPE:
                raise GwtError(
                    f"expected {path} to be {expected_type}, got {_value_type_name(value)}"
                )
            return normalized

        item_type = _list_item_type(expected_type)
        if item_type is not None:
            if not isinstance(value, list):
                raise GwtError(f"expected {path} to be {expected_type}, got {_value_type_name(value)}")
            items = cast(list[Any], value)
            for index, item in enumerate(items, start=1):
                items[index - 1] = self._validate_value_type(f"{path}[{index}]", item, item_type, line)
            return items

        record = self.program.records.get(expected_type)
        if record is not None:
            if not isinstance(value, dict):
                raise GwtError(f"expected {path} to be {expected_type}, got {_value_type_name(value)}")
            record_value = cast(dict[str, Any], value)
            self._validate_record_fields(path, record_value, record, line)
            return record_value

        variant = self.program.variants.get(expected_type)
        if variant is not None:
            self._validate_variant_value(path, value, variant, line)
            return value

        raise GwtError(f"unknown record type: {expected_type}")

    def _validate_variant_value(self, path: str, value: Any, variant: VariantDefinition, line: Line) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise GwtError(f"expected {path} to be {variant.name}, got {_value_type_name(value)}")
        record = cast(dict[str, Any], value)
        kind = record.get("kind")
        if not isinstance(kind, str):
            raise GwtError(f"record {variant.name} missing field: {path}.kind")
        case = variant.cases.get(kind)
        if case is None:
            raise GwtError(f"record {variant.name} has unknown kind: {kind}")

        flat_value = _flatten_record(record)
        expected_fields = {"kind", *case.fields}
        actual_fields = set(flat_value)

        missing = sorted(expected_fields - actual_fields)
        if missing:
            raise GwtError(f"record {variant.name} missing field: {path}.{missing[0]}")

        extra = sorted(actual_fields - expected_fields)
        if extra:
            raise GwtError(f"record {variant.name} unknown field for kind {kind}: {path}.{extra[0]}")

        for field, expected_type in case.fields.items():
            normalized = self._validate_value_type(f"{path}.{field}", flat_value[field], expected_type, line)
            _set_flat_record_value(record, field, normalized)
        return record

    def _validate_contract_bindings(self, bindings: dict[str, ContractBinding], label: str) -> None:
        for binding in bindings.values():
            try:
                value = self._get_path(binding.path, {})
                normalized = self._validate_value_type(binding.path, value, binding.value_type, binding.line)
                self._set_path(binding.path, normalized, {}, binding.line)
            except GwtError as exc:
                if self.tracer is not None:
                    self.tracer.record_contract(
                        label=label,
                        path=binding.path,
                        value_type=binding.value_type,
                        passed=False,
                        line=binding.line,
                        error=str(exc),
                    )
                raise _with_line_context(
                    binding.line,
                    GwtError(_contract_failure_message(label, binding, exc)),
                ) from exc
            if self.tracer is not None:
                self.tracer.record_contract(
                    label=label,
                    path=binding.path,
                    value_type=binding.value_type,
                    passed=True,
                    line=binding.line,
                )

    def _declared_output_state(self, request: NamedRequest) -> dict[str, Any]:
        if not request.outputs:
            return {}

        returned: dict[str, Any] = {}
        for binding in request.outputs.values():
            _set_nested_output(returned, binding.path, self._get_path(binding.path, {}))
        return returned

    def _run_given(self, line: Line) -> None:
        self._before_line(line, {}, trace_statement=False)
        try:
            left, right = _split_required(line.text, " is ", line.number)
            self._set_path(left.strip(), self._eval_expression(right.strip(), {}), {}, line)
        except GwtError as exc:
            raise _with_line_context(line, exc) from exc

    def _run_table_assignment(self, table: TableAssignment) -> None:
        self._before_line(table.line, {}, trace_statement=False)
        try:
            rows = [
                {
                    field: self._eval_expression(value, {})
                    for field, value in row.items()
                }
                for row in table.rows
            ]
            if table.item_type is not None:
                resolved_item_type = self._resolve_type_alias(table.item_type)
                record = self.program.records.get(resolved_item_type)
                if record is None:
                    if resolved_item_type in self.program.variants:
                        raise GwtError(f"GIVEN table cannot construct one-of record: {table.item_type}")
                    raise GwtError(f"unknown record: {table.item_type}")
                for index, row in enumerate(rows, start=1):
                    self._validate_record_fields(f"{table.path}[{index}]", row, record, table.line)
                self._register_path_type(table.path, f"list<{table.item_type}>")
            self._set_path(table.path, rows, {}, table.line)
        except GwtError as exc:
            raise _with_line_context(table.line, exc) from exc

    def _run_variant_assignment(self, assignment: VariantAssignment) -> None:
        self._before_line(assignment.line, {}, trace_statement=False)
        try:
            variant_name = self._resolve_type_alias(assignment.variant_name)
            variant = self.program.variants.get(variant_name)
            if variant is None:
                raise GwtError(f"unknown one-of record: {assignment.variant_name}")
            if assignment.case_name not in variant.cases:
                raise GwtError(f"unknown kind for {assignment.variant_name}: {assignment.case_name}")
            row = {
                "kind": assignment.case_name,
                **{
                    field: self._eval_expression(value, {})
                    for field, value in assignment.fields.items()
                },
            }
            try:
                current = self._get_path(assignment.path, {})
            except GwtError:
                current = []
            if not isinstance(current, list):
                raise GwtError(f"expected {assignment.path} to be a list")
            current_items = cast(list[Any], current)
            self._validate_variant_value(f"{assignment.path}[{len(current_items) + 1}]", row, variant, assignment.line)
            self._register_path_type(assignment.path, f"list<{assignment.variant_name}>")
            self._set_path(assignment.path, [*current_items, row], {}, assignment.line)
        except GwtError as exc:
            raise _with_line_context(assignment.line, exc) from exc

    def _run_command_or_action(self, line: Line, env: dict[str, Any], *, allow_let: bool = False) -> BehaviorReturn | None:
        self._before_line(line, env, trace_statement=not self._line_has_semantic_trace(line))
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
        if command == "PASS":
            if not allow_let:
                raise GwtError(f"line {line.number}: PASS is only allowed inside behavior")
            if len(tokens) != 1:
                raise GwtError(f"line {line.number}: PASS does not take arguments")
            return
        if command == "LET":
            if not allow_let:
                raise GwtError(f"line {line.number}: LET is only allowed inside behavior")
            self._run_let(line, env)
            return
        if command == "REQUIRE":
            condition = line.text.removeprefix("REQUIRE ").strip()
            if not self._evaluate_condition(condition, env, line):
                raise GwtError(f"line {line.number}: requirement failed: {condition}")
            return
        if _is_builtin_statement(tokens, line.text):
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
                current_type = self.path_types.get(
                    self._resolve_path(path, env),
                    _value_type_name(self._get_path(path, env)),
                )
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
                current_type = self.path_types.get(
                    self._resolve_path(path, env),
                    _value_type_name(self._get_path(path, env)),
                )
                raise GwtError(
                    f"line {line.number}: cannot subtract {_value_type_name(value)} from {current_type}"
                ) from exc
            self._set_path(path, new_value, env, line)
        elif tokens[0] == "append":
            if len(tokens) < 4 or "to" not in tokens:
                raise GwtError(f"line {line.number}: expected 'append value to path'")
            value_text, path = _split_required(line.text.removeprefix("append ").strip(), " to ", line.number)
            value = self._eval_expression(value_text, env)
            current = self._get_path(path, env)
            if not isinstance(current, list):
                raise GwtError(f"line {line.number}: append requires a list target")
            current_items = cast(list[Any], current)
            new_value: list[Any] = [*current_items, value]
            self._set_path(path, new_value, env, line)
        elif tokens[0] == "count":
            if len(tokens) < 4 or "into" not in tokens:
                raise GwtError(f"line {line.number}: expected 'count list into path'")
            value_text, path = _split_required(line.text.removeprefix("count ").strip(), " into ", line.number)
            value = self._eval_expression(value_text, env)
            if not isinstance(value, list):
                raise GwtError(f"line {line.number}: count requires a list")
            values = cast(list[Any], value)
            self._set_path(path, len(values), env, line)
        elif tokens[0] == "sum":
            if len(tokens) < 4 or "into" not in tokens:
                raise GwtError(f"line {line.number}: expected 'sum list into path'")
            projection = _parse_sum_projection(line.text)
            if projection is not None:
                projection_text, name, iterable_text, path = projection
                values = self._eval_expression(iterable_text.strip(), env)
                if not isinstance(values, list):
                    raise GwtError(f"line {line.number}: sum requires a list")
                total = 0
                for value in cast(list[Any], values):
                    sum_env = dict(env)
                    sum_env[name] = value
                    item = self._eval_expression(projection_text, sum_env)
                    if not _is_numeric_value(item):
                        raise GwtError(f"line {line.number}: sum requires numeric projected values")
                    total += item
                self._set_path(path, total, env, line)
                return
            value_text, path = _split_required(line.text.removeprefix("sum ").strip(), " into ", line.number)
            values = self._eval_expression(value_text, env)
            if not isinstance(values, list):
                raise GwtError(f"line {line.number}: sum requires a list")
            total = 0
            for value in cast(list[Any], values):
                if not _is_numeric_value(value):
                    raise GwtError(f"line {line.number}: sum requires a list of numbers")
                total += value
            self._set_path(path, total, env, line)
        elif tokens[0] == "find":
            self._run_find(line, env)
        elif tokens[0] == "exists":
            self._run_exists(line, env)
        elif tokens[0] == "print":
            value = self._eval_expression(line.text.removeprefix("print ").strip(), env)
            self.output.append(str(value))
            if self.tracer is not None:
                self.tracer.record_output(value=str(value), line=line)

    def _run_find(self, line: Line, env: dict[str, Any]) -> None:
        parsed = _parse_find_statement(line.text)
        if parsed is None:
            raise GwtError(f"line {line.number}: expected 'find [optional] name in list where condition into path'")
        optional, name, iterable_text, condition, path = parsed
        values = self._eval_expression(iterable_text.strip(), env)
        if not isinstance(values, list):
            raise GwtError(f"line {line.number}: find requires a list")
        for value in cast(list[Any], values):
            find_env = dict(env)
            find_env[name] = value
            if self._evaluate_condition(condition.strip(), find_env, line):
                self._set_path(path, value, env, line)
                return
        if optional:
            return
        raise GwtError(f"line {line.number}: find found no matching item")

    def _run_exists(self, line: Line, env: dict[str, Any]) -> None:
        parsed = _parse_exists_statement(line.text)
        if parsed is None:
            raise GwtError(f"line {line.number}: expected 'exists name in list where condition into path'")
        name, iterable_text, condition, path = parsed
        values = self._eval_expression(iterable_text.strip(), env)
        if not isinstance(values, list):
            raise GwtError(f"line {line.number}: exists requires a list")
        found = False
        for value in cast(list[Any], values):
            exists_env = dict(env)
            exists_env[name] = value
            if self._evaluate_condition(condition.strip(), exists_env, line):
                found = True
                break
        self._set_path(path, found, env, line)

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
                if self.tracer is not None:
                    self.tracer.enter_behavior(frame.name, line)
                try:
                    result = self._run_body(action.body, env)
                except GwtError as exc:
                    if self.tracer is not None:
                        self.tracer.exit_behavior(error=str(exc))
                    raise
                else:
                    if self.tracer is not None:
                        self.tracer.exit_behavior()
                    return result
                finally:
                    self.call_stack.pop()
        raise GwtError(
            f"line {line.number}: "
            f"{_action_mismatch_message('no action matches', call, self.actions)}"
        )

    def _run_body(self, body: list[Any], env: dict[str, Any]) -> BehaviorReturn | None:
        for statement in body:
            if isinstance(statement, IfBlock):
                self._before_line(statement.condition, env, trace_statement=False)
                try:
                    condition_result = self._evaluate_condition(statement.condition.text, env, statement.condition)
                except GwtError as exc:
                    raise _with_line_context(statement.condition, exc) from exc
                self._record_if_branch(statement, selected=condition_result)
                branch = statement.then_body if condition_result else statement.else_body
                result = self._run_body(branch, env)
            elif isinstance(statement, ForBlock):
                self._before_line(statement.header_line or statement.name_line or statement.iterable, env)
                result = self._run_for(statement, env)
            elif isinstance(statement, FindBlock):
                self._before_line(statement.header_line or statement.name_line or statement.iterable, env)
                result = self._run_find_block(statement, env)
            elif isinstance(statement, DecisionBlock):
                self._before_line(statement.header_line, env)
                result = self._run_decision_block(statement, env)
            elif isinstance(statement, MatchBlock):
                self._before_line(statement.header_line or statement.expression, env)
                result = self._run_match_block(statement, env)
            else:
                result = self._run_command_or_action(statement, env, allow_let=True)
            if isinstance(result, BehaviorReturn):
                return result
        return None

    def _before_line(self, line: Line, env: dict[str, Any], *, trace_statement: bool = True) -> None:
        stack = self._stack_frames(line, env)
        if self.debugger is not None:
            self.debugger.before_line(line, self.state, env, stack)
        if self.tracer is not None and trace_statement:
            self.tracer.before_line(line, self.state, env, stack)

    def _line_has_semantic_trace(self, line: Line) -> bool:
        tokens = _tokens(line.text, "<source>", line.number)
        if not tokens:
            return False
        if tokens[0] in {
            "set",
            "add",
            "subtract",
            "append",
            "count",
            "sum",
            "find",
            "exists",
            "print",
            "REQUIRE",
        }:
            return True
        return tokens[0] in self.actions

    def _stack_frames(self, line: Line, env: dict[str, Any]) -> list[StackFrame]:
        if not self.call_stack:
            return [StackFrame("Main", line, env)]

        frames = [StackFrame(self.call_stack[-1].name, line, env)]
        for index in range(len(self.call_stack) - 1, -1, -1):
            active = self.call_stack[index]
            caller_name = self.call_stack[index - 1].name if index > 0 else "Main"
            frames.append(StackFrame(caller_name, active.call_line, active.caller_env))
        return frames

    def _record_if_branch(self, statement: IfBlock, *, selected: bool) -> None:
        if self.tracer is None:
            return
        body = statement.then_body if selected else statement.then_body
        start_line, end_line = _body_line_range(body)
        self.tracer.record_branch(
            kind="IF",
            condition=statement.condition.text,
            selected=selected,
            line=statement.condition,
            start_line=start_line,
            end_line=end_line,
        )

    def _record_decision_branch(self, branch: DecisionBranch, *, selected: bool) -> None:
        if self.tracer is None:
            return
        start_line, end_line = _body_line_range(branch.body)
        self.tracer.record_branch(
            kind="DECIDE",
            condition=branch.condition.text,
            selected=selected,
            line=branch.condition,
            start_line=start_line,
            end_line=end_line,
        )

    def _run_for(self, statement: ForBlock, env: dict[str, Any]) -> BehaviorReturn | None:
        if statement.name in env or self._path_exists(statement.name):
            raise GwtError(f"line {statement.iterable.number}: FOR cannot overwrite an existing name")
        try:
            values = self._eval_expression(statement.iterable.text, env)
        except GwtError as exc:
            raise _with_line_context(statement.iterable, exc) from exc
        if not isinstance(values, list):
            raise GwtError(f"line {statement.iterable.number}: FOR requires a list")

        for value in cast(list[Any], values):
            loop_env = dict(env)
            loop_env[statement.name] = value
            if statement.where is not None and not self._evaluate_condition(
                statement.where.text,
                loop_env,
                statement.where,
            ):
                continue
            result = self._run_body(statement.body, loop_env)
            if isinstance(result, BehaviorReturn):
                return result
        return None

    def _run_find_block(self, statement: FindBlock, env: dict[str, Any]) -> BehaviorReturn | None:
        if statement.name in env or self._path_exists(statement.name):
            raise GwtError(f"line {statement.iterable.number}: FIND cannot overwrite an existing name")
        try:
            values = self._eval_expression(statement.iterable.text, env)
        except GwtError as exc:
            raise _with_line_context(statement.iterable, exc) from exc
        if not isinstance(values, list):
            raise GwtError(f"line {statement.iterable.number}: FIND requires a list")

        for value in cast(list[Any], values):
            find_env = dict(env)
            find_env[statement.name] = value
            if self._evaluate_condition(statement.condition.text, find_env, statement.condition):
                result = self._run_body(statement.body, find_env)
                if isinstance(result, BehaviorReturn):
                    return result
                return None
        return self._run_body(statement.else_body, env)

    def _run_decision_block(self, statement: DecisionBlock, env: dict[str, Any]) -> BehaviorReturn | None:
        for branch in statement.branches:
            self._before_line(branch.condition, env, trace_statement=False)
            try:
                selected = self._evaluate_condition(branch.condition.text, env, branch.condition)
                self._record_decision_branch(branch, selected=selected)
                if selected:
                    return self._run_body(branch.body, env)
            except GwtError as exc:
                raise _with_line_context(branch.condition, exc) from exc
        self._before_line(statement.else_line, env)
        return self._run_body(statement.else_body, env)

    def _run_match_block(self, statement: MatchBlock, env: dict[str, Any]) -> BehaviorReturn | None:
        try:
            value = self._eval_expression(statement.expression.text, env)
        except GwtError as exc:
            raise _with_line_context(statement.expression, exc) from exc

        selector = statement.cases[0].selector if statement.cases else "kind"
        if selector == "kind":
            if not isinstance(value, dict):
                raise GwtError(f"line {statement.expression.number}: DEPENDING ON requires a record value")
            record = cast(dict[str, Any], value)
            kind = record.get("kind")
            if not isinstance(kind, str):
                raise GwtError(f"line {statement.expression.number}: DEPENDING ON record has no kind")
            for case in statement.cases:
                if case.name == kind:
                    return self._run_body(case.body, env)
            if statement.else_body:
                return self._run_body(statement.else_body, env)
            raise GwtError(f"line {statement.expression.number}: DEPENDING ON has no branch for kind: {kind}")

        for case in statement.cases:
            if _value_matches_literal(value, case.literal):
                return self._run_body(case.body, env)
        if statement.else_body:
            return self._run_body(statement.else_body, env)
        raise GwtError(
            f"line {statement.expression.number}: "
            f"DEPENDING ON has no branch for value: {_literal_value_text(value)}"
        )

    def _match_action(self, action: Action, call: list[str], caller_env: dict[str, Any]) -> dict[str, Any] | None:
        if len(action.signature) != len(call):
            return None

        env: dict[str, Any] = {}
        for index, (pattern, actual) in enumerate(zip(action.signature, call)):
            parameter_name = _signature_parameter_name(action.signature, index, pattern)
            if parameter_name is None:
                if pattern != actual:
                    return None
            else:
                env[parameter_name] = self._argument_value(actual, caller_env)
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

    def _evaluate_condition(
        self,
        text: str,
        env: dict[str, Any],
        line: Line | None = None,
        *,
        trace_kind: str = "condition",
    ) -> bool:
        expression = _condition_to_expression(text)
        value = self._eval_expression(expression, env)
        if not isinstance(value, bool):
            raise GwtError(f"condition must evaluate to a boolean: {text}")
        if self.tracer is not None:
            if trace_kind == "assertion":
                self.tracer.record_assertion(text=text, result=value, line=line)
            else:
                self.tracer.record_condition(text=text, result=value, line=line)
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
            if env_value is not _MISSING:
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
        env_value = self._get_env_path(path, env)
        if env_value is not _MISSING:
            return env_value
        resolved = self._resolve_path(path, env)
        current: object = self.state
        for part in resolved.split("."):
            if not _is_runtime_map(current) or part not in current:
                raise GwtError(f"unknown path: {resolved}")
            current = current[part]
        return current

    def _set_path(self, path: str, value: Any, env: dict[str, Any], line: Line | None = None) -> None:
        resolved = self._resolve_path(path, env)
        parts = resolved.split(".")
        if not all(parts):
            raise GwtError(f"invalid path: {path}")

        if parts[0] in env and not isinstance(env[parts[0]], PathRef):
            value = self._validate_assignment(resolved, value, line)
            if len(parts) == 1:
                env[parts[0]] = value
                if self.tracer is not None:
                    self.tracer.record_local_change(path=resolved, line=line)
                return
            current: object = env[parts[0]]
            for part in parts[1:-1]:
                if not isinstance(current, dict):
                    raise GwtError(f"cannot create nested path under scalar: {part}")
                current_map = cast(dict[str, Any], current)
                next_value: Any = current_map.setdefault(part, {})
                if not isinstance(next_value, dict):
                    raise GwtError(f"cannot create nested path under scalar: {part}")
                current = cast(dict[str, Any], next_value)
            if not isinstance(current, dict):
                raise GwtError(f"cannot create nested path under scalar: {parts[-2]}")
            cast(dict[str, Any], current)[parts[-1]] = value
            if self.tracer is not None:
                self.tracer.record_local_change(path=resolved, line=line)
            return

        value = self._validate_assignment(resolved, value, line)
        change = state_change_for_set(self.state, resolved, value) if self.tracer is not None else None

        current_map = self.state
        for part in parts[:-1]:
            next_value = current_map.get(part, _MISSING)
            if next_value is _MISSING:
                next_map: dict[str, Any] = {}
                current_map[part] = next_map
                current_map = next_map
                continue
            if not isinstance(next_value, dict):
                raise GwtError(f"cannot create nested path under scalar: {part}")
            current_map = cast(dict[str, Any], next_value)
        current_map[parts[-1]] = value
        if self.tracer is not None:
            if change is not None:
                self.tracer.record_state_change(path=resolved, change=change, line=line)

    def _path_exists(self, path: str) -> bool:
        current: object = self.state
        for part in path.split("."):
            if not _is_runtime_map(current) or part not in current:
                return False
            current = current[part]
        return True

    def _get_env_path(self, path: str, env: dict[str, Any]) -> Any:
        parts = path.split(".")
        if not parts or parts[0] not in env:
            return _MISSING
        current: object = env[parts[0]]
        if isinstance(current, PathRef):
            return _MISSING
        for part in parts[1:]:
            if not isinstance(current, dict) or part not in current:
                return _MISSING
            current = cast(dict[str, Any], current)[part]
        return current


class ExpressionScope:
    def __init__(self, runtime: Runtime, env: dict[str, Any]) -> None:
        self.runtime = runtime
        self.env = env

    def resolve_name(self, name: str) -> Any:
        return self.runtime._resolve_name(name, self.env)


def _body_line_range(body: list[Any]) -> tuple[int | None, int | None]:
    lines: list[int] = []
    for statement in body:
        lines.extend(_statement_line_numbers(statement))
    if not lines:
        return None, None
    return min(lines), max(lines)


def _statement_line_numbers(statement: Any) -> list[int]:
    if isinstance(statement, Line):
        return [statement.number]
    if isinstance(statement, RecordValidation):
        return [statement.line.number]
    if isinstance(statement, TableAssignment):
        return [statement.line.number]
    if isinstance(statement, VariantAssignment):
        return [statement.line.number]
    if isinstance(statement, RequestCall):
        return [statement.line.number]
    if isinstance(statement, IfBlock):
        return [
            statement.condition.number,
            *_body_line_numbers(statement.then_body),
            *_body_line_numbers(statement.else_body),
        ]
    if isinstance(statement, ForBlock):
        header = statement.header_line or statement.name_line or statement.iterable
        return [header.number, *_body_line_numbers(statement.body)]
    if isinstance(statement, FindBlock):
        header = statement.header_line or statement.name_line or statement.iterable
        return [header.number, *_body_line_numbers(statement.body), *_body_line_numbers(statement.else_body)]
    if isinstance(statement, DecisionBlock):
        return [
            statement.header_line.number,
            *[branch.condition.number for branch in statement.branches],
            *_body_line_numbers([body for branch in statement.branches for body in branch.body]),
            statement.else_line.number,
            *_body_line_numbers(statement.else_body),
        ]
    if isinstance(statement, MatchBlock):
        header = statement.header_line or statement.expression
        return [
            header.number,
            *[case.line.number for case in statement.cases],
            *_body_line_numbers([body for case in statement.cases for body in case.body]),
            *_body_line_numbers(statement.else_body),
        ]
    return []


def _body_line_numbers(body: list[Any]) -> list[int]:
    lines: list[int] = []
    for statement in body:
        lines.extend(_statement_line_numbers(statement))
    return lines


def _logical_lines(source: str, filename: str) -> list[Line]:
    lines: list[Line] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        code, _comment = _split_comment_outside_string(raw)
        without_comment = code.rstrip()
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


def _looks_like_removed_request_contract(statement: str) -> bool:
    if " is " not in statement:
        return False
    path, value_type = statement.split(" is ", 1)
    value_type = value_type.strip()
    return _is_path(path.strip()) and _looks_like_type_name(value_type)


def _looks_like_type_name(value_type: str) -> bool:
    if not _is_type_syntax(value_type):
        return False
    if value_type in RECORD_TYPES or value_type.startswith("list<"):
        return True
    if "|" in value_type:
        return True
    return bool(value_type and value_type[0].isupper())


def _parse_named_request(
    lines: list[Line],
    index: int,
    filename: str,
    records: dict[str, RecordDefinition],
    type_aliases: dict[str, TypeAliasDefinition],
    *,
    allow_unknown_records: bool = False,
) -> tuple[NamedRequest, int]:
    header = lines[index]
    name = header.text.removeprefix("REQUEST ").strip()
    if not name:
        raise GwtError(f"{filename}:{header.number}: REQUEST requires a name")
    if _looks_like_removed_request_contract(name):
        raise GwtError(
            f"{filename}:{header.number}: top-level REQUEST contracts were removed; "
            "use REQUEST <name> with indented GIVEN bindings"
        )
    if index + 1 >= len(lines) or _indent_width(lines[index + 1].text) < 2:
        raise GwtError(f"{filename}:{header.number}: REQUEST {name} requires an indented body")

    body_start = index + 1
    body_end = body_start
    while body_end < len(lines) and _indent_width(lines[body_end].text) >= 2:
        body_end += 1

    body_lines = [_dedent_line(line, 2) for line in lines[body_start:body_end]]
    request = NamedRequest(name, _derived_line(header, name, len("REQUEST ")))
    _parse_named_request_body(
        request,
        body_lines,
        filename,
        records,
        type_aliases,
        allow_unknown_records=allow_unknown_records,
    )
    if not request.whens:
        raise GwtError(f"{filename}:{header.number}: REQUEST {name} requires at least one WHEN")
    return request, body_end


def _dedent_line(line: Line, width: int) -> Line:
    text = line.text[width:] if len(line.text) >= width else ""
    return Line(line.number, text, line.filename, line.column, max(1, len(text.strip())))


def _parse_named_request_body(
    request: NamedRequest,
    lines: list[Line],
    filename: str,
    records: dict[str, RecordDefinition],
    type_aliases: dict[str, TypeAliasDefinition],
    *,
    allow_unknown_records: bool = False,
) -> None:
    index = 0
    last_keyword: str | None = None
    while index < len(lines):
        line = lines[index]
        if _indent_width(line.text) != 0:
            raise GwtError(f"{filename}:{line.number}: REQUEST body statement is indented too far")
        text = line.text
        if text.startswith("AND "):
            if last_keyword not in {"GIVEN", "WHEN", "OUTPUT", "THEN"}:
                raise GwtError(f"{filename}:{line.number}: AND has no previous request statement")
            text = f"{last_keyword} {text.removeprefix('AND ').strip()}"

        if text.startswith("GIVEN "):
            index = _parse_request_given(
                request,
                text,
                lines,
                index,
                filename,
                records,
                type_aliases,
                allow_unknown_records=allow_unknown_records,
            )
            last_keyword = "GIVEN"
            continue

        if text.startswith("WHEN "):
            call_text = text.removeprefix("WHEN ").strip()
            if not call_text:
                raise GwtError(f"{filename}:{line.number}: REQUEST WHEN requires a behavior call")
            if index + 1 < len(lines) and _indent_width(lines[index + 1].text) > 0:
                raise GwtError(
                    f"{filename}:{line.number}: REQUEST WHEN cannot define behavior; define block-form WHEN at top level"
                )
            request.whens.append(_derived_line(line, call_text, len("WHEN ")))
            index += 1
            last_keyword = "WHEN"
            continue

        if text.startswith("OUTPUT "):
            binding = _parse_contract_binding("OUTPUT", text, filename, line)
            if binding.path in request.outputs:
                raise GwtError(f"{filename}:{line.number}: OUTPUT already declares: {binding.path}")
            request.outputs[binding.path] = binding
            index += 1
            last_keyword = "OUTPUT"
            continue

        if text.startswith("THEN "):
            statement = text.removeprefix("THEN ").strip()
            if _is_record_header(statement):
                index += 1
                expanded, index = _expand_record_block(statement, lines, index, filename)
                request.thens.extend(expanded)
            else:
                request.thens.append(_derived_line(line, statement, len("THEN ")))
                index += 1
            last_keyword = "THEN"
            continue

        if text.startswith("REQUEST "):
            raise GwtError(f"{filename}:{line.number}: nested REQUEST calls are not allowed inside a REQUEST block")
        raise GwtError(f"{filename}:{line.number}: unknown REQUEST body form: {text}")


def _parse_request_given(
    request: NamedRequest,
    text: str,
    lines: list[Line],
    index: int,
    filename: str,
    records: dict[str, RecordDefinition],
    type_aliases: dict[str, TypeAliasDefinition],
    *,
    allow_unknown_records: bool = False,
) -> int:
    line = lines[index]
    statement = text.removeprefix("GIVEN ").strip()
    has_body = index + 1 < len(lines) and _indent_width(lines[index + 1].text) > 0
    if _is_table_header(statement):
        if not has_body:
            raise GwtError(f"{filename}:{line.number}: GIVEN table requires a body")
        index += 1
        table, index = _parse_table_assignment(statement, lines, index, filename, line)
        request.givens.append(table)
        return index
    if _is_variant_assignment_header(statement):
        if not has_body:
            raise GwtError(f"{filename}:{line.number}: one-of setup requires a body")
        index += 1
        assignment, index = _parse_variant_assignment(statement, lines, index, filename, line)
        request.givens.append(assignment)
        return index
    if _is_typed_record_header(statement):
        if has_body:
            index += 1
            expanded, index, validation = _expand_typed_record_block(
                statement,
                lines,
                index,
                filename,
                records,
                type_aliases,
                allow_unknown_records=allow_unknown_records,
            )
            request.givens.extend(expanded)
            request.givens.append(validation)
            return index
        binding = _parse_contract_binding("REQUEST", f"REQUEST {statement}", filename, line)
        if binding.path in request.inputs:
            raise GwtError(f"{filename}:{line.number}: REQUEST input already declares: {binding.path}")
        request.inputs[binding.path] = binding
        return index + 1
    if _is_record_header(statement):
        if not has_body:
            raise GwtError(f"{filename}:{line.number}: record block requires a body")
        index += 1
        expanded, index = _expand_record_block(statement, lines, index, filename)
        request.givens.extend(expanded)
        return index
    if not has_body and " is " in statement:
        _path, value_type = statement.split(" is ", 1)
        if _is_type_syntax(value_type.strip()):
            binding = _parse_contract_binding("REQUEST", f"REQUEST {statement}", filename, line)
            if binding.path in request.inputs:
                raise GwtError(f"{filename}:{line.number}: REQUEST input already declares: {binding.path}")
            request.inputs[binding.path] = binding
            return index + 1
    request.givens.append(_derived_line(line, statement, len("GIVEN ")))
    return index + 1


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
        if text.startswith("WHEN ") and not (
            text.startswith("WHEN the kind is ") or text.startswith("WHEN the value is ")
        ):
            raise GwtError(f"{filename}:{line.number}: DECIDE branch WHEN can only appear inside DECIDE")
        if text.startswith("WHEN the kind is ") or text.startswith("WHEN the value is "):
            raise GwtError(f"{filename}:{line.number}: WHEN the kind/value is can only appear inside DEPENDING ON")
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
            name, expression, where = _parse_for_header(text, filename, line.number)
            index += 1
            loop_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
            if not loop_body:
                raise GwtError(f"{filename}:{line.number}: FOR requires a body")
            where_line = _derived_line(line, where, text.find(where)) if where is not None else None
            body.append(
                ForBlock(
                    name,
                    _derived_line(line, expression, text.find(expression)),
                    loop_body,
                    _derived_line(line, name, len("FOR ")),
                    _derived_line(line, text, 0),
                    where_line,
                )
            )
            last_body_keyword = None
            continue

        if text.startswith("FIND "):
            name, expression, condition = _parse_find_block_header(text, filename, line.number)
            index += 1
            find_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
            if not find_body:
                raise GwtError(f"{filename}:{line.number}: FIND requires a body")
            if index >= len(lines) or _indent_width(lines[index].text) != indent or lines[index].text.strip() != "ELSE":
                raise GwtError(f"{filename}:{line.number}: FIND requires an ELSE block")
            else_line = lines[index]
            index += 1
            else_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
            if not else_body:
                raise GwtError(f"{filename}:{else_line.number}: ELSE requires a body")
            body.append(
                FindBlock(
                    name,
                    _derived_line(line, expression, text.find(expression)),
                    _derived_line(line, condition, text.find(condition)),
                    find_body,
                    else_body,
                    _derived_line(line, name, len("FIND ")),
                    _derived_line(line, text, 0),
                )
            )
            last_body_keyword = None
            continue

        if text == "DECIDE":
            index += 1
            branches, else_body, else_line, index = _parse_decision_block(lines, index, filename, indent + 2)
            if not branches:
                raise GwtError(f"{filename}:{line.number}: DECIDE requires WHEN branches")
            body.append(
                DecisionBlock(
                    branches,
                    else_body,
                    _derived_line(line, text, 0),
                    else_line,
                )
            )
            last_body_keyword = None
            continue

        if text.startswith("DECIDE "):
            raise GwtError(f"{filename}:{line.number}: DECIDE does not take a condition")

        if text.startswith("DEPENDING ON "):
            expression = text.removeprefix("DEPENDING ON ").strip()
            if not expression:
                raise GwtError(f"{filename}:{line.number}: DEPENDING ON requires a value")
            index += 1
            cases, else_body, else_line, index = _parse_depending_block(lines, index, filename, indent + 2)
            if not cases:
                raise GwtError(f"{filename}:{line.number}: DEPENDING ON requires WHEN the kind/value is branches")
            body.append(
                MatchBlock(
                    _derived_line(line, expression, len("DEPENDING ON ")),
                    cases,
                    else_body,
                    _derived_line(line, text, 0),
                    else_line,
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


def _parse_decision_block(
    lines: list[Line], index: int, filename: str, indent: int
) -> tuple[list[DecisionBranch], list[Any], Line, int]:
    branches: list[DecisionBranch] = []
    else_body: list[Any] = []
    else_line: Line | None = None
    seen_else = False

    while index < len(lines):
        line = lines[index]
        line_indent = _indent_width(line.text)
        text = line.text.strip()
        if line_indent < indent:
            break
        if line_indent > indent:
            raise GwtError(f"{filename}:{line.number}: DECIDE branch is indented too far")

        if text == "ELSE":
            if seen_else:
                raise GwtError(f"{filename}:{line.number}: DECIDE already has ELSE")
            seen_else = True
            else_line = _derived_line(line, text, 0)
            index += 1
            else_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
            if not else_body:
                raise GwtError(f"{filename}:{line.number}: ELSE requires a body")
            continue

        if not text.startswith("WHEN "):
            raise GwtError(f"{filename}:{line.number}: DECIDE expects WHEN condition or ELSE")
        if seen_else:
            raise GwtError(f"{filename}:{line.number}: DECIDE WHEN cannot follow ELSE")
        condition = text.removeprefix("WHEN ").strip()
        if not condition:
            raise GwtError(f"{filename}:{line.number}: DECIDE WHEN requires a condition")
        index += 1
        branch_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
        if not branch_body:
            raise GwtError(f"{filename}:{line.number}: DECIDE WHEN requires a body")
        branches.append(DecisionBranch(_derived_line(line, condition, len("WHEN ")), branch_body))

    if else_line is None:
        line = lines[index - 1] if index > 0 else Line(1, "", filename)
        raise GwtError(f"{filename}:{line.number}: DECIDE requires an ELSE block")
    return branches, else_body, else_line, index


def _parse_depending_block(
    lines: list[Line], index: int, filename: str, indent: int
) -> tuple[list[MatchCase], list[Any], Line | None, int]:
    cases: list[MatchCase] = []
    else_body: list[Any] = []
    else_line: Line | None = None
    seen_else = False
    selector: str | None = None

    while index < len(lines):
        line = lines[index]
        line_indent = _indent_width(line.text)
        text = line.text.strip()
        if line_indent < indent:
            break
        if line_indent > indent:
            raise GwtError(f"{filename}:{line.number}: DEPENDING ON branch is indented too far")

        if text == "ELSE":
            if seen_else:
                raise GwtError(f"{filename}:{line.number}: DEPENDING ON already has ELSE")
            seen_else = True
            else_line = _derived_line(line, text, 0)
            index += 1
            else_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
            if not else_body:
                raise GwtError(f"{filename}:{line.number}: ELSE requires a body")
            continue

        case = _parse_depending_case_header(text, filename, line.number)
        if case is None:
            raise GwtError(
                f"{filename}:{line.number}: "
                "DEPENDING ON expects 'WHEN the kind is name', 'WHEN the value is literal', or ELSE"
            )
        if seen_else:
            raise GwtError(f"{filename}:{line.number}: WHEN the kind/value is cannot follow ELSE")
        if selector is None:
            selector = case.selector
        elif selector != case.selector:
            raise GwtError(f"{filename}:{line.number}: DEPENDING ON cannot mix kind and value branches")
        index += 1
        case_body, index = _parse_behavior_block(lines, index, filename, indent + 2)
        if not case_body:
            raise GwtError(f"{filename}:{line.number}: WHEN the kind/value is requires a body")
        cases.append(
            MatchCase(
                case.name,
                case_body,
                case.line,
                case.selector,
                case.literal,
            )
        )

    return cases, else_body, else_line, index


def _parse_depending_case_header(text: str, filename: str, line_number: int) -> MatchCase | None:
    match = re.match(r"^WHEN the kind is ([A-Za-z_][A-Za-z0-9_]*)$", text)
    if match is not None:
        case_name = match.group(1)
        if not _is_local_name(case_name):
            raise GwtError(f"{filename}:{line_number}: WHEN the kind is requires a simple name")
        return MatchCase(
            case_name,
            [],
            Line(line_number, case_name, filename, text.find(case_name) + 1, len(case_name)),
            "kind",
            None,
        )

    prefix = "WHEN the value is "
    if not text.startswith(prefix):
        return None
    literal_text = text.removeprefix(prefix).strip()
    if not literal_text:
        raise GwtError(f"{filename}:{line_number}: WHEN the value is requires a literal")
    try:
        expression = parse_expression(literal_text)
    except GwtError as exc:
        raise GwtError(f"{filename}:{line_number}: WHEN the value is requires a literal: {exc}") from exc
    if not isinstance(expression, Literal) or isinstance(expression.value, list):
        raise GwtError(f"{filename}:{line_number}: WHEN the value is requires a literal")
    return MatchCase(
        _literal_value_text(expression.value),
        [],
        Line(line_number, literal_text, filename, text.find(literal_text) + 1, len(literal_text)),
        "value",
        expression.value,
    )


def _parse_record(lines: list[Line], index: int, filename: str) -> tuple[RecordDefinition, int]:
    header = lines[index]
    tokens = _tokens(header.text, filename, header.number)
    if len(tokens) != 2:
        raise GwtError(f"{filename}:{header.number}: RECORD expects one name")
    keyword = tokens[0]
    if keyword != "RECORD":
        raise GwtError(f"{filename}:{header.number}: RECORD expects one name")
    name = tokens[1]
    if not _is_record_type_name(name):
        raise GwtError(f"{filename}:{header.number}: RECORD name must start with an uppercase letter")
    fields, field_lines, index = _parse_record_fields(lines, index + 1, filename, header.number)
    return RecordDefinition(
        name,
        fields,
        header.number,
        header.filename,
        header.column + len(keyword) + 1,
        len(name),
        field_lines,
    ), index


def _parse_type_alias(line: Line, filename: str) -> TypeAliasDefinition:
    match = re.match(r"^TYPE\s+([A-Z][A-Za-z0-9_]*)\s+is\s+(.+)$", line.text)
    if match is None:
        raise GwtError(f"{filename}:{line.number}: TYPE expects 'TYPE Name is Type'")
    name = match.group(1)
    value_type = match.group(2).strip()
    if not _is_type_syntax(value_type):
        raise GwtError(f"{filename}:{line.number}: invalid TYPE target: {value_type}")
    if value_type == name:
        raise GwtError(f"{filename}:{line.number}: TYPE cannot alias itself: {name}")
    return TypeAliasDefinition(
        name,
        value_type,
        line.number,
        line.filename,
        line.column + len("TYPE "),
        len(name),
    )


def _parse_variant(lines: list[Line], index: int, filename: str) -> tuple[VariantDefinition, int]:
    header = lines[index]
    match = re.match(r"^RECORD\s+([A-Z][A-Za-z0-9_]*)\s+is\s+one\s+of$", header.text)
    if match is None:
        raise GwtError(f"{filename}:{header.number}: RECORD one-of expects 'RECORD Name is one of'")
    name = match.group(1)
    if index + 1 >= len(lines) or _indent_width(lines[index + 1].text) != 2:
        raise GwtError(f"{filename}:{header.number}: RECORD one-of requires kinds")

    cases: dict[str, VariantCaseDefinition] = {}
    index += 1
    while index < len(lines):
        line = lines[index]
        indent = _indent_width(line.text)
        if indent < 2:
            break
        if indent != 2:
            raise GwtError(f"{filename}:{line.number}: RECORD one-of kind is indented too far")

        case_text = line.text.strip()
        if not case_text.endswith(":") or case_text == ":":
            raise GwtError(f"{filename}:{line.number}: RECORD one-of kind must use 'kind:'")
        case_name = case_text[:-1].strip()
        if not _is_local_name(case_name):
            raise GwtError(f"{filename}:{line.number}: RECORD one-of kind must be a simple name")
        if case_name in cases:
            raise GwtError(f"{filename}:{line.number}: RECORD one-of kind already defined: {case_name}")

        fields, field_lines, index = _parse_variant_case_fields(lines, index + 1, filename, line.number)
        cases[case_name] = VariantCaseDefinition(
            case_name,
            fields,
            line.number,
            line.filename,
            line.column,
            len(case_name),
            field_lines,
        )

    if not cases:
        raise GwtError(f"{filename}:{header.number}: RECORD one-of requires kinds")
    return VariantDefinition(
        name,
        cases,
        header.number,
        header.filename,
        header.column + len("RECORD "),
        len(name),
    ), index


def _parse_variant_case_fields(
    lines: list[Line], index: int, filename: str, case_line: int
) -> tuple[dict[str, str], dict[str, Line], int]:
    if index >= len(lines) or _indent_width(lines[index].text) != 4:
        raise GwtError(f"{filename}:{case_line}: RECORD one-of kind requires fields")

    fields: dict[str, str] = {}
    field_lines: dict[str, Line] = {}
    while index < len(lines):
        line = lines[index]
        indent = _indent_width(line.text)
        if indent < 4:
            break
        if indent > 4:
            raise GwtError(f"{filename}:{line.number}: RECORD one-of field is indented too far")
        field_text = line.text.strip()
        if ":" not in field_text:
            raise GwtError(f"{filename}:{line.number}: RECORD one-of field must use 'name: type'")
        field, value_type = field_text.split(":", 1)
        field = field.strip()
        value_type = value_type.strip()
        if not field:
            raise GwtError(f"{filename}:{line.number}: RECORD one-of field requires a name")
        if field == "kind":
            raise GwtError(f"{filename}:{line.number}: RECORD one-of field 'kind' is automatic")
        if not _is_local_name(field):
            raise GwtError(f"{filename}:{line.number}: RECORD one-of field must be a simple name")
        if not value_type:
            raise GwtError(f"{filename}:{line.number}: RECORD one-of field requires a type")
        if not _is_type_syntax(value_type):
            raise GwtError(f"{filename}:{line.number}: invalid RECORD one-of field type: {value_type}")
        if field in fields:
            raise GwtError(f"{filename}:{line.number}: RECORD one-of field already defined: {field}")
        fields[field] = value_type
        field_lines[field] = _derived_line(line, field, 0)
        index += 1

    if not fields:
        raise GwtError(f"{filename}:{case_line}: RECORD one-of kind requires typed fields")
    return fields, field_lines, index


def _parse_record_fields(
    lines: list[Line], index: int, filename: str, record_line: int
) -> tuple[dict[str, str], dict[str, Line], int]:
    if index >= len(lines) or not lines[index].text.startswith("  "):
        raise GwtError(f"{filename}:{record_line}: RECORD requires fields")

    fields: dict[str, str] = {}
    field_lines: dict[str, Line] = {}
    parents: list[str] = []

    while index < len(lines) and lines[index].text.startswith("  "):
        line = lines[index]
        indent = _indent_width(line.text)
        if indent % 2 != 0:
            raise GwtError(f"{filename}:{line.number}: RECORD indentation must use two spaces")

        depth = indent // 2 - 1
        if depth < 0:
            break
        if depth > len(parents):
            raise GwtError(f"{filename}:{line.number}: RECORD field is indented too far")

        field_text = line.text.strip()
        if ":" not in field_text:
            raise GwtError(f"{filename}:{line.number}: RECORD field must use 'name: type'")
        field, value_type = field_text.split(":", 1)
        field = field.strip()
        value_type = value_type.strip()
        if not field:
            raise GwtError(f"{filename}:{line.number}: RECORD field requires a name")

        parent = "" if depth == 0 else parents[depth - 1]
        path = field if parent == "" else f"{parent}.{field}"
        parents = parents[:depth]
        parents.append(path)

        if value_type:
            if not _is_type_syntax(value_type):
                raise GwtError(f"{filename}:{line.number}: invalid RECORD field type: {value_type}")
            if path in fields:
                raise GwtError(f"{filename}:{line.number}: RECORD field already defined: {path}")
            fields[path] = value_type
            field_lines[path] = _derived_line(line, field, 0)
        elif index + 1 >= len(lines) or _indent_width(lines[index + 1].text) <= indent:
            raise GwtError(f"{filename}:{line.number}: nested RECORD field requires fields")
        index += 1

    if not fields:
        raise GwtError(f"{filename}:{record_line}: RECORD requires typed fields")
    return fields, field_lines, index


def _parse_for_header(text: str, filename: str, line_number: int) -> tuple[str, str, str | None]:
    header = text.removeprefix("FOR ").strip()
    if " in " not in header:
        raise GwtError(f"{filename}:{line_number}: FOR expects 'name in expression'")
    name, expression = header.split(" in ", 1)
    name = name.strip()
    expression = expression.strip()
    expression, where = _split_where_clause(expression)
    if where is not None:
        if not where:
            raise GwtError(f"{filename}:{line_number}: FOR WHERE requires a condition")
    if not _is_local_name(name):
        raise GwtError(f"{filename}:{line_number}: FOR requires a simple local name")
    if not expression:
        raise GwtError(f"{filename}:{line_number}: FOR requires an iterable expression")
    return name, expression, where


def _parse_find_block_header(text: str, filename: str, line_number: int) -> tuple[str, str, str]:
    header = text.removeprefix("FIND ").strip()
    if " in " not in header:
        raise GwtError(f"{filename}:{line_number}: FIND expects 'name in expression WHERE condition'")
    name, expression = header.split(" in ", 1)
    name = name.strip()
    expression = expression.strip()
    expression, condition = _split_where_clause(expression)
    if condition is None:
        raise GwtError(f"{filename}:{line_number}: FIND requires a WHERE condition")
    if not condition:
        raise GwtError(f"{filename}:{line_number}: FIND WHERE requires a condition")
    if not _is_local_name(name):
        raise GwtError(f"{filename}:{line_number}: FIND requires a simple local name")
    if not expression:
        raise GwtError(f"{filename}:{line_number}: FIND requires an iterable expression")
    return name, expression, condition


def _split_where_clause(expression: str) -> tuple[str, str | None]:
    match = re.search(r"\s+WHERE\s+", expression, re.IGNORECASE)
    if match is None:
        return expression, None
    return expression[: match.start()].strip(), expression[match.end() :].strip()


def _parse_import(
    text: str,
    line: Line,
    filename: str,
    importing: set[Path],
    import_policy: ImportPolicy | None,
) -> Program:
    tokens = _tokens(text, filename, line.number)
    if len(tokens) != 2:
        raise GwtError(f"{filename}:{line.number}: USE expects one quoted path")

    base_dir = Path.cwd() if filename == "<source>" else Path(filename).resolve().parent
    raw_import_path = Path(tokens[1])
    import_path = raw_import_path
    if not import_path.is_absolute():
        import_path = base_dir / import_path
    import_path = import_path.resolve()
    if import_policy is not None:
        import_policy.validate(raw_import_path, import_path, filename, line.number)

    if import_path in importing:
        raise GwtError(f"{filename}:{line.number}: circular USE import: {import_path}")
    if not import_path.exists():
        raise GwtError(f"{filename}:{line.number}: USE file not found: {import_path}")
    if not import_path.is_file():
        raise GwtError(f"{filename}:{line.number}: USE path is not a file: {import_path}")

    importing.add(import_path)
    try:
        return parse_program(
            import_path.read_text(),
            str(import_path),
            importing,
            import_policy=import_policy,
        )
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
        raise GwtError(f"{filename}:{line_number}: table assignment expects 'path are' or 'path are RecordName'")
    item_type = match.group("item_type")
    if item_type is not None and not _is_record_type_name(item_type):
        raise GwtError(f"{filename}:{line_number}: GIVEN table type must be a record name")
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
        if isinstance(line, RecordValidation):
            substituted.append(line)
        elif isinstance(line, RequestCall):
            substituted.append(
                RequestCall(
                    _substitute_placeholders(line.name, values, line.line.number),
                    Line(
                        line.line.number,
                        _substitute_placeholders(line.line.text, values, line.line.number),
                        line.line.filename,
                        line.line.column,
                        line.line.length,
                    ),
                )
            )
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
        elif isinstance(line, VariantAssignment):
            substituted.append(
                VariantAssignment(
                    line.path,
                    line.variant_name,
                    line.case_name,
                    {
                        field: _substitute_placeholders(value, values, line.line.number)
                        for field, value in line.fields.items()
                    },
                    line.line,
                    line.field_lines,
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


def _is_record_one_of_header(text: str) -> bool:
    return re.match(r"^RECORD\s+[A-Z][A-Za-z0-9_]*\s+is\s+one\s+of$", text) is not None


def _is_variant_assignment_header(text: str) -> bool:
    return (
        re.match(
            r"^[A-Za-z_][A-Za-z0-9_.]* contains an? [A-Z][A-Za-z0-9_]* of kind [A-Za-z_][A-Za-z0-9_]*$",
            text,
        )
        is not None
    )


def _is_typed_record_header(text: str) -> bool:
    return re.match(r"^[A-Za-z_][A-Za-z0-9_.]* is [A-Z][A-Za-z0-9_]*$", text) is not None


def _parse_variant_assignment(
    header: str,
    lines: list[Line],
    index: int,
    filename: str,
    header_line: Line,
) -> tuple[VariantAssignment, int]:
    match = re.match(
        r"^(?P<path>[A-Za-z_][A-Za-z0-9_.]*) contains an? (?P<variant>[A-Z][A-Za-z0-9_]*) "
        r"of kind (?P<case>[A-Za-z_][A-Za-z0-9_]*)$",
        header,
    )
    if match is None:
        raise GwtError(
            f"{filename}:{header_line.number}: one-of setup expects 'path contains a RecordName of kind name'"
        )
    if index >= len(lines) or not lines[index].text.startswith("  "):
        raise GwtError(f"{filename}:{header_line.number}: one-of setup requires fields")

    fields: dict[str, str] = {}
    field_lines: dict[str, Line] = {}
    while index < len(lines) and lines[index].text.startswith("  "):
        line = lines[index]
        if _indent_width(line.text) != 2:
            raise GwtError(f"{filename}:{line.number}: one-of setup fields must use two spaces")
        field_text = line.text.strip()
        if ":" not in field_text:
            raise GwtError(f"{filename}:{line.number}: one-of setup field must use 'name: value'")
        field, value = field_text.split(":", 1)
        field = field.strip()
        value = value.strip()
        if not field:
            raise GwtError(f"{filename}:{line.number}: one-of setup field requires a name")
        if field == "kind":
            raise GwtError(f"{filename}:{line.number}: one-of setup field 'kind' is automatic")
        if not _is_local_name(field):
            raise GwtError(f"{filename}:{line.number}: one-of setup field must be a simple name")
        if not value:
            raise GwtError(f"{filename}:{line.number}: one-of setup field requires a value")
        if field in fields:
            raise GwtError(f"{filename}:{line.number}: one-of setup field already defined: {field}")
        fields[field] = value
        field_lines[field] = _derived_line(line, field, 0)
        index += 1

    return (
        VariantAssignment(
            match.group("path"),
            match.group("variant"),
            match.group("case"),
            fields,
            _derived_line(header_line, header, len("GIVEN ")),
            field_lines,
        ),
        index,
    )


def _expand_typed_record_block(
    header: str,
    lines: list[Line],
    index: int,
    filename: str,
    records: dict[str, RecordDefinition],
    type_aliases: dict[str, TypeAliasDefinition],
    *,
    allow_unknown_records: bool = False,
) -> tuple[list[Line], int, RecordValidation]:
    header_line = lines[index - 1]
    path, record_name = header.split(" is ", 1)
    path = path.strip()
    record_name = record_name.strip()
    resolved_name = _resolve_type_alias(record_name, type_aliases)
    if resolved_name not in records and not allow_unknown_records:
        raise GwtError(f"{filename}:{header_line.number}: unknown record: {record_name}")
    expanded, index = _expand_record_block(f"{path} is", lines, index, filename)
    return expanded, index, RecordValidation(path, record_name, header_line)


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


def _is_record_type_name(text: str) -> bool:
    return bool(re.match(r"^[A-Z][A-Za-z0-9_]*$", text))


def _is_type_syntax(value_type: str) -> bool:
    value_type = value_type.strip()
    if value_type in RECORD_TYPES or _is_record_type_name(value_type):
        return True
    if _literal_union_values(value_type) is not None:
        return True
    item_type = _list_item_type(value_type)
    if item_type is None:
        return False
    return _is_type_syntax(item_type)


def _list_item_type(value_type: str) -> str | None:
    match = LIST_TYPE_PATTERN.match(value_type.strip())
    if match is None:
        return None
    item_type = match.group(1).strip()
    return item_type or None


def _resolve_type_alias(
    value_type: str,
    aliases: dict[str, TypeAliasDefinition],
    seen: set[str] | None = None,
) -> str:
    seen = set() if seen is None else seen
    current = value_type.strip()
    while current in aliases:
        if current in seen:
            raise GwtError(f"cyclic TYPE alias: {current}")
        seen.add(current)
        current = aliases[current].value_type
    item_type = _list_item_type(current)
    if item_type is not None:
        return f"list<{_resolve_type_alias(item_type, aliases, seen)}>"
    return current


def _is_builtin_statement(tokens: list[str], text: str) -> bool:
    if not tokens:
        return False
    command = tokens[0]
    if command in {"set", "add", "subtract", "print"}:
        return True
    if command == "append":
        return "to" in tokens
    if command in {"count", "sum"}:
        return "into" in tokens
    if command == "find":
        return (
            re.match(
                r"^find (optional )?[A-Za-z_][A-Za-z0-9_]* in .+ where .+ into [A-Za-z_][A-Za-z0-9_.]*$",
                text,
                re.IGNORECASE,
            )
            is not None
        )
    if command == "exists":
        return _parse_exists_statement(text) is not None
    return False


def _signature_parameters(signature: list[str]) -> list[str]:
    parameters: list[str] = []
    for index, token in enumerate(signature):
        parameter_name = _signature_parameter_name(signature, index, token)
        if parameter_name is not None:
            parameters.append(parameter_name)
    return parameters


def _signature_shape(signature: list[str]) -> tuple[str, ...]:
    shape: list[str] = []
    for index, token in enumerate(signature):
        shape.append("_" if _signature_parameter_name(signature, index, token) is not None else token)
    return tuple(shape)


def _signature_matches(signature: list[str], call: list[str]) -> bool:
    if len(signature) != len(call):
        return False
    for index, (pattern, actual) in enumerate(zip(signature, call)):
        if _signature_parameter_name(signature, index, pattern) is None and pattern != actual:
            return False
    return True


def _unknown_request_message(name: str, request_names: Iterable[str]) -> str:
    available = sorted(request_names)
    message = f"unknown request: {name}"
    if not available:
        return f"{message}; no named REQUESTs are defined"

    close = get_close_matches(name, available, n=1, cutoff=0.72)
    if close:
        return f"{message}; did you mean {close[0]}?"

    return f"{message}; available requests: {_format_limited_list(available)}"


def _contract_failure_message(label: str, binding: ContractBinding, error: GwtError) -> str:
    detail = str(error)
    if detail == f"unknown path: {binding.path}":
        role = "input" if label == "REQUEST" else "output"
        return (
            f"{label} contract failed for {binding.path}: "
            f"missing required {role}; expected {binding.value_type}"
        )
    return f"{label} contract failed for {binding.path}: {detail}"


def _action_mismatch_message(
    prefix: str,
    call: list[str],
    actions_by_name: dict[str, list[Action]],
) -> str:
    call_text = " ".join(call)
    message = f"{prefix}: {call_text}"
    if not call:
        return message

    candidates = actions_by_name.get(call[0], [])
    if candidates:
        return f"{message}; available signatures: {_format_action_signatures(candidates)}"

    close = get_close_matches(call[0], sorted(actions_by_name), n=1, cutoff=0.72)
    if close:
        return f"{message}; did you mean {_format_action_signatures(actions_by_name[close[0]])}?"

    return message


def _format_action_signatures(actions: list[Action]) -> str:
    signatures: list[str] = []
    seen: set[str] = set()
    for action in actions:
        signature = action.signature_text or " ".join(action.signature)
        if signature in seen:
            continue
        seen.add(signature)
        signatures.append(signature)
    return _format_limited_list(signatures)


def _format_limited_list(values: list[str], *, limit: int = 5) -> str:
    shown = values[:limit]
    rendered = ", ".join(shown)
    if len(values) > limit:
        rendered = f"{rendered}, ..."
    return rendered


def _signature_parameter_name(signature: list[str], index: int, token: str) -> str | None:
    if index == 0:
        return None

    explicit_match = SIGNATURE_PARAMETER_PATTERN.match(token)
    if explicit_match is not None:
        return explicit_match.group(1)

    if _signature_has_explicit_parameters(signature):
        return None

    if token in CONNECTORS:
        return None
    return token


def _signature_has_explicit_parameters(signature: list[str]) -> bool:
    return any(SIGNATURE_PARAMETER_PATTERN.match(token) is not None for token in signature[1:])


def _flatten_record(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, item in value.items():
        path = key if prefix == "" else f"{prefix}.{key}"
        if isinstance(item, dict):
            flattened.update(_flatten_record(cast(dict[str, Any], item), path))
        else:
            flattened[path] = item
    return flattened


def _is_runtime_map(value: object) -> TypeGuard[dict[str, Any]]:
    return isinstance(value, dict)


def _set_flat_record_value(target: dict[str, Any], path: str, value: Any) -> None:
    current = target
    parts = path.split(".")
    for part in parts[:-1]:
        next_value: Any = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            raise GwtError(f"record path collides with scalar: {path}")
        current = cast(dict[str, Any], next_value)
    current[parts[-1]] = value


def _set_nested_output(target: dict[str, Any], path: str, value: Any) -> None:
    current = target
    parts = path.split(".")
    for part in parts[:-1]:
        next_value: Any = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            raise GwtError(f"OUTPUT path collides with scalar: {path}")
        current = cast(dict[str, Any], next_value)
    current[parts[-1]] = value


_INVALID_TYPE = object()


def _is_numeric_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, Decimal):
        return value.is_finite()
    return isinstance(value, (int, float))


def _normalize_primitive_value(value: Any, expected_type: str) -> Any:
    if expected_type == "number":
        if not _is_numeric_value(value):
            return _INVALID_TYPE
        return float(value) if isinstance(value, Decimal) else value
    if expected_type == "integer":
        return value if isinstance(value, int) and not isinstance(value, bool) else _INVALID_TYPE
    if expected_type == "decimal":
        if isinstance(value, Decimal):
            return value if value.is_finite() else _INVALID_TYPE
        if isinstance(value, int) and not isinstance(value, bool):
            return Decimal(value)
        if isinstance(value, str):
            try:
                normalized = Decimal(value)
            except InvalidOperation:
                return _INVALID_TYPE
            return normalized if normalized.is_finite() else _INVALID_TYPE
        return _INVALID_TYPE
    if expected_type == "text":
        return value if isinstance(value, str) else _INVALID_TYPE
    if expected_type == "boolean":
        return value if isinstance(value, bool) else _INVALID_TYPE
    if expected_type == "list":
        return cast(list[Any], value) if isinstance(value, list) else _INVALID_TYPE
    if expected_type == "any":
        return value
    raise AssertionError(expected_type)


def _value_matches_primitive_type(value: Any, expected_type: str) -> bool:
    return _normalize_primitive_value(value, expected_type) is not _INVALID_TYPE


def _value_type_name(value: Any) -> str:
    if value is None:
        return "null"
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
    try:
        parse_expression(text)
        return text
    except GwtError:
        pass

    does_not_contain_index = _find_word_outside_string(text, "does not contain")
    if does_not_contain_index is not None:
        left = text[:does_not_contain_index].strip()
        right = text[does_not_contain_index + len("does not contain") :].strip()
        if not left or not right:
            raise GwtError(f"invalid condition: {text}")
        return f"not ({left} contains {right})"

    is_index = _find_word_outside_string(text, "is")
    if is_index is None:
        return text

    left = text[:is_index]
    right_text = text[is_index + len("is") :]
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


def _split_comment_outside_string(raw: str) -> tuple[str, str | None]:
    in_string = False
    escaped = False
    for index, char in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if in_string and char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if char == "#" and not in_string:
            return raw[:index], raw[index + 1 :]
    return raw, None


def _find_word_outside_string(text: str, word: str) -> int | None:
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if in_string and char == "\\":
            escaped = True
            index += 1
            continue
        if char == '"':
            in_string = not in_string
            index += 1
            continue
        if not in_string and text.startswith(word, index):
            before = text[index - 1] if index > 0 else ""
            after_index = index + len(word)
            after = text[after_index] if after_index < len(text) else ""
            if not _is_identifier_char(before) and not _is_identifier_char(after):
                return index
        index += 1
    return None


def _is_identifier_char(char: str) -> bool:
    return bool(char) and (char.isalnum() or char in "_.")


def _split_pipes_outside_string(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if in_string and char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if char == "|" and not in_string:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def _literal_union_values(value_type: str) -> tuple[Any, ...] | None:
    if "|" not in value_type:
        return None
    parts = _split_pipes_outside_string(value_type)
    if len(parts) < 2 or any(not part for part in parts):
        return None

    values: list[Any] = []
    base_type: str | None = None
    for part in parts:
        try:
            expression = parse_expression(part)
        except GwtError:
            return None
        if not isinstance(expression, Literal):
            return None
        value = expression.value
        if isinstance(value, list):
            return None
        value_type_name = _value_type_name(value)
        if value_type_name not in {"text", "number", "integer", "decimal", "boolean"}:
            return None
        if base_type is None:
            base_type = value_type_name
        elif value_type_name != base_type:
            return None
        values.append(value)
    return tuple(values)


def _literal_union_base_type(value_type: str) -> str | None:
    values = _literal_union_values(value_type)
    if not values:
        return None
    return _value_type_name(values[0])


def _variant_kind_type(variant: VariantDefinition) -> str:
    return " | ".join(f'"{name}"' for name in variant.cases)


def _value_matches_literal(value: Any, literal: Any) -> bool:
    if isinstance(literal, bool):
        return isinstance(value, bool) and value == literal
    if isinstance(literal, int):
        return isinstance(value, int) and not isinstance(value, bool) and value == literal
    if isinstance(literal, Decimal):
        if isinstance(value, float):
            return value == float(literal)
        return isinstance(value, Decimal) and value == literal
    if isinstance(literal, float):
        return isinstance(value, float) and value == literal
    return type(value) is type(literal) and value == literal


def _format_literal_values(values: tuple[Any, ...]) -> str:
    return ", ".join(_literal_value_text(value) for value in values)


def _literal_value_text(value: Any) -> str:
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _parse_find_statement(text: str) -> tuple[bool, str, str, str, str] | None:
    match = re.match(
        r"^find (?P<optional>optional )?(?P<name>[A-Za-z_][A-Za-z0-9_]*) "
        r"in (?P<iterable>.+) where (?P<condition>.+) "
        r"into (?P<path>[A-Za-z_][A-Za-z0-9_.]*)$",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return (
        match.group("optional") is not None,
        match.group("name"),
        match.group("iterable"),
        match.group("condition"),
        match.group("path"),
    )


def _parse_exists_statement(text: str) -> tuple[str, str, str, str] | None:
    match = re.match(
        r"^exists (?P<name>[A-Za-z_][A-Za-z0-9_]*) "
        r"in (?P<iterable>.+) where (?P<condition>.+) "
        r"into (?P<path>[A-Za-z_][A-Za-z0-9_.]*)$",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return match.group("name"), match.group("iterable"), match.group("condition"), match.group("path")


def _parse_sum_projection(text: str) -> tuple[str, str, str, str] | None:
    match = re.match(
        r"^sum (?P<projection>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+) "
        r"in (?P<iterable>.+) into (?P<path>[A-Za-z_][A-Za-z0-9_.]*)$",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    projection = match.group("projection")
    name = projection.split(".", 1)[0]
    return projection, name, match.group("iterable"), match.group("path")
