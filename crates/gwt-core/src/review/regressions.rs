//! A preservation gate for verified observations, never a policy approval.
use super::{Corpus, CorpusReview, MAX_REPORT_BYTES, review_corpus, size};
use crate::{CompiledProgram, ProgramLimits, source::Result};
use serde::Serialize;

#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum RegressionScope {
    /// Success/failure, returned values, prints, diagnostic code/message, and full state.
    OutcomesAndState,
    /// Also requires identical steps, events, and diagnostic source positions.
    Execution,
}

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RegressionTotals {
    pub total: usize,
    pub passed: usize,
    pub changed: usize,
    pub baseline_mismatch: usize,
    pub unavailable: usize,
}

#[derive(Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RegressionStatus {
    Passed,
    Changed,
    BaselineMismatch,
    Unavailable,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RegressionRow {
    pub id: String,
    pub status: RegressionStatus,
    pub case_integrity: Option<String>,
    pub captured_limits: Option<ProgramLimits>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CorpusRegression {
    pub kind: &'static str,
    pub schema_version: u32,
    pub expectation_basis: &'static str,
    pub scope: RegressionScope,
    /// Every baseline replayed and every candidate matched the selected scope.
    pub passed: bool,
    pub totals: RegressionTotals,
    pub cases: Vec<RegressionRow>,
    /// Complete comparisons, including differences outside the selected scope.
    pub review: CorpusReview,
}

/// Compare each candidate entry under its captured input, target, and limits.
/// Unavailable or mismatched baselines always fail the gate. A matching failed
/// execution can pass; it remains a failed execution in the embedded review.
pub fn test_corpus(
    corpus: &Corpus,
    candidate: &CompiledProgram,
    scope: RegressionScope,
) -> Result<CorpusRegression> {
    let review = review_corpus(corpus, candidate)?;
    let mut totals = RegressionTotals::default();
    let cases = review
        .cases
        .iter()
        .map(|row| {
            totals.total += 1;
            let status = match row.status.as_str() {
                "unavailable" => {
                    totals.unavailable += 1;
                    RegressionStatus::Unavailable
                }
                "baseline_mismatch" => {
                    totals.baseline_mismatch += 1;
                    RegressionStatus::BaselineMismatch
                }
                _ => {
                    let changes = row
                        .comparison
                        .as_ref()
                        .and_then(|comparison| comparison.changes.as_ref())
                        .expect("compared review row has changes");
                    let changed = changes.outcome
                        || changes.state
                        || (matches!(scope, RegressionScope::Execution) && changes.evidence);
                    if changed {
                        totals.changed += 1;
                        RegressionStatus::Changed
                    } else {
                        totals.passed += 1;
                        RegressionStatus::Passed
                    }
                }
            };
            // Only attach metadata from cases that reached replay. Unavailable
            // entries retain their diagnostic and original corpus ID instead.
            RegressionRow {
                id: row.id.clone(),
                status,
                case_integrity: row.comparison.as_ref().and(row.case_integrity.clone()),
                captured_limits: row.comparison.as_ref().and(row.captured_limits),
            }
        })
        .collect();
    let report = CorpusRegression {
        kind: "gwt.native-regression",
        schema_version: 1,
        expectation_basis: "verified_observation_not_approval",
        scope,
        passed: review.complete && totals.passed == totals.total,
        totals,
        cases,
        review,
    };
    size(&report, MAX_REPORT_BYTES)?;
    Ok(report)
}
