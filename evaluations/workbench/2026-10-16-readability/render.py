"""Re-render retained Python dossiers without replaying or changing evidence."""

from dataclasses import fields
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from gwtlang.comparison import (
    CaseComparison, ComparedValue, ComparisonError, ComparisonErrorSource,
    ComparisonEvaluatedCondition, ComparisonResult, ComparisonSelectedDecision,
    ComparisonSource, ComparisonTotals, OutputDifference,
)
from gwtlang.execution_case import ExecutionCase
from gwtlang.workbench import render_workbench_html


def camel(name):
    first, *rest = name.split("_")
    return first + "".join(part.title() for part in rest)


def source(value, cls=ComparisonSource):
    return cls(**value) if value is not None else None


def decision(value):
    return ComparisonSelectedDecision(
        value["condition"], value["result"], source(value["source"])
    ) if value is not None else None


def condition(value):
    return ComparisonEvaluatedCondition(
        value["expression"], value["result"], json.dumps(value["operands"]),
        source(value["source"]),
    )


def error(value):
    return ComparisonError(
        value["kind"], value["message"], source(value["source"], ComparisonErrorSource)
    ) if value is not None else None


def compared(value):
    return ComparedValue.of(value["value"]) if value["present"] else ComparedValue.missing()


def difference(value):
    return OutputDifference(
        value["path"], compared(value["old"]), compared(value["new"]),
        source(value["oldLastChangeSource"]), source(value["newLastChangeSource"]),
    )


def case(value):
    converted = {field.name: value.get(camel(field.name)) for field in fields(CaseComparison)}
    for prefix in ("captured", "old", "new"):
        converted[prefix + "_selected_decision"] = decision(value[prefix + "SelectedDecision"])
        converted[prefix + "_evaluated_conditions"] = tuple(
            condition(item) for item in value[prefix + "EvaluatedConditions"]
        )
    for prefix in ("old", "new"):
        converted[prefix + "_error"] = error(value[prefix + "Error"])
    converted["output_differences"] = tuple(map(difference, value["outputDifferences"]))
    return CaseComparison(**converted)


def comparison(value):
    result = ComparisonResult(
        value["oldProgram"]["hash"], value["oldProgram"]["entry"],
        value["newProgram"]["hash"], value["newProgram"]["entry"],
        ComparisonTotals(**{
            field.name: value["totals"][camel(field.name)] for field in fields(ComparisonTotals)
        }), tuple(map(case, value["cases"])),
    )
    assert result.as_payload() == value, "Comparison reconstruction lost evidence"
    return result


def dossier(document):
    match = re.search(
        r'<script type="application/json" id="gwt-dossier-data">(.*?)</script>',
        document, re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def main():
    output = Path(__file__).resolve().parent
    retained = output.parent / "2026-10-16-adaptations"
    manifest = []
    for spec in json.loads((retained / "manifest.json").read_text()):
        if spec["kind"] != "python":
            continue
        original = ROOT / spec["sourceHtml"]
        assert hashlib.sha256(original.read_bytes()).hexdigest() == spec["sourceHtmlSha256"]
        saved = dossier(original.read_text())
        report = ROOT / spec["sourceReport"]
        assert hashlib.sha256(report.read_bytes()).hexdigest() == spec["sourceReportSha256"]
        assert saved["comparison"] == json.loads(report.read_text())
        execution_case = ExecutionCase.from_payload(saved["executionCase"])
        rendered = render_workbench_html(
            execution_case, comparison(saved["comparison"]), saved["verifiedScenario"],
            review_notice=saved["reviewNotice"], old_label=saved["programLabels"]["old"],
            new_label=saved["programLabels"]["new"], case_reference=saved["caseReference"],
        )
        assert dossier(rendered) == saved, "Re-render changed the embedded dossier"
        target = output / spec["workflow"]
        target.mkdir(exist_ok=True)
        (target / "review.html").write_text(rendered)
        spec["rows"] = saved["comparison"]["cases"]
        spec["renderedHtmlSha256"] = hashlib.sha256(rendered.encode()).hexdigest()
        manifest.append(spec)
    assert len(manifest) == 3
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Re-rendered three dossiers; all embedded evidence is identical.")


if __name__ == "__main__":
    main()
