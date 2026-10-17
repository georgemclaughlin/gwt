//! Experimental GWT native foundation: checked expressions, records, named
//! requests, behaviors, decisions, mutations, and scenarios. The language subset
//! and deliberate semantic differences are documented in docs/native-semantics.md.

mod bundle;
mod cases;
mod editor;
mod editor_completion;
pub use editor_completion::{CompletionItem, EditorCompletion, complete_editor};
mod evaluation;
pub use editor::{EditorCheck, check_editor, check_editor_query};
pub use editor_navigation::{EditorNavigation, EditorQuery, EditorSymbol};
mod editor_navigation;
mod editor_outline;
mod editor_types;
pub use editor_outline::{OutlineSymbol, outline_source};
mod formatter;
pub use formatter::{FormattedSource, format_source};
mod explanation;
mod expression;
mod failure_expectation;
mod migration;
mod print_expectation;
mod profiling;
pub use profiling::{
    EvidenceUsage, ExecutionProfile, LocationUsage, MAX_PROFILE_BYTES, OperationUsage,
};
mod program;
mod program_runtime;
mod program_source;
mod review;
mod scenario_generation;
mod scenario_source;
pub use scenario_generation::{GeneratedScenario, scenario_from_case};
pub mod source;
mod validation;
mod validation_document;
pub use validation_document::{
    MAX_VALIDATION_HTML_BYTES, ValidationDocument, render_validation_html, validate_file_document,
};
mod validation_evidence;
pub use validation_evidence::{
    CallableKind, CallableObservation, ExpectationKind, ExpectationObservation, ExpectationOutcome,
    ExpectationTotals, ValidationEvidence, ValidationWarning,
};
mod input_diagnostics;
mod inspection;
mod literal_types;
mod rounded_division;
pub use inspection::{
    BehaviorInspection, MAX_INSPECTION_BYTES, ParameterInspection, ProgramInspection,
    RequestInspection, ScenarioInspection, TypeInspection,
};
mod type_label;
mod value;
mod version;
mod vocabulary;
pub use bundle::{
    ModuleIdentity, ProgramIdentity, SourceBundle, compile_bundle, compile_file, load_bundle,
};
pub use cases::{
    CaseComparison, Changes, Difference, EngineIdentity, ExecutionCase, MAX_CASE_BYTES,
    MigrationOrigin, Presence, ReplayReport, capture_request, capture_scenario, compare_case,
    engine_identity, replay_case,
};
pub use explanation::{EvidenceStep, ExecutionExplanation, SourceExcerpt, explain_execution};
pub use migration::{
    CaseMigration, CorpusMigration, CorpusMigrationAssessment, CorpusMigrationDecisions,
    MAX_BASELINE_REPLAY_BYTES, MAX_MIGRATION_BYTES, MAX_MIGRATION_DECISION_BYTES,
    MigrationAssessment, MigrationDecision, assess_corpus_migration, assess_migration,
    corpus_integrity, prepare_corpus_migration, prepare_migration, promote_corpus_migration,
    render_corpus_migration_html, render_migration_html,
};
pub use program::{CompiledProgram, compile_program};
pub use program_runtime::{ProgramExecution, ProgramLimits, ScenarioExecution};
pub use review::{
    CaseDecision, Corpus, CorpusEntry, CorpusRegression, CorpusReview, DecisionAssessment,
    DecisionStatus, MAX_CORPUS_BYTES, MAX_DECISIONS_BYTES, RegressionRow, RegressionScope,
    RegressionStatus, RegressionTotals, ReviewDecisions, ReviewIdentity, ReviewRow, ReviewTotals,
    assess_decisions, render_review_html, review_corpus, review_identity, test_corpus,
};
pub use validation::{
    ModuleFormatCheck, ScenarioValidation, ValidationOptions, ValidationPhase, ValidationReport,
    ValidationStatus, validate_bundle, validate_file,
};
pub use version::{NativeVersion, version_info};

use serde_json::Value as Json;
use source::{Diagnostic, Result, Span};
use std::collections::BTreeMap;

pub use evaluation::{Evaluation, Event, Limits};
pub use expression::Expression;
pub use value::Type;

#[derive(Clone, Debug)]
pub struct CompiledExpression {
    expression: Expression,
    inputs: BTreeMap<String, Type>,
}

pub fn compile_expression(
    text: &str,
    file: &str,
    inputs: BTreeMap<String, Type>,
) -> Result<CompiledExpression> {
    compile_expression_at(
        text,
        Span {
            file: file.into(),
            start: 0,
            end: text.len(),
            line: 1,
            column: 1,
        },
        inputs,
    )
}

/// The supplied span anchors an expression within a larger UTF-8 source file.
pub fn compile_expression_at(
    text: &str,
    span: Span,
    inputs: BTreeMap<String, Type>,
) -> Result<CompiledExpression> {
    if span.line == 0
        || span.column == 0
        || span.start.checked_add(text.len()) != Some(span.end)
        || span.column.checked_add(text.chars().count()).is_none()
    {
        return Err(Diagnostic::new(
            "invalid_source_span",
            "source span must cover the exact expression with one-based line and column",
            &span,
        ));
    }
    let mut remaining = expression::MAX_EXPRESSION_NODES;
    let contract = Type::Record(inputs);
    validate_type(&contract, &span, 0, &mut remaining)?;
    let Type::Record(inputs) = contract else {
        unreachable!("root record")
    };
    let expression = expression::compile(text, &span, &inputs)?;
    Ok(CompiledExpression { expression, inputs })
}

