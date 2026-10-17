//! Explanations of the existing input contract; never input coercion.
use crate::{
    source::{Diagnostic, Span},
    type_label::contract_label,
    value::Type,
};
use serde_json::Value as Json;

fn json_kind(value: Option<&Json>) -> &'static str {
    match value {
        None => "missing value",
        Some(Json::Null) => "JSON null",
        Some(Json::Bool(_)) => "JSON boolean",
        Some(Json::Number(_)) => "JSON number",
        Some(Json::String(_)) => "JSON string",
        Some(Json::Array(_)) => "JSON array",
        Some(Json::Object(_)) => "JSON object",
    }
}

fn quoted_name(name: &str) -> String {
    let mut short: String = name.chars().take(128).collect();
    if name.chars().nth(128).is_some() {
        short.push('…');
    }
    serde_json::to_string(&short).expect("name JSON")
}

pub(crate) fn mismatch(ty: &Type, value: &Json, span: &Span) -> Diagnostic {
    let hint = if ty.decimal() {
        "; decimal inputs use quoted base-10 text or a JSON integer"
    } else {
        ""
    };
    Diagnostic::new(
        "input_type",
        format!(
            "expected {}; found {}{hint}",
            contract_label(ty),
            json_kind(Some(value))
        ),
        span,
    )
}

pub(crate) fn missing(ty: &Type, span: &Span) -> Diagnostic {
    Diagnostic::new(
        "missing_input",
        format!("required input is missing; expected {}", contract_label(ty)),
        span,
    )
}

pub(crate) fn missing_kind(value: Option<&Json>, span: &Span) -> Diagnostic {
    Diagnostic::new(
        "one_of_kind",
        format!(
            "one-of record requires a text field 'kind'; found {}",
            json_kind(value)
        ),
        span,
    )
}

pub(crate) fn unknown_kind(kind: &str, ty: &Type, span: &Span) -> Diagnostic {
    let Type::OneOf(kinds) = ty else {
        unreachable!("one-of input contract")
    };
    let expected = contract_label(&Type::TextUnion(kinds.keys().cloned().collect()));
    Diagnostic::new(
        "one_of_kind",
        format!(
            "unknown one-of kind {}; expected {expected}",
            quoted_name(kind)
        ),
        span,
    )
}

pub(crate) fn unknown_field(key: &str, span: &Span) -> Diagnostic {
    Diagnostic::new(
        "unknown_input",
        format!("field {} is outside the record contract", quoted_name(key)),
        span,
    )
}
