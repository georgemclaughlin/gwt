"""Self-contained local HTML renderer for behavior-review evidence.

The renderer is deliberately presentation-only. It consumes versioned
``ExecutionCase`` and ``ComparisonResult`` objects, escapes every value, and
does not execute GWT behavior or derive new policy meaning from field names.
"""

from __future__ import annotations

from html import escape
import json
from typing import cast

from .comparison import (
    CaseComparison,
    ComparedValue,
    ComparisonClassification,
    ComparisonError,
    ComparisonEvaluatedCondition,
    ComparisonResult,
    ComparisonSelectedDecision,
    ComparisonSource,
    ComparisonTotals,
    OutputDifference,
)
from .execution_case import ExecutionCase
from .payloads import (
    ExecutionCaseErrorPayload,
    ExecutionCaseEvidencePayload,
    ExecutionCaseOperandsPayload,
    ExecutionCaseRedactionPayload,
    ExecutionCaseSourcePayload,
    ExecutionCaseStateChangePayload,
    ExecutionCaseStateValuePayload,
    JsonValue,
)


_CLASSIFICATIONS: tuple[tuple[ComparisonClassification, str], ...] = (
    ("unavailable", "Unavailable"),
    ("output_changed", "Output changed"),
    ("path_changed", "Path changed"),
    ("new_failure", "New failure"),
    ("resolved_failure", "Resolved failure"),
    ("failure_changed", "Failure changed"),
    ("incompatible", "Incompatible"),
    ("baseline_mismatch", "Baseline mismatch"),
    ("unchanged", "Unchanged"),
)


def render_workbench_html(
    execution_case: ExecutionCase,
    comparison: ComparisonResult | None = None,
    verified_scenario: str | None = None,
) -> str:
    """Render a deterministic, self-contained local behavior-review dossier.

    ``verified_scenario`` is rendered verbatim as an escaped preview. The
    caller is responsible for checking, formatting, and reproducing it before
    passing it to this presentation layer.
    """

    case_payload = execution_case.as_payload()
    request = execution_case.request_name
    program = case_payload["program"]
    execution = case_payload["execution"]
    sensitivity_notice = _render_sensitivity_notice(case_payload["redaction"])

    dossier_data: dict[str, object] = {
        "executionCase": case_payload,
        "comparison": comparison.as_payload() if comparison is not None else None,
        "verifiedScenario": verified_scenario,
    }

    comparison_html = (
        _render_comparison(comparison) if comparison is not None else ""
    )
    scenario_html = (
        _render_scenario(verified_scenario)
        if verified_scenario is not None
        else ""
    )
    captured_at = str(execution["capturedAt"])
    program_name = program["name"] or "Unnamed program"
    selected_branches = _render_selected_branches(case_payload["evidence"])
    result_availability = case_payload["redaction"]["availability"]["result"]
    input_panel = _case_value_panel(
        "Input",
        case_payload["request"]["input"],
        "case-input",
        case_payload["redaction"]["availability"]["requestInput"],
    )
    result_panel = _case_value_panel(
        "Declared result",
        case_payload["result"],
        "case-result",
        result_availability,
    )
    failure_html = _render_case_failure(execution.get("error"))
    primary_note = (
        '<p class="muted">The dossier below is the first loaded, primary case. '
        'Choosing a comparison case changes only the comparison detail panel.</p>'
        if comparison is not None
        else ""
    )

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'">
  <title>{_h(request)} · GWT behavior review</title>
  <style>{_STYLES}</style>
</head>
<body>
  <a class="skip-link" href="#main-content">Skip to review content</a>
  <header class="masthead">
    <div class="masthead__inner">
      <div class="brand" aria-label="GWT behavior workbench">
        <span class="brand__mark" aria-hidden="true">G/W</span>
        <span class="brand__copy">
          <span class="eyebrow">Local behavior workbench</span>
          <strong>Behavior review dossier</strong>
        </span>
      </div>
      <span class="local-badge"><span aria-hidden="true">●</span> Local artifact</span>
    </div>
    <div class="hero">
      <p class="eyebrow">Captured execution</p>
      <h1>{_h(request)}</h1>
      <p class="hero__lede">Source-linked facts from one executable behavior run, including an explicit failure when one occurred.</p>
      <div class="hero__meta" aria-label="Capture metadata">
        <span>{_h(str(program_name))}</span>
        <span aria-hidden="true">/</span>
        <time>{_h(captured_at)}</time>
      </div>
    </div>
  </header>

  <main id="main-content" class="page-shell">
    {sensitivity_notice}
    {comparison_html}

    <section class="section" aria-labelledby="case-overview-heading">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Primary execution case</p>
          <h2 id="case-overview-heading">Case overview</h2>
        </div>
        <span class="schema-chip">Execution Case v{case_payload["schemaVersion"]}</span>
      </div>

      <div class="overview-grid">
        {_overview_card("Request", request, "request")}
        {_overview_card("Outcome", execution["outcome"], "outcome")}
        {_overview_card("Program closure", str(program["hash"]), "hash", mono=True)}
      </div>

      {primary_note}

      <div class="data-grid">
        {input_panel}
        {result_panel}
      </div>

      {failure_html}
      {selected_branches}
    </section>

    {scenario_html}
    {_render_state_changes(case_payload["stateChanges"])}
    {_render_evidence(case_payload["evidence"])}
  </main>

  <footer class="footer">
    <span>Generated from versioned execution evidence.</span>
    <span>No policy was evaluated by this renderer.</span>
  </footer>

  <script type="application/json" id="gwt-dossier-data">{_safe_json(dossier_data)}</script>
  <script>{_SCRIPT}</script>
