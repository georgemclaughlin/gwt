from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, BinaryIO, Literal, TypedDict
from urllib.parse import unquote, urlparse

from .payloads import CompletionItemPayload, RangePayload
from .service import Analysis, analyze_source, completion_items, definition_at, hover_at
from .symbols import SourceRange
from .version import current_package_version


TEXT_DOCUMENT_SYNC_FULL = 1


class LspDiagnosticPayload(TypedDict):
    range: RangePayload
    severity: int
    code: str
    source: Literal["gwt"]
    message: str


class LspDocumentSymbolPayload(TypedDict):
    name: str
    kind: int
    detail: str
    range: RangePayload
    selectionRange: RangePayload


class _LspMarkupContentPayload(TypedDict):
    kind: Literal["markdown"]
    value: str


class LspHoverPayload(TypedDict):
    contents: _LspMarkupContentPayload
    range: RangePayload


class LspDefinitionPayload(TypedDict):
    uri: str
    range: RangePayload


class LspCompletionListPayload(TypedDict):
    isIncomplete: bool
    items: list[CompletionItemPayload]


class _LspCompletionOptionsPayload(TypedDict):
    resolveProvider: bool


class _LspServerCapabilitiesPayload(TypedDict):
    textDocumentSync: int
    documentSymbolProvider: bool
    hoverProvider: bool
    definitionProvider: bool
    completionProvider: _LspCompletionOptionsPayload


class _LspServerInfoPayload(TypedDict):
    name: str
    version: str


class _LspInitializeResultPayload(TypedDict):
    capabilities: _LspServerCapabilitiesPayload
    serverInfo: _LspServerInfoPayload


