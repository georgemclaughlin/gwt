"""Compact, provider-neutral context packs for agent-authored GWT changes."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import re
import shlex
from typing import TypedDict, cast

from .errors import GwtError
from .inspection import InspectionResult, inspect_file, inspect_source
from .payloads import DiagnosticPayload, InspectionPayload, JsonValue
from .runtime import ImportPolicy, RequestCall, Scenario


AGENT_CONTEXT_SCHEMA_VERSION = 1


class AgentContextPayload(TypedDict):
    schemaVersion: int
    kind: str
    ok: bool
    file: str
    program: str | None
    programIdentity: JsonValue
    selectedRequest: str | None
    diagnostics: list[DiagnosticPayload]
    guidance: dict[str, list[str]]
    vocabulary: dict[str, list[dict[str, JsonValue]]]
    scenarioIndex: list[dict[str, JsonValue]]
    scenarioExamples: list[dict[str, JsonValue]]
    languageExamples: list[dict[str, str]]
    workflow: dict[str, JsonValue]


@dataclass(frozen=True)
class AgentContextResult:
    """A checked domain-language vocabulary and small set of worked examples."""

    inspection: InspectionResult
    selected_request: str | None
    scenario_limit: int

    @property
    def ok(self) -> bool:
        return self.inspection.ok

    def as_payload(self) -> AgentContextPayload:
        inspected = self.inspection.as_payload()
        program = self.inspection.analysis.program
        scenarios = (
            [scenario for scenario in program.scenarios if scenario.line > 0]
            if program is not None
            else []
        )
        selected = _select_scenarios(
            scenarios,
            request=self.selected_request,
            limit=self.scenario_limit,
        )
        scenario_sources = {
            scenario.line: _scenario_source(self.inspection.analysis.source, scenario)
            for scenario in selected
            if scenario.filename in {None, self.inspection.analysis.filename}
        }
        file = inspected["file"]
        scenario_index = cast(list[dict[str, JsonValue]], [
            {
                "name": scenario.name,
                "requests": _scenario_requests(scenario),
                "file": scenario.filename or file,
                "line": scenario.line,
            }
            for scenario in scenarios
        ])
        scenario_examples = cast(list[dict[str, JsonValue]], [
            {
                "name": scenario.name,
                "requests": _scenario_requests(scenario),
                "source": scenario_sources[scenario.line],
            }
            for scenario in selected
            if scenario.line in scenario_sources
        ])
        payload: AgentContextPayload = {
            "schemaVersion": AGENT_CONTEXT_SCHEMA_VERSION,
            "kind": "gwt.agent-context",
            "ok": inspected["ok"],
            "file": file,
            "program": inspected["program"],
            "programIdentity": cast(JsonValue, inspected["programIdentity"]),
            "selectedRequest": self.selected_request,
            "diagnostics": inspected["diagnostics"],
            "guidance": {
                "sourceOfTruth": [
                    "Treat the checked, scenario-backed .gwt program as the durable specification.",
                    "Use the program's domain nouns, request names, and behavior sentences before adding vocabulary.",
                    "Ask for a missing domain decision instead of silently choosing precedence, rounding, or missing-value behavior.",
                ],
                "changeShape": [
                    "Keep domain rules in GWT rather than prompts or generated host code.",
                    "Add executable scenarios for normal, boundary, missing, and precedence behavior when relevant.",
                    "Preserve named REQUEST input and OUTPUT contracts unless the public boundary intentionally changes.",
                ],
            },
            "vocabulary": {
                "types": _type_vocabulary(inspected),
                "requests": _request_vocabulary(inspected),
                "behaviors": _behavior_vocabulary(inspected),
            },
            "scenarioIndex": scenario_index,
            "scenarioExamples": scenario_examples,
            "languageExamples": [
                {"name": name, "source": source}
                for name, source in LANGUAGE_EXAMPLES
            ],
            "workflow": {
                "commands": [
                    ["python", "-m", "gwtlang", "check", file, "--json", "--lint"],
                    ["python", "-m", "gwtlang", "format", file],
                    ["python", "-m", "gwtlang", "validate", file, "--json", "--lint"],
                ],
                "completionCriteria": [
                    "No parser or checker errors remain.",
                    "The source is canonically formatted.",
                    "All executable scenarios and request invariants pass.",
                    "The scenarios demonstrate the requested semantics, not merely execution.",
                ],
            },
        }
        return payload

    def render_markdown(self) -> str:
        return render_agent_context_markdown(self.as_payload())


def build_agent_context_file(
    path: str | Path,
    *,
    request: str | None = None,
    scenario_limit: int = 2,
    import_policy: ImportPolicy | None = None,
) -> AgentContextResult:
    if scenario_limit < 0:
        raise ValueError("scenario_limit must be zero or greater")
    result = AgentContextResult(
        inspect_file(path, import_policy=import_policy),
        request,
        scenario_limit,
    )
    _validate_selected_request(result)
    return result


def build_agent_context_source(
    source: str,
    filename: str = "<source>",
    *,
    request: str | None = None,
    scenario_limit: int = 2,
    import_policy: ImportPolicy | None = None,
) -> AgentContextResult:
    if scenario_limit < 0:
        raise ValueError("scenario_limit must be zero or greater")
    result = AgentContextResult(
        inspect_source(source, filename, import_policy=import_policy),
        request,
        scenario_limit,
    )
    _validate_selected_request(result)
    return result


def render_agent_context_markdown(payload: AgentContextPayload) -> str:
    """Render a context payload for direct inclusion in an agent prompt."""

    title = payload["program"] or Path(payload["file"]).stem
    lines = [f"# GWT domain-language context: {title}", ""]
    if not payload["ok"]:
        lines.extend(
            [
                "The program does not currently check. Repair these diagnostics before changing behavior:",
                "",
            ]
        )
        for diagnostic in payload["diagnostics"]:
            lines.append(
                f"- `{diagnostic.get('code', 'GWT000')}` at "
                f"{diagnostic.get('path', payload['file'])}:{diagnostic['line']}: "
                f"{diagnostic.get('message', 'unknown diagnostic')}"
            )
        lines.append("")

    lines.extend(
        [
            "This artifact is generated context, not the source of truth. Edit and commit the `.gwt` program.",
            "",
            "## Working agreement",
            "",
        ]
    )
    for rule in payload["guidance"]["sourceOfTruth"] + payload["guidance"]["changeShape"]:
        lines.append(f"- {rule}")

    lines.extend(["", "## Domain vocabulary", ""])
    types = payload["vocabulary"]["types"]
    if types:
        lines.extend(["### Nouns and states", ""])
        for item in types:
            lines.extend(_fenced(str(item["declaration"]), "gwt"))
            lines.append("")

    requests = payload["vocabulary"]["requests"]
    if requests:
        lines.extend(["### Public requests", ""])
        for request in requests:
            lines.append(f"- `{request['name']}`")
            inputs = cast(list[dict[str, JsonValue]], request["inputs"])
            outputs = cast(list[dict[str, JsonValue]], request["outputs"])
            if inputs:
                lines.append(f"  - input: {_contract_text(inputs)}")
            if outputs:
                lines.append(f"  - output: {_contract_text(outputs)}")
        lines.append("")

    behaviors = payload["vocabulary"]["behaviors"]
    if behaviors:
        lines.extend(["### Domain verbs", ""])
        for behavior in behaviors:
            contract = cast(dict[str, JsonValue], behavior["contracts"])
            suffix: list[str] = []
            inputs = cast(dict[str, str], contract["inputs"])
            if inputs:
                suffix.append(", ".join(f"{name}: {value}" for name, value in inputs.items()))
            if contract["returns"] is not None:
                suffix.append(f"returns {contract['returns']}")
            detail = f" — {'; '.join(suffix)}" if suffix else ""
            lines.append(f"- `WHEN {behavior['signature']}`{detail}")
        lines.append("")

    lines.extend(["## Executable domain examples", ""])
    scenario_examples = payload["scenarioExamples"]
    if scenario_examples:
        for scenario in scenario_examples:
            lines.append(f"### {scenario['name']}")
            lines.append("")
            lines.extend(_fenced(str(scenario["source"]), "gwt"))
            lines.append("")
    else:
        lines.extend(
            [
                "No matching embedded scenario was selected. Use the scenario index below and read the target source before changing semantics.",
                "",
            ]
        )

    scenario_index = payload["scenarioIndex"]
    if scenario_index:
        lines.extend(["### Scenario index", ""])
        for scenario in scenario_index:
            requests_text = ", ".join(cast(list[str], scenario["requests"])) or "direct behavior steps"
            lines.append(f"- `{scenario['name']}` ({requests_text})")
        lines.append("")

    lines.extend(["## GWT syntax examples", ""])
    for example in payload["languageExamples"]:
        lines.append(f"### {example['name']}")
        lines.append("")
        lines.extend(_fenced(example["source"], "gwt"))
        lines.append("")

    lines.extend(["## Validate and repair", ""])
    commands = cast(list[list[str]], payload["workflow"]["commands"])
    lines.extend(_fenced("\n".join(shlex.join(command) for command in commands), "sh"))
    lines.append("")
    for criterion in cast(list[str], payload["workflow"]["completionCriteria"]):
        lines.append(f"- {criterion}")
    return "\n".join(lines).rstrip() + "\n"


def _validate_selected_request(result: AgentContextResult) -> None:
    if result.selected_request is None or not result.inspection.ok:
        return
    program = result.inspection.analysis.program
    if program is None or result.selected_request not in program.requests:
        choices = sorted(program.requests) if program is not None else []
        available = ", ".join(choices) if choices else "none"
        raise GwtError(
            f"unknown REQUEST for agent context: {result.selected_request}; available: {available}"
        )


def _type_vocabulary(inspected: InspectionPayload) -> list[dict[str, JsonValue]]:
    items: list[dict[str, JsonValue]] = []
    for alias in inspected["typeAliases"]:
        items.append(
            {
                "name": alias["name"],
                "kind": "typeAlias",
                "declaration": f"TYPE {alias['name']} is {alias['type']}",
                "file": alias["file"],
                "line": alias["line"],
            }
        )
    for record in inspected["records"]:
        declaration = [f"RECORD {record['name']}"]
        declaration.extend(
            f"  {field['path']}: {field['type']}" for field in record["fields"]
        )
        items.append(
            {
                "name": record["name"],
                "kind": "record",
                "declaration": "\n".join(declaration),
                "file": record["file"],
                "line": record["line"],
            }
        )
    for variant in inspected["oneOfRecords"]:
        declaration = [f"RECORD {variant['name']} is one of"]
        for case in variant["cases"]:
            declaration.append(f"  {case['name']}:")
            declaration.extend(
                f"    {field['path']}: {field['type']}" for field in case["fields"]
            )
        items.append(
            {
                "name": variant["name"],
                "kind": "oneOfRecord",
                "declaration": "\n".join(declaration),
                "file": variant["file"],
                "line": variant["line"],
            }
        )
    return items


def _request_vocabulary(inspected: InspectionPayload) -> list[dict[str, JsonValue]]:
    return [
        {
            "name": request["name"],
            "inputs": [
                {"path": binding["path"], "type": binding["type"]}
                for binding in request["inputs"]
            ],
            "outputs": [
                {"path": binding["path"], "type": binding["type"]}
                for binding in request["outputs"]
            ],
            "file": request["file"],
            "line": request["line"],
        }
        for request in inspected["requests"]
    ]


def _behavior_vocabulary(inspected: InspectionPayload) -> list[dict[str, JsonValue]]:
    return [
        {
            "name": behavior["name"],
            "signature": behavior["signatureText"],
            "contracts": cast(JsonValue, behavior["contracts"]),
            "file": behavior["file"],
            "line": behavior["line"],
        }
        for behavior in inspected["behaviors"]
    ]


def _select_scenarios(
    scenarios: Iterable[Scenario],
    *,
    request: str | None,
    limit: int,
) -> list[Scenario]:
    candidates = list(scenarios)
    if request is not None:
        candidates = [
            scenario
            for scenario in candidates
            if request in _scenario_requests(scenario)
        ]
    return candidates[:limit]


def _scenario_requests(scenario: Scenario) -> list[str]:
    return [step.name for step in scenario.whens if isinstance(step, RequestCall)]


def _scenario_source(source: str, scenario: Scenario) -> str:
    lines = source.splitlines()
    start = max(0, scenario.line - 1)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if _starts_new_top_level_block(lines, index):
            end = index
            break
    return "\n".join(lines[start:end]).rstrip() + "\n"


def _starts_new_top_level_block(lines: list[str], index: int) -> bool:
    raw = lines[index]
    if not raw or raw.startswith((" ", "\t")) or raw.lstrip().startswith("#"):
        return False
    text = raw.strip()
    if text.startswith(("SCENARIO ", "PROGRAM ", "USE ", "TYPE ", "RECORD ")):
        return True
    if text == "BACKGROUND":
        return True
    if text.startswith(("REQUEST ", "WHEN ")):
        next_line = _next_nonblank_line(lines, index + 1)
        return next_line is not None and next_line.startswith("  ")
    return False


def _next_nonblank_line(lines: list[str], start: int) -> str | None:
    for line in lines[start:]:
        if line.strip() and not line.lstrip().startswith("#"):
            return line
    return None
def _contract_text(bindings: list[dict[str, JsonValue]]) -> str:
    return ", ".join(f"`{binding['path']}: {binding['type']}`" for binding in bindings)


def _fenced(source: str, language: str) -> list[str]:
    longest = max((len(run) for run in re.findall(r"`+", source)), default=0)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}{language}", source.rstrip(), fence]


LANGUAGE_EXAMPLES = (
    (
        "Small behavior and scenario",
        """WHEN greet <name>
  GIVEN name is text
  print "Hello"

SCENARIO greets a person
GIVEN name is "Ada"
WHEN greet name
THEN name == "Ada"
""",
    ),
    (
        "Typed public request",
        """TYPE ReviewStatus is "new" | "approved"

RECORD Decision
  status: ReviewStatus

REQUEST review decision
  GIVEN decision is Decision

  WHEN approve decision

  OUTPUT decision is Decision

  THEN decision.status == "approved"

WHEN approve <decision>
  GIVEN decision is Decision
  set decision.status to "approved"

SCENARIO approves a new decision
GIVEN decision is Decision
  status: "new"

REQUEST review decision

THEN decision.status == "approved"
""",
    ),
)
