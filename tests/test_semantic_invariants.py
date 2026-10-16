"""Cross-layer invariants over real programs, independent of source formatting."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from gwtlang import compile_text
from gwtlang.execution_case import capture_execution_case
from gwtlang.formatter import format_text
from gwtlang.runtime import _cached_literal_union_values, _literal_union_values, GwtError
from gwtlang.scenario_generation import generate_scenario


class SemanticInvariantTests(unittest.TestCase):
    def test_formatting_preserves_request_results_across_rule_revisions(self):
        inputs = [
            {"facts": {"days": days, "damaged": damaged, "receipt": receipt, "clearance": clearance, "member": member}}
            for days in (30, 31, 45, 46)
            for damaged, receipt, clearance, member in (
                (False, True, False, False), (False, True, False, True),
                (True, False, False, False), (True, True, True, False),
            )
        ]
        for path in sorted(Path("examples/refund_review").glob("*.gwt")):
            source = path.read_text().replace("PROGRAM ", "PROGRAM   ").replace("GIVEN ", "GIVEN   ")
            original = compile_text(source)
            formatted = compile_text(format_text(source))
            for value in inputs:
                before = deepcopy(value)
                self.assertEqual(original.run_json(value, request="assess refund").as_payload()["result"], formatted.run_json(value, request="assess refund").as_payload()["result"])
                self.assertEqual(value, before)

    def test_exact_decimal_capture_scenario_replay_preserves_boundary_values(self):
        source = '''PROGRAM exact boundary
RECORD Facts
  amount: decimal
REQUEST assess amount
  GIVEN facts is Facts
  GIVEN accepted is false
  WHEN assess facts into accepted
  OUTPUT accepted is boolean
WHEN assess <facts> into <accepted>
  GIVEN facts is Facts
  AND accepted is boolean
  IF facts.amount >= 0.30
    set accepted to true
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.gwt"
            path.write_text(format_text(source))
            for value, expected in (("0.2999999999999999999999999999", False), ("0.30", True), ("0.3000000000000000000000000001", True)):
                case = capture_execution_case(path, {"facts": {"amount": value}}, request="assess amount")
                self.assertEqual(case.result["accepted"], expected)
                generated = generate_scenario(case.as_payload(), path)
                self.assertEqual(format_text(generated.source), generated.source)

    def test_union_cache_is_bounded_and_cannot_retain_oversized_type_text(self):
        _cached_literal_union_values.cache_clear()
        try:
            for index in range(300):
                self.assertEqual(_literal_union_values(f'"value {index}" | "other"'), (f"value {index}", "other"))
            self.assertLessEqual(_cached_literal_union_values.cache_info().currsize, 256)
            before = _cached_literal_union_values.cache_info()
            huge = "x" * 5000
            self.assertEqual(_literal_union_values(f'"{huge}" | "other"'), (huge, "other"))
            self.assertEqual(_cached_literal_union_values.cache_info(), before)
            self.assertEqual(_literal_union_values('"a|b" | "c"'), ("a|b", "c"))
            self.assertEqual(_literal_union_values("0.30 | 0.31"), (Decimal("0.30"), Decimal("0.31")))
            self.assertIsNone(_literal_union_values('"one" | 1'))
        finally:
            _cached_literal_union_values.cache_clear()

    def test_cached_type_validation_keeps_request_values_and_diagnostics_independent(self):
        source = '''REQUEST echo status
  GIVEN status is "yes" | "no"
  WHEN keep status
  OUTPUT status is "yes" | "no"
WHEN keep <status>
  PASS
'''
        program = compile_text(source)
        for value in ("yes", "no", "yes"):
            self.assertEqual(program.run_json({"status": value}, request="echo status").as_payload()["result"], {"status": value})
        with self.assertRaises(GwtError):
            program.run_json({"status": "maybe"}, request="echo status")
