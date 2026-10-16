//! Exact evidence accounting for one ordinary execution, without changing its limits.
use crate::source::{Diagnostic, Result, Span};
use crate::{CompiledProgram, ProgramExecution, ProgramIdentity, ProgramLimits};
use serde::Serialize;
use serde_json::Value as Json;
use std::{
    collections::BTreeMap,
    io::{self, Write},
};

pub const MAX_PROFILE_BYTES: usize = 8 * 1_048_576;

#[derive(Clone, Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EvidenceUsage {
    pub events: usize,
    pub bytes: usize,
    pub value_bytes: usize,
    pub metadata_bytes: usize,
}
impl EvidenceUsage {
    fn include(&mut self, bytes: usize, value_bytes: usize) {
        self.events += 1;
        self.bytes += bytes;
        self.value_bytes += value_bytes;
        self.metadata_bytes += bytes - value_bytes;
    }
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OperationUsage {
    pub operation: String,
    pub usage: EvidenceUsage,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocationUsage {
    pub span: Span,
    pub usage: EvidenceUsage,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ExecutionProfile {
    pub kind: &'static str,
    pub schema_version: u32,
    pub ok: bool,
    pub file: String,
    pub program: Option<String>,
    pub program_identity: Option<ProgramIdentity>,
    pub request: Option<String>,
    pub scenario: Option<String>,
    pub diagnostic: Option<Diagnostic>,
    pub limits: ProgramLimits,
    pub effective_call_depth_limit: usize,
    pub steps: usize,
    pub evidence: EvidenceUsage,
    pub by_operation: Vec<OperationUsage>,
    pub by_location: Vec<LocationUsage>,
    #[serde(skip)]
    span: Span,
}

struct ByteCount {
    bytes: usize,
    maximum: usize,
}
impl Write for ByteCount {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.len() > self.maximum.saturating_sub(self.bytes) {
            return Err(io::Error::other("profile exceeds its byte limit"));
        }
        self.bytes += bytes.len();
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
fn measure(value: &impl Serialize, maximum: usize, span: &Span) -> Result<usize> {
    let mut output = ByteCount { bytes: 0, maximum };
    serde_json::to_writer(&mut output, value).map_err(|_| {
        Diagnostic::new(
            "profile_limit",
            "profile input or complete report exceeds eight MiB",
            span,
        )
    })?;
    Ok(output.bytes)
}

impl CompiledProgram {
    /// Execute exactly one request with the supplied limits, then account for
    /// its retained evidence. Failed executions produce profiles with ok=false.
    pub fn profile_request(
        &self,
        name: &str,
        input: &Json,
        limits: ProgramLimits,
    ) -> Result<ExecutionProfile> {
        self.profile_execution(self.run_request(name, input, limits), limits, None)
    }

    /// Execute exactly one scenario, including an explicitly selected example row.
    pub fn profile_scenario(&self, name: &str, limits: ProgramLimits) -> Result<ExecutionProfile> {
        self.profile_execution(self.run_scenario(name, limits), limits, Some(name.into()))
    }

    fn profile_execution(
        &self,
        run: ProgramExecution,
        limits: ProgramLimits,
        scenario: Option<String>,
    ) -> Result<ExecutionProfile> {
        let mut evidence = EvidenceUsage::default();
        let mut operations = BTreeMap::<String, EvidenceUsage>::new();
        let mut locations =
            BTreeMap::<(String, usize, usize, usize, usize), (Span, EvidenceUsage)>::new();
        for event in &run.events {
            let bytes = measure(
                event,
                MAX_PROFILE_BYTES.saturating_sub(evidence.bytes),
                &event.span,
            )?;
            let value_bytes = measure(&event.value, bytes, &event.span)?;
            evidence.include(bytes, value_bytes);
            operations
                .entry(event.operation.clone())
                .or_default()
                .include(bytes, value_bytes);
            let span = &event.span;
            let key = (
                span.file.clone(),
                span.start,
                span.end,
                span.line,
                span.column,
            );
            locations
                .entry(key)
                .or_insert_with(|| (span.clone(), EvidenceUsage::default()))
                .1
                .include(bytes, value_bytes);
        }
        let mut by_operation: Vec<_> = operations
            .into_iter()
            .map(|(operation, usage)| OperationUsage { operation, usage })
            .collect();
        by_operation.sort_by(|a, b| {
            b.usage
                .bytes
                .cmp(&a.usage.bytes)
                .then_with(|| a.operation.cmp(&b.operation))
        });
        // Stable sorting retains the BTreeMap's source-order tie break.
        let mut by_location: Vec<_> = locations
            .into_values()
            .map(|(span, usage)| LocationUsage { span, usage })
            .collect();
        by_location.sort_by_key(|row| std::cmp::Reverse(row.usage.bytes));
        let report = ExecutionProfile {
            kind: "gwt.native-profile",
            schema_version: 1,
            ok: run.ok,
            file: run.file,
            program: run.program,
            program_identity: run.program_identity,
            request: run.request,
            scenario,
            diagnostic: run.diagnostic,
            limits,
            effective_call_depth_limit: limits.call_depth.min(64),
            steps: run.steps,
            evidence,
            by_operation,
            by_location,
            span: self.span.clone(),
        };
        measure(&report, MAX_PROFILE_BYTES, &report.span)?;
        Ok(report)
    }
}

impl ExecutionProfile {
    /// Serialize the complete bounded report. Groups are never silently omitted.
    pub fn to_json(&self) -> Result<Json> {
        measure(self, MAX_PROFILE_BYTES, &self.span)?;
        Ok(serde_json::to_value(self).expect("profile contains JSON-compatible data"))
    }
}
