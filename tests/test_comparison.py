from __future__ import annotations

from dataclasses import FrozenInstanceError
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gwtlang.comparison import (
    COMPARISON_SCHEMA_VERSION,
    ComparisonResult,
    compare_execution_cases,
)
from gwtlang.execution_case import (
    ExecutionCase,
    ExecutionCaseCapturePolicy,
    capture_execution_case,
    execution_case_digest,
)


class ComparisonTests(unittest.TestCase):
    def test_unchanged_and_output_changed_reconcile_and_diff_recursively(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(
                root / "new.gwt",
                high_status="rejected",
                high_reasons=("high", "manual"),
            )
            low_case = self._capture(old, 2)
            high_case = self._capture(old, 12)

            result = compare_execution_cases(old, new, [low_case, high_case])

        self.assertIsInstance(result, ComparisonResult)
        self.assertEqual(
            [case.classification for case in result.cases],
            ["unchanged", "output_changed"],
        )
        self.assertEqual(
            [case.id for case in result.cases],
            ["case-0001-decide", "case-0002-decide"],
        )
        self.assertEqual(result.totals.cases, 2)
        self.assertEqual(result.totals.unchanged, 1)
        self.assertEqual(result.totals.output_changed, 1)
        self.assertEqual(self._classified_total(result), result.totals.cases)

        differences = result.cases[1].output_differences
        self.assertEqual(
            [difference.path for difference in differences],
            ["/decision/reasons/1", "/decision/status"],
        )
        self.assertFalse(differences[0].old.present)
        self.assertEqual(differences[0].new.value, "manual")
        self.assertEqual(differences[1].old.value, "review")
        self.assertEqual(differences[1].new.value, "rejected")
        self.assertIsNotNone(differences[0].new_last_change_source)
        self.assertIsNotNone(differences[1].old_last_change_source)
        self.assertIsNotNone(differences[1].new_last_change_source)
        assert differences[1].new_last_change_source is not None
        self.assertIn(
            "set decision.status",
            differences[1].new_last_change_source.text,
        )

        payload = result.as_payload()
        self.assertEqual(payload["schemaVersion"], COMPARISON_SCHEMA_VERSION)
        self.assertEqual(payload["kind"], "gwt.comparison")
        self.assertRegex(payload["oldProgram"]["hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(payload["newProgram"]["hash"], r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("traceId", str(payload))
        self.assertNotIn("capturedAt", str(payload))
        if importlib.util.find_spec("jsonschema") is not None:
            from jsonschema import Draft202012Validator

            schema = json.loads(Path("docs/schemas/comparison.schema.json").read_text())
            Draft202012Validator(schema).validate(payload)
        text = result.as_text()
        self.assertIn("2 cases compared", text)
        self.assertIn("/decision/status: \"review\" -> \"rejected\"", text)

    def test_same_output_with_changed_decision_evidence_is_path_changed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(root / "new.gwt", high_condition="request.value > 9")
            execution_case = self._capture(old, 12)

            result = compare_execution_cases(old, new, [execution_case])

        compared = result.cases[0]
        self.assertEqual(compared.classification, "path_changed")
        self.assertEqual(compared.output_differences, ())
        self.assertNotEqual(compared.old_evidence_digest, compared.new_evidence_digest)
        self.assertTrue(compared.old_evaluated_conditions)
        self.assertTrue(compared.new_evaluated_conditions)
        self.assertEqual(
            compared.old_evaluated_conditions[-1].expression,
            "request.value >= 10",
        )
        self.assertEqual(
            compared.new_evaluated_conditions[-1].expression,
            "request.value > 9",
        )
        self.assertIsNotNone(compared.new_evaluated_conditions[-1].source)
        assert compared.old_selected_decision is not None
        assert compared.new_selected_decision is not None
        self.assertEqual(
            compared.old_selected_decision.condition,
            "request.value >= 10",
        )
        self.assertEqual(
            compared.new_selected_decision.condition,
            "request.value > 9",
        )
        assert compared.old_selected_decision.source is not None
        assert compared.new_selected_decision.source is not None
        self.assertEqual(compared.old_selected_decision.source.file, "./old.gwt")
        self.assertEqual(compared.new_selected_decision.source.file, "./new.gwt")
        self.assertIn("old decision: request.value >= 10", result.as_text())

    def test_changed_old_closure_is_a_baseline_mismatch_without_candidate_attribution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(root / "new.gwt")
            execution_case = self._capture(old, 12)
            old.write_text(old.read_text() + "\n# changed after capture\n")

            result = compare_execution_cases(old, new, [execution_case])

        compared = result.cases[0]
        self.assertEqual(compared.classification, "baseline_mismatch")
        assert compared.detail is not None
        self.assertIn("hash does not match", compared.detail)
        self.assertIsNone(compared.old_evidence_digest)
        self.assertIsNone(compared.new_evidence_digest)
        self.assertEqual(result.totals.baseline_mismatch, 1)

    def test_tampered_material_evidence_is_a_baseline_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(root / "new.gwt", high_status="rejected")
            payload = self._capture(old, 12).as_payload()
            condition = next(
                item
                for item in payload["evidence"]
                if item["kind"] == "condition"
                and item["operands"]["availability"] == "available"
            )
            condition["operands"]["values"][0]["value"] = 999
            payload["integrity"]["digest"] = execution_case_digest(payload)
            tampered = ExecutionCase.from_payload(payload)

            result = compare_execution_cases(old, new, [tampered])

        compared = result.cases[0]
        self.assertEqual(compared.classification, "baseline_mismatch")
        self.assertIn("material execution evidence", compared.detail or "")
        self.assertNotEqual(
            compared.captured_evidence_digest,
            compared.old_evidence_digest,
        )
        self.assertIsNone(compared.new_evidence_digest)

    def test_capture_time_and_trace_identity_are_not_material_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            payload = self._capture(old, 12).as_payload()
            payload["execution"]["traceId"] = "0" * 32
            payload["execution"]["capturedAt"] = "2000-01-01T00:00:00Z"
            payload["integrity"]["digest"] = execution_case_digest(payload)

            result = compare_execution_cases(
                old,
                old,
                [ExecutionCase.from_payload(payload)],
            )

        self.assertEqual(result.cases[0].classification, "unchanged")

    def test_previously_successful_case_becoming_runtime_error_is_new_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(root / "new.gwt", require="request.value < 0")
            execution_case = self._capture(old, 12)

            result = compare_execution_cases(old, new, [execution_case])

        compared = result.cases[0]
        self.assertEqual(compared.classification, "new_failure")
        self.assertIsNotNone(compared.new_error)
        assert compared.new_error is not None
        self.assertEqual(compared.new_error.kind, "GwtError")
        self.assertIn("requirement failed", compared.new_error.message)
        assert compared.new_error.source is not None
        self.assertEqual(compared.new_error.source.file, "./new.gwt")
        self.assertNotIn(str(Path(temp_dir).resolve()), str(compared.as_payload()))
        self.assertIn("new error:", result.as_text())

    def test_previously_failing_case_that_completes_is_resolved_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt", require="request.value < 0")
            new = self._write_program(root / "new.gwt")
            failed = capture_execution_case(
                old,
                {"request": {"value": 12}},
                request="decide",
                policy=ExecutionCaseCapturePolicy(on_error="record"),
            )

            result = compare_execution_cases(old, new, [failed])

        compared = result.cases[0]
        self.assertEqual(compared.classification, "resolved_failure")
        self.assertIsNotNone(compared.old_error)
        self.assertIsNone(compared.new_error)
        self.assertEqual(compared.output_differences, ())
        self.assertIn("does not imply approval", compared.detail or "")
        self.assertEqual(result.totals.resolved_failure, 1)
        self._validate_schema(result)

    def test_identical_failure_is_unchanged_and_changed_failure_is_separate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt", require="request.value < 0")
            same = self._write_program(root / "same.gwt", require="request.value < 0")
            changed = self._write_program(
                root / "changed.gwt",
                require="request.value < -10",
            )
            failed = capture_execution_case(
                old,
                {"request": {"value": 12}},
                request="decide",
                policy=ExecutionCaseCapturePolicy(on_error="record"),
            )

            unchanged = compare_execution_cases(old, same, [failed])
            failure_changed = compare_execution_cases(old, changed, [failed])

        self.assertEqual(unchanged.cases[0].classification, "unchanged")
        self.assertIsNotNone(unchanged.cases[0].old_error)
        self.assertIsNotNone(unchanged.cases[0].new_error)
        self.assertEqual(
            failure_changed.cases[0].classification,
            "failure_changed",
        )
        self._validate_schema(unchanged)
        self._validate_schema(failure_changed)

    def test_tampered_captured_failure_stops_before_candidate_attribution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt", require="request.value < 0")
            new = self._write_program(root / "new.gwt")
            payload = capture_execution_case(
                old,
                {"request": {"value": 12}},
                request="decide",
                policy=ExecutionCaseCapturePolicy(on_error="record"),
            ).as_payload()
            payload["execution"]["error"]["message"] = "different failure"
            payload["integrity"]["digest"] = execution_case_digest(payload)

            result = compare_execution_cases(
                old,
                new,
                [ExecutionCase.from_payload(payload)],
            )

        self.assertEqual(result.cases[0].classification, "baseline_mismatch")
        self.assertIn("failure does not reproduce", result.cases[0].detail or "")
        self.assertIsNone(result.cases[0].new_evidence_digest)

    def test_missing_request_is_incompatible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(root / "new.gwt", request_name="decide revised")
            execution_case = self._capture(old, 12)

            result = compare_execution_cases(old, new, [execution_case])

        compared = result.cases[0]
        self.assertEqual(compared.classification, "incompatible")
        assert compared.new_error is not None
        self.assertIn("unknown request: decide", compared.new_error.message)
        assert compared.new_error.source is not None
        self.assertEqual(compared.new_error.source.file, "<request>")
        self.assertEqual(result.totals.incompatible, 1)

    def test_changed_request_contract_is_incompatible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(root / "new.gwt", input_type="text")
            execution_case = self._capture(old, 12)

            result = compare_execution_cases(old, new, [execution_case])

        compared = result.cases[0]
        self.assertEqual(compared.classification, "incompatible")
        assert compared.new_error is not None
        self.assertIn("REQUEST contract failed", compared.new_error.message)
        self.assertEqual(result.totals.incompatible, 1)

    def test_candidate_output_contract_failure_is_new_failure_not_input_incompatibility(self):
        base = '''PROGRAM output contract comparison

RECORD Input
  value: integer

RECORD Decision
  value: integer

REQUEST decide
  GIVEN request is Input
  GIVEN decision is Decision
    value: 0
  WHEN compute request into decision
  OUTPUT decision is Decision

WHEN compute <request> into <decision>
  GIVEN request is Input
  AND decision is Decision
  set decision.value to request.value
'''
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = root / "old.gwt"
            new = root / "new.gwt"
            old.write_text(base)
            new.write_text(
                base.replace(
                    "  set decision.value to request.value\n",
                    "  set decision.value to request.value\n"
                    "  set decision.extra to 1\n",
                )
            )
            execution_case = capture_execution_case(
                old,
                {"request": {"value": 4}},
                request="decide",
            )

            result = compare_execution_cases(old, new, [execution_case])

        compared = result.cases[0]
        self.assertEqual(compared.classification, "new_failure")
        self.assertIsNotNone(compared.new_error)
        assert compared.new_error is not None
        self.assertIn("OUTPUT contract failed", compared.new_error.message)

    def test_runtime_error_text_cannot_spoof_contract_incompatibility(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(
                root / "new.gwt",
                require=(
                    'request.value < 0 or "request contract failed" == "never"'
                ),
            )

            result = compare_execution_cases(
                old,
                new,
                [self._capture(old, 12)],
            )

        self.assertEqual(result.cases[0].classification, "new_failure")

    def test_result_and_nested_values_are_immutable_by_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(root / "new.gwt", high_status="rejected")
            result = compare_execution_cases(old, new, [self._capture(old, 12)])

        with self.assertRaises(FrozenInstanceError):
            result.old_program_hash = "changed"  # pyright: ignore[reportAttributeAccessIssue]
        first_payload = result.as_payload()
        first_payload["cases"][0]["outputDifferences"][0]["new"]["value"] = "mutated"
        self.assertNotEqual(first_payload, result.as_payload())

    def test_comparison_freezes_each_side_once_for_a_lazy_corpus(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(root / "new.gwt", high_status="rejected")
            cases = [self._capture(old, 12), self._capture(old, 15)]
            reads: dict[Path, int] = {}
            original_read_bytes = Path.read_bytes

            def tracked_read_bytes(path: Path) -> bytes:
                resolved = path.resolve()
                if resolved in {old.resolve(), new.resolve()}:
                    reads[resolved] = reads.get(resolved, 0) + 1
                return original_read_bytes(path)

            def lazy_cases():
                yield cases[0]
                self._write_program(new, high_status="review")
                yield cases[1]

            with (
                patch.object(Path, "read_bytes", tracked_read_bytes),
                patch(
                    "gwtlang.execution_case.load_program_snapshot",
                    side_effect=AssertionError("comparison reloaded a program"),
                ),
            ):
                result = compare_execution_cases(old, new, lazy_cases())

        self.assertEqual(
            [case.classification for case in result.cases],
            ["output_changed", "output_changed"],
        )
        self.assertEqual(reads, {old.resolve(): 1, new.resolve(): 1})

    @staticmethod
    def _capture(program: Path, value: int) -> ExecutionCase:
        return capture_execution_case(
            program,
            {"request": {"value": value}},
            request="decide",
        )

    @staticmethod
    def _write_program(
        path: Path,
        *,
        high_condition: str = "request.value >= 10",
        high_status: str = "review",
        high_reasons: tuple[str, ...] = ("high",),
        request_name: str = "decide",
        input_type: str = "number",
        require: str | None = None,
    ) -> Path:
        lines = [
            "PROGRAM comparison",
            "",
            "RECORD Input",
            f"  value: {input_type}",
            "",
            "RECORD Decision",
            "  status: text",
            "  reasons: list<text>",
            "",
            f"REQUEST {request_name}",
            "  GIVEN request is Input",
            "  GIVEN decision is Decision",
            '    status: "new"',
            "    reasons: []",
            "  WHEN classify request into decision",
            "  OUTPUT decision is Decision",
            "",
            "WHEN classify <request> into <decision>",
            "  GIVEN request is Input",
            "  AND decision is Decision",
        ]
        if require is not None:
            lines.append(f"  REQUIRE {require}")
        lines.extend(
            [
                "  DECIDE",
                f"    WHEN {high_condition}",
                f'      set decision.status to "{high_status}"',
                *(
                    f'      append "{reason}" to decision.reasons'
                    for reason in high_reasons
                ),
                "    ELSE",
                '      set decision.status to "approved"',
                '      append "low" to decision.reasons',
            ]
        )
        path.write_text("\n".join(lines) + "\n")
        return path

    @staticmethod
    def _classified_total(result: ComparisonResult) -> int:
        totals = result.totals
        return (
            totals.unavailable
            + totals.baseline_mismatch
            + totals.unchanged
            + totals.path_changed
            + totals.output_changed
            + totals.new_failure
            + totals.resolved_failure
            + totals.failure_changed
            + totals.incompatible
        )

    @staticmethod
    def _validate_schema(result: ComparisonResult) -> None:
        if importlib.util.find_spec("jsonschema") is None:
            return
        from jsonschema import Draft202012Validator

        schema = json.loads(Path("docs/schemas/comparison.schema.json").read_text())
        Draft202012Validator(schema).validate(result.as_payload())


if __name__ == "__main__":
    unittest.main()
