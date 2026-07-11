from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from typing import cast

from gwtlang import (
    ExecutionCase,
    ExecutionCaseCapturePolicy,
    ExplainResult,
    GwtError,
    capture_execution_case,
    explain_json_file,
    load_execution_case,
    load_program_snapshot,
)
from gwtlang.__main__ import main
from gwtlang.comparison import compare_execution_cases
from gwtlang.execution_case import execution_case_digest
from gwtlang.payloads import JsonObject
from gwtlang.workbench import render_workbench_html


FAILURE_PROGRAM = '''PROGRAM failure capture

RECORD Input
  value: number

REQUEST calculate
  GIVEN input is Input
  WHEN outer input
  OUTPUT input is Input

WHEN outer <input>
  GIVEN input is Input
  inner input

WHEN inner <input>
  GIVEN input is Input
  set input.value to input.value / 0
'''


class ExecutionCaseProfileTests(unittest.TestCase):
    def test_record_policy_normalizes_parse_failures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "invalid.gwt"
            program.write_text("PROGRAM\n")
            execution_case = capture_execution_case(
                program,
                {},
                request="request",
                policy=ExecutionCaseCapturePolicy(on_error="record"),
            )

        payload = execution_case.as_payload()
        self.assertEqual(payload["execution"]["outcome"], "failed")
        self.assertEqual(payload["execution"]["error"]["stage"], "parse")
        self.assertEqual(payload["program"]["name"], None)
        self.assertEqual(payload["evidence"], [])
        self.assertNotIn("Result:", ExplainResult(execution_case).as_text())
        self._validate_schema(payload)

        injected_result = deepcopy(payload)
        injected_result["result"] = {"secret": "SHOULD-NOT-EXIST"}
        injected_result["integrity"]["digest"] = execution_case_digest(
            injected_result
        )
        with self.assertRaisesRegex(
            ValueError,
            "failed execution case result must be an empty placeholder",
        ):
            ExecutionCase.from_payload(injected_result)

    def test_default_raises_while_record_policy_captures_source_linked_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "rules.gwt"
            program.write_text(FAILURE_PROGRAM)

            with self.assertRaisesRegex(GwtError, "division by zero"):
                capture_execution_case(
                    program,
                    {"input": {"value": 4}},
                    request="calculate",
                )

            execution_case = capture_execution_case(
                program,
                {"input": {"value": 4}},
                request="calculate",
                policy=ExecutionCaseCapturePolicy(on_error="record"),
                execution_budget=321,
                max_call_depth=12,
            )
            case_path = root / "failure.execution-case.json"
            execution_case.write(case_path)
            loaded = load_execution_case(case_path)

        payload = loaded.as_payload()
        self.assertEqual(payload["execution"]["outcome"], "failed")
        self.assertEqual(
            payload["execution"]["capturePolicy"],
            {"onError": "record", "values": "full"},
        )
        self.assertEqual(payload["execution"]["executionBudget"], 321)
        self.assertEqual(payload["execution"]["maxCallDepth"], 12)
        self.assertEqual(
            payload["execution"]["status"],
            {"availability": "unavailable"},
        )
        self.assertEqual(payload["redaction"]["availability"]["result"], "unavailable")
        error = payload["execution"]["error"]
        self.assertEqual(error["kind"], "GwtError")
        self.assertEqual(error["code"], "execution-failed")
        self.assertEqual(error["stage"], "execute")
        self.assertEqual(error["message"], "division by zero")
        self.assertEqual(error["messageAvailability"], "available")
        self.assertEqual(error["source"]["file"], "./rules.gwt")
        self.assertNotIn(
            temp_dir,
            json.dumps(
                {
                    "error": error,
                    "evidence": payload["evidence"],
                    "stateChanges": payload["stateChanges"],
                }
            ),
        )

        behavior = [item for item in payload["evidence"] if item["kind"] == "behavior"]
        self.assertEqual(
            [(item["phase"], item.get("behaviorOutcome")) for item in behavior],
            [
                ("enter", None),
                ("enter", None),
                ("exit", "failed"),
                ("exit", "failed"),
            ],
        )
        self._validate_schema(payload)

    def test_failed_capture_uses_snapshot_source_after_program_is_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(FAILURE_PROGRAM)
            snapshot = load_program_snapshot(program)
            program.unlink()

            with patch(
                "gwtlang.execution_case.load_program_snapshot",
                return_value=snapshot,
            ):
                payload = capture_execution_case(
                    program,
                    {"input": {"value": 4}},
                    request="calculate",
                    policy=ExecutionCaseCapturePolicy(on_error="record"),
                ).as_payload()

        error = payload["execution"]["error"]
        self.assertEqual(error["source"]["file"], "./rules.gwt")
        self.assertEqual(
            error["source"]["text"],
            "  set input.value to input.value / 0",
        )

    def test_omit_values_is_value_free_and_distinguishes_redacted_unavailable_and_absent(self):
        secret = "PRIVATE-CUSTOMER-9f31"
        domains = [
            (
                Path("examples/vendor_onboarding/rules.gwt"),
                Path("examples/vendor_onboarding/request.json"),
                "review vendor",
                ("vendor", "vendor_name"),
            ),
            (
                Path("examples/incident_triage/rules.gwt"),
                Path("examples/incident_triage/request.json"),
                "triage incident",
                ("incident", "incident_id"),
            ),
        ]
        for program, input_path, request, secret_path in domains:
            with self.subTest(request=request):
                state = json.loads(input_path.read_text())
                state[secret_path[0]][secret_path[1]] = secret
                execution_case = capture_execution_case(
                    program,
                    state,
                    request=request,
                    json_file=f"/home/alice/{secret}-input.json",
                    policy=ExecutionCaseCapturePolicy(values="omit"),
                )
                payload = execution_case.as_payload()
                rendered = json.dumps(payload, sort_keys=True)

                self.assertNotIn(secret, rendered)
                self.assertNotIn("/home/alice", rendered)
                self.assertEqual(payload["program"]["file"], payload["program"]["identity"]["entry"])
                self.assertIsNone(payload["request"]["inputFile"])
                self.assertEqual(payload["request"]["input"], {})
                self.assertEqual(payload["result"], {})
                self.assertEqual(payload["redaction"]["mode"], "omit-values")
                self.assertFalse(payload["redaction"]["valuesIncluded"])
                self.assertEqual(
                    payload["redaction"]["availability"]["requestInput"],
                    "redacted",
                )
                self.assertEqual(
                    payload["redaction"]["availability"]["result"],
                    "redacted",
                )
                self.assertIn("/program/file", payload["redaction"]["redactedPaths"])
                self.assertIn("/request/inputFile", payload["redaction"]["redactedPaths"])
                for item in payload["evidence"]:
                    operands = item.get("operands")
                    if operands is not None:
                        self.assertEqual(operands, {"availability": "redacted"})
                for change in payload["stateChanges"]:
                    self.assertEqual(change["before"], {"availability": "redacted"})
                    self.assertEqual(change["after"], {"availability": "redacted"})
                    self.assertEqual(change["patch"], [])
                self.assertIn(
                    "Operand values redacted",
                    render_workbench_html(execution_case),
                )
                self._validate_schema(payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(FAILURE_PROGRAM)
            failed = capture_execution_case(
                program,
                {"input": {"value": 4, "secret": secret}},
                request="calculate",
                json_file=f"/home/alice/{secret}.json",
                policy=ExecutionCaseCapturePolicy(on_error="record", values="omit"),
            ).as_payload()

        serialized_failure = json.dumps(failed)
        self.assertNotIn(secret, serialized_failure)
        self.assertNotIn("/home/alice", serialized_failure)
        self.assertEqual(failed["redaction"]["availability"]["result"], "unavailable")
        self.assertEqual(
            failed["execution"]["error"]["message"],
            "GWT execution failed; error detail omitted by capture policy",
        )
        self.assertEqual(
            failed["execution"]["error"]["messageAvailability"],
            "redacted",
        )
        self._validate_schema(failed)

    def test_explain_and_workbench_render_failure_and_omission_without_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(FAILURE_PROGRAM)
            explanation = explain_json_file(
                program,
                {"input": {"value": 4}},
                request="calculate",
                policy=ExecutionCaseCapturePolicy(on_error="record", values="omit"),
            )
            text = explanation.as_text()
            html = render_workbench_html(explanation.case)

        self.assertIn("calculate failed", text)
        self.assertIn("Captured values: omitted by capture policy", text)
        self.assertIn("error detail omitted by capture policy", text)
        self.assertIn("[failed]", text)
        self.assertIn("Primary execution case", html)
        self.assertIn("Execution failed", html)
        self.assertIn("Values were omitted by the capture policy", html)

    def test_cli_flags_emit_recorded_value_free_failure_and_explicit_unlimited_limits(self):
        secret = "CLI-PRIVATE-VALUE"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "rules.gwt"
            request_path = root / "input.json"
            program.write_text(FAILURE_PROGRAM)
            request_path.write_text(json.dumps({"input": {"value": 4, "secret": secret}}))
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(
                    [
                        "capture",
                        str(program),
                        "--json-input",
                        str(request_path),
                        "--request",
                        "calculate",
                        "--record-failures",
                        "--omit-values",
                        "--execution-budget",
                        "none",
                        "--max-call-depth",
                        "none",
                    ]
                )

            explain_stdout = io.StringIO()
            with redirect_stdout(explain_stdout):
                explain_status = main(
                    [
                        "explain",
                        str(program),
                        "--json-input",
                        str(request_path),
                        "--request",
                        "calculate",
                        "--record-failures",
                        "--omit-values",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["execution"]["outcome"], "failed")
        self.assertIsNone(payload["execution"]["executionBudget"])
        self.assertIsNone(payload["execution"]["maxCallDepth"])
        self.assertNotIn(secret, stdout.getvalue())
        self.assertEqual(explain_status, 0)
        self.assertIn("calculate failed", explain_stdout.getvalue())
        self.assertNotIn(secret, explain_stdout.getvalue())

    def test_comparison_accounts_for_unreplayable_cases_without_executing_them(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            program = root / "rules.gwt"
            program.write_text(FAILURE_PROGRAM.replace(" / 0", " / 2"))
            normal = capture_execution_case(
                program,
                {"input": {"value": 4}},
                request="calculate",
                execution_budget=777,
                max_call_depth=11,
            )
            omitted = capture_execution_case(
                program,
                {"input": {"value": 4}},
                request="calculate",
                policy=ExecutionCaseCapturePolicy(values="omit"),
            )
            failing_program = root / "failing.gwt"
            failing_program.write_text(FAILURE_PROGRAM)
            failed = capture_execution_case(
                failing_program,
                {"input": {"value": 4}},
                request="calculate",
                policy=ExecutionCaseCapturePolicy(on_error="record"),
            )

            from gwtlang import comparison as comparison_module

            real_capture = comparison_module.capture_execution_case
            calls: list[tuple[int | None, int | None]] = []

            def recording_capture(*args, **kwargs):
                calls.append((kwargs.get("execution_budget"), kwargs.get("max_call_depth")))
                return real_capture(*args, **kwargs)

            with patch("gwtlang.comparison.capture_execution_case", side_effect=recording_capture):
                comparison = compare_execution_cases(
                    program,
                    program,
                    [normal, omitted, failed],
                )

        self.assertEqual(
            [case.classification for case in comparison.cases],
            ["unchanged", "unavailable", "baseline_mismatch"],
        )
        self.assertEqual(comparison.totals.cases, 3)
        self.assertEqual(comparison.totals.unavailable, 1)
        self.assertEqual(comparison.totals.baseline_mismatch, 1)
        self.assertEqual(calls, [(777, 11), (777, 11)])
        self.assertIn("1 unavailable", comparison.as_text())
        workbench = render_workbench_html(normal, comparison)
        self.assertIn('data-classification-total="unavailable"', workbench)
        self.assertIn("Choosing a comparison case changes only the comparison detail panel", workbench)
        self._validate_comparison_schema(comparison.as_payload())

    def test_loader_and_direct_constructor_reject_missing_evidence_fields(self):
        payload = capture_execution_case(
            "examples/vendor_onboarding/rules.gwt",
            json.loads(Path("examples/vendor_onboarding/request.json").read_text()),
            request="review vendor",
        ).as_payload()
        invalid = deepcopy(payload)
        del invalid["evidence"][0]["summary"]
        invalid["integrity"]["digest"] = execution_case_digest(invalid)

        with self.assertRaisesRegex(ValueError, "missing required field: summary"):
            ExecutionCase.from_payload(invalid)
        with self.assertRaisesRegex(ValueError, "missing required field: summary"):
            ExecutionCase(invalid)  # pyright: ignore[reportArgumentType]

        invalid_file = deepcopy(payload)
        invalid_file["program"]["file"] = None
        invalid_file["integrity"]["digest"] = execution_case_digest(invalid_file)
        with self.assertRaisesRegex(ValueError, "program.file must be a non-empty string"):
            ExecutionCase.from_payload(invalid_file)

        invalid_versions = deepcopy(payload)
        del invalid_versions["versions"]["languageSpecVersion"]
        invalid_versions["integrity"]["digest"] = execution_case_digest(invalid_versions)
        with self.assertRaisesRegex(ValueError, "versions fields"):
            ExecutionCase.from_payload(invalid_versions)

        invalid_edge = deepcopy(payload)
        invalid_edge["program"]["identity"]["modules"][0]["imports"] = [
            "./not-captured.gwt"
        ]
        invalid_edge["integrity"]["digest"] = execution_case_digest(invalid_edge)
        with self.assertRaisesRegex(ValueError, "uncaptured module"):
            ExecutionCase.from_payload(invalid_edge)

    def test_capture_and_explain_missing_files_return_clean_cli_errors(self):
        for command in ("capture", "explain"):
            with self.subTest(command=command):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    status = main(
                        [
                            command,
                            "missing-program.gwt",
                            "--json-input",
                            "missing-input.json",
                            "--request",
                            "request",
                        ]
                    )
                self.assertEqual(status, 1)
                self.assertIn("gwt:", stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())

    def test_capture_rejects_deep_and_non_finite_stdin_json_without_tracebacks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                "REQUEST inspect\n"
                "  GIVEN input is any\n"
                "  OUTPUT input is any\n"
            )
            inputs = [
                '{"input":NaN}',
                '{"input":Infinity}',
                '{"input":-Infinity}',
                '{"input":' + ("[" * 140) + "0" + ("]" * 140) + "}",
            ]
            for raw in inputs:
                with self.subTest(raw=raw[:30]):
                    stderr = io.StringIO()
                    with (
                        patch("sys.stdin", io.StringIO(raw)),
                        redirect_stderr(stderr),
                    ):
                        status = main(
                            [
                                "capture",
                                str(program),
                                "--json-input",
                                "-",
                                "--request",
                                "inspect",
                                "--record-failures",
                            ]
                        )
                    self.assertEqual(status, 1)
                    self.assertIn("gwt:", stderr.getvalue())
                    self.assertNotIn("Traceback", stderr.getvalue())

    def test_capture_api_rejects_deep_values_before_copying(self):
        nested: object = 0
        for _ in range(140):
            nested = [nested]
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "rules.gwt"
            program.write_text(
                "REQUEST inspect\n"
                "  GIVEN input is any\n"
                "  OUTPUT input is any\n"
            )
            with self.assertRaisesRegex(GwtError, "maximum supported nesting depth"):
                capture_execution_case(
                    program,
                    cast(JsonObject, {"input": nested}),
                    request="inspect",
                )

    def test_capture_and_explain_reject_invalid_utf8_without_tracebacks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid_program = root / "rules.gwt"
            invalid_program = root / "invalid.gwt"
            valid_input = root / "input.json"
            invalid_input = root / "invalid.json"
            valid_program.write_text(
                "REQUEST inspect\n"
                "  GIVEN input is any\n"
                "  OUTPUT input is any\n"
            )
            invalid_program.write_bytes(b"\xff")
            valid_input.write_text('{"input":1}')
            invalid_input.write_bytes(b"\xff")

            for command, program, input_path in (
                ("capture", valid_program, invalid_input),
                ("explain", valid_program, invalid_input),
                ("capture", invalid_program, valid_input),
                ("explain", invalid_program, valid_input),
            ):
                with self.subTest(command=command, program=program.name):
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        status = main(
                            [
                                command,
                                str(program),
                                "--json-input",
                                str(input_path),
                                "--request",
                                "inspect",
                            ]
                        )
                    self.assertEqual(status, 1)
                    self.assertIn("not valid UTF-8", stderr.getvalue())
                    self.assertNotIn("Traceback", stderr.getvalue())

    @staticmethod
    def _validate_schema(payload: object) -> None:
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        schema = json.loads(Path("docs/schemas/execution-case.schema.json").read_text())
        Draft202012Validator(schema).validate(payload)

    @staticmethod
    def _validate_comparison_schema(payload: object) -> None:
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        schema = json.loads(Path("docs/schemas/comparison.schema.json").read_text())
        Draft202012Validator(schema).validate(payload)


if __name__ == "__main__":
    unittest.main()
