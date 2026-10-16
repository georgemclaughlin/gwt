use crate::source::{Diagnostic, Result, Span};
use crate::{
    CaseComparison, CompiledProgram, EngineIdentity, ExecutionCase, ExecutionExplanation,
    ProgramIdentity, ProgramLimits, SourceBundle, compare_case, corpus_integrity, engine_identity,
    explain_execution,
};
use serde::{Deserialize, Serialize};
use serde_json::Value as Json;
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Write,
};

pub const MAX_CORPUS_BYTES: usize = 64 * 1_048_576;
const MAX_REPORT_BYTES: usize = 128 * 1_048_576;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CorpusEntry {
    pub id: String,
    #[serde(default)]
    pub label: String,
    pub case: Json,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct CorpusFile {
    kind: String,
    schema_version: u32,
    cases: Vec<CorpusEntry>,
}

#[derive(Debug, Serialize)]
#[serde(transparent)]
pub struct Corpus(CorpusFile);

fn error(code: &str, message: impl Into<String>) -> Diagnostic {
    Diagnostic::new(
        code,
        message,
        &Span {
            file: "<corpus>".into(),
            start: 0,
            end: 0,
            line: 1,
            column: 1,
        },
    )
}

struct Counter {
    bytes: usize,
    maximum: usize,
}
impl Write for Counter {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        if bytes.len() > self.maximum.saturating_sub(self.bytes) {
            return Err(std::io::Error::other("serialized size limit exceeded"));
        }
        self.bytes += bytes.len();
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
pub(crate) fn size(value: &impl Serialize, maximum: usize) -> Result<usize> {
    let mut counter = Counter { bytes: 0, maximum };
    serde_json::to_writer(&mut counter, value).map_err(|_| {
        error(
            "review_limit",
            "serialized corpus or review exceeds its byte limit",
        )
    })?;
    Ok(counter.bytes)
}

impl Corpus {
    pub fn entries(&self) -> &[CorpusEntry] {
        &self.0.cases
    }
    pub fn new(cases: Vec<CorpusEntry>) -> Result<Self> {
        let result = Self(CorpusFile {
            kind: "gwt.native-corpus".into(),
            schema_version: 1,
            cases,
        });
        result.validate()?;
        Ok(result)
    }
    pub fn from_json(source: &str) -> Result<Self> {
        if source.len() > MAX_CORPUS_BYTES {
            return Err(error("corpus_limit", "corpus exceeds 64 MiB"));
        }
        let result = Self(
            serde_json::from_str(source)
                .map_err(|failure| error("corpus_format", failure.to_string()))?,
        );
        result.validate()?;
        Ok(result)
    }
    fn validate(&self) -> Result<()> {
        if self.0.kind != "gwt.native-corpus" || self.0.schema_version != 1 {
            return Err(error(
                "corpus_version",
                "expected native-corpus schema version 1",
            ));
        }
        if self.0.cases.is_empty() || self.0.cases.len() > 256 {
            return Err(error(
                "corpus_limit",
                "a corpus must contain 1 to 256 cases",
            ));
        }
        let mut ids = BTreeSet::new();
        for entry in &self.0.cases {
            crate::cases::check_shape(&entry.case)?;
            if entry.id.is_empty() || entry.id.len() > 128 || entry.label.len() > 512 {
                return Err(error(
                    "corpus_format",
                    "case IDs require 1..128 bytes; labels allow at most 512 bytes",
                ));
            }
            if !ids.insert(&entry.id) {
                return Err(error(
                    "corpus_duplicate",
                    format!("duplicate case ID '{}'", entry.id),
                ));
            }
        }
        size(self, MAX_CORPUS_BYTES)?;
        Ok(())
    }
    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("corpus JSON")
    }
}

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReviewTotals {
    pub total: usize,
    pub compared: usize,
    pub baseline_mismatch: usize,
    pub unavailable: usize,
    pub candidate_failed: usize,
    pub outcome_changed: usize,
    pub state_changed: usize,
    pub evidence_changed: usize,
    pub source_changed: usize,
    pub unchanged: usize,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReviewRow {
    pub id: String,
    pub label: String,
    pub status: String,
    /// Present after case shape/integrity validation; replay may still be unavailable.
    pub case_integrity: Option<String>,
    pub captured_limits: Option<ProgramLimits>,
    pub request: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scenario: Option<String>,
    pub input: Option<Json>,
    pub baseline_source: Option<String>,
    pub diagnostic: Option<Diagnostic>,
    pub comparison: Option<CaseComparison>,
    pub baseline_explanation: Option<ExecutionExplanation>,
    pub candidate_explanation: Option<ExecutionExplanation>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CorpusReview {
    pub kind: &'static str,
    pub schema_version: u32,
    pub engine: EngineIdentity,
    /// Binds the complete input corpus, including budgets, provenance, and invalid entries.
    pub corpus_integrity: String,
    /// Every manifest entry was compared. This is coverage, not approval.
    pub complete: bool,
    pub candidate_identity: ProgramIdentity,
    pub totals: ReviewTotals,
    pub sources: BTreeMap<String, SourceBundle>,
    pub cases: Vec<ReviewRow>,
}

pub fn review_corpus(corpus: &Corpus, candidate: &CompiledProgram) -> Result<CorpusReview> {
    let Some(candidate_source) = candidate.source_bundle() else {
        return Err(error(
            "case_source",
            "review candidate requires a frozen source bundle",
        ));
    };
    let candidate_identity = candidate.identity().expect("bundle identity").clone();
    let mut report = CorpusReview {
        kind: "gwt.native-review",
        schema_version: 2,
        engine: engine_identity(),
        corpus_integrity: corpus_integrity(corpus),
        complete: false,
        candidate_identity: candidate_identity.clone(),
        totals: ReviewTotals::default(),
        sources: BTreeMap::from([(candidate_identity.digest.clone(), candidate_source.clone())]),
        cases: Vec::new(),
    };
    let mut bytes = 0;
    for entry in &corpus.0.cases {
        let mut row = ReviewRow {
            id: entry.id.clone(),
            label: entry.label.clone(),
            status: "unavailable".into(),
            case_integrity: None,
            captured_limits: None,
            request: None,
            scenario: None,
            input: None,
            baseline_source: None,
            diagnostic: None,
            comparison: None,
            baseline_explanation: None,
            candidate_explanation: None,
        };
        let process = (|| -> Result<()> {
            let case = ExecutionCase::from_json(&entry.case.to_string())?;
            row.case_integrity = Some(case.integrity().into());
            row.captured_limits = Some(case.limits());
            row.request = case.request().map(str::to_owned);
            row.scenario = case.scenario().map(str::to_owned);
            row.input = case.request().map(|_| case.input().clone());
            let comparison = compare_case(&case, candidate)?;
            // Replay validated source identity even when the observation mismatches.
            // Keep those sources available for investigating the mismatch.
            let identity = case.program_identity().digest.clone();
            row.baseline_source = Some(identity.clone());
            report
                .sources
                .entry(identity)
                .or_insert_with(|| case.source().clone());
            if !comparison.baseline.verified {
                row.status = "baseline_mismatch".into();
                row.comparison = Some(comparison);
                return Ok(());
            }
            // Only verified baseline evidence is presented as its explanation.
            let baseline = explain_execution(&comparison.baseline.actual, case.source())?;
            let result = comparison.candidate.as_ref().expect("verified comparison");
            let after = explain_execution(result, candidate_source)?;
            let changes = comparison.changes.as_ref().expect("verified comparison");
            row.status = if !result.ok {
                "candidate_failed"
            } else if changes.outcome {
                "outcome_changed"
            } else if changes.state {
                "state_changed"
            } else if changes.evidence {
                "evidence_changed"
            } else if changes.source {
                "source_changed"
            } else {
                "unchanged"
            }
            .into();
            row.baseline_explanation = Some(baseline);
            row.candidate_explanation = Some(after);
            row.comparison = Some(comparison);
            Ok(())
        })();
        if let Err(diagnostic) = process {
            row.diagnostic = Some(diagnostic);
        }
        report.totals.total += 1;
        match row.status.as_str() {
            "unavailable" => report.totals.unavailable += 1,
            "baseline_mismatch" => report.totals.baseline_mismatch += 1,
            _ => {
                report.totals.compared += 1;
                let comparison = row.comparison.as_ref().unwrap();
                let changes = comparison.changes.as_ref().unwrap();
                report.totals.candidate_failed +=
                    usize::from(!comparison.candidate.as_ref().unwrap().ok);
                report.totals.outcome_changed += usize::from(changes.outcome);
                report.totals.state_changed += usize::from(changes.state);
                report.totals.evidence_changed += usize::from(changes.evidence);
                report.totals.source_changed += usize::from(changes.source);
                report.totals.unchanged += usize::from(
                    !changes.source && !changes.outcome && !changes.state && !changes.evidence,
                );
            }
        }
        bytes += size(&row, MAX_REPORT_BYTES.saturating_sub(bytes))?;
        report.cases.push(row);
    }
    report.complete = report.totals.compared == report.totals.total;
    size(&report, MAX_REPORT_BYTES)?;
    Ok(report)
}

mod html;
pub use html::render_review_html;

mod regressions;
pub use regressions::{
    CorpusRegression, RegressionRow, RegressionScope, RegressionStatus, RegressionTotals,
    test_corpus,
};

mod decisions;
pub use decisions::{
    CaseDecision, DecisionAssessment, DecisionStatus, MAX_DECISIONS_BYTES, ReviewDecisions,
    ReviewIdentity, assess_decisions, review_identity,
};
