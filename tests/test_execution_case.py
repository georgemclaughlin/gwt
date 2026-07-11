from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from gwtlang import (
    EXECUTION_CASE_SCHEMA_VERSION,
    ExecutionCase,
    capture_execution_case,
    explain_json_file,
    load_execution_case,
)
from gwtlang.__main__ import main
from gwtlang.execution_case import execution_case_digest
from gwtlang.version import (
    LANGUAGE_SPEC_VERSION,
    PACKAGE_NAME,
    PAYLOAD_SCHEMA_VERSION,
    current_package_version,
)


class ExecutionCaseTests(unittest.TestCase):
    def test_capture_is_generic_across_decisions_and_non_decision_result(self):
        cases = [
            (
                "examples/vendor_onboarding/rules.gwt",
                "examples/vendor_onboarding/request.json",
                "review vendor",
                "needs_review",
                "manual_review_required",
                "decision.risk_points >= 6",
                "decision.risk_points",
            ),
            (
                "examples/incident_triage/rules.gwt",
                "examples/incident_triage/request.json",
                "triage incident",
                "page",
                "customer_impact",
                "incident.customer_count >= 100",
                "decision.escalation_level",
            ),
            (
                "examples/release_readiness/rules.gwt",
                "examples/release_readiness/request.json",
                "review release",
                "needs_review",
                "missing_approval",
                "decision.missing_approval_count > 0",
                "decision.missing_approval_count",
            ),
        ]
        for program, input_file, request, status, reason, condition, changed_path in cases:
            with self.subTest(request=request):
                input_state = json.loads(Path(input_file).read_text())
                execution_case = capture_execution_case(
                    program,
                    input_state,
                    request=request,
                    json_file=input_file,
                )
                payload = execution_case.as_payload()

                self._assert_common_case(payload, request, input_state)
                self.assertIsNone(payload["execution"]["status"])
                self.assertIsNone(payload["execution"]["reason"])
                self.assertEqual(payload["result"]["decision"]["status"], status)
                self.assertEqual(payload["result"]["decision"]["reason"], reason)
                self.assertIn(
                    condition,
                    payload["execution"]["selectedDecision"]["condition"],
                )
                self.assertTrue(
                    any(change["path"] == changed_path for change in payload["stateChanges"])
                )

        cart_input = {
            "cart": {
                "mode": "reserve",
                "quantity": 2,
                "unit_price": "12.30",
                "total": "0.00",
                "status": "pending",
            }
        }
        cart_case = capture_execution_case(
            "examples/exact_pricing/rules.gwt",
            cart_input,
            request="price cart",
        ).as_payload()

        self._assert_common_case(cart_case, "price cart", cart_input)
        self.assertIsNone(cart_case["execution"]["status"])
        self.assertIsNone(cart_case["execution"]["reason"])
        self.assertIsNone(cart_case["execution"]["selectedDecision"])
        self.assertEqual(cart_case["result"]["cart"]["total"], "24.60")
        self.assertEqual(cart_case["result"]["cart"]["status"], "reserved")
        self.assertTrue(
            any(change["path"] == "cart.total" for change in cart_case["stateChanges"])
        )

    def test_explain_json_cli_emits_schema_conforming_execution_case(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = main(
                [
                    "explain",
                    "examples/vendor_onboarding/rules.gwt",
                    "--json-input",
                    "examples/vendor_onboarding/request.json",
                    "--request",
                    "review vendor",
                    "--json",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["kind"], "gwt.execution-case")
        self.assertEqual(payload["execution"]["outcome"], "completed")
        self.assertEqual(payload["execution"]["selectedDecision"]["result"], True)

        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator

            schema = json.loads(Path("docs/schemas/execution-case.schema.json").read_text())
            Draft202012Validator(schema).validate(payload)

    def test_capture_cli_emits_canonical_execution_case_json_to_stdout(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = main(
                [
                    "capture",
                    "examples/vendor_onboarding/rules.gwt",
                    "--json-input",
                    "examples/vendor_onboarding/request.json",
                    "--request",
                    "review vendor",
                ]
            )

        rendered = stdout.getvalue()
        payload = json.loads(rendered)
        self.assertEqual(status, 0)
        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(rendered, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        self.assertEqual(payload["kind"], "gwt.execution-case")
        self.assertEqual(payload["request"]["name"], "review vendor")
        self.assertEqual(
            payload["request"]["inputFile"],
            "examples/vendor_onboarding/request.json",
        )

    def test_capture_cli_reads_json_input_from_stdin(self):
        input_state = {
            "cart": {
                "mode": "reserve",
                "quantity": 2,
                "unit_price": "12.30",
                "total": "0.00",
                "status": "pending",
            }
        }
        stdout = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(input_state))), redirect_stdout(stdout):
            status = main(
                [
                    "capture",
                    "examples/exact_pricing/rules.gwt",
                    "--json-input",
                    "-",
                    "--request",
                    "price cart",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["request"]["input"], input_state)
        self.assertIsNone(payload["request"]["inputFile"])
        self.assertEqual(payload["result"]["cart"]["total"], "24.60")

    def test_capture_cli_reports_invalid_json_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "invalid.json"
            input_path.write_text("{\n")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = main(
                    [
                        "capture",
                        "examples/exact_pricing/rules.gwt",
                        "--json-input",
                        str(input_path),
                        "--request",
                        "price cart",
                    ]
                )

        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(f"{input_path}:2:1: invalid JSON", stderr.getvalue())

    def test_capture_cli_honors_import_policy_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rules = root / "rules"
            rules.mkdir()
            dependency_path = root / "steps.gwt"
            program_path = rules / "workflow.gwt"
            input_path = rules / "request.json"
            dependency_path.write_text(
                """
                WHEN increase <count>
                  add 1 to count
                """
            )
            program_path.write_text(
                """
                USE "../steps.gwt"

                REQUEST increase count
                  GIVEN count is number

                  WHEN increase count

                  OUTPUT count is number
                """
            )
            input_path.write_text('{"count": 1}\n')

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                allowed_status = main(
                    [
                        "capture",
                        str(program_path),
                        "--json-input",
                        str(input_path),
                        "--request",
                        "increase count",
                        "--import-root",
                        str(root),
                        "--no-absolute-imports",
                    ]
                )

            stderr = io.StringIO()
            with redirect_stderr(stderr):
                rejected_status = main(
                    [
                        "capture",
                        str(program_path),
                        "--json-input",
                        str(input_path),
                        "--request",
                        "increase count",
                        "--import-root",
                        str(rules),
                        "--no-absolute-imports",
                    ]
                )

            program_path.write_text(
                program_path.read_text().replace(
                    'USE "../steps.gwt"',
                    f'USE "{dependency_path}"',
                )
            )
            absolute_stderr = io.StringIO()
            with redirect_stderr(absolute_stderr):
                absolute_status = main(
                    [
                        "capture",
                        str(program_path),
                        "--json-input",
                        str(input_path),
                        "--request",
                        "increase count",
                        "--import-root",
                        str(root),
                        "--no-absolute-imports",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(allowed_status, 0)
        self.assertTrue(payload["program"]["importsDetected"])
        self.assertEqual(payload["result"]["count"], 2)
        self.assertEqual(rejected_status, 1)
        self.assertIn("USE import is outside allowed roots", stderr.getvalue())
        self.assertEqual(absolute_status, 1)
        self.assertIn("USE absolute import is not allowed", absolute_stderr.getvalue())

    def test_capture_cli_atomically_writes_output_that_round_trips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "vendor.execution-case.json"
            output_path.write_text("replace me")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(
                    [
                        "capture",
                        "examples/vendor_onboarding/rules.gwt",
                        "--json-input",
                        "examples/vendor_onboarding/request.json",
                        "--request",
                        "review vendor",
                        "--output",
                        str(output_path),
                    ]
                )

            rendered = output_path.read_text()
            loaded = load_execution_case(output_path)
            temporary_files = list(output_path.parent.glob(f".{output_path.name}.*.tmp"))

        self.assertEqual(status, 0)
        self.assertEqual(stdout.getvalue(), f"Wrote {output_path}\n")
        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(
            rendered,
            json.dumps(json.loads(rendered), indent=2, sort_keys=True) + "\n",
        )
        self.assertEqual(loaded.request_name, "review vendor")
        self.assertEqual(temporary_files, [])

    def test_execution_case_round_trips_through_typed_loader(self):
        input_state = json.loads(Path("examples/incident_triage/request.json").read_text())
        original = capture_execution_case(
            "examples/incident_triage/rules.gwt",
            input_state,
            request="triage incident",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "incident.execution-case.json"
            original.write(path)
            loaded = load_execution_case(path)

        self.assertIsInstance(loaded, ExecutionCase)
        self.assertEqual(loaded.request_name, "triage incident")
        self.assertEqual(loaded.input, input_state)
        self.assertEqual(loaded.result, original.result)
        self.assertIsNone(loaded.status)
        self.assertEqual(loaded.result["decision"]["status"], "page")
        self.assertEqual(loaded.as_payload(), original.as_payload())

    def test_execution_case_integrity_detects_changed_content(self):
        original = capture_execution_case(
            "examples/exact_pricing/rules.gwt",
            {
                "cart": {
                    "mode": "reserve",
                    "quantity": 2,
                    "unit_price": "12.30",
                    "total": "0.00",
                    "status": "pending",
                }
            },
            request="price cart",
        ).as_payload()
        changed = deepcopy(original)
        changed["result"]["cart"]["total"] = "0.01"

        with self.assertRaisesRegex(ValueError, "integrity digest mismatch"):
            ExecutionCase.from_payload(changed)

    def test_execution_case_integrity_is_canonical_and_schema_conforming(self):
        execution_case = capture_execution_case(
            "examples/incident_triage/rules.gwt",
            json.loads(Path("examples/incident_triage/request.json").read_text()),
            request="triage incident",
        )
        payload = execution_case.as_payload()

        self.assertEqual(
            payload["integrity"]["algorithm"],
            "gwt-execution-case-sha256-v1",
        )
        self.assertEqual(payload["integrity"]["scope"], "artifact-without-integrity")
        self.assertRegex(payload["integrity"]["digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(ExecutionCase.from_payload(payload).as_payload(), payload)

    def test_semantic_evidence_records_call_flow_and_evaluated_operands_across_domains(self):
        domains = [
            (
                "examples/vendor_onboarding/rules.gwt",
                "examples/vendor_onboarding/request.json",
                "review vendor",
                (
                    "decision.missing_document_count > 0 or "
                    "decision.expired_document_count > 0 or "
                    "decision.risk_points >= 6"
                ),
                {
                    "name": "decision.missing_document_count",
                    "valueType": "integer",
                    "value": 1,
                },
            ),
            (
                "examples/incident_triage/rules.gwt",
                "examples/incident_triage/request.json",
                "triage incident",
                (
                    "incident.customer_count >= 100 or "
                    "incident.revenue_at_risk or "
                    'incident.severity == "high"'
                ),
                {
                    "name": "incident.customer_count",
                    "valueType": "integer",
                    "value": 180,
                },
            ),
        ]

        for program, input_file, request, expression, expected_operand in domains:
            with self.subTest(request=request):
                payload = capture_execution_case(
                    program,
                    json.loads(Path(input_file).read_text()),
                    request=request,
                ).as_payload()
                active_calls = []
                behavior_facts = [
                    item for item in payload["evidence"]
                    if item["kind"] == "behavior"
                ]
                self.assertTrue(behavior_facts)
                for fact in behavior_facts:
                    self.assertIsNotNone(fact["source"])
                    if fact["phase"] == "enter":
                        self.assertEqual(fact["depth"], len(active_calls))
                        self.assertEqual(
                            fact["parentCallId"],
                            active_calls[-1] if active_calls else None,
                        )
                        active_calls.append(fact["callId"])
                    else:
                        self.assertEqual(fact["callId"], active_calls[-1])
                        self.assertEqual(fact["behaviorOutcome"], "completed")
                        active_calls.pop()
                self.assertEqual(active_calls, [])

                condition = next(
                    item for item in payload["evidence"]
                    if item["kind"] == "condition"
                    and item.get("expression") == expression
                    and item.get("result") is True
                )
                self.assertEqual(
                    condition["operands"],
                    {
                        "availability": "available",
                        "values": [expected_operand],
                    },
                )
                assertion_facts = [
                    item for item in payload["evidence"]
                    if item["kind"] == "assertion"
                ]
                self.assertTrue(assertion_facts)
                self.assertTrue(
                    all(
                        item["operands"]["availability"] == "available"
                        and item["operands"]["values"]
                        for item in assertion_facts
                    )
                )

    def test_program_identity_hashes_the_complete_import_closure(self):
        input_state = json.loads(Path("examples/checkout/request.json").read_text())
        payload = capture_execution_case(
            "examples/checkout/scenarios.gwt",
            input_state,
            request="checkout cart",
        ).as_payload()

        self.assertTrue(payload["program"]["importsDetected"])
        self.assertEqual(payload["program"]["hashScope"], "dependency-closure")
        self.assertTrue(payload["program"]["importsIncludedInHash"])
        self.assertEqual(payload["program"]["limitations"], [])
        self.assertEqual(payload["program"]["hash"], payload["program"]["identity"]["digest"])
        self.assertEqual(
            payload["program"]["identity"]["algorithm"],
            "gwt-program-closure-sha256-v1",
        )
        self.assertGreater(len(payload["program"]["identity"]["modules"]), 1)

    def test_evidence_sources_are_portable_logical_module_specifiers(self):
        def write_tree(root: Path) -> Path:
            root.mkdir()
            entry = root / "rules.gwt"
            entry.write_text(
                'USE "./steps.gwt"\n\n'
                "RECORD Input\n"
                "  value: integer\n"
                "  result: integer\n\n"
                "REQUEST double input\n"
                "  GIVEN input is Input\n"
                "  WHEN double input\n"
                "  OUTPUT input is Input\n"
                "  THEN input.result == 4\n"
            )
            (root / "steps.gwt").write_text(
                "WHEN double <input>\n"
                "  IF input.value > 0\n"
                "    set input.result to input.value * 2\n"
            )
            return entry

        with tempfile.TemporaryDirectory() as temp_dir:
            temporary_root = Path(temp_dir)
            first_entry = write_tree(temporary_root / "first-workstation")
            second_entry = write_tree(temporary_root / "second-workstation")
            first = capture_execution_case(
                first_entry,
                {"input": {"value": 2, "result": 0}},
                request="double input",
            ).as_payload()
            second = capture_execution_case(
                second_entry,
                {"input": {"value": 2, "result": 0}},
                request="double input",
            ).as_payload()

        def source_files(payload):
            evidence_files = [
                item["source"]["file"]
                for item in payload["evidence"]
                if item["source"] is not None
            ]
            change_files = [
                item["source"]["file"]
                for item in payload["stateChanges"]
                if item["source"] is not None
            ]
            return evidence_files + change_files

        first_sources = source_files(first)
        second_sources = source_files(second)
        self.assertEqual(first_sources, second_sources)
        self.assertEqual(set(first_sources), {"./rules.gwt", "./steps.gwt"})
        self.assertEqual(
            first["program"]["identity"],
            second["program"]["identity"],
        )
        self.assertNotIn(
            str(temporary_root),
            json.dumps(
                {
                    "evidence": first["evidence"],
                    "stateChanges": first["stateChanges"],
                }
            ),
        )

        invalid_source = deepcopy(first)
        invalid_source["evidence"][0]["source"]["file"] = "/tmp/rules.gwt"
        invalid_source["integrity"]["digest"] = execution_case_digest(
            invalid_source
        )
        with self.assertRaisesRegex(
            ValueError,
            "must name a program identity module or pseudo source",
        ):
            ExecutionCase.from_payload(invalid_source)

    def test_plain_text_explanation_is_domain_neutral(self):
        input_state = json.loads(Path("examples/vendor_onboarding/request.json").read_text())
        output = explain_json_file(
            "examples/vendor_onboarding/rules.gwt",
            input_state,
            request="review vendor",
        ).as_text()

        self.assertIn("review vendor completed", output)
        self.assertIn("Selected branches:", output)
        self.assertIn("DECIDE WHEN:", output)
        self.assertIn(
            "observed: decision.missing_document_count = 1 (integer)",
            output,
        )
        self.assertIn("Behavior calls:", output)
        self.assertIn("classify <decision> at ./rules.gwt", output)
        self.assertIn('decision.risk_points: 0 -> 10', output)
        self.assertNotIn("because:", output)
        self.assertNotIn("crossed the review threshold", output)

    def test_state_changes_start_after_effective_json_input_baseline(self):
        source = '''PROGRAM effective input baseline

REQUEST update account
  GIVEN account is any
  WHEN finish account
  OUTPUT account is any

WHEN finish <account>
  set account.status to "finished"

BACKGROUND
GIVEN account.status is "background"
AND account.count is 1
'''
        with tempfile.TemporaryDirectory() as temp_dir:
            program_path = Path(temp_dir) / "rules.gwt"
            program_path.write_text(source)

            payload = capture_execution_case(
                program_path,
                {"account": {"status": "submitted", "count": 2}},
                request="update account",
            ).as_payload()

        changes = payload["stateChanges"]
        self.assertEqual([change["path"] for change in changes], ["account.status"])
        self.assertEqual(changes[0]["before"], {"present": True, "value": "submitted"})
        self.assertEqual(changes[0]["after"], {"present": True, "value": "finished"})

    def test_capture_reads_each_program_module_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            entry = root / "rules.gwt"
            dependency = root / "steps.gwt"
            entry.write_text(
                'USE "./steps.gwt"\n\n'
                "RECORD Input\n"
                "  value: number\n\n"
                "REQUEST copy value\n"
                "  GIVEN request is Input\n"
                "  WHEN copy request\n"
                "  OUTPUT result is Input\n"
            )
            dependency.write_text(
                "WHEN copy <request>\n"
                "  set result.value to request.value\n"
            )
            reads: dict[Path, int] = {}
            original_read_bytes = Path.read_bytes

            def tracked_read_bytes(path: Path) -> bytes:
                resolved = path.resolve()
                if resolved in {entry.resolve(), dependency.resolve()}:
                    reads[resolved] = reads.get(resolved, 0) + 1
                return original_read_bytes(path)

            with patch.object(Path, "read_bytes", tracked_read_bytes):
                payload = capture_execution_case(
                    entry,
                    {"request": {"value": 4}},
                    request="copy value",
                ).as_payload()

        self.assertEqual(payload["result"], {"result": {"value": 4}})
        self.assertEqual(reads, {entry.resolve(): 1, dependency.resolve(): 1})

    def _assert_common_case(self, payload, request, input_state):
        self.assertEqual(payload["schemaVersion"], EXECUTION_CASE_SCHEMA_VERSION)
        self.assertEqual(payload["kind"], "gwt.execution-case")
        self.assertRegex(payload["program"]["hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(payload["program"]["hashScope"], "dependency-closure")
        self.assertTrue(payload["program"]["importsIncludedInHash"])
        self.assertEqual(payload["program"]["hash"], payload["program"]["identity"]["digest"])
        self.assertEqual(payload["program"]["limitations"], [])
        self.assertEqual(payload["versions"]["packageName"], PACKAGE_NAME)
        self.assertEqual(payload["versions"]["packageVersion"], current_package_version())
        self.assertEqual(payload["versions"]["languageSpecVersion"], LANGUAGE_SPEC_VERSION)
        self.assertEqual(payload["versions"]["payloadSchemaVersion"], PAYLOAD_SCHEMA_VERSION)
        self.assertEqual(payload["request"]["name"], request)
        self.assertEqual(payload["request"]["input"], input_state)
        self.assertEqual(payload["execution"]["outcome"], "completed")
        self.assertRegex(payload["execution"]["traceId"], r"^[0-9a-f]{32}$")
        self.assertTrue(re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+Z", payload["execution"]["capturedAt"]))
        self.assertEqual(
            [item["sequence"] for item in payload["evidence"]],
            sorted(item["sequence"] for item in payload["evidence"]),
        )
        self.assertEqual(
            [item["sequence"] for item in payload["stateChanges"]],
            sorted(item["sequence"] for item in payload["stateChanges"]),
        )
        self.assertTrue(all(item["source"] is not None for item in payload["evidence"]))
        self.assertEqual(payload["redaction"]["mode"], "none")
        self.assertTrue(payload["redaction"]["valuesIncluded"])
        self.assertRegex(payload["integrity"]["digest"], r"^sha256:[0-9a-f]{64}$")
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
