use crate::source::{Diagnostic, Result, Span};
use crate::{ProgramExecution, SourceBundle, compile_bundle};
use serde::Serialize;
use serde_json::Value as Json;

#[derive(Debug, Serialize)]
pub struct SourceExcerpt {
    pub span: Span,
    pub text: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EvidenceStep {
    pub event: usize,
    pub operation: String,
    pub summary: String,
    pub source: SourceExcerpt,
    pub operands: Vec<usize>,
    pub value: Json,
    pub skipped: Option<SourceExcerpt>,
    pub definition: Option<SourceExcerpt>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub observed_failure: Option<SourceExcerpt>,
}

#[derive(Debug, Serialize)]
pub struct ExecutionExplanation {
    pub ok: bool,
    pub failure: Option<SourceExcerpt>,
    pub steps: Vec<EvidenceStep>,
}

pub(crate) fn excerpt(span: &Span, source: &SourceBundle) -> Result<SourceExcerpt> {
    let invalid = || {
        Diagnostic::new(
            "evidence_source",
            "evidence does not identify a valid position in its frozen source",
            span,
        )
    };
    let text = source.modules.get(&span.file).ok_or_else(invalid)?;
    let slice = text.get(span.start..span.end).ok_or_else(invalid)?;
    let prefix = &text[..span.start];
    let line = prefix.bytes().filter(|byte| *byte == b'\n').count() + 1;
    let column = prefix.rsplit('\n').next().unwrap().chars().count() + 1;
    if span.line != line || span.column != column {
        return Err(invalid());
    }
    Ok(SourceExcerpt {
        span: span.clone(),
        text: slice.into(),
    })
}

/// Describe recorded facts, with exact source and operand references. This does
/// not infer counterfactual causes or establish that a domain outcome is desired.
pub fn explain_execution(
    execution: &ProgramExecution,
    source: &SourceBundle,
) -> Result<ExecutionExplanation> {
    let program = compile_bundle(source)?;
    if execution.program_identity.as_ref() != program.identity() {
        return Err(Diagnostic::new(
            "evidence_source",
            "execution and explanation source identities differ",
            &program.span,
        ));
    }
    let mut steps = Vec::new();
    for (index, event) in execution.events.iter().enumerate() {
        if (matches!(
            event.operation.as_str(),
            "branch" | "kind branch" | "value branch" | "collection selection"
        ) && !event.value["selected"].is_boolean())
            || (event.operation == "assert" && !event.value.is_boolean())
            || (event.operation == "assert prints" && !event.value["matched"].is_boolean())
            || (event.operation == "assert failure" && !event.value["matched"].is_boolean())
        {
            return Err(Diagnostic::new(
                "evidence_value",
                "condition/assertion evidence must record a boolean",
                &event.span,
            ));
        }
        if event.operation == "append item"
            && (!event.value.is_object()
                || event.value.as_object().unwrap().len() != 4
                || !event.value["path"].is_string()
                || !event.value["sourcePath"].is_string()
                || event.value["index"].as_u64().is_none()
                || event.value.get("item").is_none())
        {
            return Err(Diagnostic::new(
                "evidence_value",
                "append item evidence requires paths, a nonnegative index, and the inserted item",
                &event.span,
            ));
        }
        if event.sequence != index + 1
            || event
                .inputs
                .iter()
                .any(|id| *id == 0 || *id >= event.sequence)
        {
            return Err(Diagnostic::new(
                "evidence_dependency",
                "event IDs must be ordered and operands must refer to earlier events",
                &event.span,
            ));
        }
        let summary = match event.operation.as_str() {
            "value branch" => {
                if event.value["selected"] == true {
                    "Scalar value matched; branch selected."
                } else {
                    "Scalar value did not match; branch not selected."
                }
            }
            "kind branch" => {
                if event.value["selected"] == true {
                    "Record kind matched; branch selected."
                } else {
                    "Record kind did not match; branch not selected."
                }
            }
            "branch" => {
                if event.value["selected"] == true {
                    "Condition matched; branch selected."
                } else {
                    "Condition did not match."
                }
            }
            "branch skipped" => "Branch was not evaluated.",
            "else selected" => "Fallback branch selected.",
            "set" | "add" | "subtract" | "append" | "count" | "sum" | "initialize field" => {
                "Recorded state change; before and after values are shown below."
            }
            "append item" => {
                "Appended the recorded item at the zero-based index; existing items were unchanged."
            }
            "enter collection" => "Started collection traversal with fixed membership.",
            "collection item" => "Bound the next collection item.",
            "collection selection" => {
                if event.value["selected"] == true {
                    "Item selected for the body."
                } else {
                    "Item did not satisfy the filter."
                }
            }
            "leave collection" if event.value["exit"] == "return" => {
                "Collection traversal exited after a return."
            }
            "leave collection" => "Collection traversal completed.",
            "rounded division" => {
                "Divided exact operands using the explicitly selected decimal scale and rounding mode; the result is shown below."
            }
            "sum item" => "Added this item's numeric value to the recorded subtotal.",
            "initialize" => "Initialized a state value.",
            "table row" => {
                "Evaluated this setup row and checked its record contract before adding it to the collection."
            }
            "example row" => "Selected these source values for this scenario example.",
            "assert" => {
                if event.value == true {
                    "Assertion passed."
                } else {
                    "Assertion failed."
                }
            }
            "enter behavior" => "Entered behavior with the recorded arguments.",
            "argument value" => {
                "Value satisfied the parameter contract; copied it into local state for this call."
            }
            "leave behavior" => "Behavior completed.",
            "return" => "Value satisfied its return contract; exited this behavior.",
            "enter request" => "Entered request.",
            "leave request" => "Request completed.",
            "output contract" => "Output value satisfied its contract.",
            "print" => "Appended a value to captured output.",
            "assert prints" if event.value["matched"] == true => {
                "Captured output matched the expected sequence."
            }
            "assert prints" => "Captured output differed from the expected sequence.",
            "assert failure" if event.value["matched"] == true => {
                "Action failed with the expected code; the scenario can continue."
            }
            "assert failure" => "Action did not fail with the expected code.",
            "pass" => "Explicit no-op.",
            _ if event.operation.starts_with("read ") => "Read the recorded state value.",
            _ => "Evaluated expression to the recorded value.",
        };
        let definition = if matches!(event.operation.as_str(), "enter behavior" | "enter request") {
            let span: Span =
                serde_json::from_value(event.value["definition"].clone()).map_err(|_| {
                    Diagnostic::new(
                        "evidence_source",
                        "call event has no valid definition span",
                        &event.span,
                    )
                })?;
            Some(excerpt(&span, source)?)
        } else {
            None
        };
        steps.push(EvidenceStep {
            event: event.sequence,
            operation: event.operation.clone(),
            summary: summary.into(),
            source: excerpt(&event.span, source)?,
            operands: event.inputs.clone(),
            value: event.value.clone(),
            skipped: event
                .skipped
                .as_ref()
                .map(|span| excerpt(span, source))
                .transpose()?,
            definition,
            observed_failure: if event.operation == "assert failure"
                && !event.value["actual"].is_null()
            {
                let span: Span = serde_json::from_value(event.value["actual"]["span"].clone())
                    .map_err(|_| {
                        Diagnostic::new(
                            "evidence_source",
                            "expected-failure event has no valid observed failure span",
                            &event.span,
                        )
                    })?;
                Some(excerpt(&span, source)?)
            } else {
                None
            },
        });
    }
    Ok(ExecutionExplanation {
        ok: execution.ok,
        failure: execution
            .diagnostic
            .as_ref()
            .map(|diagnostic| excerpt(&diagnostic.span, source))
            .transpose()?,
        steps,
    })
}
