from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import GwtError
from .payloads import SourceRangePayload, SymbolPayload
from .runtime import (
    Action,
    DecisionBlock,
    FindBlock,
    ForBlock,
    IfBlock,
    Line,
    MatchBlock,
    Program,
    Scenario,
    _signature_parameters as _runtime_signature_parameters,
    _tokens,
)


@dataclass(frozen=True)
class SourceRange:
    filename: str | None
    line: int
    column: int
    length: int

    def as_payload(self, fallback_filename: str) -> SourceRangePayload:
        filename = self.filename or fallback_filename
        start_character = max(0, self.column - 1)
        end_character = start_character + max(1, self.length)
        return {
            "file": filename,
            "line": self.line,
            "column": self.column,
            "length": max(1, self.length),
            "range": {
                "start": {"line": self.line - 1, "character": start_character},
                "end": {"line": self.line - 1, "character": end_character},
            },
        }


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str
    source_range: SourceRange
    detail: str | None = None
    container: str | None = None

    def as_payload(self, fallback_filename: str) -> SymbolPayload:
        payload = {
            "name": self.name,
            "kind": self.kind,
            **self.source_range.as_payload(fallback_filename),
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        if self.container is not None:
            payload["container"] = self.container
        return payload


@dataclass(frozen=True)
class SymbolTable:
    symbols: list[Symbol]

    def as_payload(self, fallback_filename: str) -> list[SymbolPayload]:
        return [symbol.as_payload(fallback_filename) for symbol in self.symbols]


def build_symbol_table(program: Program) -> SymbolTable:
    symbols: list[Symbol] = []

    for dto in program.dtos.values():
        symbols.append(
            Symbol(
                dto.name,
                "dto",
                SourceRange(dto.filename, dto.line, dto.column, dto.length),
                detail=f"RECORD {dto.name}",
            )
        )
        for field_name, field_type in dto.fields.items():
            field_line = dto.field_lines.get(field_name)
            if field_line is None:
                continue
            symbols.append(
                Symbol(
                    field_name,
                    "dto_field",
                    _line_range(field_line),
                    detail=field_type,
                    container=dto.name,
                )
            )

    for variant in program.variants.values():
        symbols.append(
            Symbol(
                variant.name,
                "dto",
                SourceRange(variant.filename, variant.line, variant.column, variant.length),
                detail=f"RECORD {variant.name} is one of",
            )
        )
        for case in variant.cases.values():
            symbols.append(
                Symbol(
                    case.name,
                    "dto_field",
                    SourceRange(case.filename, case.line, case.column, case.length),
                    detail="kind",
                    container=variant.name,
                )
            )
            for field_name, field_type in case.fields.items():
                field_line = case.field_lines.get(field_name)
                if field_line is None:
                    continue
                symbols.append(
                    Symbol(
                        field_name,
                        "dto_field",
                        _line_range(field_line),
                        detail=field_type,
                        container=f"{variant.name}.{case.name}",
                    )
                )

    for request in program.requests.values():
        symbols.append(
            Symbol(
                request.name,
                "request",
                _line_range(request.line),
                detail=f"REQUEST {request.name}",
            )
        )
        for binding in [*request.inputs.values(), *request.outputs.values()]:
            symbols.append(
                Symbol(
                    binding.path,
                    "contract",
                    _line_range(binding.line),
                    detail=f"{binding.kind.upper()} {binding.path} is {binding.value_type}",
                    container=request.name,
                )
            )

    for action in program.actions:
        symbols.append(
            Symbol(
                action.signature_text or " ".join(action.signature),
                "behavior",
                SourceRange(action.filename, action.line, action.column, action.length),
                detail=_behavior_detail(action),
            )
        )
        for parameter in _signature_parameters(action):
            symbols.append(
                Symbol(
                    parameter,
                    "parameter",
                    _action_token_range(action, parameter),
                    detail=action.contract.inputs.get(parameter),
                    container=action.signature_text or " ".join(action.signature),
                )
            )
        _collect_body_symbols(symbols, action.body, action.signature_text or " ".join(action.signature))

    for scenario in program.scenarios:
        if scenario.line <= 0:
            continue
        symbols.append(
            Symbol(
                scenario.name,
                "scenario",
                SourceRange(scenario.filename, scenario.line, scenario.column, scenario.length),
                detail=f"SCENARIO {scenario.name}",
            )
        )

    return SymbolTable(symbols)


def _line_range(line: Line) -> SourceRange:
    return SourceRange(line.filename, line.number, line.column, line.length)


def _behavior_detail(action: Action) -> str:
    if action.contract.return_type is None:
        return "behavior"
    return f"returns {action.contract.return_type}"


def _signature_parameters(action: Action) -> list[str]:
    return _runtime_signature_parameters(action.signature)


def _action_token_range(action: Action, token: str) -> SourceRange:
    signature_text = action.signature_text or " ".join(action.signature)
    explicit_index = signature_text.find(f"<{token}>")
    if explicit_index >= 0:
        index = explicit_index + 1
    else:
        index = signature_text.find(token)
    column = action.column + index if index >= 0 else action.column
    return SourceRange(action.filename, action.line, column, len(token))


def _collect_body_symbols(symbols: list[Symbol], body: list[Any], container: str) -> None:
    for statement in body:
        if isinstance(statement, Line):
            try:
                tokens = _tokens(statement.text, statement.filename or "<source>", statement.number)
            except GwtError:
                continue
            if len(tokens) >= 2 and tokens[0] == "LET":
                symbols.append(Symbol(tokens[1], "local", _token_range(statement, tokens[1]), container=container))
        elif isinstance(statement, ForBlock):
            symbols.append(
                Symbol(
                    statement.name,
                    "local",
                    _line_range(statement.name_line or statement.iterable),
                    detail="loop item",
                    container=container,
                )
            )
            _collect_body_symbols(symbols, statement.body, container)
        elif isinstance(statement, FindBlock):
            symbols.append(
                Symbol(
                    statement.name,
                    "local",
                    _line_range(statement.name_line or statement.iterable),
                    detail="matched item",
                    container=container,
                )
            )
            _collect_body_symbols(symbols, statement.body, container)
            _collect_body_symbols(symbols, statement.else_body, container)
        elif isinstance(statement, IfBlock):
            _collect_body_symbols(symbols, statement.then_body, container)
            _collect_body_symbols(symbols, statement.else_body, container)
        elif isinstance(statement, DecisionBlock):
            for branch in statement.branches:
                _collect_body_symbols(symbols, branch.body, container)
            _collect_body_symbols(symbols, statement.else_body, container)
        elif isinstance(statement, MatchBlock):
            for case in statement.cases:
                _collect_body_symbols(symbols, case.body, container)
            _collect_body_symbols(symbols, statement.else_body, container)


def _token_range(line: Line, token: str) -> SourceRange:
    index = line.text.find(token)
    column = line.column + index if index >= 0 else line.column
    return SourceRange(line.filename, line.number, column, len(token))
