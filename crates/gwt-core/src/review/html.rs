use super::{CorpusReview, ReviewRow, error};
use crate::source::Result;
use crate::{ExecutionExplanation, Presence, ProgramExecution, SourceExcerpt};
use serde_json::{Value as Json, json};
use std::fmt::Write;

fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}
fn code(value: &Json) -> String {
    format!(
        "<pre>{}</pre>",
        escape(&serde_json::to_string_pretty(value).expect("JSON"))
    )
}
fn difference_value(value: &Presence) -> String {
    match value {
        Presence::Missing => "<p class=caption>Missing field</p>".into(),
        Presence::Present(value) => code(value),
    }
}
fn excerpt(value: &SourceExcerpt) -> String {
    format!(
        "<p class=location>{}:{}:{}</p><pre class=source>{}</pre>",
        escape(&value.span.file),
        value.span.line,
        value.span.column,
        if value.text.is_empty() {
            "(program boundary)".into()
        } else {
            escape(&value.text)
        }
    )
}
fn label(status: &str) -> &str {
    match status {
        "outcome_changed" => "Outcome changed",
        "state_changed" => "State changed",
        "evidence_changed" => "Evidence changed",
        "source_changed" => "Source changed",
        "unchanged" => "Unchanged",
        "candidate_failed" => "Candidate failed",
        "baseline_mismatch" => "Baseline mismatch",
        _ => "Unavailable",
    }
}
fn trail(explanation: &ExecutionExplanation, prefix: &str) -> String {
    let mut html = String::new();
    if let Some(failure) = &explanation.failure {
        write!(
            html,
            "<div class=failure><strong>Execution stopped here</strong>{}</div>",
            excerpt(failure)
        )
        .unwrap();
    }
    html.push_str("<ol class=trail>");
    for step in &explanation.steps {
        let minor = !matches!(
            step.operation.as_str(),
            "branch"
                | "kind branch"
                | "value branch"
                | "branch skipped"
                | "else selected"
                | "set"
                | "initialize field"
                | "table row"
                | "add"
                | "subtract"
                | "append"
                | "append item"
                | "count"
                | "sum"
                | "enter collection"
                | "collection item"
                | "collection selection"
                | "leave collection"
                | "sum item"
                | "example row"
                | "assert"
                | "enter behavior"
                | "enter request"
                | "output contract"
                | "return"
                | "assert prints"
                | "assert failure"
                | "argument value"
        );
        let mut preview: String = step.source.text.chars().take(180).collect();
        if preview.len() < step.source.text.len() {
            preview.push('…');
        }
        write!(html, "<li id=\"{prefix}-event-{}\" class=\"event {}\"><details><summary><span class=event-number>#{}</span> <strong>{}</strong> {}<span class=step-source>{}</span></summary>{}",
            step.event, if minor { "minor" } else { "" }, step.event, escape(&step.operation), escape(&step.summary), escape(&preview), excerpt(&step.source)).unwrap();
        if !step.operands.is_empty() {
            html.push_str("<p class=operands>Recorded operands: ");
            for operand in &step.operands {
                write!(
                    html,
                    "<a href=\"#{prefix}-event-{operand}\" data-operand>{operand}</a> "
                )
                .unwrap();
            }
            html.push_str("</p>");
        }
        if let Some(skipped) = &step.skipped {
            write!(
                html,
                "<p><strong>Not evaluated</strong></p>{}",
                excerpt(skipped)
            )
            .unwrap();
        }
        if let Some(definition) = &step.definition {
            write!(
                html,
                "<details><summary>Behavior or request definition</summary>{}</details>",
                excerpt(definition)
            )
            .unwrap();
        }
        if let Some(failure) = &step.observed_failure {
            write!(
                html,
                "<p><strong>Observed action failure</strong></p>{}",
                excerpt(failure)
            )
            .unwrap();
        }
        write!(
            html,
            "<p class=caption>Recorded value</p>{}</details></li>",
            code(&step.value)
        )
        .unwrap();
    }
    html.push_str("</ol>");
    html
}
fn run(
    execution: &ProgramExecution,
    explanation: &ExecutionExplanation,
    title: &str,
    prefix: &str,
) -> String {
    let mut html = format!(
        "<section class=run><h3>{title}</h3><p class=\"badge {}\">{}</p>",
        if execution.ok { "ok" } else { "bad" },
        if execution.ok {
            "Completed"
        } else {
            "Execution failed"
        }
    );
    if let Some(diagnostic) = &execution.diagnostic {
        write!(
            html,
            "<p class=failure>{}: {}</p>",
            escape(&diagnostic.code),
            escape(&diagnostic.message)
        )
        .unwrap();
    }
    write!(html, "<h4>{}</h4>{}<details><summary>State and captured output</summary><h4>State</h4>{}<h4>Captured output</h4>{}</details><h4>Decision trail</h4>{}<p class=caption>{} execution steps · {} recorded events</p></section>",
        if execution.request.is_some() { "Declared result" } else { "Scenario result" },
        code(execution.result.as_ref().unwrap_or(&Json::Null)), code(&execution.state), code(&json!(execution.output)), trail(explanation, prefix), execution.steps, execution.events.len()).unwrap();
    html
}
fn panel(row: &ReviewRow, index: usize) -> String {
    let mut html = format!(
        "<template id=\"case-{index}\"><article data-case-panel><h2>{}</h2><p>{}</p><p class=badge>{}</p>",
        escape(&row.id),
        escape(&row.label),
        label(&row.status)
    );
    write!(html, "<fieldset class=decision><legend>Your decision for this case</legend><label>Decision<select data-decision><option value=pending>Pending</option><option value=accept {}>Accept</option><option value=reject>Reject</option><option value=needs_information>Needs information</option></select></label><label>Review note<textarea data-decision-note rows=3 placeholder=\"Explain a rejection or the information needed\"></textarea></label><p class=caption>{}</p></fieldset>",
        if matches!(row.status.as_str(), "unavailable" | "baseline_mismatch") { "disabled" } else { "" },
        if matches!(row.status.as_str(), "unavailable" | "baseline_mismatch") { "This case cannot be accepted until its comparison evidence is verified." } else { "Acceptance records your judgment about this case, including any expected failure." }).unwrap();
    if let Some(request) = &row.request {
        write!(html, "<p>Request: <strong>{}</strong></p>", escape(request)).unwrap();
    }
    if let Some(scenario) = &row.scenario {
        write!(
            html,
            "<p>Scenario: <strong>{}</strong></p>",
            escape(scenario)
        )
        .unwrap();
        html.push_str("<p class=caption>This comparison runs each revision's scenario, including its setup and assertions. Request cases keep supplied host input fixed.</p>");
    }
    if let Some(input) = &row.input {
        write!(
            html,
            "<details><summary>Supplied input</summary>{}</details>",
            code(input)
        )
        .unwrap();
    }
    if let Some(limits) = &row.captured_limits {
        write!(html, "<details data-captured-limits><summary>Captured execution limits</summary><p class=caption>Limits saved with this case. Comparison never overrides them. A matching result does not establish capacity for other inputs.</p>{}</details>", code(&json!(limits))).unwrap();
    }
    if let Some(integrity) = &row.case_integrity {
        write!(html, "<details><summary>Case identity</summary><p class=caption>This identifier binds the saved observation and its capture settings; it is not an approval or signature.</p><pre>{}</pre></details>", escape(integrity)).unwrap();
    }
    if let Some(diagnostic) = &row.diagnostic {
        write!(html, "<div class=failure><h3>Comparison unavailable</h3><p>{}: {}</p><p>This entry is not counted as compared.</p></div>", escape(&diagnostic.code), escape(&diagnostic.message)).unwrap();
    }
    if let Some(comparison) = &row.comparison {
        if !comparison.baseline.verified {
            write!(html, "<div class=failure><h3>Recorded baseline did not reproduce</h3><p>The candidate was not run. These differences compare the stored observation with the replay.</p>{}<p>{}</p></div>",
                code(&json!(comparison.baseline.differences)), if comparison.baseline.differences_truncated { "Difference list truncated; verification compared the entire execution." } else { "All differences shown." }).unwrap();
        } else {
            html.push_str("<h3>Outcome differences</h3>");
            if comparison.outcome_differences.is_empty() {
                html.push_str(
                    "<p>No change to the outcome. Source, state, or evidence may still differ.</p>",
                );
            } else {
                html.push_str("<div class=table-wrap><table><thead><tr><th>Field</th><th>Baseline</th><th>Candidate</th></tr></thead><tbody>");
                for difference in &comparison.outcome_differences {
                    write!(
                        html,
                        "<tr><td><code>{}</code></td><td>{}</td><td>{}</td></tr>",
                        escape(&difference.path),
                        difference_value(&difference.before),
                        difference_value(&difference.after)
                    )
                    .unwrap();
                }
                html.push_str("</tbody></table></div>");
                if comparison.outcome_differences_truncated {
                    html.push_str("<p class=failure>Difference list truncated. Full executions remain available in the review JSON.</p>");
                }
            }
            write!(
                html,
                "<details><summary>Change flags</summary>{}</details>",
                code(&json!(comparison.changes))
            )
            .unwrap();
            html.push_str("<label class=toggle><input type=checkbox data-all-events> Show all expression and lifecycle events</label><div class=runs>");
            if let (Some(baseline), Some(candidate), Some(execution)) = (
                &row.baseline_explanation,
                &row.candidate_explanation,
                &comparison.candidate,
            ) {
                html.push_str(&run(
                    &comparison.baseline.actual,
                    baseline,
                    "Verified baseline",
                    &format!("row-{index}-old"),
                ));
                html.push_str(&run(
                    execution,
                    candidate,
                    "Candidate",
                    &format!("row-{index}-new"),
                ));
            }
            html.push_str("</div>");
        }
    }
    html.push_str("</article></template>");
    html
}

