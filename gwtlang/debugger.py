from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any, TextIO

from .errors import GwtError
from .runtime import Line, PathRef, Runtime, parse_program


@dataclass(frozen=True)
class Breakpoint:
    filename: str
    line: int


class DebugStop(Exception):
    pass


class DebugController:
    def __init__(
        self,
        breakpoints: list[Breakpoint],
        *,
        stdin: TextIO,
        stdout: TextIO,
    ) -> None:
        self.breakpoints = {_breakpoint_key(breakpoint.filename, breakpoint.line) for breakpoint in breakpoints}
        self.stdin = stdin
        self.stdout = stdout
        self.pause_next = False

    def before_line(self, line: Line, state: dict[str, Any], env: dict[str, Any]) -> None:
        if not self._should_pause(line):
            return
        self.pause_next = False
        self._send(
            {
                "event": "stopped",
                "reason": "breakpoint",
                "file": line.filename,
                "line": line.number,
                "column": line.column,
                "text": line.text,
                "state": _debug_value(state),
                "locals": _debug_value(env),
            }
        )
        self._wait_for_resume()

    def _should_pause(self, line: Line) -> bool:
        if self.pause_next:
            return True
        if line.filename is None:
            return False
        return _breakpoint_key(line.filename, line.number) in self.breakpoints

    def _wait_for_resume(self) -> None:
        while True:
            raw = self.stdin.readline()
            if raw == "":
                raise DebugStop()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            command = message.get("command")
            if command == "continue":
                return
            if command == "next":
                self.pause_next = True
                return
            if command in {"stop", "disconnect", "terminate"}:
                raise DebugStop()

    def _send(self, message: dict[str, Any]) -> None:
        self.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.stdout.flush()


def run_debug_file(
    file: str | Path,
    *,
    mode: str = "test",
    breakpoints: list[Breakpoint] | None = None,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> int:
    path = Path(file)
    controller = DebugController(breakpoints or [], stdin=stdin, stdout=stdout)
    try:
        program = parse_program(path.read_text(), filename=str(path.resolve()))
        result = Runtime(program, debugger=controller).run()
    except DebugStop:
        _send(stdout, {"event": "terminated", "exitCode": 0})
        return 0
    except GwtError as exc:
        _send(stdout, {"event": "output", "category": "stderr", "output": f"{exc}\n"})
        _send(stdout, {"event": "terminated", "exitCode": 1})
        return 1

    for scenario in result.scenarios:
        for output in scenario.output:
            _send(stdout, {"event": "output", "category": "stdout", "output": f"{output}\n"})
        _send(stdout, {"event": "output", "category": "stdout", "output": f"PASS {scenario.name}\n"})
    _send(stdout, {"event": "terminated", "exitCode": 0})
    return 0


def parse_breakpoint(text: str, default_file: str | Path) -> Breakpoint:
    if ":" in text:
        filename, line_text = text.rsplit(":", 1)
        if filename == "":
            filename = str(default_file)
    else:
        filename = str(default_file)
        line_text = text
    return Breakpoint(str(Path(filename).resolve()), int(line_text))


def _send(stdout: TextIO, message: dict[str, Any]) -> None:
    stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    stdout.flush()


def _breakpoint_key(filename: str, line: int) -> tuple[str, int]:
    return str(Path(filename).resolve()), line


def _debug_value(value: Any) -> Any:
    if isinstance(value, PathRef):
        return {"pathRef": value.path}
    if isinstance(value, dict):
        return {str(key): _debug_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_debug_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)
