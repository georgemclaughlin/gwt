import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from gwtlang import (
    AGENT_CONTEXT_SCHEMA_VERSION,
    GwtError,
    GwtClient,
    build_agent_context_file,
    build_agent_context_source,
)
from gwtlang.agent_context import LANGUAGE_EXAMPLES
from gwtlang.__main__ import main
from gwtlang.formatter import format_text
from gwtlang.service import analyze_source


PROGRAM = """PROGRAM review workflow

TYPE ReviewStatus is "new" | "approved"

RECORD Decision
  status: ReviewStatus

REQUEST review decision
  GIVEN decision is Decision

  WHEN approve decision

  OUTPUT decision is Decision

  THEN decision.status == "approved"

REQUEST leave decision
  GIVEN decision is Decision

  WHEN leave decision

  OUTPUT decision is Decision

WHEN approve <decision>
  GIVEN decision is Decision
  set decision.status to "approved"

WHEN leave <decision>
  GIVEN decision is Decision
  print "unchanged"

SCENARIO approves a new decision
GIVEN decision is Decision
  status: "new"

REQUEST review decision

THEN decision.status == "approved"

SCENARIO leaves a decision alone
GIVEN decision is Decision
  status: "new"

REQUEST leave decision

THEN decision.status == "new"
"""


