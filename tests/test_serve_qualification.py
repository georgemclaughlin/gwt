from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest

from gwtlang.case_corpus import CaseCorpusEntrySpec, write_case_corpus
from gwtlang.execution_case import ExecutionCaseCapturePolicy, capture_execution_case
from gwtlang.http_server import GwtHttpService, create_http_server
from gwtlang.serve_qualification import (
    qualify_served_endpoint,
    qualify_served_program,
)


PROGRAM = Path("examples/deployable_api/rules.gwt")
REQUEST = "triage ticket"


class ServeQualificationTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("uvicorn"), "uvicorn is optional")
    def test_qualifies_real_asgi_boundary_with_a_full_value_corpus(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            case = capture_execution_case(
                PROGRAM,
                _triage_input(),
                request=REQUEST,
            )
            case_path = root / "incident.execution-case.json"
            case.write(case_path)
            case_id = case.as_payload()["integrity"]["digest"]
            corpus_path = root / "corpus.json"
            write_case_corpus(
                corpus_path,
                name="serve qualification smoke",
                entries=[
                    CaseCorpusEntrySpec(
                        reference="incident",
                        case_id=case_id,
                        artifact=case_path.name,
                    )
                ],
            )

            result = qualify_served_program(
                PROGRAM,
                corpus_path,
                timeout_seconds=10,
            )

        self.assertTrue(result.ok)
        self.assertEqual(
            [check.name for check in result.checks],
            [
                "startup",
                "readiness",
                "program_identity",
                "openapi",
                "corpus",
                "process_shutdown",
                "overload",
                "active_shutdown",
            ],
        )
        self.assertTrue(all(check.ok for check in result.checks))
        self.assertEqual(len(result.cases), 1)
        self.assertTrue(result.cases[0].ok)
        payload = result.as_payload()
        self.assertEqual(payload["kind"], "gwt.serve-qualification")
        self.assertEqual(payload["schemaVersion"], 1)
        corpus_payload = payload["corpus"]
        self.assertIsInstance(corpus_payload, dict)
        if not isinstance(corpus_payload, dict):
            raise AssertionError("expected corpus report object")
        self.assertEqual(corpus_payload["cases"], 1)
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator

            schema = json.loads(
                Path("docs/schemas/serve-qualification.schema.json").read_text()
            )
            Draft202012Validator(schema).validate(payload)

    def test_rejects_shape_only_corpus_before_starting_a_server(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            case = capture_execution_case(
                PROGRAM,
                _triage_input(),
                request=REQUEST,
                policy=ExecutionCaseCapturePolicy(values="omit"),
            )
            case_path = root / "shape.execution-case.json"
            case.write(case_path)
            corpus_path = root / "corpus.json"
            write_case_corpus(
                corpus_path,
                name="shape-only corpus",
                entries=[
                    CaseCorpusEntrySpec(
                        reference="shape",
                        case_id=case.as_payload()["integrity"]["digest"],
                        artifact=case_path.name,
                    )
                ],
            )

            with self.assertRaisesRegex(ValueError, "omits replay values"):
                qualify_served_program(PROGRAM, corpus_path)

    def test_qualifies_an_existing_endpoint_without_managing_its_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            case = capture_execution_case(PROGRAM, _triage_input(), request=REQUEST)
            case_path = root / "incident.execution-case.json"
            case.write(case_path)
            corpus_path = root / "corpus.json"
            write_case_corpus(
                corpus_path,
                name="existing endpoint smoke",
                entries=[
                    CaseCorpusEntrySpec(
                        reference="incident",
                        case_id=case.as_payload()["integrity"]["digest"],
                        artifact=case_path.name,
                    )
                ],
            )
            service = GwtHttpService.from_file(PROGRAM)
            server = create_http_server(service, port=0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address[:2]
            try:
                result = qualify_served_endpoint(
                    PROGRAM,
                    corpus_path,
                    f"http://{host}:{port}",
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()

        self.assertTrue(result.ok)
        self.assertEqual(
            [check.name for check in result.checks],
            ["readiness", "program_identity", "openapi", "corpus"],
        )
        self.assertEqual(len(result.cases), 1)
        self.assertTrue(result.cases[0].ok)


def _triage_input() -> dict[str, object]:
    return {
        "ticket": {
            "customer_id": "C-100",
            "subject": "checkout unavailable",
            "severity": "medium",
            "account_value": 5000,
            "has_outage": True,
        }
    }
