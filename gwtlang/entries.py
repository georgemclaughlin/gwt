from __future__ import annotations

from dataclasses import dataclass

from .runtime import (
    Action,
    GwtError,
    Program,
    _signature_parameter_name,
    _signature_parameters,
    _tokens,
)


@dataclass(frozen=True)
class EntryCandidate:
    text: str
    behavior: str
    signature: list[str]
    parameters: list[str]
    filename: str | None
    line: int
    column: int
    length: int
    exported: bool = False
    entry: str | None = None

    def as_payload(self, fallback_filename: str) -> dict[str, object]:
        filename = self.filename or fallback_filename
        payload: dict[str, object] = {
            "text": self.text,
            "behavior": self.behavior,
            "signature": self.signature,
            "parameters": self.parameters,
            "file": filename,
            "line": self.line,
            "column": self.column,
            "length": self.length,
            "range": {
                "start": {"line": self.line - 1, "character": self.column - 1},
                "end": {
                    "line": self.line - 1,
                    "character": self.column - 1 + max(1, self.length),
                },
            },
        }
        if self.exported:
            payload["exported"] = True
            payload["entry"] = self.entry or self.text
        return payload


def entry_candidates(program: Program) -> list[EntryCandidate]:
    if program.exports:
        return [
            _export_candidate(name, exported.entry, exported.line)
            for name, exported in program.exports.items()
        ]

    request_roots = {
        binding.path.split(".", 1)[0] for binding in program.inputs.values()
    }
    if not request_roots:
        return []

    entries: list[EntryCandidate] = []
    seen: set[str] = set()
    for action in program.actions:
        parameters = _signature_parameters(action.signature)
        if not parameters or not all(parameter in request_roots for parameter in parameters):
            continue

        text = entry_text(action)
        if text in seen:
            continue
        seen.add(text)
        entries.append(
            EntryCandidate(
                text,
                action.name,
                list(action.signature),
                parameters,
                action.filename,
                action.line,
                action.column,
                action.length,
            )
        )
    return entries


def _export_candidate(name: str, entry: str, line: object) -> EntryCandidate:
    filename = getattr(line, "filename", None)
    line_number = getattr(line, "number", 1)
    try:
        signature = _tokens(entry, filename or "<source>", line_number)
    except GwtError:
        signature = entry.split()
    return EntryCandidate(
        name,
        signature[0] if signature else entry,
        signature,
        [],
        filename,
        line_number,
        getattr(line, "column", 1),
        getattr(line, "length", len(name)),
        True,
        entry,
    )


def entry_text(action: Action) -> str:
    parts: list[str] = []
    for index, token in enumerate(action.signature):
        parameter_name = _signature_parameter_name(action.signature, index, token)
        parts.append(parameter_name or token)
    return " ".join(parts)