class AgentContextTests(unittest.TestCase):
    def test_payload_captures_domain_vocabulary_and_selected_scenario(self):
        result = build_agent_context_source(
            PROGRAM,
            filename="review.gwt",
            request="review decision",
        )

        payload = result.as_payload()

        self.assertTrue(result.ok)
        self.assertEqual(payload["schemaVersion"], AGENT_CONTEXT_SCHEMA_VERSION)
        self.assertEqual(payload["kind"], "gwt.agent-context")
        self.assertEqual(payload["program"], "review workflow")
        self.assertEqual(payload["selectedRequest"], "review decision")
        self.assertEqual(payload["vocabulary"]["types"][0]["name"], "ReviewStatus")
        self.assertEqual(payload["vocabulary"]["types"][1]["name"], "Decision")
        self.assertEqual(payload["vocabulary"]["requests"][0]["name"], "review decision")
        self.assertEqual(payload["vocabulary"]["behaviors"][0]["signature"], "approve <decision>")
        self.assertEqual(
            [scenario["name"] for scenario in payload["scenarioExamples"]],
            ["approves a new decision"],
        )
        self.assertIn("REQUEST review decision", payload["scenarioExamples"][0]["source"])
        self.assertNotIn("leaves a decision alone", payload["scenarioExamples"][0]["source"])
        self.assertEqual(len(payload["scenarioIndex"]), 2)
        self.assertEqual(len(payload["languageExamples"]), 2)

    def test_file_context_retains_closure_identity_and_imported_vocabulary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            types = root / "types.gwt"
            rules = root / "rules.gwt"
            types.write_text("RECORD Decision\n  status: text\n")
            rules.write_text(
                'USE "./types.gwt"\n\n'
                "REQUEST review decision\n"
                "  GIVEN decision is Decision\n\n"
                "  WHEN approve decision\n\n"
                "  OUTPUT decision is Decision\n\n"
                "WHEN approve <decision>\n"
                "  GIVEN decision is Decision\n"
                '  set decision.status to "approved"\n'
            )

            payload = build_agent_context_file(rules).as_payload()

        self.assertIsNotNone(payload["programIdentity"])
        self.assertEqual(payload["vocabulary"]["types"][0]["name"], "Decision")
        self.assertEqual(
            payload["workflow"]["commands"][0][:4],
            ["python", "-m", "gwtlang", "check"],
        )

    def test_reference_client_exposes_agent_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            rules = Path(temp_dir) / "rules.gwt"
            rules.write_text(PROGRAM)

            payload = GwtClient(rules).agent_context(
                request="review decision",
                scenario_limit=1,
            ).as_payload()

        self.assertEqual(payload["selectedRequest"], "review decision")
        self.assertEqual(len(payload["scenarioExamples"]), 1)

    def test_markdown_is_prompt_ready_but_marks_gwt_as_source_of_truth(self):
        rendered = build_agent_context_source(PROGRAM, filename="review.gwt").render_markdown()

        self.assertIn("# GWT domain-language context: review workflow", rendered)
        self.assertIn("generated context, not the source of truth", rendered)
        self.assertIn("## Domain vocabulary", rendered)
        self.assertIn("`WHEN approve <decision>`", rendered)
        self.assertIn("python -m gwtlang validate review.gwt --json --lint", rendered)

    def test_scenario_limit_zero_keeps_index_without_embedding_source(self):
        payload = build_agent_context_source(PROGRAM, scenario_limit=0).as_payload()

        self.assertEqual(payload["scenarioExamples"], [])
        self.assertEqual(len(payload["scenarioIndex"]), 2)

    def test_implicit_empty_main_is_not_presented_as_executable_evidence(self):
        payload = build_agent_context_source(
            "PROGRAM empty\n\nRECORD Decision\n  status: text\n"
        ).as_payload()

        self.assertEqual(payload["scenarioExamples"], [])
        self.assertEqual(payload["scenarioIndex"], [])

    def test_unknown_selected_request_is_rejected_with_available_names(self):
        with self.assertRaisesRegex(
            GwtError,
            "unknown REQUEST for agent context: missing; available: leave decision, review decision",
        ):
            build_agent_context_source(PROGRAM, request="missing")

    def test_invalid_program_returns_diagnostics_in_context(self):
        result = build_agent_context_source("AND value is 1\n", filename="bad.gwt")

        payload = result.as_payload()
        self.assertFalse(result.ok)
        self.assertEqual(payload["diagnostics"][0]["code"], "GWT900")
        self.assertIn("does not currently check", result.render_markdown())

    def test_bundled_language_examples_remain_valid_and_canonical(self):
        for name, source in LANGUAGE_EXAMPLES:
            with self.subTest(name=name):
                self.assertEqual(analyze_source(source).diagnostics, [])
                self.assertEqual(format_text(source), source)

    def test_json_payload_matches_published_schema_when_jsonschema_is_available(self):
        if importlib.util.find_spec("jsonschema") is None:
            self.skipTest("jsonschema package is not installed")
        from jsonschema import Draft202012Validator

        schema = json.loads(Path("docs/schemas/agent-context.schema.json").read_text())
        Draft202012Validator(schema).validate(
            build_agent_context_source(PROGRAM, filename="review.gwt").as_payload()
        )

    def test_cli_emits_json_and_can_atomically_write_markdown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rules = root / "rules.gwt"
            output = root / "agent-context.md"
            rules.write_text(PROGRAM)
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                status = main(
                    [
                        "agent-context",
                        str(rules),
                        "--request",
                        "review decision",
                        "--json",
                    ]
                )
            json_payload = json.loads(stdout.getvalue())

            write_stdout = io.StringIO()
            with redirect_stdout(write_stdout):
                write_status = main(
                    ["agent-context", str(rules), "--output", str(output)]
                )
            output_text = output.read_text()

        self.assertEqual(status, 0)
        self.assertEqual(json_payload["selectedRequest"], "review decision")
        self.assertEqual(write_status, 0)
        self.assertEqual(write_stdout.getvalue(), f"Wrote {output}\n")
        self.assertIn("## Domain vocabulary", output_text)

    def test_cli_reports_unknown_request_without_traceback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            rules = Path(temp_dir) / "rules.gwt"
            rules.write_text(PROGRAM)
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                status = main(
                    ["agent-context", str(rules), "--request", "missing"]
                )

        self.assertEqual(status, 1)
        self.assertIn("unknown REQUEST for agent context", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