impl CompiledExpression {
    pub fn expression(&self) -> &Expression {
        &self.expression
    }

    /// Inputs are normalized once against the complete contract. Each call has
    /// independent values, budgets, and evidence; the checked tree is reusable.
    pub fn evaluate(&self, inputs: &Json, limits: Limits) -> Result<Evaluation> {
        validate_input_shape(inputs, self.expression.span())?;
        if serde_json::to_vec(inputs).map_or(true, |v| v.len() > 1_048_576) {
            return Err(Diagnostic::new(
                "input_limit",
                "input JSON exceeds one MiB",
                self.expression.span(),
            ));
        }
        let value::Value::Record(values) = value::normalize(
            &Type::Record(self.inputs.clone()),
            Some(inputs),
            self.expression.span(),
        )?
        else {
            unreachable!("root contract is a record")
        };
        let slots: Vec<_> = values.into_values().collect();
        Ok(evaluation::evaluate(&self.expression, &slots, limits))
    }
}

fn validate_input_shape(input: &Json, span: &Span) -> Result<()> {
    let mut stack = vec![(input, 0)];
    let mut nodes = 0;
    let mut text_bytes: usize = 0;
    while let Some((value, depth)) = stack.pop() {
        nodes += 1;
        if nodes > value::MAX_VALUE_NODES || depth > value::MAX_VALUE_DEPTH {
            return Err(Diagnostic::new(
                "input_limit",
                "input exceeds nesting or value-count limit",
                span,
            ));
        }
        match value {
            Json::Array(items) => {
                if items.len() > value::MAX_VALUE_NODES {
                    return Err(Diagnostic::new(
                        "input_limit",
                        "input array exceeds the value-count limit",
                        span,
                    ));
                }
                stack.extend(items.iter().map(|item| (item, depth + 1)));
            }
            Json::Object(fields) => {
                if fields.len() > value::MAX_VALUE_NODES {
                    return Err(Diagnostic::new(
                        "input_limit",
                        "input record exceeds the value-count limit",
                        span,
                    ));
                }
                for (key, item) in fields {
                    text_bytes = text_bytes.saturating_add(key.len());
                    stack.push((item, depth + 1));
                }
            }
            Json::String(text) => text_bytes = text_bytes.saturating_add(text.len()),
            _ => {}
        }
        if text_bytes > 1_048_576 {
            return Err(Diagnostic::new(
                "input_limit",
                "input text exceeds one MiB",
                span,
            ));
        }
    }
    Ok(())
}

fn validate_type(ty: &Type, span: &Span, depth: usize, remaining: &mut usize) -> Result<()> {
    if depth > value::MAX_VALUE_DEPTH || *remaining == 0 {
        return Err(Diagnostic::new(
            "type_limit",
            "type contract exceeds nesting or node limit",
            span,
        ));
    }
    *remaining -= 1;
    match ty {
        Type::IntegerUnion(_) | Type::DecimalUnion(_) | Type::BooleanUnion(_) => {
            crate::literal_types::validate(ty, span)?;
        }
        Type::TextUnion(values) => {
            let unique: std::collections::BTreeSet<_> = values.iter().collect();
            if values.is_empty() || unique.len() != values.len() {
                return Err(Diagnostic::new(
                    "invalid_type",
                    "text union must contain distinct values",
                    span,
                ));
            }
        }
        Type::Record(fields) => validate_fields(fields, span, depth, remaining)?,
        Type::List(inner) | Type::Optional(inner) => {
            validate_type(inner, span, depth + 1, remaining)?
        }
        Type::OneOf(kinds) => {
            if kinds.is_empty() {
                return Err(Diagnostic::new(
                    "invalid_type",
                    "one-of record requires at least one kind",
                    span,
                ));
            }
            for (name, fields) in kinds {
                program_source::name(name, span)?;
                if fields.is_empty() || fields.contains_key("kind") {
                    return Err(Diagnostic::new(
                        "invalid_type",
                        "one-of kinds require fields and cannot declare the automatic 'kind' field",
                        span,
                    ));
                }
                if *remaining == 0 {
                    return Err(Diagnostic::new(
                        "type_limit",
                        "one-of contract exceeds node limit",
                        span,
                    ));
                }
                *remaining -= 1;
                validate_fields(fields, span, depth, remaining)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn validate_fields(
    fields: &BTreeMap<String, Type>,
    span: &Span,
    depth: usize,
    remaining: &mut usize,
) -> Result<()> {
    for (name, field) in fields {
        let mut chars = name.chars();
        if !chars
            .next()
            .is_some_and(|c| c.is_ascii_alphabetic() || c == '_')
            || !chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
            || matches!(
                name.as_str(),
                "true" | "false" | "not" | "and" | "or" | "is" | "contains" | "present" | "absent"
            )
        {
            return Err(Diagnostic::new(
                "invalid_name",
                format!("invalid or reserved input name '{name}'"),
                span,
            ));
        }
        validate_type(field, span, depth + 1, remaining)?;
    }
    Ok(())
}