</body>
</html>
'''


def _render_comparison(comparison: ComparisonResult) -> str:
    totals = comparison.totals
    attention_cases = tuple(
        case for case in comparison.cases if case.classification != "unchanged"
    )
    total_cards = "".join(
        _total_card(classification, label, _classification_count(totals, classification))
        for classification, label in _CLASSIFICATIONS
    )

    if not attention_cases:
        cases_html = '''
          <div class="empty-state">
            <span class="empty-state__icon" aria-hidden="true">✓</span>
            <div><strong>No changed cases</strong><p>All comparable cases retained the same declared output and material execution evidence.</p></div>
          </div>'''
    else:
        filter_buttons = [
            f'<button class="filter-button is-active" type="button" data-filter="all" aria-pressed="true">All <span>{len(attention_cases)}</span></button>'
        ]
        for classification, label in _CLASSIFICATIONS:
            if classification == "unchanged":
                continue
            count = sum(
                1 for case in attention_cases if case.classification == classification
            )
            if count:
                filter_buttons.append(
                    f'<button class="filter-button" type="button" data-filter="{classification}" aria-pressed="false">{_h(label)} <span>{count}</span></button>'
                )

        case_buttons: list[str] = []
        case_panels: list[str] = []
        for position, case in enumerate(attention_cases):
            target = f"comparison-case-{position + 1}"
            selected = position == 0
            label = _classification_label(case.classification)
            case_buttons.append(
                f'''<button class="impact-case{' is-selected' if selected else ''}" type="button"
                  data-case-choice data-classification="{case.classification}"
                  data-target="{target}" aria-controls="{target}" aria-pressed="{'true' if selected else 'false'}">
                  <span class="impact-case__top"><span class="classification classification--{case.classification}">{_h(label)}</span><span class="impact-case__id">{_h(case.id)}</span></span>
                  <strong>{_h(case.request)}</strong>
                  <span>{len(case.output_differences)} output difference{'s' if len(case.output_differences) != 1 else ''}</span>
                </button>'''
            )
            case_panels.append(
                _render_comparison_case(case, target, hidden=not selected)
            )

        cases_html = f'''
          <div class="filter-row" aria-label="Filter changed cases">{''.join(filter_buttons)}</div>
          <div class="impact-layout">
            <nav class="impact-list" aria-label="Changed cases">{''.join(case_buttons)}</nav>
            <div class="impact-detail" aria-live="polite">{''.join(case_panels)}</div>
          </div>'''

    return f'''
    <section class="section comparison-section" aria-labelledby="comparison-heading" data-comparison>
      <div class="section-heading">
        <div>
          <p class="eyebrow">Candidate impact</p>
          <h2 id="comparison-heading">Behavior comparison</h2>
        </div>
        <span class="schema-chip">Comparison v1</span>
      </div>

      <div class="program-compare" aria-label="Compared program identities">
        <div><span>Old closure</span><code>{_h(comparison.old_program_hash)}</code></div>
        <span class="program-compare__arrow" aria-hidden="true">→</span>
        <div><span>New closure</span><code>{_h(comparison.new_program_hash)}</code></div>
      </div>

      <div class="totals-grid" data-testid="comparison-totals">{total_cards}</div>

      <div class="subsection-heading">
        <div><p class="eyebrow">Review queue</p><h3>Changed &amp; unresolved cases</h3></div>
        <span>{len(attention_cases)} of {totals.cases}</span>
      </div>
      {cases_html}
    </section>'''


def _render_sensitivity_notice(redaction: ExecutionCaseRedactionPayload) -> str:
    if redaction.get("valuesIncluded") is True:
        title = "Full values are included"
        detail = "This dossier contains captured input, result, evidence, and state values. Keep it local unless those values are safe to share."
        badge = "Full-value capture"
    else:
        title = "Captured values are limited"
        detail = "Review the case redaction metadata before relying on unavailable or removed values."
        badge = f"Mode: {redaction.get('mode', 'unspecified')}"
    return f'''
    <aside class="sensitivity-notice" role="note" aria-label="Data sensitivity">
      <div class="sensitivity-notice__icon" aria-hidden="true">!</div>
      <div><strong>{_h(title)}</strong><p>{_h(detail)}</p></div>
      <span>{_h(badge)}</span>
    </aside>'''


def _render_comparison_case(
    case: CaseComparison,
    target: str,
    *,
    hidden: bool,
) -> str:
    difference_html = "".join(
        _render_output_difference(difference)
        for difference in case.output_differences
    )
    if not difference_html:
        difference_html = '<p class="muted">No declared output fields changed.</p>'

    decisions = f'''
      <div class="decision-pair">
        {_comparison_decision("Old selected DECIDE branch", case.old_selected_decision)}
        {_comparison_decision("New selected DECIDE branch", case.new_selected_decision)}
      </div>'''
    conditions = f'''
      <div class="decision-pair">
        {_comparison_conditions("Old evaluated predicates", case.old_evaluated_conditions)}
        {_comparison_conditions("New evaluated predicates", case.new_evaluated_conditions)}
      </div>'''
    errors = "".join(
        _render_error(label, error)
        for label, error in (("Old error", case.old_error), ("New error", case.new_error))
        if error is not None
    )
    detail = (
        f'<p class="impact-summary">{_h(case.detail)}</p>'
        if case.detail is not None
        else ""
    )
    hidden_attribute = " hidden" if hidden else ""
    label = _classification_label(case.classification)
    return f'''
      <article id="{target}" class="impact-panel" data-case-panel{hidden_attribute}>
        <header>
          <div><span class="classification classification--{case.classification}">{_h(label)}</span><h4>{_h(case.request)}</h4></div>
          <code>{_h(case.id)}</code>
        </header>
        {detail}
        <div class="impact-hashes">
          <span>Recorded closure <code>{_h(case.recorded_program_hash)}</code></span>
          <span>Captured evidence <code>{_h(case.captured_evidence_digest)}</code></span>
          {_optional_digest("Old evidence", case.old_evidence_digest)}
          {_optional_digest("New evidence", case.new_evidence_digest)}
        </div>
        <div class="impact-block"><h5>Declared output differences</h5>{difference_html}</div>
        <div class="impact-block"><h5>Selected DECIDE branches</h5>{decisions}</div>
        <div class="impact-block"><h5>Evaluated predicates</h5>{conditions}</div>
        {errors}
      </article>'''


def _render_output_difference(difference: OutputDifference) -> str:
    old_source = _comparison_source(difference.old_last_change_source)
    new_source = _comparison_source(difference.new_last_change_source)
    return f'''
      <div class="field-diff">
        <code class="field-diff__path">{_h(difference.path)}</code>
        <div><span>Old</span>{_compared_value(difference.old)}{old_source}</div>
        <span class="field-diff__arrow" aria-hidden="true">→</span>
        <div><span>New</span>{_compared_value(difference.new)}{new_source}</div>
      </div>'''


def _comparison_decision(
    label: str,
    decision: ComparisonSelectedDecision | None,
) -> str:
    if decision is None:
        body = '<span class="absence">Not present</span>'
    else:
        source = _comparison_source(decision.source)
        body = f'<code>{_h(decision.condition)}</code>{source}'
    return f'<div class="decision-card"><span>{_h(label)}</span>{body}</div>'


def _comparison_conditions(
    label: str,
    conditions: tuple[ComparisonEvaluatedCondition, ...],
) -> str:
    if not conditions:
        body = '<span class="absence">Not available</span>'
    else:
        body = "".join(
            f'''<div class="condition-fact">
              <code>{_h(condition.expression)}</code>
              <span class="truth-chip">{str(condition.result).lower()}</span>
              {_comparison_condition_operands(condition)}
              {_comparison_source(condition.source)}
            </div>'''
            for condition in conditions
        )
    return f'<div class="decision-card"><span>{_h(label)}</span>{body}</div>'


def _comparison_condition_operands(
    condition: ComparisonEvaluatedCondition,
) -> str:
    operands = condition.operands
    if operands["availability"] == "available":
        values = operands.get("values", [])
        if not values:
            return '<span class="condition-operands">No identifier operands</span>'
        rendered = ", ".join(
            f"{operand['name']} = {_json_inline(operand['value'])} "
            f"({operand['valueType']})"
            for operand in values
        )
        return f'<span class="condition-operands">{_h(rendered)}</span>'
    if operands["availability"] == "redacted":
        return '<span class="condition-operands">Operands redacted</span>'
    return (
        '<span class="condition-operands">Operands unavailable: '
        f'{_h(operands.get("reason", "not recorded"))}</span>'
    )


def _comparison_source(source: ComparisonSource | None) -> str:
    if source is None:
        return ""
    return f'<span class="source-link">{_h(source.file)}:{source.line}:{source.column}</span>'


def _render_error(label: str, error: ComparisonError) -> str:
    source = ""
    if error.source is not None:
        source = f'<span>{_h(error.source.file)}:{error.source.line}:{error.source.column}</span>'
    return f'''
      <div class="error-card">
        <div><span class="error-card__label">{_h(label)}</span>{source}</div>
        <code>{_h(error.message)}</code>
      </div>'''


def _render_selected_branches(
    evidence: list[ExecutionCaseEvidencePayload],
) -> str:
    selected = [
        item
        for item in evidence
        if item["kind"] == "branch" and item.get("selected") is True
    ]
    if not selected:
        return '''
      <article class="rule-card rule-card--empty">
        <div class="rule-card__marker" aria-hidden="true">—</div>
        <div><p class="eyebrow">Selected branches</p><h3>No branch selection was recorded</h3><p>The evidence contains no selected branch fact.</p></div>
      </article>'''
    cards = "".join(
        f'''<div class="decision-card">
          <span>{_h(str(item.get("branchKind", "branch")))} {_h(str(item.get("branchLabel", "")))} branch</span>
          <code>{_h(str(item.get("expression", "") or "ELSE"))}</code>
          {_execution_source(item["source"])}
        </div>'''
        for item in selected
    )
    return f'''
      <article class="rule-card" data-testid="selected-branches">
        <div class="rule-card__marker" aria-hidden="true">↳</div>
        <div>
          <p class="eyebrow">Selected branches</p>
          <h3>{len(selected)} recorded selection{"s" if len(selected) != 1 else ""}</h3>
          <div class="decision-pair">{cards}</div>
        </div>
      </article>'''


def _render_evidence(
    evidence: list[ExecutionCaseEvidencePayload],
) -> str:
    ordered = sorted(evidence, key=lambda item: item["sequence"])
    if not ordered:
        body = '<div class="empty-state compact"><span aria-hidden="true">—</span><p>No evidence events were recorded.</p></div>'
    else:
        body = '<ol class="timeline">' + "".join(
            _render_evidence_item(item) for item in ordered
        ) + "</ol>"
    return f'''
    <details class="section evidence-section">
      <summary class="section-heading">
        <div><p class="eyebrow">Ordered facts</p><h2 id="evidence-heading">Evidence timeline</h2></div>
        <span class="evidence-summary__actions"><span class="count-chip">{len(ordered)} events</span><span class="evidence-toggle" aria-hidden="true">Expand</span></span>
      </summary>
      {body}
    </details>'''


def _render_evidence_item(item: ExecutionCaseEvidencePayload) -> str:
    kind = item["kind"]
    summary = item["summary"] or "No summary recorded"
    details: list[tuple[str, str]] = []
    for key, label in (
        ("label", "Contract"),
        ("path", "Path"),
        ("valueType", "Type"),
        ("branchKind", "Branch"),
        ("branchLabel", "Branch label"),
        ("startLine", "Body starts"),
        ("endLine", "Body ends"),
        ("expression", "Expression"),
        ("result", "Result"),
        ("selected", "Selected"),
        ("phase", "Phase"),
        ("signature", "Signature"),
        ("depth", "Depth"),
        ("behaviorOutcome", "Outcome"),
        ("callId", "Call ID"),
        ("parentCallId", "Parent call ID"),
    ):
        if key in item:
            details.append((label, _json_inline(cast(JsonValue, item[key]))))
    details_html = "".join(
        f'<div><dt>{_h(label)}</dt><dd><code>{_h(value)}</code></dd></div>'
        for label, value in details
    )
    operands_html = _render_operands(item.get("operands"))
    source = _execution_source(item["source"])
    return f'''
        <li class="timeline-item timeline-item--{_h(kind)}">
          <div class="timeline-item__sequence" aria-label="Sequence {item['sequence']}">{item['sequence']}</div>
          <article>
            <header><span class="event-kind">{_h(kind)}</span><span class="timeline-item__summary">{_h(summary)}</span></header>
            <dl class="fact-list">{details_html}</dl>
            {operands_html}
            {source}
          </article>
        </li>'''


def _render_operands(operands: ExecutionCaseOperandsPayload | None) -> str:
    if operands is None:
        return ""
    availability = operands.get("availability", "unavailable")
    if availability == "redacted":
        return '''
          <div class="operands operands--unavailable">
            <span>Operand values redacted</span><code>capture policy: omit</code>
          </div>'''
    if availability != "available":
        reason = operands.get("reason", "not-observed")
        return f'''
          <div class="operands operands--unavailable">
            <span>Operands unavailable</span><code>{_h(reason)}</code>
          </div>'''
    values = operands.get("values", [])
    rows = "".join(
        f'''<div class="operand-row">
          <code>{_h(operand['name'])}</code>
          <span>{_h(operand['valueType'])}</span>
          <strong>{_h(_json_inline(operand['value']))}</strong>
        </div>'''
        for operand in values
    )
    if not rows:
        rows = '<span class="absence">No operand values recorded</span>'
    return f'''
      <div class="operands">
        <div class="operands__heading"><span>Operands</span><strong>available</strong></div>
        {rows}
      </div>'''


def _render_state_changes(
    changes: list[ExecutionCaseStateChangePayload],
) -> str:
    ordered = sorted(changes, key=lambda item: item["sequence"])
    if not ordered:
        body = '<div class="empty-state compact"><span aria-hidden="true">—</span><p>No state changes were recorded.</p></div>'
    else:
        body = '<div class="state-list">' + "".join(
            _render_state_change(change) for change in ordered
        ) + "</div>"
    return f'''
    <section class="section" aria-labelledby="state-heading">
      <div class="section-heading">
        <div><p class="eyebrow">State transition</p><h2 id="state-heading">State differences</h2></div>
        <span class="count-chip">{len(ordered)} changes</span>
      </div>
      {body}
    </section>'''


def _render_state_change(change: ExecutionCaseStateChangePayload) -> str:
    return f'''
      <article class="state-change">
        <header>
          <div><span class="sequence-chip">#{change['sequence']}</span><code>{_h(change['path'])}</code></div>
          <span class="operation-chip">{_h(change['operation'])}</span>
        </header>
        <div class="state-change__values">
          <div><span>Before</span>{_execution_value(change['before'])}</div>
          <span class="state-change__arrow" aria-hidden="true">→</span>
          <div><span>After</span>{_execution_value(change['after'])}</div>
        </div>
        {_execution_source(change['source'])}
      </article>'''


def _render_scenario(source: str) -> str:
    return f'''
    <section class="section scenario-section" aria-labelledby="scenario-heading">
      <div class="section-heading">
        <div><p class="eyebrow">Durable behavior</p><h2 id="scenario-heading">Verified scenario preview</h2></div>
        <span class="verified-chip"><span aria-hidden="true">✓</span> Verified before render</span>
      </div>
      <div class="code-window">
        <div class="code-window__bar"><span></span><span></span><span></span><strong>scenario.gwt</strong></div>
        <pre tabindex="0"><code>{_h(source)}</code></pre>
      </div>
    </section>'''


def _overview_card(label: str, value: str, slug: str, *, mono: bool = False) -> str:
    value_class = " overview-card__value--mono" if mono else ""
    return f'''
      <article class="overview-card" data-testid="overview-{slug}">
        <span>{_h(label)}</span>
        <strong class="overview-card__value{value_class}">{_h(value)}</strong>
      </article>'''


def _json_panel(label: str, value: object, test_id: str) -> str:
    return f'''
      <article class="json-panel" data-testid="{test_id}">
        <header><h3>{_h(label)}</h3><span>JSON</span></header>
        <pre tabindex="0"><code>{_h(_pretty_json(value))}</code></pre>
      </article>'''


def _case_value_panel(
    label: str,
    value: object,
    test_id: str,
    availability: str,
) -> str:
    if availability == "available":
        return _json_panel(label, value, test_id)
    message = (
        "Values were omitted by the capture policy."
        if availability == "redacted"
        else "No declared result is available because execution did not complete."
    )
    return f'''
      <article class="json-panel" data-testid="{test_id}">
        <header><h3>{_h(label)}</h3><span>{_h(availability)}</span></header>
        <p class="muted">{_h(message)}</p>
      </article>'''


def _render_case_failure(error: ExecutionCaseErrorPayload | None) -> str:
    if error is None:
        return ""
    source = _execution_source(error["source"])
    availability = error["messageAvailability"]
    return f'''
      <article class="error-card" data-testid="execution-failure">
        <div><span class="error-card__label">Execution failed</span><span>{_h(error['stage'])}</span></div>
        <code>{_h(error['message'])}</code>
        <p class="muted">Error detail: {_h(availability)}</p>
        {source}
      </article>'''


def _total_card(
    classification: ComparisonClassification,
    label: str,
    count: int,
) -> str:
    return f'''
      <article class="total-card total-card--{classification}" data-classification-total="{classification}">
        <strong>{count}</strong><span>{_h(label)}</span>
      </article>'''


def _classification_count(
    totals: ComparisonTotals,
    classification: ComparisonClassification,
) -> int:
    return {
        "unavailable": totals.unavailable,
        "baseline_mismatch": totals.baseline_mismatch,
        "unchanged": totals.unchanged,
        "path_changed": totals.path_changed,
        "output_changed": totals.output_changed,
        "new_failure": totals.new_failure,
        "resolved_failure": totals.resolved_failure,
        "failure_changed": totals.failure_changed,
        "incompatible": totals.incompatible,
    }[classification]


def _classification_label(classification: ComparisonClassification) -> str:
    return dict(_CLASSIFICATIONS)[classification]


def _execution_source(source: ExecutionCaseSourcePayload | None) -> str:
    if source is None:
        return '<span class="source-link source-link--missing">No source location recorded</span>'
    text = f'<code>{_h(source["text"])}</code>' if source["text"] else ""
    return f'''
      <div class="source-reference">
        <span class="source-link">{_h(source['file'])}:{source['line']}:{source['column']}</span>
        {text}
      </div>'''


def _execution_value(value: ExecutionCaseStateValuePayload) -> str:
    if "availability" in value:
        return f'<span class="absence">{_h(value["availability"].capitalize())}</span>'
    if not value["present"]:
        return '<span class="absence">Not present</span>'
    return f'<code>{_h(_json_inline(value.get("value")))}</code>'


def _compared_value(value: ComparedValue) -> str:
    if not value.present:
        return '<span class="absence">Not present</span>'
    return f'<code>{_h(_json_inline(value.value))}</code>'


def _optional_digest(label: str, digest: str | None) -> str:
    if digest is None:
        return ""
    return f'<span>{_h(label)} <code>{_h(digest)}</code></span>'


def _pretty_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    )


def _json_inline(value: JsonValue | None) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _safe_json(value: object) -> str:
    """Serialize JSON safely inside a non-executable ``script`` element."""

    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _h(value: object) -> str:
    return escape(str(value), quote=True)


_STYLES = r'''
:root {
  --ink: #17211d;
  --ink-soft: #52605a;
  --paper: #f5f1e8;
  --paper-deep: #e8e1d3;
  --card: #fffdf8;
  --line: #d8d0c0;
  --line-strong: #b8ad9b;
  --forest: #103e35;
  --forest-light: #1b5a4c;
  --mint: #cce8d5;
  --lime: #d9ef9f;
  --amber: #f1c36d;
  --rose: #e99582;
  --blue: #9ec9d7;
  --violet: #c3b4dc;
  --shadow: 0 18px 50px rgba(31, 42, 37, .09);
  --radius: 22px;
  --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  --sans: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--ink);
  background:
    linear-gradient(90deg, rgba(16, 62, 53, .025) 1px, transparent 1px) 0 0 / 42px 42px,
    linear-gradient(rgba(16, 62, 53, .025) 1px, transparent 1px) 0 0 / 42px 42px,
    var(--paper);
  font-family: var(--sans);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
