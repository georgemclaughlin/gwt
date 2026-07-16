from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from gwtlang import GwtClient, load_case_corpus
from gwtlang.comparison import compare_execution_cases
from gwtlang.execution_case import capture_execution_case


ROOT = Path(__file__).resolve().parents[1]
DFE_PILOT = ROOT / "examples/external_pilots/dfe_npq_funding_eligibility"
DFE_RULES = DFE_PILOT / "rules.gwt"
DFE_SLICE = DFE_PILOT / "exact_status_slice.json"
DFE_REQUEST = "assess funding eligibility"
SEMANTIC_PILOT = ROOT / "examples/external_pilots/semantic_release_commit_analyzer"
SEMANTIC_RULES = SEMANTIC_PILOT / "rules.gwt"
SEMANTIC_REQUEST = "analyze normalized commit"
SEMANTIC_CONFORMANCE = SEMANTIC_PILOT / "conformance_cases.json"
SEMANTIC_RUNNER = SEMANTIC_PILOT / "run_conformance.py"
SEMANTIC_EVIDENCE_DEMO = SEMANTIC_PILOT / "served_evidence_demo.py"
SEMANTIC_EVALUATED_REQUEST = SEMANTIC_PILOT / "evaluated-request.json"
SEMANTIC_EVALUATED_PROVENANCE = SEMANTIC_PILOT / "evaluated-fact-provenance.json"
SEMANTIC_EVALUATED_REQUEST_NAME = "select release from evaluated rules"
SPREE_PILOT = ROOT / "examples/external_pilots/spree_item_total"
SPREE_RULES = SPREE_PILOT / "rules.gwt"
SPREE_SLICE = SPREE_PILOT / "oracle_slice.json"
SPREE_REQUEST = "assess item total eligibility"


