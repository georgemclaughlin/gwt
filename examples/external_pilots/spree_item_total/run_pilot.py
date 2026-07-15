from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from gwtlang import GwtClient


PILOT_DIR = Path(__file__).resolve().parent
RULES = PILOT_DIR / "rules.gwt"
ORACLE = PILOT_DIR / "ruby_oracle.rb"
SLICE = PILOT_DIR / "oracle_slice.json"
REQUEST = "assess item total eligibility"
UPSTREAM_COMMIT = "249dbf3c68461288f8444d754bcf27d0fa962250"
RUBY_IMAGE = "ruby:3.4.9-alpine"


def _run(command: list[str], *, input_text: str | None = None) -> str:
    completed = subprocess.run(
        command,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}"
        )
    return completed.stdout


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare the Spree ItemTotal class with the local GWT pilot"
    )
    parser.add_argument("upstream_root", type=Path, help="pinned local Spree checkout")
    args = parser.parse_args()

    upstream_root = args.upstream_root.resolve()
    commit = _run(["git", "-C", str(upstream_root), "rev-parse", "HEAD"]).strip()
    if commit != UPSTREAM_COMMIT:
        parser.error(f"upstream checkout must be pinned at {UPSTREAM_COMMIT}")

    fixture = json.loads(SLICE.read_text())
    cases = fixture["cases"]
    oracle_input = [{"id": case["id"], **case["facts"]} for case in cases]
    oracle_output = _run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            f"{upstream_root}:/upstream:ro",
            "-v",
            f"{PILOT_DIR}:/pilot:ro",
            RUBY_IMAGE,
            "ruby",
            "/pilot/ruby_oracle.rb",
            "/upstream",
        ],
        input_text=json.dumps(oracle_input),
    )
    ruby_results = {item["id"]: item for item in json.loads(oracle_output)}

    compiled = GwtClient(RULES).compile(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    mismatches: list[str] = []
    for case in cases:
        expected = case["expected"]
        ruby = {key: ruby_results[case["id"]][key] for key in expected}
        gwt_facts = dict(case["facts"])
        has_maximum = gwt_facts.pop("has_maximum")
        if not has_maximum:
            gwt_facts.pop("amount_max")
        gwt = compiled.run_json(
            {"facts": gwt_facts},
            request=REQUEST,
        ).as_payload()["result"]["decision"]
        if ruby != expected or gwt != expected:
            mismatches.append(case["id"])

    if mismatches:
        parser.error(f"Ruby/GWT mismatch for: {', '.join(mismatches)}")
    print(f"exact Ruby/GWT parity: {len(cases)}/{len(cases)}")
    print(f"upstream: spree/spree@{UPSTREAM_COMMIT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
