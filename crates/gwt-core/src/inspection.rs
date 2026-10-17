//! Contract discovery from the checked program, without executing its statements.
use crate::{
    CompiledProgram, ProgramIdentity, Type,
    source::{Diagnostic, Result, Span},
};
use serde::Serialize;
use serde_json::Value;
use std::io::{self, Write};

pub const MAX_INSPECTION_BYTES: usize = 8 * 1_048_576;

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ParameterInspection<'a> {
    pub name: &'a str,
    #[serde(rename = "type")]
    pub ty: &'a Type,
    pub span: &'a Span,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RequestInspection<'a> {
    pub name: &'a str,
    pub inputs: Vec<ParameterInspection<'a>>,
    pub required_inputs: Vec<&'a str>,
    pub outputs: Vec<ParameterInspection<'a>>,
    pub span: &'a Span,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BehaviorInspection<'a> {
    pub signature: String,
    pub parameters: Vec<ParameterInspection<'a>>,
    pub returns: Option<&'a Type>,
    pub return_span: Option<&'a Span>,
    pub span: &'a Span,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct TypeInspection<'a> {
    pub name: &'a str,
    pub declaration: &'a str,
    #[serde(rename = "type")]
    pub ty: &'a Type,
    pub span: &'a Span,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ScenarioInspection<'a> {
    pub name: &'a str,
    pub span: &'a Span,
    pub example_row: Option<usize>,
    pub example_span: Option<&'a Span>,
    pub declared_expectations: usize,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ProgramInspection<'a> {
    pub kind: &'static str,
    pub schema_version: u32,
    pub ok: bool,
    pub program: Option<&'a str>,
    pub program_identity: Option<&'a ProgramIdentity>,
    pub types: Vec<TypeInspection<'a>>,
    pub requests: Vec<RequestInspection<'a>>,
    pub behaviors: Vec<BehaviorInspection<'a>>,
    pub scenarios: Vec<ScenarioInspection<'a>>,
    #[serde(skip)]
    span: &'a Span,
}

fn parameter(parameter: &crate::program::Parameter) -> ParameterInspection<'_> {
    ParameterInspection {
        name: &parameter.name,
        ty: &parameter.ty,
        span: &parameter.span,
    }
}

impl CompiledProgram {
    /// Borrow resolved declarations, with no state initialization or execution.
    /// Successful inspection is not evidence that scenarios or postconditions pass.
    pub fn inspect(&self) -> ProgramInspection<'_> {
        ProgramInspection {
            kind: "gwt.native-inspection",
            schema_version: 1,
            ok: true,
            program: self.name.as_deref(),
            program_identity: self.identity.as_ref(),
            types: self
                .type_declarations
                .iter()
                .map(|(name, ty, node)| TypeInspection {
                    name,
                    declaration: &node.text,
                    ty,
                    span: &node.span,
                })
                .collect(),
            requests: self
                .requests
                .iter()
                .map(|request| RequestInspection {
                    name: &request.name,
                    span: &request.span,
                    inputs: request.inputs.iter().map(|(p, _)| parameter(p)).collect(),
                    required_inputs: request
                        .inputs
                        .iter()
                        .filter(|(p, _)| !matches!(p.ty, Type::Optional(_)))
                        .map(|(p, _)| p.name.as_str())
                        .collect(),
                    outputs: request.outputs.iter().map(|(p, _)| parameter(p)).collect(),
                })
                .collect(),
            behaviors: self
                .behaviors
                .iter()
                .map(|behavior| BehaviorInspection {
                    signature: behavior.signature.join(" "),
                    parameters: behavior.parameters.iter().map(parameter).collect(),
                    returns: behavior.returns.as_ref(),
                    return_span: behavior.return_site.as_ref(),
                    span: &behavior.span,
                })
                .collect(),
            scenarios: self
                .scenarios
                .iter()
                .map(|scenario| ScenarioInspection {
                    name: &scenario.name,
                    span: &scenario.span,
                    example_row: scenario.example.as_ref().map(|row| row.index),
                    example_span: scenario.example.as_ref().map(|row| &row.span),
                    declared_expectations: scenario.expectations.len(),
                })
                .collect(),
            span: &self.span,
        }
    }
}

struct BoundedJson(Vec<u8>);
impl Write for BoundedJson {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.len() > MAX_INSPECTION_BYTES.saturating_sub(self.0.len()) {
            return Err(io::Error::other("inspection exceeds eight MiB"));
        }
        self.0.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

impl ProgramInspection<'_> {
    /// Produce the complete bounded protocol value or a diagnostic. Contracts
    /// are never abbreviated or silently omitted to satisfy the output limit.
    pub fn to_json(&self) -> Result<Value> {
        let mut output = BoundedJson(Vec::new());
        serde_json::to_writer(&mut output, self).map_err(|_| {
            Diagnostic::new(
                "inspection_limit",
                "complete inspection exceeds eight MiB; inspect a smaller entry module",
                self.span,
            )
        })?;
        // Bound serialized size first, then build a Value directly. Parsing the
        // bytes again would impose JSON's default recursion limit on valid,
        // already-checked nested contract trees.
        drop(output);
        Ok(serde_json::to_value(self).expect("inspection contains JSON-compatible data"))
    }
}
