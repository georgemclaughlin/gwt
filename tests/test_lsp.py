import io
import json
from pathlib import Path
import tempfile
import unittest

from gwtlang.lsp import LspServer, filename_to_uri, lsp_definition, lsp_diagnostics, lsp_document_symbols, lsp_hover
from gwtlang.service import analyze_source


SOURCE = """DTO Cart
  total: number

WHEN total cart
  GIVEN cart is Cart
  THEN returns number
  RETURN cart.total

GIVEN cart is Cart
  total: 3

WHEN total cart
"""


class LspTests(unittest.TestCase):
    def test_lsp_payload_helpers(self):
        analysis = analyze_source(SOURCE, "example.gwt")

        self.assertTrue(any(symbol["name"] == "total cart" for symbol in lsp_document_symbols(analysis)))
        self.assertEqual(lsp_hover(analysis, 0, 5)["contents"]["kind"], "markdown")
        self.assertEqual(lsp_definition(analysis, 11, 6)["range"]["start"]["line"], 3)

    def test_lsp_diagnostics_include_codes(self):
        analysis = analyze_source("GIVEN count is 1\nWHEN missing count\n", "bad.gwt")

        diagnostics = lsp_diagnostics(analysis)

        self.assertEqual(diagnostics[0]["code"], "GWT001")
        self.assertEqual(diagnostics[0]["severity"], 1)
        self.assertEqual(diagnostics[0]["source"], "gwt")

    def test_stdio_server_publishes_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            uri = filename_to_uri(str(Path(temp_dir) / "bad.gwt"))
            messages = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {
                        "textDocument": {
                            "uri": uri,
                            "languageId": "gwt",
                            "version": 1,
                            "text": "GIVEN count is 1\nWHEN missing count\n",
                        }
                    },
                },
                {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}},
                {"jsonrpc": "2.0", "method": "exit", "params": {}},
            ]

            output = io.BytesIO()
            status = LspServer(_encoded_messages(messages), output).run()
            responses = _decoded_messages(output.getvalue())

        self.assertEqual(status, 0)
        self.assertEqual(responses[0]["id"], 1)
        diagnostics = responses[1]["params"]["diagnostics"]
        self.assertEqual(responses[1]["method"], "textDocument/publishDiagnostics")
        self.assertEqual(diagnostics[0]["code"], "GWT001")
        self.assertEqual(responses[2]["id"], 2)


def _encoded_messages(messages: list[dict[str, object]]) -> io.BytesIO:
    stream = io.BytesIO()
    for message in messages:
        payload = json.dumps(message).encode("utf-8")
        stream.write(f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload)
    stream.seek(0)
    return stream


def _decoded_messages(data: bytes) -> list[dict[str, object]]:
    stream = io.BytesIO(data)
    messages = []
    while True:
        header = stream.readline()
        if header == b"":
            break
        length = int(header.decode("ascii").split(":", 1)[1].strip())
        blank = stream.readline()
        assert blank == b"\r\n"
        messages.append(json.loads(stream.read(length).decode("utf-8")))
    return messages


if __name__ == "__main__":
    unittest.main()
