//! Decisions refer to one immutable proposal; presentation does not infer old-engine semantics.
use super::{CaseMigration, error};
use crate::source::Result;
use crate::{DecisionStatus, SourceBundle};
use serde::{Deserialize, Serialize};
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::fmt::Write;

pub const MAX_MIGRATION_DECISION_BYTES: usize = 32_768;

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct DecisionFile {
    kind: String,
    schema_version: u32,
    proposal_integrity: String,
    reviewer: String,
    status: DecisionStatus,
    note: String,
}
#[derive(Debug, Serialize)]
#[serde(transparent)]
pub struct MigrationDecision(DecisionFile);
impl MigrationDecision {
    pub fn pending(proposal: &CaseMigration) -> Self {
        Self(DecisionFile {
            kind: "gwt.native-migration-decision".into(),
            schema_version: 1,
            proposal_integrity: proposal.integrity().into(),
            reviewer: String::new(),
            status: DecisionStatus::Pending,
            note: String::new(),
        })
    }
    pub fn from_json(source: &str) -> Result<Self> {
        if source.len() > MAX_MIGRATION_DECISION_BYTES {
            return Err(error(
                "migration_decision_limit",
                "decision file exceeds 32 KiB",
            ));
        }
        let decision = Self(
            serde_json::from_str(source)
                .map_err(|failure| error("migration_decision_format", failure.to_string()))?,
        );
        decision.validate()?;
        Ok(decision)
    }
    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("decision JSON")
    }
    fn validate(&self) -> Result<()> {
        let file = &self.0;
        if file.kind != "gwt.native-migration-decision"
            || file.schema_version != 1
            || !crate::cases::is_sha256(&file.proposal_integrity)
        {
            return Err(error(
                "migration_decision_format",
                "expected migration-decision schema 1 and a proposal SHA-256",
            ));
        }
        if file.reviewer.len() > 256
            || file.reviewer.chars().any(char::is_control)
            || file.note.len() > 4096
        {
            return Err(error(
                "migration_decision_limit",
                "reviewer permits 256 UTF-8 bytes without controls; note permits 4096 UTF-8 bytes",
            ));
        }
        if file.status != DecisionStatus::Pending
            && (file.reviewer.trim().is_empty() || file.note.trim().is_empty())
        {
            return Err(error(
                "migration_decision_required",
                "a non-pending choice requires a reviewer and a note",
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MigrationAssessment {
    kind: &'static str,
    schema_version: u32,
    pub proposal_integrity: String,
    pub decision_integrity: String,
    pub original_case_integrity: String,
    pub candidate_case_integrity: Option<String>,
    pub reviewer: String,
    pub status: DecisionStatus,
    pub note: String,
    /// A matching explicit choice, not authenticated identity or proof of domain correctness.
    pub accepted: bool,
}

/// Assess only against a freshly prepared proposal from trusted previous-engine replay.
pub fn assess_migration(
    proposal: &CaseMigration,
    decision: &MigrationDecision,
) -> Result<MigrationAssessment> {
    decision.validate()?;
    if decision.0.proposal_integrity != proposal.integrity() {
        return Err(error(
            "migration_decision_stale",
            "decision belongs to a different proposal; review the new transition",
        ));
    }
    if decision.0.status == DecisionStatus::Accept && proposal.candidate().is_none() {
        return Err(error(
            "migration_decision_unavailable",
            "an unavailable candidate cannot be accepted",
        ));
    }
    let mut bytes = Vec::new();
    crate::cases::canonical(&json!(decision), &mut bytes);
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-migration-decision-sha256-v1\0");
    hash.update(bytes);
    Ok(MigrationAssessment {
        kind: "gwt.native-migration-assessment",
        schema_version: 1,
        proposal_integrity: proposal.integrity().into(),
        decision_integrity: format!("sha256:{:x}", hash.finalize()),
        original_case_integrity: proposal.original().integrity().into(),
        candidate_case_integrity: proposal.candidate().map(|case| case.integrity().into()),
        reviewer: decision.0.reviewer.clone(),
        status: decision.0.status,
        note: decision.0.note.clone(),
        accepted: decision.0.status == DecisionStatus::Accept && proposal.candidate().is_some(),
    })
}

pub(super) fn escape(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}
pub(super) fn code(value: &Json) -> String {
    format!(
        "<pre>{}</pre>",
        escape(&serde_json::to_string_pretty(value).expect("JSON"))
    )
}
fn span_excerpt(span: &Json, source: &SourceBundle) -> Result<String> {
    let span = serde_json::from_value(span.clone()).map_err(|_| {
        error(
            "migration_evidence",
            "recorded event has an invalid source span",
        )
    })?;
    let excerpt = crate::explanation::excerpt(&span, source)?;
    Ok(format!(
        "<p class=location>{}:{}:{}</p><pre class=source>{}</pre>",
        escape(&excerpt.span.file),
        excerpt.span.line,
        excerpt.span.column,
        escape(&excerpt.text)
    ))
}
pub(super) fn execution(
    run: &Json,
    source: &SourceBundle,
    title: &str,
    prefix: &str,
) -> Result<String> {
    let ok = run["ok"].as_bool().ok_or_else(|| {
        error(
            "migration_evidence",
            "observation must record execution success",
        )
    })?;
    let mut html = format!(
        "<section class=execution><h3>{}</h3><p class=badge>{}</p>",
        escape(title),
        if ok {
            "Execution completed"
        } else {
            "Execution failed"
        }
    );
    if !run["diagnostic"].is_null() {
        write!(
            html,
            "<div class=failure>{}{}</div>",
            code(&run["diagnostic"]),
            span_excerpt(&run["diagnostic"]["span"], source)?
        )
        .unwrap();
    }
    write!(
        html,
        "<h4>Result</h4>{}<details><summary>State and printed output</summary>{}</details>",
        code(&run["result"]),
        code(&json!({"state":run["state"],"output":run["output"]}))
    )
    .unwrap();
    html.push_str("<details class=event-trail><summary>Recorded execution events</summary><p class=caption>These are the engine's recorded values and source locations. They do not establish why a different engine behaved differently.</p><ol>");
    let events = run["events"].as_array().ok_or_else(|| {
        error(
            "migration_evidence",
            "observation must contain recorded events",
        )
    })?;
    for (index, event) in events.iter().enumerate() {
        if event["sequence"].as_u64() != Some((index + 1) as u64) {
            return Err(error("migration_evidence", "event IDs must be ordered"));
        }
        let operation = event["operation"]
            .as_str()
            .ok_or_else(|| error("migration_evidence", "event operation must be text"))?;
        let inputs = event["inputs"]
            .as_array()
            .ok_or_else(|| error("migration_evidence", "event operands must be an array"))?;
        write!(
            html,
            "<li id={prefix}-event-{}><details><summary>#{0} <strong>{}</strong></summary>{}",
            index + 1,
            escape(operation),
            span_excerpt(&event["span"], source)?
        )
        .unwrap();
        if !inputs.is_empty() {
            html.push_str("<p>Recorded operands: ");
        }
        for input in inputs {
            let id = input
                .as_u64()
                .filter(|id| *id > 0 && *id <= (index as u64))
                .ok_or_else(|| {
                    error(
                        "migration_evidence",
                        "event operands must identify prior events",
                    )
                })?;
            write!(
                html,
                "<a data-operand href=\"#{prefix}-event-{id}\">{id}</a> "
            )
            .unwrap();
        }
        if !inputs.is_empty() {
            html.push_str("</p>");
        }
        let value = event
            .get("value")
            .ok_or_else(|| error("migration_evidence", "event must retain its recorded value"))?;
        html.push_str(&code(value));
        if let Some(skipped) = event.get("skipped").filter(|value| !value.is_null()) {
            html.push_str("<p>Not evaluated</p>");
            html.push_str(&span_excerpt(skipped, source)?);
        }
        html.push_str("</details></li>");
        if html.len() > 64 * 1_048_576 {
            return Err(error(
                "migration_review_limit",
                "execution presentation exceeds 64 MiB",
            ));
        }
    }
    write!(
        html,
        "</ol></details><p class=caption>{} recorded steps · {} events</p></section>",
        run["steps"],
        events.len()
    )
    .unwrap();
    Ok(html)
}

pub fn render_migration_html(proposal: &CaseMigration) -> Result<String> {
    let original = proposal.original();
    let name = original
        .request()
        .or_else(|| original.scenario())
        .expect("validated target");
    let mut html = String::from(
        "<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><meta http-equiv=Content-Security-Policy content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'\"><title>GWT engine migration review</title><style>",
    );
    html.push_str(include_str!("review.css"));
    html.push_str("</style><body><header><p class=eyebrow>GWT · Engine migration</p>");
    write!(html,"<h1>{}</h1><p>{}: {}</p><p class=notice>Review this transition before carrying the case forward. Source, target, input, and execution limits are held fixed.</p></header><main data-candidate={}> ",escape(name),if original.request().is_some(){"Request"}else{"Scenario"},match proposal.status {"observation_preserved"=>"Observation preserved","observation_changed"=>"Observation changed",_=>"Candidate unavailable"},proposal.candidate().is_some()).unwrap();
    if let Some(changes) = &proposal.changes {
        html.push_str("<section class=metrics aria-label=\"Change summary\">");
        for (name, changed) in [
            ("Outcome", changes.outcome),
            ("State", changes.state),
            ("Evidence", changes.evidence),
        ] {
            write!(
                html,
                "<div><strong>{}</strong><span>{name}</span></div>",
                if changed { "Changed" } else { "Same" }
            )
            .unwrap();
        }
        html.push_str("</section>");
    }
    write!(html,"<section class=decision><h2>Your decision</h2><label>Reviewer<input data-reviewer autocomplete=off></label><label>Decision<select data-status><option value=pending>Pending</option><option value=accept {}>Accept</option><option value=reject>Reject</option><option value=needs_information>Needs information</option></select></label><label>Review note<textarea data-note rows=4></textarea></label><div class=actions><button data-save>Download decision</button><label class=file-label>Load decision<input type=file data-load accept=\"application/json,.json\"></label><button data-download>Download proposal</button></div><p class=caption>Choices stay in this page until downloaded. The reviewer name is self-reported. Export rechecks both engines and requires acceptance of this exact proposal.</p><p data-message role=status></p></section>",if proposal.candidate().is_none(){"disabled"}else{""}).unwrap();
    html.push_str(&render_details(proposal, "")?);
    html.push_str("<noscript><p>All recorded behavior remains readable without JavaScript. Saving or restoring a decision requires JavaScript.</p></noscript></main>");
    for (id, data) in [
        (
            "proposal-data",
            serde_json::to_string(proposal).expect("proposal JSON"),
        ),
        (
            "decision-data",
            MigrationDecision::pending(proposal).to_json(),
        ),
    ] {
        write!(
            html,
            "<script type=application/json id={id}>{}</script>",
            data.replace('<', "\\u003c")
                .replace('>', "\\u003e")
                .replace('&', "\\u0026")
        )
        .unwrap();
    }
    html.push_str("<script>");
    html.push_str(include_str!("review.js"));
    html.push_str("</script></body></html>");
    if html.len() > 256 * 1_048_576 {
        return Err(error(
            "migration_review_limit",
            "migration HTML exceeds 256 MiB",
        ));
    }
    Ok(html)
}

pub(super) fn render_details(proposal: &CaseMigration, prefix: &str) -> Result<String> {
    let original = proposal.original();
    let mut html = String::new();
    html.push_str("<section class=differences><h2>What changed</h2>");
    if let Some(diagnostic) = &proposal.candidate_diagnostic {
        html.push_str(&code(&json!(diagnostic)));
    } else if proposal.observation_differences.is_empty() {
        html.push_str("<p>The complete recorded observations match. This alone is not approval of the engine transition.</p>");
    } else {
        for difference in &proposal.observation_differences {
            write!(html,"<details><summary>{}</summary><div class=columns><section><h3>Previous engine</h3>{}</section><section><h3>Current engine</h3>{}</section></div></details>",escape(&difference.path),code(&json!(difference.before)),code(&json!(difference.after))).unwrap();
        }
        if proposal.observation_differences_truncated {
            html.push_str("<p class=notice>Only the first 128 differences are listed. Download the proposal for complete original and candidate observations.</p>");
        }
    }
    html.push_str("</section><h2>Recorded behavior</h2><div class=columns>");
    html.push_str(&execution(
        original.observed(),
        original.source(),
        "Previous engine",
        &format!("{prefix}before"),
    )?);
    if let Some(candidate) = proposal.candidate() {
        html.push_str(&execution(
            candidate.observed(),
            candidate.source(),
            "Current engine",
            &format!("{prefix}after"),
        )?);
    } else {
        html.push_str("<section><h3>Current engine</h3><p>No candidate observation is available.</p></section>");
    }
    html.push_str("</div><details class=provenance><summary>Engine identities, inputs, and provenance</summary>");
    html.push_str(&code(&json!({"previousEngine":original.engine(),"targetEngine":proposal.target_engine,"previousExecutableSha256":proposal.previous_executable_sha256,"proposalIntegrity":proposal.integrity(),"originalCaseIntegrity":original.integrity(),"candidateCaseIntegrity":proposal.candidate().map(|case|case.integrity()),"input":original.input(),"limits":original.limits()})));
    html.push_str("</details><details class=provenance><summary>Frozen source</summary>");
    for (name, source) in &original.source().modules {
        write!(
            html,
            "<h3>{}</h3><pre>{}</pre>",
            escape(name),
            escape(source)
        )
        .unwrap();
    }
    html.push_str("</details>");
    Ok(html)
}
