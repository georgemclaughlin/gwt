"""Subprocess boundary for trusted maintenance-benchmark candidates.

This is process isolation and a timeout boundary, not a security sandbox.
The parent withholds expected answers and scores the returned values.
"""

from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
import json
from pathlib import Path
import runpy
import sys
from typing import Any


def main() -> None:
    language, candidate = sys.argv[1:]
    payload = json.load(sys.stdin)
    results: list[dict[str, Any]] = []
    # Candidate output must not corrupt the worker's JSON protocol.
    with redirect_stdout(sys.stderr):
        if language == "python":
            namespace = runpy.run_path(candidate)
            decide = namespace["decide"]
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
            from gwtlang import compile_file

            program = compile_file(candidate, import_roots=[Path(candidate).parent], allow_absolute_imports=False)

            def decide(value: dict[str, Any]) -> Any:
                return program.run_json(value, request=payload["request"]).as_payload()["result"]

        for value in payload["inputs"]:
            try:
                results.append({"ok": True, "result": deepcopy(decide(deepcopy(value)))})
            except Exception as exc:
                results.append({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    print(json.dumps(results, allow_nan=False))


if __name__ == "__main__":
    main()
