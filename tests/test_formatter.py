from pathlib import Path
import tempfile
import unittest

from gwtlang import GwtError, format_file, format_text, is_formatted, run_text


class FormatterTests(unittest.TestCase):
    def test_native_finite_annotations_preserve_tokens_without_enabling_python_types(self):
        source = '''TYPE Confirmed is true
TYPE Rate is 0.5 | 1.0 | 2.0
TYPE Codes is list<optional<-1 | (9007199254740993)>>
RECORD Facts
  confirmed: true
  note: text  # true | 1 stays in the comment
WHEN confirm
  THEN returns true
  print "true | 1"
  RETURN true
'''
        self.assertEqual(format_text(source), source)
        self.assertEqual(format_text(format_text(source)), source)
        with self.assertRaises(GwtError):
            run_text('TYPE Confirmed is true\nGIVEN flag is true\n')
        for target in ['list<true>>', '1 + 1 | 2', 'true |', '(true']:
            with self.subTest(target=target), self.assertRaises(GwtError):
                format_text(f'TYPE Broken is {target}\n')

    def test_native_local_record_construction_preserves_fields_comments_and_wrappers(self):
        source = '''RECORD Box
  note: optional<text>
WHEN build
  LET empty be Box:
  LET result be Envelope:
    box:
      note: "café # 😀: LET fake be Box:"
    values: []  # keep [] and constructor text
  print result
REQUEST build
  WHEN LET result be Box:
    note: "request"
  OUTPUT result is Box
SCENARIO constructed
WHEN LET result be Box:
  note: "scenario"
THEN result.note is present
'''
        self.assertEqual(format_text(source), source)
        self.assertEqual(format_text(format_text(source)), source)

    def test_native_constructor_projection_rejects_bad_field_layout_and_quotes(self):
        for body in ['     note: "odd"', '    note "missing colon"',
                     '    note: "unterminated', '    note: "value"\n      nested: 1',
                     '      note: "too deep"']:
            with self.subTest(body=body), self.assertRaises(GwtError):
                format_text('WHEN build\n  LET result be Box:\n' + body + '\n')
        with self.assertRaises(GwtError):
            format_text('WHEN build\n  LET result be optional<Box>>:\n')

    def test_native_kind_contracts_preserve_annotations_literals_and_comments(self):
        source = '''TYPE Email is Contact of kind email
TYPE Phones is list<Contact of kind phone>
TYPE Label is "Contact of kind email" | "other"
RECORD Batch
  backup: optional<Contact of kind email>
WHEN inspect <contact>
  GIVEN contact is Contact of kind email
  print "Contact of kind phone"  # Contact of kind email
'''
        self.assertEqual(format_text(source), source)
        self.assertEqual(format_text(format_text(source)), source)
        # Source validation still rejects malformed type targets and indentation.
        with self.assertRaises(GwtError):
            format_text('TYPE Emails is list<Contact of kind email>>\n')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            types = root / 'types.gwt'
            original = 'RECORD Contact is one of\n  email:\n    address: text\nTYPE Email is Contact of kind email\n'
            types.write_text(original)
            entry = 'USE "types.gwt"\nGIVEN contact is Email\n  kind: "email"\n  address: "a@example.test"\n'
            self.assertEqual(format_text(entry, filename=str(root / 'main.gwt')), entry)
            self.assertEqual(types.read_text(), original)
            with self.assertRaises(GwtError):
                run_text(entry, filename=str(root / 'main.gwt'))

    def test_native_expected_failures_keep_action_and_assertion_order(self):
        source = 'GIVEN amount is 7\nWHEN print amount / 0\nTHEN fails with "division_by_zero"\nAND prints []\nAND amount == 7\n'
        self.assertEqual(format_text(source), source)
        self.assertEqual(format_text(format_text(source)), source)

    def test_native_print_expectations_preserve_exact_json(self):
        # The native extension asserts serialized output, not a Python expression.
        source = 'WHEN print "done"\nTHEN prints ["done", {"note": "# | café", "missing": null}, 9007199254740993]\nAND prints []\n'
        self.assertEqual(format_text(source), source)
        self.assertEqual(format_text(format_text(source)), source)

    def test_native_grouped_arguments_keep_quotes_groups_and_copy_spelling(self):
        # Native call grouping is a documented extension. Formatting is syntax
        # oriented; this does not claim Python runtime/checker support for it.
        source = '''WHEN calculate <amount>
  GIVEN amount is decimal
  THEN returns decimal
  LET result be discount (amount * 2) at 0.1
  label result with "text # with (groups) and [lists]"
  inspect [1, (2 + 3)]
  inspect (amount)
  RETURN result
'''
        formatted = format_text(source)
        self.assertEqual(formatted, source)
        self.assertEqual(format_text(formatted), formatted)

    def test_format_text_normalizes_spacing_tables_and_comments(self):
        source = """

            PROGRAM   sample


            # leading comment
            GIVEN  order.items are
              | sku | quantity |
              | "keyboard" | 2 |
              | "mouse" | 10 |  # keeps comments

            WHEN total items
              FOR  item in order.items
                add  item.quantity to total
        """

        formatted = format_text(source)

        self.assertEqual(
            formatted,
            """PROGRAM sample

# leading comment
GIVEN order.items are
  | sku        | quantity |
  | "keyboard" | 2        |
  | "mouse"    | 10       |  # keeps comments

WHEN total items
  FOR item in order.items
    add item.quantity to total
""",
        )
        self.assertTrue(is_formatted(formatted))

    def test_format_text_keeps_runtime_behavior(self):
        source = """
            GIVEN  cart.items is [10, 20, 30]
            AND cart.total is 0

            WHEN total cart
              FOR item in cart.items
                add item to cart.total

            WHEN total cart
            THEN cart.total == 60
        """

        formatted = format_text(source)
        result = run_text(formatted)

        self.assertEqual(result.state["cart"]["total"], 60)

    def test_format_text_normalizes_find_block_keyword_spacing(self):
        formatted = format_text(
            """
            GIVEN order.items is []

            WHEN reserve order
              FIND  item in order.items WHERE item.sku == "widget"
                print item.sku
              ELSE
                print "missing"
            """
        )

        self.assertIn("  FIND item in order.items WHERE item.sku == \"widget\"\n", formatted)

    def test_format_text_normalizes_pass_keyword_spacing(self):
        formatted = format_text(
            """
            WHEN keep going
              PASS
            """
        )

        self.assertEqual(formatted, "WHEN keep going\n  PASS\n")

    def test_format_text_normalizes_one_of_and_depending_on(self):
        formatted = format_text(
            """
            RECORD  Statement is one of
              let_number:
                value:   number

            GIVEN program.statements contains a Statement of kind let_number
              value:  2

            WHEN handle <statement>
              DEPENDING ON  statement
                WHEN the kind is let_number
                  print  statement.value
            """
        )

        self.assertEqual(
            formatted,
            """RECORD Statement is one of
  let_number:
    value: number

GIVEN program.statements contains a Statement of kind let_number
  value: 2

WHEN handle <statement>
  DEPENDING ON statement
    WHEN the kind is let_number
      print statement.value
""",
        )

    def test_format_text_normalizes_request_and_value_depending_on(self):
        formatted = format_text(
            """
            REQUEST   decide mode
              GIVEN   mode is text

              WHEN   decide mode

              OUTPUT   mode is text

            WHEN decide <mode>
              DEPENDING ON  mode
                WHEN the value is "reserve"
                  print  "reserved"
                ELSE
                  print  "other"
            """
        )

        self.assertEqual(
            formatted,
            """REQUEST decide mode
  GIVEN mode is text

  WHEN decide mode

  OUTPUT mode is text

WHEN decide <mode>
  DEPENDING ON mode
    WHEN the value is "reserve"
      print "reserved"
    ELSE
      print "other"
""",
        )

    def test_format_text_normalizes_decide_block(self):
        formatted = format_text(
            """
            WHEN classify <score> into <decision>
              DECIDE
                WHEN  score >= 10
                  print  "high"
                WHEN score >= 5
                  print  "medium"
                ELSE
                  PASS
            """
        )

        self.assertEqual(
            formatted,
            """WHEN classify <score> into <decision>
  DECIDE
    WHEN score >= 10
      print "high"
    WHEN score >= 5
      print "medium"
    ELSE
      PASS
""",
        )

    def test_format_file_reports_changed_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "counter.gwt"
            path.write_text(
                """
                GIVEN  count is 1
                THEN count == 1
                """
            )

            result = format_file(path)

        self.assertTrue(result.changed)
        self.assertEqual(result.formatted, "GIVEN count is 1\nTHEN count == 1\n")

    def test_formatter_rejects_removed_dto_keyword(self):
        with self.assertRaisesRegex(GwtError, "unknown top-level form: DTO Account"):
            format_text(
                """
                DTO Account
                  balance: number
                """
            )

    def test_formatter_accepts_request_file_with_external_records(self):
        formatted = format_text(
            """
            GIVEN application is LoanApplication
              amount: 100

            WHEN submit application
            """
        )

        self.assertEqual(
            formatted,
            "GIVEN application is LoanApplication\n  amount: 100\n\nWHEN submit application\n",
        )


if __name__ == "__main__":
    unittest.main()