class ExternalPilotRegressionTests(unittest.TestCase):
    def test_spree_openapi_preserves_exact_and_optional_decimal_boundary(self):
        openapi = GwtClient(SPREE_RULES).openapi().as_payload()
        operation = openapi["paths"][
            "/requests/assess-item-total-eligibility"
        ]["post"]
        schemas = openapi["components"]["schemas"]
        facts = schemas["ItemTotalFacts"]

        self.assertEqual(operation["operationId"], "assessItemTotalEligibility")
        self.assertEqual(
            operation["requestBody"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/AssessItemTotalEligibilityRequest"},
        )
        self.assertNotIn("amount_max", facts["required"])
        self.assertIn({"type": "null"}, facts["properties"]["amount_max"]["anyOf"])
        decimal_input = facts["properties"]["amount_min"]
        self.assertEqual(
            [branch["type"] for branch in decimal_input["anyOf"]],
            ["string", "integer"],
        )
        self.assertEqual(decimal_input["x-gwt-json-input"], "decimal string or integer")
        self.assertEqual(decimal_input["x-gwt-json-output"], "decimal string")

    def test_commit_analyzer_host_evaluated_openapi_contract_is_closed(self):
        openapi = GwtClient(SEMANTIC_RULES).openapi().as_payload()
        operation = openapi["paths"][
            "/requests/select-release-from-evaluated-rules"
        ]["post"]
        schemas = openapi["components"]["schemas"]

        self.assertEqual(operation["operationId"], "selectReleaseFromEvaluatedRules")
        self.assertEqual(
            operation["requestBody"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/SelectReleaseFromEvaluatedRulesRequest"},
        )
        self.assertEqual(
            operation["responses"]["200"]["content"]["application/json"]["schema"],
            {"$ref": "#/components/schemas/SelectReleaseFromEvaluatedRulesOutput"},
        )
        self.assertEqual(
            schemas["SelectReleaseFromEvaluatedRulesRequest"],
            {
                "type": "object",
                "properties": {
                    "evaluations": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/RuleEvaluation"},
                    }
                },
                "required": ["evaluations"],
                "additionalProperties": False,
            },
        )
        self.assertEqual(schemas["RuleEvaluation"]["required"], ["id", "matched", "release"])
        self.assertFalse(schemas["RuleEvaluation"]["additionalProperties"])
        self.assertEqual(
            schemas["ReleaseOutcome"]["enum"],
            [
                "major",
                "premajor",
                "minor",
                "preminor",
                "patch",
                "prepatch",
                "prerelease",
                "false",
                "null",
                "undefined",
            ],
        )

    def test_commit_analyzer_conformance_slice_retains_parity_and_known_gaps(self):
        fixture = json.loads(SEMANTIC_CONFORMANCE.read_text())
        self.assertEqual(
            fixture["source"]["commit"],
            "f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758",
        )
        self.assertEqual(len(fixture["cases"]), 20)
        self.assertEqual(
            Counter(case["classification"] for case in fixture["cases"]),
            {"exact_parity": 18, "known_boundary_gap": 2},
        )
        for case in fixture["cases"]:
            self.assertEqual(len(case["host_matches"]), len(case["rules"]))

        completed = subprocess.run(
            [sys.executable, str(SEMANTIC_RUNNER)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("direct exact upstream/GWT parity: 18/18", completed.stdout)
        self.assertIn("direct documented boundary gaps: 2/2", completed.stdout)
        self.assertIn("host-adapter upstream/GWT parity: 20/20", completed.stdout)

    def test_commit_analyzer_host_match_facts_have_declared_provenance(self):
        request = json.loads(SEMANTIC_EVALUATED_REQUEST.read_text())
        provenance = json.loads(SEMANTIC_EVALUATED_PROVENANCE.read_text())
        execution_case = capture_execution_case(
            SEMANTIC_RULES,
            request,
            request=SEMANTIC_EVALUATED_REQUEST_NAME,
            fact_provenance=provenance,
        )
        self.assertEqual(
            execution_case.fact_provenance,
            [
                {
                    "path": "evaluations",
                    "source": "host commit matcher: micromatch-backed RuleEvaluation facts",
                    "description": (
                        "Ordered rule outcomes after the adapter applies breaking/revert "
                        "gates and micromatch criteria; GWT owns only release selection."
                    ),
                }
            ],
        )

    def test_commit_analyzer_served_evidence_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "evidence"
            completed = subprocess.run(
                [sys.executable, str(SEMANTIC_EVIDENCE_DEMO), str(output_dir)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            corpus = load_case_corpus(output_dir / "corpus.json")
            comparison = json.loads((output_dir / "comparison.json").read_text())
            workbench = (output_dir / "workbench.html").read_text()
            candidate = (output_dir / "candidate-rules.gwt").read_text()
            loaded_cases = corpus.cases

        self.assertIn("served Execution Cases captured: 20/20", completed.stdout)
        self.assertIn("candidate comparisons changed: 3/20", completed.stdout)
        self.assertIn(f"Wrote {output_dir / 'corpus.json'}", completed.stdout)
        self.assertIn(f"OK {output_dir / 'corpus.json'}", completed.stdout)
        self.assertEqual(corpus.as_payload()["kind"], "gwt.case-corpus")
        self.assertEqual(len(corpus.entries), 20)
        self.assertEqual(len(loaded_cases), 20)
        self.assertEqual(len({entry.case_id for entry in corpus.entries}), 20)
        for entry, execution_case in zip(corpus.entries, loaded_cases):
            self.assertEqual(
                execution_case.as_payload()["integrity"]["digest"],
                entry.case_id,
            )
            self.assertEqual(
                execution_case.fact_provenance[0]["path"],
                "evaluations",
            )
        self.assertEqual(comparison["totals"]["cases"], 20)
        self.assertEqual(comparison["totals"]["unchanged"], 17)
        self.assertEqual(comparison["totals"]["outputChanged"], 3)
        self.assertEqual(
            {
                item["reference"]
                for item in comparison["cases"]
                if item["classification"] != "unchanged"
            },
            {"patch-then-minor", "minor-then-patch", "prerelease-ladder"},
        )
        self.assertIn("Local evidence lifecycle demo", workbench)
        self.assertIn("IF rank < result.release_rank", candidate)

    def test_seeded_fact_provenance_sidecars_match_declared_pilot_inputs(self):
        pilots = (
            (DFE_PILOT, DFE_RULES, DFE_REQUEST),
            (SEMANTIC_PILOT, SEMANTIC_RULES, SEMANTIC_REQUEST),
            (SPREE_PILOT, SPREE_RULES, SPREE_REQUEST),
        )
        for pilot, rules, request_name in pilots:
            with self.subTest(pilot=pilot.name):
                request = json.loads((pilot / "request.json").read_text())
                provenance = json.loads(
                    (pilot / "fact-provenance.json").read_text()
                )
                execution_case = capture_execution_case(
                    rules,
                    request,
                    request=request_name,
                    fact_provenance=provenance,
                )
                self.assertEqual(
                    [item["path"] for item in execution_case.fact_provenance],
                    sorted(provenance),
                )

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
