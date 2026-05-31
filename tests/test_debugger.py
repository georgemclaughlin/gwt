import io
import json
from pathlib import Path
import tempfile
import unittest

from gwtlang.debugger import Breakpoint, debug_lines_for_file, parse_breakpoint, run_debug_file


class DebuggerTests(unittest.TestCase):
    def test_debug_runner_stops_on_breakpoint_and_continues(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "counter.gwt"
            program.write_text(
                """
WHEN increase amount in count
  add amount to count

GIVEN count is 1
WHEN increase 2 in count
THEN count == 3
""".lstrip()
            )
            stdin = io.StringIO('{"command":"continue"}\n')
            stdout = io.StringIO()

            status = run_debug_file(
                program,
                breakpoints=[Breakpoint(str(program.resolve()), 2)],
                stdin=stdin,
                stdout=stdout,
            )

        messages = [json.loads(line) for line in stdout.getvalue().splitlines()]
        self.assertEqual(status, 0)
        self.assertEqual(messages[0]["event"], "stopped")
        self.assertEqual(messages[0]["line"], 2)
        self.assertEqual(messages[0]["locals"]["amount"], 2)
        self.assertEqual(messages[0]["state"]["count"], 1)
        self.assertEqual([frame["name"] for frame in messages[0]["stack"]], ["increase amount in count", "Main"])
        self.assertEqual(messages[-1], {"event": "terminated", "exitCode": 0})

    def test_debug_runner_reports_nested_call_stack(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "nested.gwt"
            program.write_text(
                """
WHEN double amount into result
  add amount to result

WHEN wrap amount into result
  double amount into result

GIVEN result is 0
WHEN wrap 2 into result
THEN result == 2
""".lstrip()
            )
            stdin = io.StringIO('{"command":"continue"}\n')
            stdout = io.StringIO()

            status = run_debug_file(
                program,
                breakpoints=[Breakpoint(str(program.resolve()), 2)],
                stdin=stdin,
                stdout=stdout,
            )

        messages = [json.loads(line) for line in stdout.getvalue().splitlines()]
        stack = messages[0]["stack"]
        self.assertEqual(status, 0)
        self.assertEqual([frame["name"] for frame in stack], ["double amount into result", "wrap amount into result", "Main"])
        self.assertEqual([frame["line"] for frame in stack], [2, 5, 8])
        self.assertEqual(stack[0]["locals"]["amount"], 2)
        self.assertEqual(stack[1]["locals"]["amount"], 2)
        self.assertEqual(stack[2]["locals"], {})

    def test_debug_runner_step_next_stops_on_next_statement(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "counter.gwt"
            program.write_text(
                """
GIVEN count is 1
WHEN add 2 to count
THEN count == 3
""".lstrip()
            )
            stdin = io.StringIO('{"command":"next"}\n{"command":"continue"}\n')
            stdout = io.StringIO()

            status = run_debug_file(
                program,
                breakpoints=[Breakpoint(str(program.resolve()), 1)],
                stdin=stdin,
                stdout=stdout,
            )

        stops = [json.loads(line) for line in stdout.getvalue().splitlines() if json.loads(line)["event"] == "stopped"]
        self.assertEqual(status, 0)
        self.assertEqual([stop["line"] for stop in stops], [1, 2])

    def test_parse_breakpoint_uses_default_file_for_line_only(self):
        breakpoint = parse_breakpoint("12", "/tmp/example.gwt")

        self.assertEqual(breakpoint.filename, str(Path("/tmp/example.gwt").resolve()))
        self.assertEqual(breakpoint.line, 12)

    def test_debug_lines_report_only_runtime_executable_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            program = Path(temp_dir) / "checkout.gwt"
            program.write_text(
                """
DTO Cart
  total: number

WHEN total items into cart
  GIVEN items is list
  FOR item in items
    add item to cart.total

GIVEN cart is
  total: 0

WHEN total [1, 2] into cart

THEN cart.total == 3

EXAMPLES
  | unused |
  | 1      |
""".lstrip()
            )

            lines = debug_lines_for_file(program)

        line_numbers = {line.line for line in lines}
        self.assertEqual(line_numbers, {6, 7, 10, 12, 14})
        self.assertNotIn(1, line_numbers)
        self.assertNotIn(4, line_numbers)
        self.assertNotIn(16, line_numbers)
        self.assertNotIn(18, line_numbers)


if __name__ == "__main__":
    unittest.main()
