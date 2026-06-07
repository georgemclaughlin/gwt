import unittest

from gwtlang.service import analyze_source, completion_items, definition_at, hover_at


SOURCE = """RECORD Cart
  total: number

WHEN total <cart>
  GIVEN cart is Cart
  THEN returns number
  RETURN cart.total

GIVEN cart is Cart
  total: 3

WHEN total cart
"""


class ServiceTests(unittest.TestCase):
    def test_analyze_source_returns_program_diagnostics_and_symbols(self):
        analysis = analyze_source(SOURCE, "example.gwt")

        self.assertIsNotNone(analysis.program)
        self.assertEqual(analysis.diagnostics, [])
        self.assertTrue(any(symbol.kind == "behavior" and symbol.name == "total <cart>" for symbol in analysis.symbols.symbols))

    def test_analyze_source_returns_parser_diagnostic(self):
        analysis = analyze_source("AND count is 1\n", "bad.gwt")

        self.assertIsNone(analysis.program)
        self.assertEqual(analysis.diagnostics[0].code, "GWT900")
        self.assertIn("AND has no previous", analysis.diagnostics[0].message)

    def test_hover_finds_symbols_by_position(self):
        analysis = analyze_source(SOURCE, "example.gwt")

        hover = hover_at(analysis, 0, 8)

        self.assertIsNotNone(hover)
        self.assertIn("record: Cart", hover.contents)

    def test_definition_finds_behavior_call_target(self):
        analysis = analyze_source(SOURCE, "example.gwt")

        target = definition_at(analysis, 11, 6)

        self.assertIsNotNone(target)
        self.assertEqual(target.line, 4)
        self.assertEqual(target.column, 6)

    def test_definition_ignores_decide_branch_when_label(self):
        analysis = analyze_source(
            """WHEN mark high into decision
  set decision.status to "high"

WHEN classify <score> into <decision>
  DECIDE
    WHEN score > 0
      mark high into decision
    ELSE
      PASS
""",
            "example.gwt",
        )

        branch_target = definition_at(analysis, 5, 4)
        call_target = definition_at(analysis, 6, 8)

        self.assertIsNone(branch_target)
        self.assertIsNotNone(call_target)
        self.assertEqual(call_target.line, 1)

    def test_completion_items_include_behavior_and_dto(self):
        analysis = analyze_source(SOURCE, "example.gwt")
        labels = {item["label"] for item in completion_items(analysis)}

        self.assertIn("Cart", labels)
        self.assertIn("total <cart>", labels)


if __name__ == "__main__":
    unittest.main()
