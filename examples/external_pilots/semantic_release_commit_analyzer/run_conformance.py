from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
from typing import Any, cast

from gwtlang import GwtClient


PILOT_DIR = Path(__file__).resolve().parent
RULES = PILOT_DIR / "rules.gwt"
CASES = PILOT_DIR / "conformance_cases.json"
ORACLE = PILOT_DIR / "upstream_oracle.mjs"
REQUEST = "analyze normalized commit"
UPSTREAM_COMMIT = "f16dd2e9fbf4fc17ab6fefb171a6c6e0645b6758"
RELEASE_TYPES = {
    "major",
    "premajor",
    "minor",
    "preminor",
    "patch",
    "prepatch",
    "prerelease",
}


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


def _release_token(value: object) -> str:
    if value is None:
        return "null"
    if value is False:
        return "false"
    if isinstance(value, str) and value in RELEASE_TYPES:
        return value
    raise ValueError(f"unsupported release outcome: {value!r}")


def _property(commit: dict[str, Any], name: str) -> tuple[str, str]:
    if name not in commit:
        return "missing", ""
    value = commit[name]
    if value is None:
        return "null", ""
    if isinstance(value, str):
        return "present", value
    raise ValueError(f"commit {name!r} must be text, null, or missing")


def _normalize_case(case: dict[str, Any]) -> dict[str, object]:
    commit = cast(dict[str, Any], case["commit"])
    type_state, type_value = _property(commit, "type")
    scope_state, scope_value = _property(commit, "scope")
    notes = commit.get("notes")
    has_breaking_note = isinstance(notes, list) and len(notes) > 0
    is_revert = commit.get("revert") is not None and "revert" in commit

    normalized_rules: list[dict[str, object]] = []
    for index, raw_rule in enumerate(cast(list[dict[str, Any]], case["rules"]), start=1):
        unsupported = set(raw_rule) - {"type", "scope", "breaking", "revert", "release"}
        if unsupported:
            raise ValueError(f"rule has unsupported fields: {sorted(unsupported)}")
        rule_type = raw_rule.get("type", "")
        rule_scope = raw_rule.get("scope", "")
        if not isinstance(rule_type, str) or not isinstance(rule_scope, str):
            raise ValueError("rule type and scope criteria must be text")
        normalized_rules.append(
            {
                "id": f"rule-{index}",
                "match_type": "type" in raw_rule,
                "type_value": rule_type,
                "match_scope": "scope" in raw_rule,
                "scope_value": rule_scope,
                "requires_breaking": bool(raw_rule.get("breaking", False)),
                "requires_revert": bool(raw_rule.get("revert", False)),
                "release": _release_token(raw_rule.get("release")),
            }
        )

    return {
        "commit": {
            "type_state": type_state,
            "type_value": type_value,
            "scope_state": scope_state,
            "scope_value": scope_value,
            "has_breaking_note": has_breaking_note,
            "is_revert": is_revert,
        },
        "rules": normalized_rules,
    }


def _upstream_results(upstream_root: Path, cases: list[dict[str, Any]]) -> dict[str, str]:
    commit = _run(["git", "-C", str(upstream_root), "rev-parse", "HEAD"]).strip()
    if commit != UPSTREAM_COMMIT:
        raise ValueError(f"upstream checkout must be pinned at {UPSTREAM_COMMIT}")
    payload = [
        {"id": case["id"], "commit": case["commit"], "rules": case["rules"]}
        for case in cases
    ]
    output = _run(
        ["node", str(ORACLE), str(upstream_root)],
        input_text=json.dumps(payload),
    )
    values = cast(list[dict[str, str]], json.loads(output))
    return {item["id"]: item["release"] for item in values}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare the pinned commit-analyzer decision core with GWT"
    )
    parser.add_argument(
        "upstream_root",
        nargs="?",
        type=Path,
        help="optional pinned local commit-analyzer checkout for a live oracle run",
    )
    args = parser.parse_args()

    fixture = cast(dict[str, Any], json.loads(CASES.read_text()))
    if fixture["source"]["commit"] != UPSTREAM_COMMIT:
        parser.error("conformance source pin does not match the runner")
    cases = cast(list[dict[str, Any]], fixture["cases"])
    upstream = (
        _upstream_results(args.upstream_root.resolve(), cases)
        if args.upstream_root is not None
        else {case["id"]: case["expected"]["upstream"] for case in cases}
    )

    compiled = GwtClient(RULES).compile(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    failures: list[str] = []
    classifications: Counter[str] = Counter()
    for case in cases:
        case_id = cast(str, case["id"])
        expected = cast(dict[str, str], case["expected"])
        gwt = compiled.run_json(
            _normalize_case(case),
            request=REQUEST,
        ).as_payload()["result"]["result"]["release"]
        if upstream[case_id] != expected["upstream"]:
            failures.append(
                f"{case_id}: upstream {upstream[case_id]!r}, expected {expected['upstream']!r}"
            )
        if gwt != expected["gwt"]:
            failures.append(f"{case_id}: GWT {gwt!r}, expected {expected['gwt']!r}")
        classification = cast(str, case["classification"])
        classifications[classification] += 1
        if classification == "exact_parity" and upstream[case_id] != gwt:
            failures.append(f"{case_id}: expected exact upstream/GWT parity")
        if classification == "known_boundary_gap" and upstream[case_id] == gwt:
            failures.append(f"{case_id}: expected the documented boundary gap")

    if failures:
        parser.error("conformance failures:\n  " + "\n  ".join(failures))
    print(f"exact upstream/GWT parity: {classifications['exact_parity']}/18")
    print(f"documented boundary gaps: {classifications['known_boundary_gap']}/2")
    print(f"upstream: semantic-release/commit-analyzer@{UPSTREAM_COMMIT}")
    print("oracle: live checkout" if args.upstream_root is not None else "oracle: pinned snapshot")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
