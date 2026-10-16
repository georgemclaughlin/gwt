//! Turn a verified observation into a readable, executable regression case.
use std::collections::{BTreeMap, BTreeSet};

use serde::Serialize;
use serde_json::{Value as Json, json};

use crate::source::{Diagnostic, Result, Span};
use crate::{
    ExecutionCase, ProgramIdentity, ProgramLimits, SourceBundle, Type, compile_bundle, replay_case,
};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GeneratedScenario {
    kind: &'static str,
    schema_version: u32,
    name: String,
    captured_program_identity: ProgramIdentity,
    captured_engine: crate::EngineIdentity,
    case_integrity: String,
    expectation_basis: &'static str,
    assertion_scope: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    captured_failure: Option<Diagnostic>,
    validation_limits: ProgramLimits,
    source: SourceBundle,
}
impl GeneratedScenario {
    pub fn source_bundle(&self) -> &SourceBundle {
        &self.source
    }
    pub fn name(&self) -> &str {
        &self.name
    }
}
fn error(code: &str, message: impl Into<String>) -> Diagnostic {
    Diagnostic::new(
        code,
        message,
        &Span {
            file: "<scenario-generation>".into(),
            start: 0,
            end: 0,
            line: 1,
            column: 1,
        },
    )
}

struct Writer {
    names: BTreeSet<String>,
    types: Vec<(Type, String)>,
    declarations: Vec<String>,
    steps: Vec<String>,
    sequence: usize,
    bytes: usize,
}
impl Writer {
    fn fresh(&mut self, prefix: &str) -> String {
        loop {
            self.sequence += 1;
            let name = format!("{prefix}{}", self.sequence);
            if self.names.insert(name.clone()) {
                return name;
            }
        }
    }
    fn push(&mut self, declaration: bool, line: String) -> Result<()> {
        self.bytes += line.len() + 1;
        if self.bytes > crate::program_source::MAX_PROGRAM_BYTES - 1024 {
            return Err(error(
                "scenario_generation_limit",
                "generated scenario exceeds one MiB",
            ));
        }
        if declaration {
            self.declarations.push(line);
        } else {
            self.steps.push(line);
        }
        Ok(())
    }
    fn ty(&mut self, ty: &Type) -> Result<String> {
        if let Some((_, name)) = self.types.iter().find(|(existing, _)| existing == ty) {
            return Ok(name.clone());
        }
        let name = match ty {
            Type::Boolean => "boolean".into(),
            Type::Integer => "integer".into(),
            Type::Decimal => "decimal".into(),
            Type::Text => "text".into(),
            Type::TextUnion(values) => values
                .iter()
                .map(|value| json!(value).to_string())
                .collect::<Vec<_>>()
                .join(" | "),
            Type::IntegerUnion(values) => values.join(" | "),
            Type::DecimalUnion(values) => values
                .iter()
                .map(|v| {
                    if v.contains('.') {
                        v.clone()
                    } else {
                        format!("{v}.0")
                    }
                })
                .collect::<Vec<_>>()
                .join(" | "),
            Type::BooleanUnion(values) => values
                .iter()
                .map(bool::to_string)
                .collect::<Vec<_>>()
                .join(" | "),
            Type::Optional(inner) => format!("optional<{}>", self.ty(inner)?),
            Type::List(inner) => format!("list<{}>", self.ty(inner)?),
            Type::Record(fields) => {
                let name = self.fresh("CapturedRecord");
                let mut lines = vec![format!("RECORD {name}")];
                for (field, ty) in fields {
                    lines.push(format!("  {field}: {}", self.ty(ty)?));
                }
                for line in lines {
                    self.push(true, line)?;
                }
                self.push(true, String::new())?;
                name
            }
            Type::OneOf(kinds) => {
                let name = self.fresh("CapturedKinds");
                let mut lines = vec![format!("RECORD {name} is one of")];
                for (kind, fields) in kinds {
                    lines.push(format!("  {kind}:"));
                    for (field, ty) in fields {
                        lines.push(format!("    {field}: {}", self.ty(ty)?));
                    }
                }
                for line in lines {
                    self.push(true, line)?;
                }
                self.push(true, String::new())?;
                name
            }
        };
        self.types.push((ty.clone(), name.clone()));
        Ok(name)
    }
    fn expression(&mut self, ty: &Type, value: &Json) -> Result<String> {
        match ty {
            Type::Optional(inner) if !value.is_null() => self.expression(inner, value),
            Type::Record(_) | Type::OneOf(_) | Type::Optional(_) => {
                let name = self.fresh("captured_value_");
                self.bind(&name, ty, value)?;
                Ok(name)
            }
            Type::List(inner) => {
                let mut values = Vec::new();
                for value in value.as_array().expect("verified list") {
                    values.push(self.expression(inner, value)?);
                }
                Ok(format!("[{}]", values.join(", ")))
            }
            _ => Ok(value.to_string()),
        }
    }
    fn fields(
        &mut self,
        fields: &BTreeMap<String, Type>,
        value: &Json,
        depth: usize,
    ) -> Result<Vec<String>> {
        let mut lines = Vec::new();
        let indent = "  ".repeat(depth);
        for (field, ty) in fields {
            let value = &value[field];
            if value.is_null() && matches!(ty, Type::Optional(_)) {
                continue;
            }
            if let Type::Record(nested) = ty {
                lines.push(format!("{indent}{field}:"));
                lines.extend(self.fields(nested, value, depth + 1)?);
            } else if matches!(ty, Type::OneOf(_)) {
                let fields = ty
                    .fields_for_kind(value["kind"].as_str().expect("verified kind"))
                    .expect("verified one-of fields");
                lines.push(format!("{indent}{field}:"));
                lines.extend(self.fields(&fields, value, depth + 1)?);
            } else {
                lines.push(format!("{indent}{field}: {}", self.expression(ty, value)?));
            }
        }
        Ok(lines)
    }
    fn bind(&mut self, name: &str, ty: &Type, value: &Json) -> Result<()> {
        if let Type::Record(fields) = ty {
            let lines = self.fields(fields, value, 1)?;
            if !lines.is_empty() {
                let type_name = self.ty(ty)?;
                self.push(false, format!("GIVEN {name} is {type_name}"))?;
                for line in lines {
                    self.push(false, line)?;
                }
                self.push(false, String::new())?;
                return Ok(());
            }
        }
        // A typed wrapper preserves empty-list, optional, union and decimal
        // contracts without inventing casts or null literals in the language.
        let wrapper_type = Type::Record(BTreeMap::from([
            ("ready".into(), Type::Boolean),
            ("value".into(), ty.clone()),
        ]));
        let wrapper_name = self.fresh("captured_holder_");
        let type_name = self.ty(&wrapper_type)?;
        let data = json!({"ready":true,"value":value});
        let Type::Record(fields) = &wrapper_type else {
            unreachable!()
        };
        let lines = self.fields(fields, &data, 1)?;
        self.push(false, format!("GIVEN {wrapper_name} is {type_name}"))?;
        for line in lines {
            self.push(false, line)?;
        }
        self.push(false, format!("GIVEN {name} is {wrapper_name}.value"))?;
        self.push(false, String::new())?;
        Ok(())
    }
}

