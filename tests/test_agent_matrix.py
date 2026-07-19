from __future__ import annotations

import unittest

from gwtlang.agent_matrix import (
    _deterministic_format_repair,
    _latest_responses,
    _normalize_response,
    _public_repair_feedback,
    _task_prompt,
    _validate_tasks,
)


class AgentMatrixTests(unittest.TestCase):
    def test_prompt_contains_task_and_blind_execution_boundary(self):
        prompt = _task_prompt(
            {
                "caseId": "author-example",
                "kind": "author",
                "task": "Implement the behavior.",
                "contextVariant": "source-only",
                "context": {"source": "RECORD Example\n"},
            }
        )

        self.assertIn("author-example", prompt)
        self.assertIn("Do not inspect the filesystem", prompt)
        self.assertIn("complete canonical GWT source", prompt)

    def test_repair_prompt_contains_only_supplied_public_feedback(self):
        prompt = _task_prompt(
            {"caseId": "repair-example", "kind": "repair", "task": "Repair it."},
            previous={"action": "code", "source": "set value 1"},
            feedback=[{"gate": "check", "message": "invalid statement"}],
        )

        self.assertIn("PUBLIC DETERMINISTIC FEEDBACK", prompt)
        self.assertIn("invalid statement", prompt)
        self.assertIn("Hidden behavioral probes are not included", prompt)

    def test_normalize_code_and_clarification_responses(self):
        code = _normalize_response(
            "author-example",
            {"action": "code", "source": "GIVEN result is 1\n", "clarifications": []},
        )
        clarification = _normalize_response(
            "clarify-example",
            {"action": "clarify", "source": "", "clarifications": ["Which rule wins?"]},
        )

        self.assertEqual(code["attempt"], 1)
        self.assertEqual(code["source"], "GIVEN result is 1\n")
        self.assertEqual(clarification["clarifications"], ["Which rule wins?"])

    def test_normalize_preserves_repair_attempt_number(self):
        response = _normalize_response(
            "repair-example",
            {"action": "code", "source": "GIVEN result is 1\n", "clarifications": []},
            attempt=2,
        )

        self.assertEqual(response["attempt"], 2)

    def test_normalize_rejects_incomplete_action_payloads(self):
        with self.assertRaisesRegex(ValueError, "requires source"):
            _normalize_response(
                "author-example",
                {"action": "code", "source": "", "clarifications": []},
            )
        with self.assertRaisesRegex(ValueError, "requires questions"):
            _normalize_response(
                "clarify-example",
                {"action": "clarify", "source": "", "clarifications": []},
            )

    def test_task_ids_are_unique_and_safe_for_log_paths(self):
        _validate_tasks([{"caseId": "author-safe.case_1"}])

        with self.assertRaisesRegex(ValueError, "unsafe caseId"):
            _validate_tasks([{"caseId": "../escape"}])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            _validate_tasks([{"caseId": "same"}, {"caseId": "same"}])

    def test_latest_responses_selects_highest_attempt(self):
        latest = _latest_responses(
            [
                {"caseId": "case", "attempt": 2},
                {"caseId": "case", "attempt": 1},
            ]
        )

        self.assertEqual(latest["case"]["attempt"], 2)

    def test_public_feedback_exposes_check_and_format_gates_without_probes(self):
        task = {"caseId": "repair-example", "kind": "repair"}
        invalid = _public_repair_feedback(
            task,
            {"action": "code", "source": "WHEN unknown behavior\n"},
        )
        noncanonical = _public_repair_feedback(
            task,
            {
                "action": "code",
                "source": (
                    "WHEN greet <name>\n"
                    "  PASS\n"
                    "\n"
                    "SCENARIO greeting\n"
                    'GIVEN name is "Ada"\n'
                    "WHEN greet name\n"
                    "THEN name == \"Ada\""
                ),
            },
        )

        self.assertEqual(invalid[0]["gate"], "check")
        self.assertEqual(noncanonical[0]["gate"], "format")
        self.assertNotIn("probe", str(invalid).lower())

    def test_format_only_repair_uses_deterministic_canonical_source(self):
        repaired = _deterministic_format_repair(
            "repair-example",
            2,
            previous={"action": "code", "source": "GIVEN result is 1"},
            feedback=[{"gate": "format", "canonicalSource": "GIVEN result is 1\n"}],
        )

        self.assertIsNotNone(repaired)
        self.assertEqual(repaired["attempt"], 2)
        self.assertEqual(repaired["source"], "GIVEN result is 1\n")


if __name__ == "__main__":
    unittest.main()
