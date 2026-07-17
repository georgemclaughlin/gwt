from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from examples.deployable_api import qualify_container
from gwtlang.case_corpus import CaseCorpusEntrySpec, write_case_corpus
from gwtlang.execution_case import capture_execution_case


PROGRAM = Path("examples/deployable_api/rules.gwt")
REQUEST = "triage ticket"


class ContainerQualificationTests(unittest.TestCase):
    def test_pid1_check_requires_python_to_own_the_process(self):
        self.assertTrue(
            qualify_container._is_gwt_pid1(
                "/usr/local/bin/python3.12",
                ("python", "-m", "gwtlang", "serve", "rules.gwt"),
            )
        )
        self.assertFalse(
            qualify_container._is_gwt_pid1(
                "/usr/bin/dash",
                (
                    "sh",
                    "-c",
                    "python -m gwtlang serve rules.gwt",
                ),
            )
        )

    def test_json_build_failure_emits_a_schema_valid_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            corpus_path = _write_corpus(Path(temp_dir))
            stdout = io.StringIO()
            with (
                patch.object(qualify_container.shutil, "which", return_value="docker"),
                patch.object(
                    qualify_container,
                    "_build_image",
                    side_effect=RuntimeError("synthetic build failure"),
                ),
                patch.object(qualify_container, "_remove_container"),
                patch.object(qualify_container, "_remove_image"),
                redirect_stdout(stdout),
            ):
                status = qualify_container.main(
                    [
                        str(PROGRAM),
                        "--program-root",
                        str(PROGRAM.parent),
                        "--corpus",
                        str(corpus_path),
                        "--json",
                    ]
                )

        self.assertEqual(status, 1)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["kind"], "gwt.serve-qualification")
        self.assertEqual(payload["cases"], [])
        self.assertEqual(payload["corpus"]["cases"], 1)
        self.assertEqual(
            [check["name"] for check in payload["checks"]],
            ["container_boundary"],
        )
        self.assertIn("synthetic build failure", payload["checks"][0]["detail"])
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator

            schema = json.loads(
                Path("docs/schemas/serve-qualification.schema.json").read_text()
            )
            Draft202012Validator(schema).validate(payload)

    def test_cleanup_suppresses_docker_timeout_and_bounds_the_call(self):
        timeout = 0.25
        with patch.object(
            qualify_container.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("docker", timeout),
        ) as run:
            qualify_container._remove_container("test-container", timeout=timeout)
            qualify_container._remove_image("test-image", timeout=timeout)

        self.assertEqual(run.call_count, 2)
        self.assertTrue(
            all(call.kwargs["timeout"] == timeout for call in run.call_args_list)
        )

    def test_log_collection_timeout_becomes_a_bounded_diagnostic(self):
        timeout = 0.25
        with patch.object(
            qualify_container.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("docker", timeout),
        ) as run:
            detail = qualify_container._container_log_tail(
                "test-container",
                timeout,
            )

        self.assertEqual(detail, "timed out collecting container logs")
        self.assertEqual(run.call_args.kwargs["timeout"], timeout)


def _write_corpus(root: Path) -> Path:
    case = capture_execution_case(PROGRAM, _triage_input(), request=REQUEST)
    case_path = root / "incident.execution-case.json"
    case.write(case_path)
    corpus_path = root / "corpus.json"
    write_case_corpus(
        corpus_path,
        name="container failure report",
        entries=[
            CaseCorpusEntrySpec(
                reference="incident",
                case_id=case.as_payload()["integrity"]["digest"],
                artifact=case_path.name,
            )
        ],
    )
    return corpus_path


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


if __name__ == "__main__":
    unittest.main()