/// Replay first, generate assertions over observed outputs, then compile and test.
/// No filesystem access; a returned artifact owns its complete frozen source closure.
pub fn scenario_from_case(case: &ExecutionCase, name: &str) -> Result<GeneratedScenario> {
    if name.trim().is_empty()
        || name.trim() != name
        || name.len() > 256
        || name.chars().any(char::is_control)
        || name.contains('#')
    {
        return Err(error(
            "scenario_name",
            "scenario name must be 1 to 256 UTF-8 bytes, without controls, comments, or surrounding whitespace",
        ));
    }
    let replay = replay_case(case)?;
    if !replay.verified {
        return Err(error(
            "scenario_baseline_mismatch",
            "recorded execution did not reproduce; no scenario was generated",
        ));
    }
    let request_name = case.request().ok_or_else(|| {
        error(
            "scenario_case_target",
            "this case already captures a scenario; use its frozen source for replay or comparison",
        )
    })?;
    let failure = replay.actual.diagnostic.as_ref();
    if failure.is_some_and(|error| !crate::failure_expectation::supported(&error.code)) {
        return Err(error(
            "scenario_failure_unsupported",
            "this failure is outside the scenario expectation model; preserve it for exact case replay",
        ));
    }
    let program = compile_bundle(case.source())?;
    let request = program
        .requests
        .iter()
        .find(|request| request.name == request_name)
        .expect("verified successful request");
    let mut writer = Writer {
        names: BTreeSet::new(),
        types: Vec::new(),
        declarations: Vec::new(),
        steps: Vec::new(),
        sequence: 0,
        bytes: 0,
    };
    for (path, source) in &case.source().modules {
        for node in crate::program_source::parse(source, path)? {
            if node.text.starts_with("TYPE ") || node.text.starts_with("RECORD ") {
                if let Some(name) = node.text.split_whitespace().nth(1) {
                    writer.names.insert(name.into());
                }
            }
        }
    }
    for (parameter, _) in request.inputs.iter().chain(&request.outputs) {
        writer.names.insert(parameter.name.clone());
        // Reuse the declaration's original type spelling for readable common cases.
        let source = &case.source().modules[&parameter.span.file];
        let declaration = &source[parameter.span.start..parameter.span.end];
        if let Some((_, ty)) = declaration.split_once(" is ") {
            writer.types.push((parameter.ty.clone(), ty.trim().into()));
        }
    }
    // Use normalized inputs, not post-execution state: inputs can be mutable outputs.
    let input_type = Type::Record(
        request
            .inputs
            .iter()
            .map(|(parameter, _)| (parameter.name.clone(), parameter.ty.clone()))
            .collect(),
    );
    let inputs = crate::value::normalize(&input_type, Some(case.input()), &program.span)?.json();
    writer.push(false, format!("SCENARIO {name}"))?;
    for (parameter, _) in &request.inputs {
        writer.bind(&parameter.name, &parameter.ty, &inputs[&parameter.name])?;
    }
    writer.push(false, format!("REQUEST {}", request.name))?;
    if let Some(failure) = failure {
        writer.push(false, format!("THEN fails with {}", json!(failure.code)))?;
    }
    writer.push(false, String::new())?;
    let (bindings, observed) = if failure.is_some() {
        (&request.inputs, &replay.actual.state)
    } else {
        (
            &request.outputs,
            replay.actual.result.as_ref().expect("successful outputs"),
        )
    };
    let mut assertions = Vec::new();
    for (parameter, _) in bindings {
        let expected = writer.fresh(&format!("expected_{}_", parameter.name));
        writer.bind(&expected, &parameter.ty, &observed[&parameter.name])?;
        assertions.push(format!("THEN {} == {expected}", parameter.name));
    }
    for assertion in assertions {
        writer.push(false, assertion)?;
    }
    writer.push(
        false,
        format!("THEN prints {}", json!(replay.actual.output)),
    )?;
    let original = case.source();
    let mut source = original.clone();
    let mut index = 1;
    let entry = loop {
        let entry = format!("captured_scenario_{index}.gwt");
        if !source
            .modules
            .keys()
            .any(|path| path == &entry || path.starts_with(&(entry.clone() + "/")))
        {
            break entry;
        }
        index += 1;
    };
    let header = format!(
        "# Generated from a verified observation; review expectations before adopting.\n# Case integrity: {}\nUSE {}",
        case.integrity(),
        json!(original.entry)
    );
    let declarations = writer.declarations.join("\n");
    let steps = writer.steps.join("\n");
    let text = [header.as_str(), declarations.trim_end(), steps.trim_end()]
        .into_iter()
        .filter(|section| !section.is_empty())
        .collect::<Vec<_>>()
        .join("\n\n")
        + "\n";
    source.entry = entry.clone();
    source.modules.insert(entry, text);
    let generated = compile_bundle(&source)?;
    let limits = ProgramLimits::default();
    let rows = generated.test_scenarios(limits);
    if rows.len() != 1 || !rows[0].execution.ok {
        let reason = rows
            .first()
            .and_then(|row| row.execution.diagnostic.as_ref())
            .map_or_else(|| "unexpected scenario count".into(), ToString::to_string);
        return Err(error(
            "scenario_validation",
            format!("generated scenario did not validate: {reason}"),
        ));
    }
    for (parameter, _) in bindings {
        if rows[0].execution.state[&parameter.name] != observed[&parameter.name] {
            return Err(error(
                "scenario_validation",
                "generated request state differs from the verified observation",
            ));
        }
    }
    if let Some(failure) = failure {
        let expected = json!(failure);
        if !rows[0].execution.events.iter().any(|event| {
            event.operation == "assert failure"
                && event.value["matched"] == true
                && event.value["actual"] == expected
        }) {
            return Err(error(
                "scenario_validation",
                "generated action failure differs from the verified observation",
            ));
        }
    }
    if rows[0].execution.output != replay.actual.output {
        return Err(error(
            "scenario_validation",
            "generated printed output differs from the verified observation",
        ));
    }
    Ok(GeneratedScenario {
        kind: "gwt.native-generated-scenario",
        schema_version: 3,
        name: name.into(),
        captured_program_identity: case.program_identity().clone(),
        captured_engine: crate::engine_identity(),
        case_integrity: case.integrity().into(),
        expectation_basis: "verified_observation_not_approval",
        assertion_scope: if failure.is_some() {
            "failure_code_inputs_and_printed_sequence"
        } else {
            "declared_outputs_and_printed_sequence"
        },
        captured_failure: failure.cloned(),
        validation_limits: limits,
        source,
    })
}
