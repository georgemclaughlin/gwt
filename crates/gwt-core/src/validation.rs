//! Validation gates over one frozen import closure. No source is rewritten.
use crate::source::Diagnostic;
use crate::validation_evidence::{EvidenceCollector, expectations};
use crate::{ExpectationObservation, ValidationEvidence, ValidationWarning};
use crate::{
    ProgramIdentity, ProgramLimits, SourceBundle, compile_bundle, format_source, load_bundle,
};
use serde::Serialize;
use std::path::Path;

#[derive(Clone, Copy, Debug, Default)]
pub struct ValidationOptions {
    pub allow_no_scenarios: bool,
    pub limits: ProgramLimits,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum ValidationStatus {
    Passed,
    Failed,
    Skipped,
    NotExercised,
}

#[derive(Debug, Serialize)]
pub struct ValidationPhase {
    pub status: ValidationStatus,
    pub reason: Option<String>,
    pub diagnostic: Option<Diagnostic>,
}

impl ValidationPhase {
    fn passed() -> Self {
        Self {
            status: ValidationStatus::Passed,
            reason: None,
            diagnostic: None,
        }
    }
    fn skipped(reason: &str) -> Self {
        Self {
            status: ValidationStatus::Skipped,
            reason: Some(reason.into()),
            diagnostic: None,
        }
    }
    fn failed(error: Diagnostic) -> Self {
        Self {
            status: ValidationStatus::Failed,
            reason: None,
            diagnostic: Some(error),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct ModuleFormatCheck {
    pub file: String,
    pub changed: Option<bool>,
    pub diagnostic: Option<Diagnostic>,
}

/// Compact results release each execution's state/output/evidence before the next
/// scenario. Use run/test for full execution evidence, not this gate summary.
#[derive(Debug, Serialize)]
pub struct ScenarioValidation {
    pub name: String,
    pub ok: bool,
    pub steps: usize,
    pub diagnostic: Option<Diagnostic>,
    pub expectations: Vec<ExpectationObservation>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ValidationReport {
    pub kind: &'static str,
    pub schema_version: u32,
    pub ok: bool,
    pub allow_no_scenarios: bool,
    pub limits: ProgramLimits,
    pub program_identity: Option<ProgramIdentity>,
    pub load: ValidationPhase,
    pub check: ValidationPhase,
    pub format: ValidationPhase,
    pub scenarios: ValidationPhase,
    pub modules: Vec<ModuleFormatCheck>,
    pub results: Vec<ScenarioValidation>,
    pub evidence: Option<ValidationEvidence>,
    pub warnings: Vec<ValidationWarning>,
}

impl ValidationReport {
    pub(crate) fn load_failure(error: Diagnostic, options: ValidationOptions) -> Self {
        let mut report = Self::new(options);
        report.load = ValidationPhase::failed(error);
        report
    }
    fn new(options: ValidationOptions) -> Self {
        Self {
            kind: "gwt.native-validation",
            schema_version: 1,
            ok: false,
            allow_no_scenarios: options.allow_no_scenarios,
            limits: options.limits,
            program_identity: None,
            load: ValidationPhase::passed(),
            check: ValidationPhase::skipped("source loading failed"),
            format: ValidationPhase::skipped("static checking did not pass"),
            scenarios: ValidationPhase::skipped("static checking did not pass"),
            modules: Vec::new(),
            results: Vec::new(),
            evidence: None,
            warnings: Vec::new(),
        }
    }
}

/// Load once, then validate only the captured bytes. Loading is not an atomic
/// filesystem snapshot; compilation, formatting, and execution do not reopen it.
pub fn validate_file(
    entry: &Path,
    root: Option<&Path>,
    options: ValidationOptions,
) -> ValidationReport {
    match load_bundle(entry, root) {
        Ok(bundle) => validate_bundle(&bundle, options),
        Err(error) => ValidationReport::load_failure(error, options),
    }
}

/// Require scenarios unless the caller explicitly permits a declaration-only
/// module. Even with that permission, zero scenarios remain `notExercised`.
pub fn validate_bundle(bundle: &SourceBundle, options: ValidationOptions) -> ValidationReport {
    let mut report = ValidationReport::new(options);
    let program = match compile_bundle(bundle) {
        Ok(program) => program,
        Err(error) => {
            report.check = ValidationPhase::failed(error);
            return report;
        }
    };
    report.check = ValidationPhase::passed();
    report.program_identity = program.identity().cloned();
    for (file, text) in &bundle.modules {
        report.modules.push(match format_source(text, file) {
            Ok(formatted) => ModuleFormatCheck {
                file: file.clone(),
                changed: Some(formatted.changed),
                diagnostic: None,
            },
            Err(error) => ModuleFormatCheck {
                file: file.clone(),
                changed: None,
                diagnostic: Some(error),
            },
        });
    }
    report.format = if report
        .modules
        .iter()
        .all(|module| module.changed == Some(false))
    {
        ValidationPhase::passed()
    } else {
        ValidationPhase {
            status: ValidationStatus::Failed,
            reason: Some("one or more modules need formatting or could not be formatted".into()),
            diagnostic: None,
        }
    };
    let mut evidence = EvidenceCollector::new(&program);
    for scenario in &program.scenarios {
        let execution = program.run_scenario(&scenario.name, options.limits);
        let expectations = expectations(scenario, &execution.events);
        evidence.observe(&scenario.name, &expectations, &execution.events);
        report.results.push(ScenarioValidation {
            name: scenario.name.clone(),
            ok: execution.ok,
            steps: execution.steps,
            diagnostic: execution.diagnostic,
            expectations,
        });
    }
    let (evidence, warnings) = evidence.finish();
    report.evidence = Some(evidence);
    report.warnings = warnings;
    report.scenarios = if report.results.is_empty() {
        ValidationPhase {
            status: ValidationStatus::NotExercised,
            reason: Some("the entry has no executable scenarios".into()),
            diagnostic: None,
        }
    } else if report.results.iter().all(|result| result.ok) {
        ValidationPhase::passed()
    } else {
        ValidationPhase {
            status: ValidationStatus::Failed,
            reason: Some("one or more scenarios failed".into()),
            diagnostic: None,
        }
    };
    report.ok = report.format.status == ValidationStatus::Passed
        && (report.scenarios.status == ValidationStatus::Passed
            || (options.allow_no_scenarios
                && report.scenarios.status == ValidationStatus::NotExercised));
    report
}
