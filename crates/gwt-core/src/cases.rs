//! Native execution cases are observations, not specifications of desired behavior.
use crate::source::{Diagnostic, Result, Span};
use crate::{
    CompiledProgram, ProgramExecution, ProgramIdentity, ProgramLimits, SourceBundle, compile_bundle,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

pub const MAX_CASE_BYTES: usize = 16 * 1_048_576;
const MAX_DIFFERENCES: usize = 128;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EngineIdentity {
    pub profile: String,
    pub source_digest: String,
}

pub fn engine_identity() -> EngineIdentity {
    EngineIdentity {
        profile: "gwt-native-case-engine-v1".into(),
        source_digest: env!("GWT_NATIVE_ENGINE_SOURCE").into(),
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Record {
    engine: EngineIdentity,
    source: SourceBundle,
    program_identity: ProgramIdentity,
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        deserialize_with = "target_name"
    )]
    request: Option<String>,
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        deserialize_with = "target_name"
    )]
    scenario: Option<String>,
    input: Json,
    limits: ProgramLimits,
    observed: Json,
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        deserialize_with = "migration_origin"
    )]
    migration: Option<MigrationOrigin>,
}

fn migration_origin<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<Option<MigrationOrigin>, D::Error> {
    MigrationOrigin::deserialize(deserializer).map(Some)
}

/// A migration preserves its immediate parent. Retain the proposal for the full chain.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct MigrationOrigin {
    pub parent_case_integrity: String,
    pub previous_engine: EngineIdentity,
    pub previous_executable_sha256: String,
}

pub(crate) fn is_sha256(value: &str) -> bool {
    value.strip_prefix("sha256:").is_some_and(|hex| {
        hex.len() == 64
            && hex
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    })
}

