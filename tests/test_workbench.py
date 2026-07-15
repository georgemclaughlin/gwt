from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from gwtlang.comparison import compare_execution_cases
from gwtlang.execution_case import (
    ExecutionCase,
    ExecutionCaseCapturePolicy,
    capture_execution_case,
)
from gwtlang.workbench import render_workbench_html


class WorkbenchRendererTests(unittest.TestCase):
    def test_renders_host_fact_provenance_without_treating_it_as_verified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = self._write_program(Path(temp_dir) / "rules.gwt")
            execution_case = capture_execution_case(
                program,
                {"request": {"value": 12, "note": "fixture"}},
                request="review item",
                fact_provenance={
                    "request.value": {
                        "source": "orders-service#normalized-score",
                        "description": "Derived from the host's current order.",
                    }
                },
            )

            rendered = render_workbench_html(execution_case)

        self.assertIn("Host fact provenance", rendered)
        self.assertIn("request.value", rendered)
        self.assertIn("orders-service#normalized-score", rendered)
        self.assertIn("Derived from the host&#x27;s current order.", rendered)
        self.assertIn("Host-supplied, unauthenticated metadata", rendered)
        match = re.search(
            r'<script type="application/json" id="gwt-dossier-data">(.*?)</script>',
            rendered,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        assert match is not None
        embedded = json.loads(match.group(1))
        self.assertEqual(
            embedded["executionCase"]["factProvenance"],
            execution_case.as_payload()["factProvenance"],
        )

    def test_marks_fact_provenance_omitted_without_leaking_descriptions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = self._write_program(Path(temp_dir) / "rules.gwt")
            execution_case = capture_execution_case(
                program,
                {"request": {"value": 12, "note": "fixture"}},
                request="review item",
                fact_provenance={
                    "request.value": {
                        "source": "sensitive host source",
                        "description": "sensitive derivation detail",
                    }
                },
                policy=ExecutionCaseCapturePolicy(values="omit"),
            )

            rendered = render_workbench_html(execution_case)

        self.assertIn("Host fact provenance", rendered)
        self.assertIn("Host fact provenance was omitted by the capture policy", rendered)
        self.assertIn('<span class="count-chip">omitted</span>', rendered)
        self.assertNotIn("sensitive host source", rendered)
        self.assertNotIn("sensitive derivation detail", rendered)

    def test_renders_exact_case_facts_and_verified_scenario(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = self._write_program(Path(temp_dir) / "rules.gwt")
            execution_case = self._capture(program)
            scenario = '''SCENARIO captured review
GIVEN request is Input
  value: 12
REQUEST review item
THEN decision.status == "needs_review"
'''

            rendered = render_workbench_html(
                execution_case,
                verified_scenario=scenario,
            )

        payload = execution_case.as_payload()
        self.assertIn("Behavior review dossier", rendered)
        self.assertIn("review item", rendered)
        self.assertIn(payload["program"]["hash"], rendered)
        self.assertIn("needs_review", rendered)
        self.assertIn("threshold_reached", rendered)
        self.assertIn("request.value &gt;= 10", rendered)
        self.assertIn("Evidence timeline", rendered)
        self.assertIn(">behavior<", rendered)
        self.assertIn("Call ID", rendered)
        self.assertIn("Operands", rendered)
        self.assertIn("request.value", rendered)
        self.assertIn(">12<", rendered)
        self.assertIn("State differences", rendered)
        self.assertIn("Verified scenario preview", rendered)
        self.assertIn("SCENARIO captured review", rendered)
        self.assertIn("Full values are included", rendered)
        self.assertIn("Keep it local", rendered)
        self.assertLess(
            rendered.index("Verified scenario preview"),
            rendered.index("State differences"),
        )
        self.assertLess(
            rendered.index("State differences"),
            rendered.index("Evidence timeline"),
        )
        self.assertIn('<details class="section evidence-section">', rendered)

    def test_comparison_is_primary_and_displays_reconciled_counts_and_diffs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(root / "new.gwt", high_status="rejected")
            execution_case = self._capture(old)
            comparison = compare_execution_cases(old, new, [execution_case])

            rendered = render_workbench_html(execution_case, comparison)

        self.assertLess(rendered.index("Behavior comparison"), rendered.index("Case overview"))
        self.assertIn('data-classification-total="output_changed"', rendered)
        self.assertIn("Output changed", rendered)
        self.assertIn("<h4>review item</h4>", rendered)
        self.assertNotIn('<span class="muted">review item</span>', rendered)
        self.assertIn("1 of 1", rendered)
        self.assertIn("/decision/status", rendered)
        self.assertIn("needs_review", rendered)
        self.assertIn("rejected", rendered)
        self.assertIn(comparison.old_program_hash, rendered)
        self.assertIn(comparison.new_program_hash, rendered)
        totals = comparison.totals
        self.assertEqual(
            totals.cases,
            totals.unavailable
            + totals.baseline_mismatch
            + totals.unchanged
            + totals.path_changed
            + totals.output_changed
            + totals.new_failure
            + totals.resolved_failure
            + totals.failure_changed
            + totals.incompatible,
        )

    def test_prioritizes_output_changes_and_collapses_path_only_queue(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old = self._write_program(root / "old.gwt")
            new = self._write_program(
                root / "new.gwt",
                high_status="rejected",
                threshold=11,
            )
            low_case = capture_execution_case(
                old,
                {"request": {"value": 2, "note": "low"}},
                request="review item",
            )
            high_case = self._capture(old)
            comparison = compare_execution_cases(old, new, [low_case, high_case])

            rendered = render_workbench_html(
                low_case,
                comparison,
                review_notice="Pinned upstream oracle; local evaluation only.",
                old_label="upstream service @ abc123",
                new_label="GWT seeded candidate",
            )
            path_only = compare_execution_cases(old, new, [low_case])
            path_only_rendered = render_workbench_html(low_case, path_only)

        self.assertEqual(comparison.cases[0].classification, "path_changed")
        self.assertEqual(comparison.cases[1].classification, "output_changed")
        self.assertLess(
            rendered.index('data-classification="output_changed"'),
            rendered.index('data-classification="path_changed"'),
        )
        self.assertIn('<details class="path-change-queue" data-path-queue>', rendered)
        self.assertIn("Path-only changes", rendered)
        self.assertIn("Review provenance", rendered)
        self.assertIn("Pinned upstream oracle; local evaluation only.", rendered)
        self.assertIn("Baseline · upstream service @ abc123", rendered)
        self.assertIn("Candidate · GWT seeded candidate", rendered)
        self.assertIn("Only execution paths changed", path_only_rendered)
        self.assertIn("Open the path-only queue", path_only_rendered)
        self.assertNotIn('class="impact-case is-selected"', path_only_rendered)

    def test_escapes_html_and_embeds_round_trippable_safe_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = self._write_program(Path(temp_dir) / "rules.gwt")
            attack = '</script><img src=x onerror="window.pwned=1">\u2028&'
            malicious = self._capture(program, note=attack)

        scenario = f"SCENARIO {attack}\n"

        rendered = render_workbench_html(
            malicious,
            verified_scenario=scenario,
            review_notice=attack,
            old_label=attack,
        )

        self.assertNotIn('</script><img src=x', rendered)
        self.assertNotIn('<img src=x', rendered)
        self.assertIn('&lt;/script&gt;&lt;img src=x onerror=', rendered)
        self.assertIn('\\u003c/script\\u003e\\u003cimg', rendered)
        self.assertEqual(rendered.count("</script>"), 2)
        match = re.search(
            r'<script type="application/json" id="gwt-dossier-data">(.*?)</script>',
            rendered,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        assert match is not None
        embedded = json.loads(match.group(1))
        self.assertEqual(
            embedded["executionCase"]["request"]["input"]["request"]["note"],
            attack,
        )
        self.assertEqual(embedded["verifiedScenario"], scenario)
        self.assertEqual(embedded["reviewNotice"], attack)
        self.assertEqual(embedded["programLabels"]["old"], attack)

    def test_rendering_is_deterministic_and_has_no_network_or_evaluator_surface(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = self._write_program(Path(temp_dir) / "rules.gwt")
            execution_case = self._capture(program)

            first = render_workbench_html(execution_case)
            second = render_workbench_html(execution_case)

        self.assertEqual(first, second)
        lowered = first.lower()
        for forbidden in (
            "http://",
            "https://",
            "//cdn",
            "<link ",
            "@import",
            "fetch(",
            "xmlhttprequest",
            "websocket",
            "eventsource",
            "eval(",
            "new function",
            "audit",
            "inbox",
            "account",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, lowered)
        self.assertIn("connect-src 'none'", first)
        self.assertIn("No policy was evaluated by this renderer.", first)
        self.assertNotIn("Behavior comparison", first)
        self.assertNotIn("Verified scenario preview", first)

    @staticmethod
    def _capture(program: Path, *, note: str = "fixture") -> ExecutionCase:
        return capture_execution_case(
            program,
            {"request": {"value": 12, "note": note}},
            request="review item",
        )

    @staticmethod
    def _write_program(
        path: Path,
        *,
        high_status: str = "needs_review",
        threshold: int = 10,
    ) -> Path:
        path.write_text(
            f'''PROGRAM workbench

RECORD Input
  value: number
  note: text

RECORD Decision
  status: text
  reason: text

REQUEST review item
  GIVEN request is Input
  GIVEN decision is Decision
    status: "new"
    reason: "new"
  WHEN review request into decision
  OUTPUT decision is Decision

WHEN review <request> into <decision>
  GIVEN request is Input
  AND decision is Decision
  DECIDE
    WHEN request.value >= {threshold}
      set decision.status to "{high_status}"
      set decision.reason to "threshold_reached"
    ELSE
      set decision.status to "approved"
      set decision.reason to "below_threshold"
'''
        )
        return path


if __name__ == "__main__":
    unittest.main()