/// Self-contained offline HTML. Values are escaped as text, never parsed into
/// JavaScript numbers; downloaded JSON retains exact native numeric tokens.
pub fn render_review_html(report: &CorpusReview) -> Result<String> {
    let mut html = String::from(
        "<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><meta http-equiv=Content-Security-Policy content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'\"><title>GWT behavior review</title><style>",
    );
    html.push_str(include_str!("review.css"));
    html.push_str("</style><body><header><p class=eyebrow>GWT · Native behavior review</p><h1>What changed in these decisions?</h1><p>Compare observed outcomes, inspect the rules that ran, and keep unverified cases visible.</p></header><main>");
    let totals = &report.totals;
    write!(html, "<section class=metrics aria-label=\"Review coverage\"><div><strong>{} / {}</strong><span>cases compared</span></div><div><strong>{}</strong><span>outcomes changed</span></div><div><strong>{}</strong><span>candidate failures</span></div><div><strong>{}</strong><span>cases not verified</span></div></section>", totals.compared, totals.total, totals.outcome_changed, totals.candidate_failed, totals.baseline_mismatch + totals.unavailable).unwrap();
    write!(html, "<p class=notice>{} Coverage is not approval of a rule change. Source-position changes can alter evidence without changing an outcome.</p>", if report.complete { "Every case was compared." } else { "Review coverage is incomplete. Unverified cases are retained below." }).unwrap();
    html.push_str("<section class=decision-tools aria-label=\"Saved reviewer decisions\"><label>Reviewer<input type=text data-reviewer autocomplete=off placeholder=\"Name or team\"></label><div class=decision-actions><button data-download-decisions>Download decisions</button><label class=file-label>Load decisions<input type=file data-load-decisions accept=\"application/json,.json\"></label></div><p data-decision-count aria-live=polite></p><p class=caption>Changes stay in this page until you download decisions. Saved decisions apply only to this exact review. The reviewer name is self-reported.</p><p data-decision-message role=status></p></section>");
    html.push_str("<div class=toolbar><label>Find a case<input type=search data-search placeholder=\"Case, request, scenario, input, or changed field\"></label><label>Show<select data-filter><option value=all>All cases</option><option value=outcome_changed>Outcome changed</option><option value=candidate_failed>Candidate failed</option><option value=unverified>Unverified cases</option><option value=state_changed>State changed, same outcome</option><option value=evidence_changed>Evidence changed, same state</option><option value=source_changed>Source changed only</option><option value=unchanged>Unchanged</option><option value=decision_pending>Decision pending</option><option value=decision_accept>Accepted</option><option value=decision_reject>Rejected</option><option value=decision_needs_information>Needs information</option></select></label><button data-download>Download review JSON</button></div><p data-count aria-live=polite></p><div class=workspace><nav class=queue aria-label=\"Captured cases\">");
    for (index, row) in report.cases.iter().enumerate() {
        let search = format!(
            "{} {} {} {} {} {}",
            row.id,
            row.label,
            row.request.as_deref().unwrap_or(""),
            row.scenario.as_deref().unwrap_or(""),
            row.input.as_ref().unwrap_or(&Json::Null),
            row.comparison
                .as_ref()
                .map(|c| json!(c.outcome_differences))
                .unwrap_or(Json::Null)
        );
        let changed = row
            .comparison
            .as_ref()
            .and_then(|c| c.changes.as_ref())
            .is_some_and(|c| c.outcome);
        write!(html, "<button data-case=\"{index}\" data-status=\"{}\" data-changed=\"{changed}\" data-search-text=\"{}\" aria-pressed=false><strong>{}</strong><span>{}</span><small>{}</small></button>", escape(&row.status), escape(&search), escape(&row.id), escape(&row.label), label(&row.status)).unwrap();
    }
    html.push_str("</nav><section class=selection aria-label=\"Selected case\"><div data-panel></div><p data-empty hidden>No cases match these filters.</p></section></div><details class=snapshots><summary>Frozen source snapshots and review identity</summary><p>These are the exact source texts used for the displayed executions.</p>");
    write!(
        html,
        "<h3>Engine</h3>{}<h3>Candidate identity</h3>{}",
        code(&json!(report.engine)),
        code(&json!(report.candidate_identity))
    )
    .unwrap();
    for (digest, source) in &report.sources {
        write!(
            html,
            "<details><summary>{} · {}</summary>",
            escape(&source.entry),
            escape(digest)
        )
        .unwrap();
        for (path, text) in &source.modules {
            write!(html, "<h4>{}</h4><pre>{}</pre>", escape(path), escape(text)).unwrap();
        }
        html.push_str("</details>");
    }
    html.push_str("</details><noscript><p>This review needs JavaScript for case selection. Use the JSON report produced by the review command when JavaScript is unavailable.</p></noscript></main>");
    for (index, row) in report.cases.iter().enumerate() {
        html.push_str(&panel(row, index));
        if html.len() > 128 * 1_048_576 {
            return Err(error("review_limit", "review presentation exceeds 128 MiB"));
        }
    }
    let data = serde_json::to_string(report)
        .expect("review JSON")
        .replace('<', "\\u003c")
        .replace('>', "\\u003e")
        .replace('&', "\\u0026");
    html.push_str("<script type=application/json id=review-data>");
    html.push_str(&data);
    html.push_str("</script><script type=application/json id=decision-data>");
    let decisions = super::ReviewDecisions::pending(report)?
        .to_json()
        .replace('<', "\\u003c")
        .replace('>', "\\u003e")
        .replace('&', "\\u0026");
    html.push_str(&decisions);
    html.push_str("</script><script>");
    html.push_str(include_str!("review.js"));
    html.push_str("</script></body></html>");
    if html.len() > 256 * 1_048_576 {
        return Err(error(
            "review_limit",
            "complete review HTML exceeds 256 MiB",
        ));
    }
    Ok(html)
}