button, code, pre { font: inherit; }
button { color: inherit; }
code, pre { font-family: var(--mono); }

.skip-link {
  position: fixed;
  z-index: 100;
  top: 12px;
  left: 12px;
  padding: 10px 14px;
  color: white;
  background: var(--forest);
  border-radius: 8px;
  transform: translateY(-150%);
}
.skip-link:focus { transform: translateY(0); }

.masthead {
  color: #f9f6ef;
  background:
    radial-gradient(circle at 88% 15%, rgba(217, 239, 159, .2), transparent 24rem),
    linear-gradient(135deg, #0b3029, #123d34 52%, #18382f);
  border-bottom: 1px solid rgba(255, 255, 255, .12);
}
.masthead__inner, .hero, .page-shell, .footer {
  width: min(1440px, calc(100% - 48px));
  margin-inline: auto;
}
.masthead__inner {
  min-height: 82px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 1px solid rgba(255, 255, 255, .12);
}
.brand { display: flex; align-items: center; gap: 14px; }
.brand__mark {
  width: 46px;
  height: 46px;
  display: grid;
  place-items: center;
  color: var(--forest);
  background: var(--lime);
  border-radius: 14px;
  font: 800 13px/1 var(--mono);
  letter-spacing: -.06em;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .5);
}
.brand__copy { display: grid; }
.brand__copy strong { font-size: 16px; letter-spacing: -.01em; }
.eyebrow {
  margin: 0 0 5px;
  color: inherit;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.brand .eyebrow { color: #b9d3ca; margin-bottom: 1px; font-size: 9px; }
.local-badge, .schema-chip, .count-chip, .verified-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  width: fit-content;
  padding: 7px 11px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .04em;
  white-space: nowrap;
}
.local-badge { color: #daf0e7; background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.12); }
.local-badge span { color: var(--lime); }

.hero { padding: 74px 0 82px; }
.hero .eyebrow { color: var(--lime); }
.hero h1 {
  max-width: 950px;
  margin: 0;
  font-size: clamp(42px, 6vw, 82px);
  line-height: .98;
  letter-spacing: -.055em;
  text-wrap: balance;
}
.hero__lede { max-width: 680px; margin: 24px 0 0; color: #c6d8d1; font-size: 18px; }
.hero__meta { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 28px; color: #9fbab1; font: 12px/1.4 var(--mono); }

.page-shell { padding: 42px 0 80px; }
.sensitivity-notice {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 15px;
  margin-bottom: 18px;
  padding: 15px 17px;
  color: #4c3920;
  background: #fff2cf;
  border: 1px solid #e5c77d;
  border-radius: 15px;
  box-shadow: 0 10px 28px rgba(73, 53, 18, .07);
}
.sensitivity-notice__icon { width: 34px; height: 34px; display: grid; place-items: center; color: white; background: #805e24; border-radius: 10px; font-weight: 900; }
.sensitivity-notice strong { font-size: 13px; }
.sensitivity-notice p { margin: 2px 0 0; color: #705d3b; font-size: 12px; }
.sensitivity-notice > span { padding: 5px 8px; color: #5b431d; background: rgba(255,255,255,.54); border: 1px solid rgba(128,94,36,.24); border-radius: 7px; font: 9px/1.3 var(--mono); text-transform: uppercase; letter-spacing: .06em; }
.section {
  margin-bottom: 28px;
  padding: clamp(22px, 3.6vw, 44px);
  background: rgba(255, 253, 248, .94);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
.comparison-section { border-top: 5px solid var(--forest); }
.evidence-section > summary {
  margin-bottom: 0;
  cursor: pointer;
  list-style: none;
}
.evidence-section > summary::-webkit-details-marker { display: none; }
.evidence-section[open] > summary { margin-bottom: 28px; }
.evidence-summary__actions { display: inline-flex; align-items: center; gap: 9px; }
.evidence-toggle {
  padding: 7px 10px;
  color: var(--forest);
  background: var(--mint);
  border-radius: 999px;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.evidence-section[open] .evidence-toggle { font-size: 0; }
.evidence-section[open] .evidence-toggle::after { content: "Collapse"; font-size: 10px; }
.section-heading, .subsection-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
}
.section-heading { margin-bottom: 28px; }
.section-heading .eyebrow, .subsection-heading .eyebrow, .rule-card .eyebrow { color: var(--forest-light); }
.section h2, .section h3, .section h4, .section h5 { margin: 0; line-height: 1.12; letter-spacing: -.03em; }
.section h2 { font-size: clamp(28px, 3vw, 42px); }
.section h3 { font-size: 22px; }
.schema-chip, .count-chip { color: var(--forest); background: var(--mint); }
.verified-chip { color: #25471d; background: var(--lime); }

.program-compare {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 20px;
  margin-bottom: 24px;
  padding: 18px 20px;
  color: #dcebe5;
  background: var(--forest);
  border-radius: 16px;
}
.program-compare > div { min-width: 0; display: grid; gap: 5px; }
.program-compare span { color: #9fc0b5; font-size: 10px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.program-compare code { overflow-wrap: anywhere; font-size: 11px; }
.program-compare__arrow { color: var(--lime) !important; font-size: 22px !important; }

.totals-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 38px;
}
.total-card {
  min-height: 108px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 18px;
  background: #f8f5ee;
  border: 1px solid var(--line);
  border-radius: 15px;
}
.total-card strong { font-size: 34px; line-height: 1; letter-spacing: -.05em; }
.total-card span { color: var(--ink-soft); font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; }
.total-card--unavailable { border-top: 4px solid var(--line-strong); }
.total-card--output_changed { border-top: 4px solid var(--rose); }
.total-card--path_changed { border-top: 4px solid var(--amber); }
.total-card--new_failure { border-top: 4px solid #c15e56; }
.total-card--failure_changed { border-top: 4px solid #8f4c6f; }
.total-card--resolved_failure { border-top: 4px solid #57936b; }
.total-card--incompatible { border-top: 4px solid var(--violet); }
.total-card--baseline_mismatch { border-top: 4px solid var(--blue); }
.total-card--unchanged { border-top: 4px solid #8fbd8e; }

.subsection-heading { margin: 0 0 16px; padding-top: 3px; }
.subsection-heading > span { color: var(--ink-soft); font: 12px/1 var(--mono); }
.filter-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.filter-button {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 8px 11px;
  color: var(--ink-soft);
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 750;
  cursor: pointer;
}
.filter-button span { min-width: 21px; padding: 1px 6px; color: var(--ink); background: var(--paper-deep); border-radius: 999px; font: 10px/1.5 var(--mono); }
.filter-button:hover, .filter-button.is-active { color: white; background: var(--forest); border-color: var(--forest); }
.filter-button.is-active span { color: var(--forest); background: var(--lime); }

.impact-layout { display: grid; grid-template-columns: minmax(230px, .62fr) minmax(0, 1.38fr); gap: 16px; }
.impact-list { display: flex; flex-direction: column; gap: 8px; }
.impact-case {
  width: 100%;
  display: grid;
  gap: 8px;
  padding: 14px;
  text-align: left;
  background: #f9f6ef;
  border: 1px solid var(--line);
  border-radius: 14px;
  cursor: pointer;
}
.impact-case:hover, .impact-case.is-selected { background: white; border-color: var(--forest-light); box-shadow: 0 8px 20px rgba(20, 65, 55, .09); }
.impact-case.is-selected { box-shadow: inset 4px 0 0 var(--forest-light), 0 8px 20px rgba(20, 65, 55, .09); }
.impact-case__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.impact-case__id, .impact-case > span:last-child { color: var(--ink-soft); font: 10px/1.3 var(--mono); }
.impact-case strong { font-size: 14px; }
.classification {
  display: inline-flex;
  width: fit-content;
  padding: 4px 7px;
  color: #3d322d;
  background: var(--paper-deep);
  border-radius: 6px;
  font-size: 9px;
  font-weight: 850;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.classification--output_changed { background: #f8d3cb; }
.classification--unavailable { background: var(--paper-deep); }
.classification--path_changed { background: #f7dfae; }
.classification--new_failure { color: white; background: #a4463f; }
.classification--failure_changed { color: white; background: #7f3f61; }
.classification--resolved_failure { color: white; background: #3f7d55; }
.classification--incompatible { background: #ddd2ef; }
.classification--baseline_mismatch { background: #cce4eb; }
.classification--unchanged { background: #d7ead6; }

.impact-panel { min-width: 0; padding: 22px; background: white; border: 1px solid var(--line); border-radius: 16px; }
.impact-panel[hidden] { display: none; }
.impact-panel > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
.impact-panel > header > div { display: grid; gap: 8px; }
.impact-panel > header code { color: var(--ink-soft); font-size: 10px; }
.impact-summary { margin: 16px 0 0; color: var(--ink-soft); }
.impact-hashes { display: grid; gap: 5px; padding: 15px 0; color: var(--ink-soft); font-size: 11px; }
.impact-hashes span { min-width: 0; }
.impact-hashes code { overflow-wrap: anywhere; color: var(--ink); }
.impact-block { margin-top: 18px; }
.impact-block h5 { margin-bottom: 10px; color: var(--ink-soft); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.field-diff {
  display: grid;
  grid-template-columns: minmax(100px, .8fr) minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  border-top: 1px solid var(--line);
}
.field-diff__path { overflow-wrap: anywhere; color: var(--forest-light); font-size: 11px; }
.field-diff > div { min-width: 0; display: grid; gap: 3px; }
.field-diff > div > span:first-child { color: var(--ink-soft); font-size: 9px; text-transform: uppercase; letter-spacing: .08em; }
.field-diff > div > code { overflow-wrap: anywhere; font-size: 11px; }
.field-diff__arrow { color: var(--line-strong); }
.decision-pair { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.decision-card { min-width: 0; display: grid; gap: 7px; padding: 13px; background: #f7f4ed; border-radius: 12px; }
.decision-card > span:first-child { color: var(--ink-soft); font-size: 9px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.decision-card code { overflow-wrap: anywhere; font-size: 11px; }
.condition-fact { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 10px; padding-top: 8px; border-top: 1px solid var(--line); }
.condition-fact:first-of-type { padding-top: 0; border-top: 0; }
.condition-operands { grid-column: 1 / -1; color: var(--ink-soft); font: 9px/1.45 var(--mono); }
.condition-fact .source-link { grid-column: 1 / -1; }
.source-link { color: var(--forest-light); font: 10px/1.4 var(--mono); }
.source-link--missing { color: var(--ink-soft); }
.error-card { margin-top: 12px; padding: 14px; color: #622d29; background: #fae3de; border: 1px solid #efb9ad; border-radius: 12px; }
.error-card > div { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 5px; font-size: 10px; }
.error-card__label { font-weight: 850; text-transform: uppercase; letter-spacing: .08em; }
.error-card code { font-size: 11px; overflow-wrap: anywhere; }

.overview-grid { display: grid; grid-template-columns: .8fr .7fr 1fr 1.7fr; gap: 10px; margin-bottom: 16px; }
.overview-card { min-width: 0; min-height: 126px; display: flex; flex-direction: column; justify-content: space-between; padding: 19px; background: #f8f5ee; border: 1px solid var(--line); border-radius: 16px; }
.overview-card > span { color: var(--ink-soft); font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .09em; }
.overview-card__value { overflow-wrap: anywhere; font-size: 19px; line-height: 1.2; letter-spacing: -.02em; }
.overview-card__value--mono { font: 10px/1.5 var(--mono); letter-spacing: 0; }
.data-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }
.json-panel { min-width: 0; overflow: hidden; background: #14231e; border: 1px solid #203b33; border-radius: 16px; }
.json-panel header { min-height: 48px; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; color: #d9e7e1; background: #1a3029; border-bottom: 1px solid rgba(255,255,255,.08); }
.json-panel h3 { font-size: 13px; letter-spacing: 0; }
.json-panel header span { color: #90afa4; font: 9px/1 var(--mono); letter-spacing: .12em; }
.json-panel pre, .code-window pre { margin: 0; overflow: auto; }
.json-panel pre { min-height: 280px; max-height: 520px; padding: 20px; color: #d9e7e1; font-size: 11px; line-height: 1.75; }

.rule-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 18px;
  margin-top: 16px;
  padding: 20px;
  background: linear-gradient(120deg, #e4f0dc, #edf4e5);
  border: 1px solid #bfd0ae;
  border-radius: 16px;
}
.rule-card--empty { grid-template-columns: auto minmax(0, 1fr); background: #f5f1e8; border-color: var(--line); }
.rule-card__marker { width: 42px; height: 42px; display: grid; place-items: center; color: white; background: var(--forest); border-radius: 12px; font-size: 22px; }
.rule-card h3 code { overflow-wrap: anywhere; font-size: 15px; letter-spacing: 0; }
.rule-card p:last-child { margin: 6px 0 0; color: var(--ink-soft); }
.truth-chip { align-self: start; padding: 6px 9px; color: var(--forest); background: rgba(255,255,255,.6); border: 1px solid rgba(16,62,53,.16); border-radius: 8px; font: 10px/1.2 var(--mono); }
.source-reference { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 9px; }
.source-reference > code { overflow-wrap: anywhere; color: var(--ink-soft); font-size: 10px; }

.timeline { position: relative; margin: 0; padding: 0; list-style: none; }
.timeline::before { content: ""; position: absolute; top: 18px; bottom: 18px; left: 18px; width: 1px; background: var(--line-strong); }
.timeline-item { position: relative; display: grid; grid-template-columns: 38px minmax(0, 1fr); gap: 18px; padding-bottom: 14px; }
.timeline-item:last-child { padding-bottom: 0; }
.timeline-item__sequence { position: relative; z-index: 1; width: 37px; height: 37px; display: grid; place-items: center; color: var(--forest); background: var(--card); border: 1px solid var(--line-strong); border-radius: 50%; font: 10px/1 var(--mono); }
.timeline-item > article { min-width: 0; padding: 16px 18px; background: #f8f5ee; border: 1px solid var(--line); border-radius: 14px; }
.timeline-item > article > header { display: flex; align-items: center; gap: 10px; }
.event-kind { padding: 4px 7px; color: var(--forest); background: var(--mint); border-radius: 6px; font-size: 9px; font-weight: 850; letter-spacing: .07em; text-transform: uppercase; }
.timeline-item__summary { min-width: 0; overflow-wrap: anywhere; font-size: 13px; font-weight: 700; }
.fact-list { display: flex; flex-wrap: wrap; gap: 8px 18px; margin: 13px 0 0; }
.fact-list > div { min-width: 110px; display: grid; gap: 3px; }
.fact-list dt { color: var(--ink-soft); font-size: 9px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.fact-list dd { min-width: 0; margin: 0; }
.fact-list code { overflow-wrap: anywhere; font-size: 11px; }
.operands { margin-top: 13px; overflow: hidden; background: white; border: 1px solid var(--line); border-radius: 10px; }
.operands__heading, .operand-row { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(80px, .5fr) minmax(0, .8fr); align-items: center; gap: 10px; padding: 9px 11px; }
.operands__heading { display: flex; justify-content: space-between; color: var(--ink-soft); background: #f0ece3; font-size: 9px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.operands__heading strong { color: var(--forest-light); }
.operand-row + .operand-row { border-top: 1px solid var(--line); }
.operand-row code, .operand-row strong { min-width: 0; overflow-wrap: anywhere; font-size: 10px; }
.operand-row span { color: var(--ink-soft); font-size: 9px; }
.operands--unavailable { display: flex; justify-content: space-between; gap: 12px; padding: 10px 11px; color: var(--ink-soft); background: #f3efe7; font-size: 10px; }
.operands--unavailable code { overflow-wrap: anywhere; }

.state-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.state-change { min-width: 0; padding: 17px; background: #f8f5ee; border: 1px solid var(--line); border-radius: 15px; }
.state-change > header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.state-change > header > div { min-width: 0; display: flex; align-items: center; gap: 8px; }
.state-change > header code { overflow-wrap: anywhere; font-size: 11px; }
.sequence-chip, .operation-chip { padding: 4px 7px; border-radius: 6px; font: 9px/1.2 var(--mono); }
.sequence-chip { color: var(--forest); background: var(--mint); }
.operation-chip { color: #5a4520; background: #f5dfae; }
.state-change__values { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); align-items: center; gap: 8px; margin-top: 14px; padding: 12px; background: white; border-radius: 11px; }
.state-change__values > div { min-width: 0; display: grid; gap: 4px; }
.state-change__values > div > span { color: var(--ink-soft); font-size: 9px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.state-change__values code { overflow-wrap: anywhere; font-size: 10px; }
.state-change__arrow { color: var(--line-strong); }
.state-change > .source-reference { padding-top: 11px; border-top: 1px solid var(--line); }
.absence { color: var(--ink-soft); font-size: 11px; font-style: italic; }
.muted { color: var(--ink-soft); }

.scenario-section { border-top: 5px solid var(--lime); }
.code-window { overflow: hidden; color: #dbe8e3; background: #101c18; border: 1px solid #243b34; border-radius: 17px; }
.code-window__bar { height: 48px; display: flex; align-items: center; gap: 7px; padding: 0 16px; background: #192923; border-bottom: 1px solid rgba(255,255,255,.08); }
.code-window__bar span { width: 9px; height: 9px; background: #799187; border-radius: 50%; }
.code-window__bar span:first-child { background: var(--rose); }
.code-window__bar span:nth-child(2) { background: var(--amber); }
.code-window__bar span:nth-child(3) { background: var(--lime); }
.code-window__bar strong { margin-left: 8px; color: #9fb5ac; font: 10px/1 var(--mono); }
.code-window pre { max-height: 680px; padding: 24px; font-size: 12px; line-height: 1.72; }

.empty-state { display: flex; align-items: center; gap: 16px; padding: 22px; color: var(--ink-soft); background: #f6f3ec; border: 1px dashed var(--line-strong); border-radius: 15px; }
.empty-state p { margin: 2px 0 0; }
.empty-state__icon { width: 38px; height: 38px; display: grid; place-items: center; color: var(--forest); background: var(--mint); border-radius: 50%; font-weight: 900; }
.empty-state.compact { padding: 16px; }

.footer { display: flex; justify-content: space-between; gap: 20px; padding: 0 0 42px; color: var(--ink-soft); font-size: 11px; }

button:focus-visible, a:focus-visible, pre:focus-visible { outline: 3px solid #e1ad3e; outline-offset: 3px; }

@media (max-width: 1080px) {
  .totals-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .overview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 820px) {
  .masthead__inner, .hero, .page-shell, .footer { width: min(100% - 28px, 1440px); }
  .hero { padding: 54px 0 62px; }
  .section { padding: 22px; border-radius: 18px; }
  .impact-layout, .data-grid, .state-list { grid-template-columns: 1fr; }
  .impact-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .json-panel pre { min-height: 220px; }
}
@media (max-width: 600px) {
  .masthead__inner { min-height: 72px; }
  .brand__copy .eyebrow { display: none; }
  .local-badge { padding-inline: 9px; }
  .hero h1 { font-size: 42px; }
  .hero__meta { display: grid; }
  .hero__meta [aria-hidden="true"] { display: none; }
  .section-heading { align-items: flex-start; flex-direction: column; }
  .sensitivity-notice { grid-template-columns: auto minmax(0, 1fr); }
  .sensitivity-notice > span { grid-column: 2; }
  .totals-grid, .overview-grid, .impact-list { grid-template-columns: 1fr 1fr; }
  .total-card { min-height: 90px; }
  .program-compare { grid-template-columns: 1fr; }
  .program-compare__arrow { transform: rotate(90deg); }
  .field-diff { grid-template-columns: 1fr; }
  .field-diff__arrow { transform: rotate(90deg); }
  .decision-pair { grid-template-columns: 1fr; }
  .rule-card { grid-template-columns: auto minmax(0, 1fr); }
  .truth-chip { grid-column: 2; }
  .footer { flex-direction: column; }
}
@media (max-width: 410px) {
  .totals-grid, .overview-grid, .impact-list { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after { transition-duration: .001ms !important; animation-duration: .001ms !important; }
}
@media print {
  body { background: white; }
  .masthead { color: var(--ink); background: white; }
  .masthead__inner, .hero, .page-shell, .footer { width: 100%; }
  .local-badge, .filter-row, .skip-link { display: none; }
  .section { break-inside: avoid; box-shadow: none; }
  .impact-panel[hidden] { display: block; margin-top: 12px; }
}
'''


_SCRIPT = r'''
(() => {
  "use strict";
  const comparison = document.querySelector("[data-comparison]");
  if (!comparison) return;

  const filters = Array.from(comparison.querySelectorAll("[data-filter]"));
  const choices = Array.from(comparison.querySelectorAll("[data-case-choice]"));
  const panels = Array.from(comparison.querySelectorAll("[data-case-panel]"));

  const selectCase = (choice) => {
    const target = choice.getAttribute("data-target");
    choices.forEach((item) => {
      const selected = item === choice;
      item.classList.toggle("is-selected", selected);
      item.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    panels.forEach((panel) => { panel.hidden = panel.id !== target; });
  };

  const applyFilter = (classification) => {
    filters.forEach((button) => {
      const active = button.getAttribute("data-filter") === classification;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const visible = choices.filter((choice) => {
      const show = classification === "all" || choice.getAttribute("data-classification") === classification;
      choice.hidden = !show;
      return show;
    });
    const selected = choices.find((choice) => choice.getAttribute("aria-pressed") === "true");
    if (!selected || selected.hidden) {
      if (visible.length) selectCase(visible[0]);
      else panels.forEach((panel) => { panel.hidden = true; });
    }
  };

  filters.forEach((button) => {
    button.addEventListener("click", () => applyFilter(button.getAttribute("data-filter") || "all"));
  });
  choices.forEach((choice) => {
    choice.addEventListener("click", () => selectCase(choice));
  });
})();
'''
