//! Whole-corpus transitions retain every entry and require complete explicit acceptance.
use super::{CaseMigration, error, prepare_migration};
use crate::source::{Diagnostic, Result};
use crate::{
    CaseDecision, Corpus, CorpusEntry, DecisionStatus, EngineIdentity, ExecutionCase,
    MAX_CORPUS_BYTES, MAX_DECISIONS_BYTES, ReplayReport, engine_identity, replay_case,
};
use serde::{Deserialize, Serialize};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, fmt::Write};
const MAX_REPORT_BYTES: usize = 128 * 1_048_576;

fn identity(domain: &[u8], value: &impl Serialize) -> String {
    let mut bytes = Vec::new();
    crate::cases::canonical(&serde_json::to_value(value).expect("JSON"), &mut bytes);
    let mut hash = Sha256::new();
    hash.update(domain);
    hash.update(bytes);
    format!("sha256:{:x}", hash.finalize())
}
/// Identity includes entry order, IDs, labels, and every complete saved case.
pub fn corpus_integrity(corpus: &Corpus) -> String {
    identity(b"gwt-native-corpus-sha256-v1\0", corpus)
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct Row {
    id: String,
    label: String,
    status: &'static str,
    proposal: Option<CaseMigration>,
    retained_case: Option<ExecutionCase>,
    current_replay: Option<ReplayReport>,
    diagnostic: Option<Diagnostic>,
}
impl Row {
    fn candidate(&self) -> Option<&ExecutionCase> {
        if self.status == "current_verified" {
            self.retained_case.as_ref()
        } else {
            self.proposal.as_ref().and_then(CaseMigration::candidate)
        }
    }
}
#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct Totals {
    total: usize,
    ready: usize,
    retained_current: usize,
    observation_preserved: usize,
    observation_changed: usize,
    unavailable: usize,
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CorpusMigration {
    kind: &'static str,
    schema_version: u32,
    engine: EngineIdentity,
    original_corpus_integrity: String,
    complete: bool,
    approved: bool,
    totals: Totals,
    cases: Vec<Row>,
    integrity: String,
}
impl CorpusMigration {
    pub fn integrity(&self) -> &str {
        &self.integrity
    }
    pub fn complete(&self) -> bool {
        self.complete
    }
    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("migration JSON")
    }
}

