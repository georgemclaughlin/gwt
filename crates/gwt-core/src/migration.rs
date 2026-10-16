//! Explicit engine transitions, with old-engine replay supplied by a trusted executor.
use crate::cases::{canonical, check_shape, differences, is_sha256, outcome};
use crate::source::{Diagnostic, Result, Span};
use crate::{Changes, Difference, EngineIdentity, ExecutionCase, engine_identity};
use serde::Serialize;
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
mod corpus;
mod review;
pub use corpus::{
    CorpusMigration, CorpusMigrationAssessment, CorpusMigrationDecisions, assess_corpus_migration,
    corpus_integrity, prepare_corpus_migration, promote_corpus_migration,
    render_corpus_migration_html,
};
pub use review::{
    MAX_MIGRATION_DECISION_BYTES, MigrationAssessment, MigrationDecision, assess_migration,
    render_migration_html,
};

pub const MAX_BASELINE_REPLAY_BYTES: usize = 32 * 1_048_576;
pub const MAX_MIGRATION_BYTES: usize = 64 * 1_048_576;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CaseMigration {
    kind: &'static str,
    schema_version: u32,
    status: &'static str,
    approved: bool,
    baseline_verification: &'static str,
    previous_executable_sha256: String,
    target_engine: EngineIdentity,
    original: ExecutionCase,
    baseline_replay: Json,
    candidate: Option<ExecutionCase>,
    candidate_diagnostic: Option<Diagnostic>,
    changes: Option<Changes>,
    observation_differences: Vec<Difference>,
    observation_differences_truncated: bool,
    outcome_differences: Vec<Difference>,
    outcome_differences_truncated: bool,
    integrity: String,
}
impl CaseMigration {
    pub fn candidate(&self) -> Option<&ExecutionCase> {
        self.candidate.as_ref()
    }
    pub fn original(&self) -> &ExecutionCase {
        &self.original
    }
    pub fn integrity(&self) -> &str {
        &self.integrity
    }
}

fn error(code: &str, message: impl Into<String>) -> Diagnostic {
    Diagnostic::new(
        code,
        message,
        &Span {
            file: "<engine-migration>".into(),
            start: 0,
            end: 0,
            line: 1,
            column: 1,
        },
    )
}

/// Build a proposal, never approval or an overwrite of the original case.
///
/// The caller MUST obtain `baseline_response` by executing the trusted original
/// engine's `replay` command successfully on this exact case. This function checks
/// response consistency, not the authenticity of a supplied transcript or digest.
/// The native CLI performs that process execution; the library performs no I/O.
pub fn prepare_migration(
    case: &ExecutionCase,
    baseline_response: &str,
    executable_sha256: &str,
) -> Result<CaseMigration> {
    if case.engine() == &engine_identity() {
        return Err(error(
            "migration_same_engine",
            "this case already belongs to the current engine; use replay",
        ));
    }
    if case.engine().profile != engine_identity().profile
        || !is_sha256(&case.engine().source_digest)
    {
        return Err(error(
            "migration_engine_profile",
            "only the native case engine v1 profile is supported",
        ));
    }
    if !is_sha256(executable_sha256) {
        return Err(error(
            "migration_executable",
            "previous executable requires its SHA-256 digest",
        ));
    }
    if baseline_response.len() > MAX_BASELINE_REPLAY_BYTES {
        return Err(error("migration_limit", "baseline replay exceeds 32 MiB"));
    }
    let baseline: Json = serde_json::from_str(baseline_response).map_err(|_| {
        error(
            "migration_baseline",
            "previous engine did not return a valid replay report",
        )
    })?;
    check_shape(&baseline)?;
    let expected = json!({"kind":"gwt.native-replay","schemaVersion":1,"verified":true,"differences":[],"differencesTruncated":false,"actual":case.observed()});
    if baseline != expected {
        return Err(error(
            "migration_baseline",
            "previous engine must reproduce the complete original observation with no differences",
        ));
    }
    let recaptured = case.recapture_for_migration(executable_sha256);
    let mut proposal = CaseMigration {
        kind: "gwt.native-case-migration",
        schema_version: 1,
        status: "candidate_unavailable",
        approved: false,
        baseline_verification: "trusted_previous_engine_replay",
        previous_executable_sha256: executable_sha256.into(),
        target_engine: engine_identity(),
        original: case.clone(),
        baseline_replay: baseline,
        candidate: None,
        candidate_diagnostic: None,
        changes: None,
        observation_differences: Vec::new(),
        observation_differences_truncated: false,
        outcome_differences: Vec::new(),
        outcome_differences_truncated: false,
        integrity: String::new(),
    };
    match recaptured {
        Ok(candidate) => {
            let before = case.observed();
            let after = candidate.observed();
            let old_outcome = outcome(before);
            let new_outcome = outcome(after);
            proposal.changes = Some(Changes {
                source: false,
                outcome: old_outcome != new_outcome,
                state: before["state"] != after["state"],
                evidence: before["events"] != after["events"]
                    || before["diagnostic"] != after["diagnostic"]
                    || before["steps"] != after["steps"],
            });
            (
                proposal.observation_differences,
                proposal.observation_differences_truncated,
            ) = differences(before, after);
            (
                proposal.outcome_differences,
                proposal.outcome_differences_truncated,
            ) = differences(&old_outcome, &new_outcome);
            proposal.status = if before == after {
                "observation_preserved"
            } else {
                "observation_changed"
            };
            proposal.candidate = Some(candidate);
        }
        Err(error) => proposal.candidate_diagnostic = Some(error),
    }
    let mut value = json!(proposal);
    value
        .as_object_mut()
        .expect("proposal object")
        .remove("integrity");
    let mut bytes = Vec::new();
    canonical(&value, &mut bytes);
    if bytes.len() > MAX_MIGRATION_BYTES - 128 {
        return Err(error(
            "migration_limit",
            "migration proposal exceeds 64 MiB",
        ));
    }
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-case-migration-sha256-v1\0");
    hash.update(bytes);
    proposal.integrity = format!("sha256:{:x}", hash.finalize());
    Ok(proposal)
}
