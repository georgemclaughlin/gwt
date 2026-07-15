from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from gwtlang import GwtClient
from gwtlang.comparison import compare_execution_cases
from gwtlang.execution_case import capture_execution_case


ROOT = Path(__file__).resolve().parents[1]
DFE_PILOT = ROOT / "examples/external_pilots/dfe_npq_funding_eligibility"
DFE_RULES = DFE_PILOT / "rules.gwt"
DFE_SLICE = DFE_PILOT / "exact_status_slice.json"
DFE_REQUEST = "assess funding eligibility"
SPREE_PILOT = ROOT / "examples/external_pilots/spree_item_total"
SPREE_RULES = SPREE_PILOT / "rules.gwt"
SPREE_SLICE = SPREE_PILOT / "oracle_slice.json"
SPREE_REQUEST = "assess item total eligibility"


class ExternalPilotRegressionTests(unittest.TestCase):
    def test_spree_pinned_oracle_snapshot_retains_exact_boundary_results(self):
        fixture = json.loads(SPREE_SLICE.read_text())
        self.assertEqual(
            fixture["source"]["commit"],
            "249dbf3c68461288f8444d754bcf27d0fa962250",
        )
        compiled = GwtClient(SPREE_RULES).compile(
            import_roots=[SPREE_RULES.parent],
            allow_absolute_imports=False,
        )

        for case in fixture["cases"]:
            with self.subTest(case=case["id"]):
                facts = dict(case["facts"])
                has_maximum = facts.pop("has_maximum")
                if not has_maximum:
                    facts.pop("amount_max")
                result = compiled.run_json(
                    {"facts": facts},
                    request=SPREE_REQUEST,
                )
                self.assertEqual(
                    result.as_payload()["result"]["decision"],
                    case["expected"],
                )

    def test_dfe_pinned_oracle_snapshot_retains_exact_status_parity(self):
        fixture = self._dfe_fixture()
        compiled = GwtClient(DFE_RULES).compile(
            import_roots=[DFE_RULES.parent],
            allow_absolute_imports=False,
        )

        for case, request in self._dfe_requests(fixture):
            with self.subTest(case=case["id"]):
                result = compiled.run_json(request, request=DFE_REQUEST)
                decision = result.as_payload()["result"]["decision"]
                self.assertEqual(decision, case["expected"])

    def test_dfe_seeded_precedence_error_stays_visible_beyond_coarse_outcome(self):
        fixture = self._dfe_fixture()
        requests = list(self._dfe_requests(fixture))
        cases = [
            capture_execution_case(DFE_RULES, request, request=DFE_REQUEST)
            for _, request in requests
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "candidate.gwt"
            candidate.write_text(self._seeded_dfe_candidate())
            comparison = compare_execution_cases(DFE_RULES, candidate, cases)

        classifications = Counter(
            case.classification for case in comparison.cases
        )
        self.assertEqual(
            classifications,
            {"output_changed": 1, "path_changed": 11},
        )
        changed = next(
            case
            for case in comparison.cases
            if case.classification == "output_changed"
        )
        changed_paths = {difference.path for difference in changed.output_differences}
        self.assertEqual(
            changed_paths,
            {"/decision/status_code", "/decision/description"},
        )
        changed_values = {
            difference.path: (difference.old.value, difference.new.value)
            for difference in changed.output_differences
        }
        self.assertEqual(
            changed_values["/decision/status_code"],
            ("unfunded_cohort", "not_in_england"),
        )

    @staticmethod
    def _dfe_fixture() -> dict[str, object]:
        fixture = json.loads(DFE_SLICE.read_text())
        assert fixture["source"]["commit"] == (
            "f3601047213660121a5b8e0850c8ecef798f8e03"
        )
        return fixture

    @staticmethod
    def _dfe_requests(fixture: dict[str, object]):
        defaults = fixture["defaults"]
        assert isinstance(defaults, dict)
        cases = fixture["cases"]
        assert isinstance(cases, list)
        for case in cases:
            assert isinstance(case, dict)
            facts = {**defaults, **case["input_overrides"]}
            yield case, {"facts": facts}

    @staticmethod
    def _seeded_dfe_candidate() -> str:
        source = DFE_RULES.read_text()
        original = '''    WHEN facts.cohort_funded == false
      record status "unfunded_cohort" outcome "not_funded" description "unfunded_cohort" into decision
    WHEN facts.inside_catchment == false
      record status "not_in_england" outcome "not_funded" description "outside_catchment" into decision
'''
        mutated = '''    WHEN facts.inside_catchment == false
      record status "not_in_england" outcome "not_funded" description "outside_catchment" into decision
    WHEN facts.cohort_funded == false
      record status "unfunded_cohort" outcome "not_funded" description "unfunded_cohort" into decision
'''
        if source.count(original) != 1:
            raise AssertionError("DfE seeded mutation target drifted")
        return source.replace(original, mutated, 1)


if __name__ == "__main__":
    unittest.main()