/// The executor MUST run the explicitly trusted old engine against each supplied case.
/// Response consistency checks do not authenticate that process or its publisher.
/// Current-engine cases are replayed locally and never sent to this executor.
pub fn prepare_corpus_migration(
    corpus: &Corpus,
    mut executor: impl FnMut(&ExecutionCase) -> Result<(String, String)>,
) -> Result<CorpusMigration> {
    let mut report = CorpusMigration {
        kind: "gwt.native-corpus-migration",
        schema_version: 1,
        engine: engine_identity(),
        original_corpus_integrity: corpus_integrity(corpus),
        complete: false,
        approved: false,
        totals: Totals::default(),
        cases: Vec::new(),
        integrity: String::new(),
    };
    let mut bytes = 0;
    for entry in corpus.entries() {
        let mut row = Row {
            id: entry.id.clone(),
            label: entry.label.clone(),
            status: "unavailable",
            proposal: None,
            retained_case: None,
            current_replay: None,
            diagnostic: None,
        };
        let result = (|| -> Result<()> {
            let case = ExecutionCase::from_json(&entry.case.to_string())?;
            if case.engine() == &report.engine {
                let replay = replay_case(&case)?;
                row.status = if replay.verified {
                    "current_verified"
                } else {
                    "baseline_mismatch"
                };
                row.retained_case = Some(case);
                row.current_replay = Some(replay);
            } else {
                let (response, digest) = executor(&case)?;
                let proposal = prepare_migration(&case, &response, &digest)?;
                row.status = proposal.status;
                row.proposal = Some(proposal);
            }
            Ok(())
        })();
        if let Err(diagnostic) = result {
            row.diagnostic = Some(diagnostic);
        }
        report.totals.total += 1;
        if row.candidate().is_some() {
            report.totals.ready += 1;
        }
        match row.status {
            "current_verified" => report.totals.retained_current += 1,
            "observation_preserved" => report.totals.observation_preserved += 1,
            "observation_changed" => report.totals.observation_changed += 1,
            _ => report.totals.unavailable += 1,
        }
        bytes += crate::review::size(&row, MAX_REPORT_BYTES)?;
        if bytes > MAX_REPORT_BYTES {
            return Err(error("migration_limit", "corpus migration exceeds 128 MiB"));
        }
        report.cases.push(row);
    }
    report.complete = report.totals.ready == report.totals.total;
    crate::review::size(&report, MAX_REPORT_BYTES)?;
    let mut value = json!(report);
    value.as_object_mut().unwrap().remove("integrity");
    report.integrity = identity(b"gwt-native-corpus-migration-sha256-v1\0", &value);
    crate::review::size(&report, MAX_REPORT_BYTES)?;
    Ok(report)
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct DecisionsFile {
    kind: String,
    schema_version: u32,
    report_integrity: String,
    reviewer: String,
    decisions: Vec<CaseDecision>,
}
#[derive(Debug, Serialize)]
#[serde(transparent)]
pub struct CorpusMigrationDecisions(DecisionsFile);
impl CorpusMigrationDecisions {
    pub fn pending(report: &CorpusMigration) -> Self {
        Self(DecisionsFile {
            kind: "gwt.native-corpus-migration-decisions".into(),
            schema_version: 1,
            report_integrity: report.integrity.clone(),
            reviewer: String::new(),
            decisions: report
                .cases
                .iter()
                .map(|row| CaseDecision {
                    id: row.id.clone(),
                    status: DecisionStatus::Pending,
                    note: String::new(),
                })
                .collect(),
        })
    }
    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("decision JSON")
    }
    pub fn from_json(source: &str) -> Result<Self> {
        if source.len() > MAX_DECISIONS_BYTES {
            return Err(error(
                "migration_decisions_limit",
                "decisions exceed two MiB",
            ));
        }
        let result = Self(
            serde_json::from_str(source)
                .map_err(|e| error("migration_decisions_format", e.to_string()))?,
        );
        result.validate()?;
        Ok(result)
    }
    fn validate(&self) -> Result<()> {
        let file = &self.0;
        if file.kind != "gwt.native-corpus-migration-decisions"
            || file.schema_version != 1
            || !crate::cases::is_sha256(&file.report_integrity)
        {
            return Err(error(
                "migration_decisions_format",
                "expected corpus migration decisions schema 1 and report SHA-256",
            ));
        }
        if file.reviewer.len() > 256
            || file.reviewer.chars().any(char::is_control)
            || file.decisions.is_empty()
            || file.decisions.len() > 256
        {
            return Err(error(
                "migration_decisions_limit",
                "reviewer permits 256 UTF-8 bytes without controls; decisions require 1..256 entries",
            ));
        }
        let mut ids = BTreeSet::new();
        for choice in &file.decisions {
            if choice.id.is_empty()
                || choice.id.len() > 128
                || choice.note.len() > 4096
                || !ids.insert(&choice.id)
            {
                return Err(error(
                    "migration_decisions_format",
                    "unique IDs require 1..128 bytes; notes permit 4096 bytes",
                ));
            }
            if choice.status != DecisionStatus::Pending
                && (file.reviewer.trim().is_empty() || choice.note.trim().is_empty())
            {
                return Err(error(
                    "migration_decisions_required",
                    "non-pending choices require a reviewer and a note",
                ));
            }
        }
        Ok(())
    }
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CorpusMigrationAssessment {
    kind: &'static str,
    schema_version: u32,
    report_integrity: String,
    decision_integrity: String,
    original_corpus_integrity: String,
    reviewer: String,
    total: usize,
    accepted: usize,
    pending: usize,
    rejected: usize,
    needs_information: usize,
    pub all_accepted: bool,
}
pub fn assess_corpus_migration(
    report: &CorpusMigration,
    decisions: &CorpusMigrationDecisions,
) -> Result<CorpusMigrationAssessment> {
    decisions.validate()?;
    if decisions.0.report_integrity != report.integrity {
        return Err(error(
            "migration_decisions_stale",
            "decisions belong to a different corpus transition; review the new report",
        ));
    }
    let expected: BTreeSet<_> = report.cases.iter().map(|row| &row.id).collect();
    let actual: BTreeSet<_> = decisions.0.decisions.iter().map(|row| &row.id).collect();
    if actual != expected {
        return Err(error(
            "migration_decisions_coverage",
            "decisions must cover every corpus entry exactly once",
        ));
    }
    let mut assessment = CorpusMigrationAssessment {
        kind: "gwt.native-corpus-migration-assessment",
        schema_version: 1,
        report_integrity: report.integrity.clone(),
        decision_integrity: identity(
            b"gwt-native-corpus-migration-decisions-sha256-v1\0",
            decisions,
        ),
        original_corpus_integrity: report.original_corpus_integrity.clone(),
        reviewer: decisions.0.reviewer.clone(),
        total: report.cases.len(),
        accepted: 0,
        pending: 0,
        rejected: 0,
        needs_information: 0,
        all_accepted: false,
    };
    for choice in &decisions.0.decisions {
        match choice.status {
            DecisionStatus::Pending => assessment.pending += 1,
            DecisionStatus::Reject => assessment.rejected += 1,
            DecisionStatus::NeedsInformation => assessment.needs_information += 1,
            DecisionStatus::Accept => {
                if report
                    .cases
                    .iter()
                    .find(|row| row.id == choice.id)
                    .unwrap()
                    .candidate()
                    .is_none()
                {
                    return Err(error(
                        "migration_decisions_unavailable",
                        format!(
                            "case '{}' cannot be accepted without verified candidate evidence",
                            choice.id
                        ),
                    ));
                }
                assessment.accepted += 1;
            }
        }
    }
    assessment.all_accepted = report.complete && assessment.accepted == assessment.total;
    Ok(assessment)
}
/// Produce a separate complete corpus only after all entries are explicitly accepted.
pub fn promote_corpus_migration(
    report: &CorpusMigration,
    decisions: &CorpusMigrationDecisions,
) -> Result<(Corpus, CorpusMigrationAssessment)> {
    let assessment = assess_corpus_migration(report, decisions)?;
    if !assessment.all_accepted {
        return Err(error(
            "migration_not_accepted",
            "every corpus entry requires acceptance before export",
        ));
    }
    let corpus = Corpus::new(
        report
            .cases
            .iter()
            .map(|row| CorpusEntry {
                id: row.id.clone(),
                label: row.label.clone(),
                case: json!(row.candidate().expect("accepted candidate")),
            })
            .collect(),
    )?;
    crate::review::size(&corpus, MAX_CORPUS_BYTES)?;
    Ok((corpus, assessment))
}

pub fn render_corpus_migration_html(report: &CorpusMigration) -> Result<String> {
    use super::review::{code, escape, execution, render_details};
    let mut html = String::from(
        "<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content=\"width=device-width,initial-scale=1\"><meta http-equiv=Content-Security-Policy content=\"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'\"><title>GWT corpus migration review</title><style>",
    );
    html.push_str(include_str!("review.css"));
    html.push_str(".case{margin-top:24px;padding:20px;background:white;border:1px solid var(--line);border-radius:10px}.case h2{overflow-wrap:anywhere}.case label{display:block}.filters{display:flex;flex-wrap:wrap;gap:16px}.filters input{font:inherit;padding:8px}.case[hidden]{display:none}</style><body><header><p class=eyebrow>GWT · Corpus migration</p><h1>Review the complete engine transition</h1><p>Every case keeps its ID, label, order, source, input, target, and limits. Export requires an explicit acceptance for every verified entry.</p></header><main>");
    write!(html,"<section class=metrics><div><strong>{}</strong><span>Total cases</span></div><div><strong>{}</strong><span>Ready for review</span></div><div><strong>{}</strong><span>Unavailable</span></div></section>",report.totals.total,report.totals.ready,report.totals.unavailable).unwrap();
    html.push_str("<section class=decision><h2>Saved decisions</h2><label>Reviewer<input data-reviewer autocomplete=off></label><p class=caption>The name is self-reported. Non-pending choices require a note. Choices are bound to this complete report, including corpus membership and metadata.</p><div class=actions><button data-save>Download decisions</button><label class=file-label>Load decisions<input type=file data-load accept=\"application/json,.json\"></label><button data-download>Download report</button></div><p data-message role=status></p><p data-counts aria-live=polite></p></section><section class=filters><label>Find a case<input data-search type=search></label><label>Show<select data-filter><option value=all>All cases</option><option value=changed>Changed observations</option><option value=unavailable>Unavailable</option><option value=pending>Pending decisions</option></select></label></section><p data-empty hidden>No cases match.</p>");
    for (index, row) in report.cases.iter().enumerate() {
        let ready = row.candidate().is_some();
        write!(html,"<section class=case data-index={index} data-ready={ready} data-changed={}><h2>{}</h2><p>{}</p><p class=badge>{}</p><label>Decision<select data-status><option value=pending>Pending</option><option value=accept {}>Accept</option><option value=reject>Reject</option><option value=needs_information>Needs information</option></select></label><label>Review note<textarea data-note rows=3></textarea></label><details data-evidence><summary>Inspect recorded behavior</summary>",row.status=="observation_changed",escape(&row.id),escape(&row.label),match row.status {"current_verified"=>"Current engine · replay verified", "observation_preserved"=>"Previous engine · observation preserved", "observation_changed"=>"Previous engine · observation changed", "candidate_unavailable"=>"Current candidate unavailable", "baseline_mismatch"=>"Current baseline did not replay", _=>"Verification unavailable"},if ready {""}else{"disabled"}).unwrap();
        let prefix = format!("case-{index}-");
        if let Some(proposal) = &row.proposal {
            if let Some(changes) = &proposal.changes {
                write!(
                    html,
                    "<p class=notice>Outcome: {} · State: {} · Evidence: {}</p>",
                    if changes.outcome { "changed" } else { "same" },
                    if changes.state { "changed" } else { "same" },
                    if changes.evidence { "changed" } else { "same" }
                )
                .unwrap();
            }
            html.push_str(&render_details(proposal, &prefix)?);
        } else if row.status == "current_verified" {
            let case = row.retained_case.as_ref().unwrap();
            html.push_str(&execution(
                case.observed(),
                case.source(),
                "Retained current-engine observation",
                &format!("{prefix}current"),
            )?);
            html.push_str(&code(&json!({"engine":case.engine(),"caseIntegrity":case.integrity(),"request":case.request(),"scenario":case.scenario(),"input":case.input(),"limits":case.limits(),"source":case.source()})));
        } else {
            html.push_str(&code(
                &json!({"diagnostic":row.diagnostic,"replay":row.current_replay}),
            ));
        }
        html.push_str("</details></section>");
        if html.len() > 256 * 1_048_576 {
            return Err(error(
                "migration_review_limit",
                "corpus migration HTML exceeds 256 MiB",
            ));
        }
    }
    html.push_str("<noscript><p>All recorded cases are readable without JavaScript. Decision save/load and filters require JavaScript.</p></noscript></main>");
    for (id, data) in [
        ("report-data", report.to_json()),
        (
            "decision-data",
            CorpusMigrationDecisions::pending(report).to_json(),
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
    html.push_str(include_str!("corpus.js"));
    html.push_str("</script></body></html>");
    if html.len() > 256 * 1_048_576 {
        return Err(error(
            "migration_review_limit",
            "corpus migration HTML exceeds 256 MiB",
        ));
    }
    Ok(html)
}
