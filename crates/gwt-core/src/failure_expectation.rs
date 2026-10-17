//! Scenario assertions may expect defined behavior failures, never engine/resource failures.
use crate::source::{Diagnostic, Result, Span};

pub(crate) fn supported(code: &str) -> bool {
    matches!(
        code,
        "assertion_failed" | "division_by_zero" | "nonterminating_decimal"
    )
}

pub(crate) fn parse(text: &str, span: &Span) -> Result<String> {
    let code: String = serde_json::from_str(text).map_err(|_| {
        Diagnostic::new(
            "failure_expectation",
            "THEN fails with requires a quoted failure code",
            span,
        )
    })?;
    if !supported(&code) {
        return Err(Diagnostic::new(
            "failure_expectation_code",
            "expected failure must be assertion_failed, division_by_zero, or nonterminating_decimal; resource and engine failures cannot satisfy a scenario",
            span,
        ));
    }
    Ok(code)
}