// Missing target fields are allowed by the versioned shape; explicit null is
// not. Accepted target fields therefore survive canonical serialization exactly.
fn target_name<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<Option<String>, D::Error> {
    String::deserialize(deserializer).map(Some)
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct File {
    kind: String,
    schema_version: u32,
    record: Record,
    integrity: String,
}

/// An immutable case. Loading checks shape and integrity; replay verifies the observation.
#[derive(Clone, Debug, Serialize)]
#[serde(transparent)]
pub struct ExecutionCase(File);

#[derive(Debug, Serialize)]
#[serde(tag = "presence", content = "value", rename_all = "lowercase")]
pub enum Presence {
    Missing,
    Present(Json),
}

#[derive(Debug, Serialize)]
pub struct Difference {
    pub path: String,
    pub before: Presence,
    pub after: Presence,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReplayReport {
    pub kind: &'static str,
    pub schema_version: u32,
    /// True means the entire observed execution was reproduced, including a recorded failure.
    pub verified: bool,
    pub differences: Vec<Difference>,
    pub differences_truncated: bool,
    pub actual: ProgramExecution,
}

#[derive(Debug, Serialize)]
pub struct Changes {
    pub source: bool,
    pub outcome: bool,
    pub state: bool,
    /// Includes values, source positions, diagnostics, and steps; not a causal claim.
    pub evidence: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CaseComparison {
    pub kind: &'static str,
    pub schema_version: u32,
    pub status: &'static str,
    pub baseline: ReplayReport,
    pub candidate: Option<ProgramExecution>,
    pub changes: Option<Changes>,
    pub outcome_differences: Vec<Difference>,
    pub outcome_differences_truncated: bool,
}

fn span() -> Span {
    Span {
        file: "<execution-case>".into(),
        start: 0,
        end: 0,
        line: 1,
        column: 1,
    }
}
fn error(code: &str, message: impl Into<String>) -> Diagnostic {
    Diagnostic::new(code, message, &span())
}

fn check_limits(limits: ProgramLimits) -> Result<()> {
    let maximum = ProgramLimits::default();
    if limits.execution.steps > maximum.execution.steps
        || limits.execution.evidence_bytes > maximum.execution.evidence_bytes
        || limits.execution.text_bytes > maximum.execution.text_bytes
        || limits.call_depth > maximum.call_depth
    {
        return Err(error(
            "case_limits",
            "captured/replayed limits cannot exceed the native default profile",
        ));
    }
    Ok(())
}

pub(crate) fn check_shape(value: &Json) -> Result<()> {
    let mut pending = vec![(value, 0)];
    let mut nodes = 0;
    while let Some((value, depth)) = pending.pop() {
        nodes += 1;
        if depth > 96 || nodes > 500_000 {
            return Err(error(
                "case_limit",
                "case exceeds 96 value levels or 500000 JSON values",
            ));
        }
        match value {
            Json::Array(items) => pending.extend(items.iter().map(|item| (item, depth + 1))),
            Json::Object(items) => pending.extend(items.values().map(|item| (item, depth + 1))),
            _ => (),
        }
    }
    Ok(())
}

/// Canonical JSON: recursively sorted object keys, compact JSON scalars/arrays.
/// Numeric tokens retain serde_json's arbitrary-precision representation.
pub(crate) fn canonical(value: &Json, bytes: &mut Vec<u8>) {
    match value {
        Json::Object(fields) => {
            bytes.push(b'{');
            let mut fields: Vec<_> = fields.iter().collect();
            fields.sort_by_key(|(a, _)| *a);
            for (index, (key, value)) in fields.into_iter().enumerate() {
                if index > 0 {
                    bytes.push(b',');
                }
                serde_json::to_writer(&mut *bytes, key).expect("JSON key");
                bytes.push(b':');
                canonical(value, bytes);
            }
            bytes.push(b'}');
        }
        Json::Array(items) => {
            bytes.push(b'[');
            for (index, value) in items.iter().enumerate() {
                if index > 0 {
                    bytes.push(b',');
                }
                canonical(value, bytes);
            }
            bytes.push(b']');
        }
        _ => serde_json::to_writer(bytes, value).expect("JSON scalar"),
    }
}

fn integrity(file: &File) -> Result<String> {
    let value = json!({"kind":file.kind,"schemaVersion":file.schema_version,"record":file.record});
    check_shape(&value)?;
    let mut bytes = Vec::new();
    canonical(&value, &mut bytes);
    if bytes.len() > MAX_CASE_BYTES - 128 {
        return Err(error("case_limit", "execution case exceeds sixteen MiB"));
    }
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-case-sha256-v1\0");
    hash.update(bytes);
    Ok(format!("sha256:{:x}", hash.finalize()))
}

impl ExecutionCase {
    pub fn from_json(source: &str) -> Result<Self> {
        if source.len() > MAX_CASE_BYTES {
            return Err(error("case_limit", "execution case exceeds sixteen MiB"));
        }
        let file: File = serde_json::from_str(source)
            .map_err(|failure| error("case_format", failure.to_string()))?;
        let case = Self(file);
        case.validate()?;
        Ok(case)
    }
    pub fn to_json(&self) -> String {
        serde_json::to_string(self).expect("execution case JSON")
    }
    pub fn integrity(&self) -> &str {
        &self.0.integrity
    }
    pub fn observed(&self) -> &Json {
        &self.0.record.observed
    }
    pub fn input(&self) -> &Json {
        &self.0.record.input
    }
    pub fn request(&self) -> Option<&str> {
        self.0.record.request.as_deref()
    }
    pub fn scenario(&self) -> Option<&str> {
        self.0.record.scenario.as_deref()
    }
    fn execute(&self, program: &CompiledProgram) -> ProgramExecution {
        if let Some(request) = self.request() {
            program.run_request(request, self.input(), self.limits())
        } else {
            program.run_scenario(
                self.scenario().expect("validated scenario target"),
                self.limits(),
            )
        }
    }
    pub fn source(&self) -> &SourceBundle {
        &self.0.record.source
    }
    pub fn program_identity(&self) -> &ProgramIdentity {
        &self.0.record.program_identity
    }
    pub fn limits(&self) -> ProgramLimits {
        self.0.record.limits
    }
    pub fn engine(&self) -> &EngineIdentity {
        &self.0.record.engine
    }
    pub fn migration(&self) -> Option<&MigrationOrigin> {
        self.0.record.migration.as_ref()
    }
    fn validate(&self) -> Result<()> {
        let file = &self.0;
        if file.kind != "gwt.native-case" || !matches!(file.schema_version, 1..=3) {
            return Err(error(
                "case_version",
                "expected gwt.native-case schema version 1, 2, or 3",
            ));
        }
        let name = match (file.schema_version, self.request(), self.scenario()) {
            (1 | 3, Some(request), None) => request,
            (2 | 3, None, Some(scenario)) if file.record.input.is_null() => scenario,
            _ => {
                return Err(error(
                    "case_format",
                    "case requires one version-appropriate target; scenarios require null input",
                ));
            }
        };
        match (file.schema_version, self.migration()) {
            (1 | 2, None) => (),
            (3, Some(origin))
                if is_sha256(&origin.parent_case_integrity)
                    && is_sha256(&origin.previous_executable_sha256)
                    && is_sha256(&origin.previous_engine.source_digest)
                    && origin.previous_engine.profile == "gwt-native-case-engine-v1"
                    && origin.previous_engine != file.record.engine => {}
            _ => {
                return Err(error(
                    "case_migration",
                    "schema 3 requires valid migration provenance; schemas 1 and 2 cannot carry it",
                ));
            }
        }
        if name.is_empty() || name.len() > 4096 {
            return Err(error(
                "case_format",
                "execution target name must contain 1 to 4096 UTF-8 bytes",
            ));
        }
        check_limits(file.record.limits)?;
        crate::validate_input_shape(&file.record.input, &span())?;
        if serde_json::to_vec(&file.record.input)
            .expect("JSON input")
            .len()
            > 1_048_576
        {
            return Err(error("case_limit", "case input exceeds one MiB"));
        }
        if file.record.observed.get("kind") != Some(&json!("gwt.native-run"))
            || file.record.observed.get("schemaVersion") != Some(&json!(1))
        {
            return Err(error(
                "case_format",
                "observed execution must use native-run schema version 1",
            ));
        }
        if integrity(file)? != file.integrity {
            return Err(error(
                "case_integrity",
                "case content does not match its integrity digest",
            ));
        }
        Ok(())
    }

    pub(crate) fn recapture_for_migration(&self, executable_sha256: &str) -> Result<Self> {
        let program = compile_bundle(self.source())?;
        if program.identity() != Some(self.program_identity()) {
            return Err(error(
                "case_source",
                "case source does not match its program identity",
            ));
        }
        let mut candidate = if let Some(request) = self.request() {
            capture_request(&program, request, self.input(), self.limits())?
        } else {
            capture_scenario(
                &program,
                self.scenario().expect("validated target"),
                self.limits(),
            )?
        };
        candidate.0.schema_version = 3;
        candidate.0.record.migration = Some(MigrationOrigin {
            parent_case_integrity: self.integrity().into(),
            previous_engine: self.engine().clone(),
            previous_executable_sha256: executable_sha256.into(),
        });
        candidate.0.integrity = integrity(&candidate.0)?;
        candidate.validate()?;
        Ok(candidate)
    }
}

pub fn capture_request(
    program: &CompiledProgram,
    request: &str,
    input: &Json,
    limits: ProgramLimits,
) -> Result<ExecutionCase> {
    let Some(source) = program.source_bundle() else {
        return Err(error(
            "case_source",
            "capture requires a compiled source bundle",
        ));
    };
    check_limits(limits)?;
    if request.is_empty() || request.len() > 4096 {
        return Err(error(
            "case_format",
            "request name must contain 1 to 4096 UTF-8 bytes",
        ));
    }
    crate::validate_input_shape(input, &span())?;
    if serde_json::to_vec(input).expect("JSON input").len() > 1_048_576 {
        return Err(error("case_limit", "case input exceeds one MiB"));
    }
    let observed =
        serde_json::to_value(program.run_request(request, input, limits)).expect("execution JSON");
    let mut file = File {
        kind: "gwt.native-case".into(),
        schema_version: 1,
        record: Record {
            engine: engine_identity(),
            source: source.clone(),
            program_identity: program.identity().expect("bundle identity").clone(),
            request: Some(request.into()),
            scenario: None,
            input: input.clone(),
            limits,
            observed,
            migration: None,
        },
        integrity: String::new(),
    };
    file.integrity = integrity(&file)?;
    let case = ExecutionCase(file);
    case.validate()?;
    Ok(case)
}

/// Freeze one existing scenario, its source closure, settings, and entire run.
/// A failed execution can be captured; a misspelled scenario name cannot.
pub fn capture_scenario(
    program: &CompiledProgram,
    scenario: &str,
    limits: ProgramLimits,
) -> Result<ExecutionCase> {
    let Some(source) = program.source_bundle() else {
        return Err(error(
            "case_source",
            "capture requires a compiled source bundle",
        ));
    };
    check_limits(limits)?;
    if scenario.is_empty() || scenario.len() > 4096 {
        return Err(error(
            "case_format",
            "scenario name must contain 1 to 4096 UTF-8 bytes",
        ));
    }
    if !program.scenario_names().contains(&scenario) {
        return Err(error(
            "unknown_scenario",
            format!("unknown scenario '{scenario}'"),
        ));
    }
    let mut file = File {
        kind: "gwt.native-case".into(),
        schema_version: 2,
        record: Record {
            engine: engine_identity(),
            source: source.clone(),
            program_identity: program.identity().expect("bundle identity").clone(),
            request: None,
            scenario: Some(scenario.into()),
            input: Json::Null,
            limits,
            observed: serde_json::to_value(program.run_scenario(scenario, limits))
                .expect("execution JSON"),
            migration: None,
        },
        integrity: String::new(),
    };
    file.integrity = integrity(&file)?;
    let case = ExecutionCase(file);
    case.validate()?;
    Ok(case)
}

pub(crate) fn differences(before: &Json, after: &Json) -> (Vec<Difference>, bool) {
    fn walk(
        before: Option<&Json>,
        after: Option<&Json>,
        path: &str,
        output: &mut Vec<Difference>,
        truncated: &mut bool,
    ) {
        if before == after {
            return;
        }
        if output.len() == MAX_DIFFERENCES {
            *truncated = true;
            return;
        }
        match (before, after) {
            (Some(Json::Object(left)), Some(Json::Object(right))) => {
                let keys: BTreeSet<_> = left.keys().chain(right.keys()).collect();
                for key in keys {
                    walk(
                        left.get(key),
                        right.get(key),
                        &format!("{path}/{}", key.replace('~', "~0").replace('/', "~1")),
                        output,
                        truncated,
                    );
                }
            }
            (Some(Json::Array(left)), Some(Json::Array(right))) => {
                for index in 0..left.len().max(right.len()) {
                    walk(
                        left.get(index),
                        right.get(index),
                        &format!("{path}/{index}"),
                        output,
                        truncated,
                    );
                }
            }
            _ => output.push(Difference {
                path: path.into(),
                before: before.map_or(Presence::Missing, |value| Presence::Present(value.clone())),
                after: after.map_or(Presence::Missing, |value| Presence::Present(value.clone())),
            }),
        }
    }
    let mut result = Vec::new();
    let mut truncated = false;
    walk(Some(before), Some(after), "", &mut result, &mut truncated);
    (result, truncated)
}

pub fn replay_case(case: &ExecutionCase) -> Result<ReplayReport> {
    case.validate()?;
    let record = &case.0.record;
    if record.engine != engine_identity() {
        return Err(error(
            "case_engine",
            "case engine fingerprint differs; explicit migration is required",
        ));
    }
    let program = compile_bundle(&record.source)?;
    if program.identity() != Some(&record.program_identity) {
        return Err(error(
            "case_source",
            "case source does not match its program identity",
        ));
    }
    let actual = case.execute(&program);
    let payload = serde_json::to_value(&actual).expect("execution JSON");
    let (differences, differences_truncated) = differences(&record.observed, &payload);
    Ok(ReplayReport {
        kind: "gwt.native-replay",
        schema_version: 1,
        verified: record.observed == payload,
        differences,
        differences_truncated,
        actual,
    })
}

pub(crate) fn outcome(execution: &Json) -> Json {
    json!({"ok":execution["ok"],"result":execution["result"],"output":execution["output"],
        "diagnostic":execution.get("diagnostic").filter(|value| !value.is_null()).map(|diagnostic| json!({"code":diagnostic["code"],"message":diagnostic["message"]}))})
}

pub fn compare_case(case: &ExecutionCase, candidate: &CompiledProgram) -> Result<CaseComparison> {
    if candidate.identity().is_none() {
        return Err(error(
            "case_source",
            "comparison candidate requires a compiled source bundle",
        ));
    }
    let baseline = replay_case(case)?;
    if !baseline.verified {
        return Ok(CaseComparison {
            kind: "gwt.native-comparison",
            schema_version: 1,
            status: "baseline_mismatch",
            baseline,
            candidate: None,
            changes: None,
            outcome_differences: Vec::new(),
            outcome_differences_truncated: false,
        });
    }
    let result = case.execute(candidate);
    let payload = serde_json::to_value(&result).expect("execution JSON");
    let before = outcome(case.observed());
    let after = outcome(&payload);
    let changes = Changes {
        source: case.program_identity() != candidate.identity().expect("checked bundle"),
        outcome: before != after,
        state: case.observed()["state"] != payload["state"],
        evidence: case.observed()["events"] != payload["events"]
            || case.observed()["diagnostic"] != payload["diagnostic"]
            || case.observed()["steps"] != payload["steps"],
    };
    let (outcome_differences, outcome_differences_truncated) = differences(&before, &after);
    Ok(CaseComparison {
        kind: "gwt.native-comparison",
        schema_version: 1,
        status: "compared",
        baseline,
        candidate: Some(result),
        changes: Some(changes),
        outcome_differences,
        outcome_differences_truncated,
    })
}