class LspServer:
    def __init__(self, reader: BinaryIO, writer: BinaryIO) -> None:
        self.reader = reader
        self.writer = writer
        self.documents: dict[str, str] = {}
        self.shutdown_requested = False

    def run(self) -> int:
        while True:
            message = self._read_message()
            if message is None:
                return 0
            if self._handle_message(message):
                return 0

    def _handle_message(self, message: dict[str, Any]) -> bool:
        method = message.get("method")
        if method == "initialize":
            self._send_response(message.get("id"), _initialize_result())
        elif method == "initialized":
            pass
        elif method == "shutdown":
            self.shutdown_requested = True
            self._send_response(message.get("id"), None)
        elif method == "exit":
            return True
        elif method == "textDocument/didOpen":
            text_document = message["params"]["textDocument"]
            self.documents[text_document["uri"]] = text_document.get("text", "")
            self._publish_diagnostics(text_document["uri"])
        elif method == "textDocument/didChange":
            text_document = message["params"]["textDocument"]
            changes = message["params"].get("contentChanges", [])
            if changes:
                self.documents[text_document["uri"]] = changes[-1].get("text", "")
            self._publish_diagnostics(text_document["uri"])
        elif method == "textDocument/didClose":
            uri = message["params"]["textDocument"]["uri"]
            self.documents.pop(uri, None)
            self._send_notification("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": []})
        elif method == "textDocument/documentSymbol":
            analysis = self._analysis_for_text_document(message["params"]["textDocument"])
            self._send_response(message.get("id"), lsp_document_symbols(analysis))
        elif method == "textDocument/hover":
            analysis = self._analysis_for_text_document(message["params"]["textDocument"])
            position = message["params"]["position"]
            self._send_response(message.get("id"), lsp_hover(analysis, position["line"], position["character"]))
        elif method == "textDocument/definition":
            analysis = self._analysis_for_text_document(message["params"]["textDocument"])
            position = message["params"]["position"]
            self._send_response(message.get("id"), lsp_definition(analysis, position["line"], position["character"]))
        elif method == "textDocument/completion":
            analysis = self._analysis_for_text_document(message["params"]["textDocument"])
            self._send_response(message.get("id"), lsp_completion(analysis))
        elif "id" in message:
            self._send_error(message.get("id"), -32601, f"Method not found: {method}")
        return False

    def _publish_diagnostics(self, uri: str) -> None:
        analysis = self._analysis_for_uri(uri)
        self._send_notification(
            "textDocument/publishDiagnostics",
            {"uri": uri, "diagnostics": lsp_diagnostics(analysis)},
        )

    def _analysis_for_text_document(self, text_document: dict[str, Any]) -> Analysis:
        return self._analysis_for_uri(text_document["uri"])

    def _analysis_for_uri(self, uri: str) -> Analysis:
        filename = uri_to_filename(uri)
        source = self.documents.get(uri)
        if source is None:
            try:
                source = Path(filename).read_text()
            except OSError:
                source = ""
        return analyze_source(source, filename)

    def _read_message(self) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = self.reader.readline()
            if line == b"":
                return None
            if line in {b"\r\n", b"\n"}:
                break
            name, value = line.decode("ascii").split(":", 1)
            headers[name.lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return None
        payload = self.reader.read(content_length)
        return json.loads(payload.decode("utf-8"))

    def _send_response(self, request_id: object, result: object) -> None:
        self._write_message({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _send_error(self, request_id: object, code: int, message: str) -> None:
        self._write_message({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})

    def _send_notification(self, method: str, params: object) -> None:
        self._write_message({"jsonrpc": "2.0", "method": method, "params": params})

    def _write_message(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        self.writer.write(header + payload)
        self.writer.flush()


def run_stdio_server() -> int:
    return LspServer(sys.stdin.buffer, sys.stdout.buffer).run()


def lsp_diagnostics(analysis: Analysis) -> list[LspDiagnosticPayload]:
    return [
        {
            "range": _lsp_range(diagnostic.line, diagnostic.column, diagnostic.length),
            "severity": _diagnostic_severity(diagnostic.severity),
            "code": diagnostic.code,
            "source": "gwt",
            "message": diagnostic.message,
        }
        for diagnostic in analysis.diagnostics
    ]


def lsp_document_symbols(analysis: Analysis) -> list[LspDocumentSymbolPayload]:
    return [
        {
            "name": symbol.name,
            "kind": _symbol_kind(symbol.kind),
            "detail": symbol.detail or symbol.kind,
            "range": _range_payload(symbol.source_range),
            "selectionRange": _range_payload(symbol.source_range),
        }
        for symbol in analysis.symbols.symbols
    ]


def lsp_hover(analysis: Analysis, line: int, character: int) -> LspHoverPayload | None:
    hover = hover_at(analysis, line, character)
    if hover is None:
        return None
    return {
        "contents": {"kind": "markdown", "value": hover.contents},
        "range": _range_payload(hover.source_range),
    }


def lsp_definition(analysis: Analysis, line: int, character: int) -> LspDefinitionPayload | None:
    source_range = definition_at(analysis, line, character)
    if source_range is None:
        return None
    return {"uri": filename_to_uri(source_range.filename or analysis.filename), "range": _range_payload(source_range)}


def lsp_completion(analysis: Analysis) -> LspCompletionListPayload:
    return {"isIncomplete": False, "items": completion_items(analysis)}


def filename_to_uri(filename: str) -> str:
    return Path(filename).resolve().as_uri()


def uri_to_filename(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return uri
    return unquote(parsed.path)


def _initialize_result() -> _LspInitializeResultPayload:
    return {
        "capabilities": {
            "textDocumentSync": TEXT_DOCUMENT_SYNC_FULL,
            "documentSymbolProvider": True,
            "hoverProvider": True,
            "definitionProvider": True,
            "completionProvider": {"resolveProvider": False},
        },
        "serverInfo": {"name": "gwt-language-server", "version": current_package_version()},
    }


def _diagnostic_severity(severity: str) -> int:
    return {"error": 1, "warning": 2, "information": 3, "hint": 4}.get(severity, 1)


def _symbol_kind(kind: str) -> int:
    return {
        "record": 5,
        "record_field": 8,
        "behavior": 12,
        "parameter": 13,
        "local": 13,
        "contract": 13,
        "scenario": 2,
    }.get(kind, 13)


def _range_payload(source_range: SourceRange) -> RangePayload:
    return _lsp_range(source_range.line, source_range.column, source_range.length)


def _lsp_range(line: int, column: int, length: int) -> RangePayload:
    start_line = max(0, line - 1)
    start_character = max(0, column - 1)
    return {
        "start": {"line": start_line, "character": start_character},
        "end": {"line": start_line, "character": start_character + max(1, length)},
    }
