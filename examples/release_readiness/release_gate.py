from __future__ import annotations

import argparse
import filecmp
import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, Literal, cast

from gwtlang import GwtClient, check_file, is_formatted
from rules_types import (
    ApprovalStatus,
    CheckStatus,
    FeatureFlag,
    ReleaseApproval,
    ReleaseCheck,
    ReleaseDecision,
    ReleaseReadinessClient,
    ReviewReleaseOutput,
    ReviewReleaseRequest,
)


ROOT = Path(__file__).resolve().parents[2]
RULES = Path(__file__).with_name("rules.gwt")

EvidenceMode = Literal["ci-passed", "local"]
ReportFormat = Literal["markdown", "json"]

CI_REQUIRED_CHECKS = (
    "unit_tests",
    "python_typecheck",
    "example_formatting",
    "top_level_examples",
    "reference_request_workflows",
    "typed_module_fixture",
    "generated_host_types",
    "openapi_generation",
    "typescript_client",
    "vscode_extension",
    "whitespace",
)

DOC_ALIGNMENT_PATHS = {
    "README.md",
    "docs/grammar.md",
    "docs/language.md",
    "docs/design-principles.md",
    "docs/roadmap-v0.3.md",
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    client = GwtClient(RULES)
    validation = client.validate(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    if not validation.ok:
        print(json.dumps(validation.as_payload(), indent=2, sort_keys=True))
        return 1

    compiled = client.compile(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    )
    rules = ReleaseReadinessClient(compiled)
    manifest = client.inspect(
        import_roots=[RULES.parent],
        allow_absolute_imports=False,
    ).as_payload()

    evidence_mode = cast(EvidenceMode, args.evidence)
    report_format = cast(ReportFormat, args.report)
    changed_paths = collect_changed_paths(ROOT, ignore=args.ignore_working_tree)
    request = build_request(args, evidence_mode, changed_paths)
    execution = rules.run_review_release(request)
    result = cast(ReviewReleaseOutput, execution.as_payload()["result"])
    decision = result["decision"]

    report = build_report(
        request,
        decision,
        advisory=not args.enforce,
        evidence_mode=evidence_mode,
        program_hash=str(manifest["programHash"]),
        changed_paths=changed_paths,
    )
    rendered = render_report(report, report_format)
    if args.output:
        cast(Path, args.output).write_text(rendered)
    else:
        print(rendered)

    if args.enforce and decision["status"] != "approved":
        return 1
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Use GWT release-readiness rules as an advisory repo release gate."
    )
    parser.add_argument(
        "--evidence",
        choices=["ci-passed", "local"],
        default="ci-passed",
        help=(
            "Use prior CI step success as check evidence, or run local checks "
            "from this script."
        ),
    )
    parser.add_argument(
        "--report",
        choices=["markdown", "json"],
        default="markdown",
        help="Report format.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Shortcut for --report json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the report to a file instead of stdout.",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero unless the GWT decision is approved.",
    )
    parser.add_argument(
        "--release-approved",
        action="store_true",
        help="Mark the maintainer release approval as present.",
    )
    parser.add_argument(
        "--environment",
        choices=["staging", "production"],
        default="production",
        help="Release environment passed to GWT.",
    )
    parser.add_argument(
        "--version",
        help="Release version. Defaults to the pyproject.toml project version.",
    )
    parser.add_argument(
        "--active-incident-count",
        type=int,
        default=0,
        help="Known active production incidents.",
    )
    parser.add_argument(
        "--no-rollback-plan",
        action="store_true",
        help="Report that no rollback plan exists.",
    )
    parser.add_argument(
        "--ignore-working-tree",
        action="store_true",
        help="Do not add advisory risk flags for local working-tree changes.",
    )
    args = parser.parse_args(argv)
    if args.json:
        args.report = "json"
    return args


def build_request(
    args: argparse.Namespace,
    evidence_mode: EvidenceMode,
    changed_paths: list[str],
) -> ReviewReleaseRequest:
    version = str(args.version or package_version(ROOT) or "unknown")
    checks = [
        release_check("gwt_release_rules_validate", "passed"),
        release_check(
            "package_version_declared",
            "passed" if version != "unknown" else "failed",
        ),
    ]
    checks.extend(collect_release_checks(evidence_mode))

    return {
        "release": {
            "version": version,
            "environment": args.environment,
            "rollback_plan_present": not args.no_rollback_plan,
            "active_incident_count": args.active_incident_count,
            "checks": checks,
            "approvals": collect_approvals(args, changed_paths),
            "feature_flags": collect_feature_flags(changed_paths),
        }
    }


def collect_release_checks(evidence_mode: EvidenceMode) -> list[ReleaseCheck]:
    if evidence_mode == "local":
        return collect_local_checks(ROOT)
    return [release_check(name, "passed") for name in CI_REQUIRED_CHECKS]


def collect_local_checks(root: Path) -> list[ReleaseCheck]:
    checks: list[ReleaseCheck] = []
    checks.append(command_check("unit_tests", [sys.executable, "-m", "unittest", "discover"], root))
    checks.append(
        command_check(
            "python_typecheck",
            ["npx", "--yes", "pyright@1.1.410", "--project", "pyrightconfig.json"],
            root,
        )
    )
    checks.append(
        release_check(
            "example_formatting",
            "passed" if examples_are_formatted(root) else "failed",
        )
    )
    checks.append(
        release_check(
            "top_level_examples",
            "passed" if top_level_examples_check(root) else "failed",
        )
    )
    checks.append(
        release_check(
            "reference_request_workflows",
            "passed" if reference_request_workflows_pass(root) else "failed",
        )
    )
    checks.append(
        release_check(
            "typed_module_fixture",
            "passed" if typed_module_fixtures_pass(root) else "failed",
        )
    )
    checks.append(
        release_check(
            "generated_host_types",
            "passed" if generated_host_types_are_clean(root) else "failed",
        )
    )
    checks.append(
        release_check(
            "openapi_generation",
            "passed" if openapi_generation_passes(root) else "failed",
        )
    )
    checks.append(
        command_check(
            "typescript_client",
            ["npm", "run", "check"],
            root / "clients" / "typescript",
        )
    )
    checks.append(
        command_check(
            "vscode_extension",
            ["npm", "run", "check"],
            root / "vscode-gwt",
        )
    )
    checks.append(command_check("whitespace", ["git", "diff", "--check"], root))
    return checks


def collect_approvals(
    args: argparse.Namespace,
    changed_paths: list[str],
) -> list[ReleaseApproval]:
    return [
        release_approval(
            "maintainer",
            "approved" if args.release_approved else "missing",
        ),
        release_approval("docs_spec_alignment", docs_spec_alignment(changed_paths)),
    ]


def collect_feature_flags(changed_paths: list[str]) -> list[FeatureFlag]:
    if not changed_paths:
        return []

    flags = [feature_flag("working_tree_has_changes", enabled=True, risky=True)]
    if any(path.startswith("gwtlang/") for path in changed_paths):
        flags.append(feature_flag("runtime_language_change", enabled=True, risky=True))
    if any(is_spec_surface_path(path) for path in changed_paths):
        flags.append(feature_flag("spec_surface_change", enabled=True, risky=True))
    return flags


def docs_spec_alignment(changed_paths: list[str]) -> ApprovalStatus:
    if not changed_paths:
        return "approved"

    runtime_or_checker_changed = any(path.startswith("gwtlang/") for path in changed_paths)
    docs_changed = any(
        path in DOC_ALIGNMENT_PATHS or path.startswith("docs/spec/")
        for path in changed_paths
    )
    if runtime_or_checker_changed and not docs_changed:
        return "missing"
    return "approved"


def is_spec_surface_path(path: str) -> bool:
    return path in DOC_ALIGNMENT_PATHS or path.startswith("docs/spec/")


def package_version(root: Path) -> str | None:
    try:
        with (root / "pyproject.toml").open("rb") as handle:
            data = tomllib.load(handle)
    except OSError:
        return None

    project = data.get("project")
    if not isinstance(project, dict):
        return None
    project_data = cast(dict[str, Any], project)
    version = project_data.get("version")
    return version if isinstance(version, str) and version else None


def examples_are_formatted(root: Path) -> bool:
    for program in sorted((root / "examples").rglob("*.gwt")):
        if not is_formatted(program.read_text(), filename=str(program)):
            return False
    return True


def top_level_examples_check(root: Path) -> bool:
    for program in sorted((root / "examples").glob("*.gwt")):
        result = check_file(program)
        if not result.ok:
            return False
    return True


def reference_request_workflows_pass(root: Path) -> bool:
    commands = [
        [
            sys.executable,
            "-m",
            "gwtlang",
            "run",
            "examples/order_fulfillment/rules.gwt",
            "--input",
            "examples/order_fulfillment/request.gwt",
            "--json",
        ],
        [
            sys.executable,
            "-m",
            "gwtlang",
            "run",
            "examples/language_tour/rules.gwt",
            "--input",
            "examples/language_tour/request.gwt",
            "--json",
        ],
    ]
    return all(run_command(command, root) for command in commands)


def typed_module_fixtures_pass(root: Path) -> bool:
    return all(
        run_command([sys.executable, str(path)], root)
        for path in (
            root / "examples" / "vendor_onboarding" / "host_app.py",
            root / "examples" / "release_readiness" / "host_app.py",
        )
    )


def generated_host_types_are_clean(root: Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        checks = [
            (
                [
                    sys.executable,
                    "-m",
                    "gwtlang",
                    "types",
                    "examples/vendor_onboarding/rules.gwt",
                    "--language",
                    "typescript",
                    "--output",
                    str(tmp_path / "vendor-onboarding.generated.d.ts"),
                ],
                root / "clients" / "typescript" / "examples" / "vendor-onboarding.generated.d.ts",
                tmp_path / "vendor-onboarding.generated.d.ts",
            ),
            (
                [
                    sys.executable,
                    "-m",
                    "gwtlang",
                    "types",
                    "examples/vendor_onboarding/rules.gwt",
                    "--language",
                    "python",
                    "--output",
                    str(tmp_path / "vendor-onboarding.rules_types.py"),
                ],
                root / "examples" / "vendor_onboarding" / "rules_types.py",
                tmp_path / "vendor-onboarding.rules_types.py",
            ),
            (
                [
                    sys.executable,
                    "-m",
                    "gwtlang",
                    "types",
                    "examples/release_readiness/rules.gwt",
                    "--language",
                    "python",
                    "--output",
                    str(tmp_path / "release-readiness.rules_types.py"),
                ],
                root / "examples" / "release_readiness" / "rules_types.py",
                tmp_path / "release-readiness.rules_types.py",
            ),
        ]
        for command, expected, actual in checks:
            if not run_command(command, root):
                return False
            if not filecmp.cmp(expected, actual, shallow=False):
                return False
    return True


def openapi_generation_passes(root: Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "gwt-openapi.json"
        if not run_command(
            [
                sys.executable,
                "-m",
                "gwtlang",
                "openapi",
                "examples/deployable_api/rules.gwt",
                "--output",
                str(output),
            ],
            root,
        ):
            return False
        try:
            loaded = cast(object, json.loads(output.read_text()))
        except json.JSONDecodeError:
            return False
    if not isinstance(loaded, dict):
        return False
    document = cast(dict[str, object], loaded)
    return document.get("openapi") == "3.1.0"


def command_check(name: str, command: list[str], cwd: Path) -> ReleaseCheck:
    return release_check(name, "passed" if run_command(command, cwd) else "failed")


def run_command(command: list[str], cwd: Path) -> bool:
    completed = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        text=True,
    )
    return completed.returncode == 0


def collect_changed_paths(root: Path, *, ignore: bool) -> list[str]:
    if ignore:
        return []

    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        return []

    paths: list[str] = []
    for line in completed.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            paths.append(path)
    return sorted(paths)


def release_check(name: str, status: CheckStatus) -> ReleaseCheck:
    return {
        "name": name,
        "required": True,
        "status": status,
    }


def release_approval(name: str, status: ApprovalStatus) -> ReleaseApproval:
    return {
        "name": name,
        "required": True,
        "status": status,
    }


def feature_flag(name: str, *, enabled: bool, risky: bool) -> FeatureFlag:
    return {
        "name": name,
        "enabled": enabled,
        "risky": risky,
    }


def build_report(
    request: ReviewReleaseRequest,
    decision: ReleaseDecision,
    *,
    advisory: bool,
    evidence_mode: EvidenceMode,
    program_hash: str,
    changed_paths: list[str],
) -> dict[str, object]:
    return {
        "advisory": advisory,
        "changed_paths": changed_paths,
        "decision": decision,
        "evidence_mode": evidence_mode,
        "programHash": program_hash,
        "request": request,
        "rules": str(RULES.relative_to(ROOT)),
    }


def render_report(report: dict[str, object], report_format: ReportFormat) -> str:
    if report_format == "json":
        return json.dumps(report, indent=2, sort_keys=True)

    request = cast(ReviewReleaseRequest, report["request"])
    decision = cast(ReleaseDecision, report["decision"])
    release = request["release"]
    lines = [
        "# GWT Release Gate",
        "",
        f"Decision: **{decision['status']}** ({decision['reason']})",
        f"Mode: {'advisory' if report['advisory'] else 'enforced'}",
        f"Evidence: {report['evidence_mode']}",
        f"Version: {release['version']}",
        f"Rules: {report['rules']}",
        f"Program hash: `{report['programHash']}`",
        "",
        "## Checks",
    ]
    lines.extend(
        f"- {check['status']}: {check['name']}"
        for check in release["checks"]
    )
    lines.extend(["", "## Approvals"])
    lines.extend(
        f"- {approval['status']}: {approval['name']}"
        for approval in release["approvals"]
    )
    lines.extend(["", "## Risk Flags"])
    if release["feature_flags"]:
        lines.extend(
            f"- {'enabled' if flag['enabled'] else 'disabled'}: {flag['name']} "
            f"(risky={str(flag['risky']).lower()})"
            for flag in release["feature_flags"]
        )
    else:
        lines.append("- none")
    if report["changed_paths"]:
        lines.extend(["", "## Changed Paths"])
        lines.extend(f"- {path}" for path in cast(list[str], report["changed_paths"]))
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
