//! Saved reviewer choices bind to an exact freshly reproducible review.
use super::{CorpusReview, MAX_REPORT_BYTES, error, size};
use crate::source::Result;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

pub const MAX_DECISIONS_BYTES: usize = 2 * 1_048_576;
const ALGORITHM: &str = "gwt-native-review-sha256-v1";

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReviewIdentity {
    pub algorithm: String,
    pub digest: String,
}

pub fn review_identity(report: &CorpusReview) -> Result<ReviewIdentity> {
    size(report, MAX_REPORT_BYTES)?;
    let value = serde_json::to_value(report).expect("review JSON");
    let mut bytes = Vec::new();
    crate::cases::canonical(&value, &mut bytes);
    let mut hash = Sha256::new();
    hash.update(ALGORITHM.as_bytes());
    hash.update([0]);
    hash.update(bytes);
    Ok(ReviewIdentity {
        algorithm: ALGORITHM.into(),
        digest: format!("sha256:{:x}", hash.finalize()),
    })
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DecisionStatus {
    Pending,
    Accept,
    Reject,
    NeedsInformation,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CaseDecision {
    pub id: String,
    pub status: DecisionStatus,
    pub note: String,
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct DecisionsFile {
    kind: String,
    schema_version: u32,
    report_identity: ReviewIdentity,
    reviewer: String,
    decisions: Vec<CaseDecision>,
}

#[derive(Debug, Serialize)]
#[serde(transparent)]
pub struct ReviewDecisions(DecisionsFile);

impl ReviewDecisions {
    pub fn pending(report: &CorpusReview) -> Result<Self> {
        let result = Self(DecisionsFile {
            kind: "gwt.native-review-decisions".into(),
            schema_version: 1,
            report_identity: review_identity(report)?,
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
        });
        result.validate()?;
        Ok(result)
    }
    pub fn from_json(source: &str) -> Result<Self> {
        if source.len() > MAX_DECISIONS_BYTES {
            return Err(error("decisions_limit", "review decisions exceed two MiB"));
        }
        let result = Self(
            serde_json::from_str(source)
                .map_err(|failure| error("decisions_format", failure.to_string()))?,
        );
        result.validate()?;
        Ok(result)
    }
    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("decision JSON")
    }
    fn validate(&self) -> Result<()> {
        let file = &self.0;
        if file.kind != "gwt.native-review-decisions" || file.schema_version != 1 {
            return Err(error(
                "decisions_version",
                "expected native-review-decisions schema version 1",
            ));
        }
        if file.report_identity.algorithm != ALGORITHM
            || file.report_identity.digest.len() != 71
            || !file.report_identity.digest.starts_with("sha256:")
            || !file.report_identity.digest[7..]
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return Err(error(
                "decisions_identity",
                "invalid native review identity",
            ));
        }
        if file.reviewer.len() > 256 || file.reviewer.chars().any(char::is_control) {
            return Err(error(
                "decisions_reviewer",
                "reviewer permits at most 256 UTF-8 bytes and no control characters",
            ));
        }
        if file.decisions.is_empty() || file.decisions.len() > 256 {
            return Err(error(
                "decisions_limit",
                "decisions must include 1 to 256 cases",
            ));
        }
        let mut ids = BTreeSet::new();
        for decision in &file.decisions {
            if decision.id.is_empty() || decision.id.len() > 128 || decision.note.len() > 4096 {
                return Err(error(
                    "decisions_limit",
                    "case IDs permit 1..128 bytes and notes at most 4096 bytes",
                ));
            }
            if !ids.insert(&decision.id) {
                return Err(error(
                    "decisions_duplicate",
                    "case decision IDs must be unique",
                ));
            }
            if decision.status != DecisionStatus::Pending && file.reviewer.trim().is_empty() {
                return Err(error(
                    "decisions_reviewer",
                    "record a reviewer before making a decision",
                ));
            }
            if matches!(
                decision.status,
                DecisionStatus::Reject | DecisionStatus::NeedsInformation
            ) && decision.note.trim().is_empty()
            {
                return Err(error(
                    "decisions_note",
                    "rejection or a request for information requires a note",
                ));
            }
        }
        size(self, MAX_DECISIONS_BYTES)?;
        Ok(())
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DecisionAssessment {
    pub kind: &'static str,
    pub schema_version: u32,
    pub report_identity: ReviewIdentity,
    pub reviewer: String,
    pub total: usize,
    pub pending: usize,
    pub accepted: usize,
    pub rejected: usize,
    pub needs_information: usize,
    /// All cases were compared and explicitly accepted in the supplied file.
    /// This does not authenticate a reviewer or establish domain correctness.
    pub all_accepted: bool,
}

pub fn assess_decisions(
    report: &CorpusReview,
    decisions: &ReviewDecisions,
) -> Result<DecisionAssessment> {
    decisions.validate()?;
    let identity = review_identity(report)?;
    if identity != decisions.0.report_identity {
        return Err(error(
            "decisions_stale",
            "decisions belong to a different review; regenerate the report and review the changes",
        ));
    }
    let expected: BTreeSet<_> = report.cases.iter().map(|row| &row.id).collect();
    let actual: BTreeSet<_> = decisions
        .0
        .decisions
        .iter()
        .map(|decision| &decision.id)
        .collect();
    if expected.len() != report.cases.len() || actual != expected {
        return Err(error(
            "decisions_coverage",
            "decisions must contain every report case exactly once",
        ));
    }
    let mut assessment = DecisionAssessment {
        kind: "gwt.native-review-assessment",
        schema_version: 1,
        report_identity: identity,
        reviewer: decisions.0.reviewer.clone(),
        total: report.cases.len(),
        pending: 0,
        accepted: 0,
        rejected: 0,
        needs_information: 0,
        all_accepted: false,
    };
    for decision in &decisions.0.decisions {
        match decision.status {
            DecisionStatus::Pending => assessment.pending += 1,
            DecisionStatus::Reject => assessment.rejected += 1,
            DecisionStatus::NeedsInformation => assessment.needs_information += 1,
            DecisionStatus::Accept => {
                let row = report
                    .cases
                    .iter()
                    .find(|row| row.id == decision.id)
                    .expect("matched ID");
                if matches!(row.status.as_str(), "unavailable" | "baseline_mismatch")
                    || !row.comparison.as_ref().is_some_and(|comparison| {
                        comparison.baseline.verified && comparison.candidate.is_some()
                    })
                    || row.baseline_explanation.is_none()
                    || row.candidate_explanation.is_none()
                {
                    return Err(error(
                        "decisions_unverified",
                        format!(
                            "case '{}' has unverified comparison evidence and cannot be accepted",
                            row.id
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
