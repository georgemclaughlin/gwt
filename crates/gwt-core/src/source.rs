use serde::{Deserialize, Serialize};

/// UTF-8 byte offsets are half-open; human line and column numbers start at one.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Span {
    pub file: String,
    pub start: usize,
    pub end: usize,
    pub line: usize,
    pub column: usize,
}

impl Span {
    pub fn within(&self, text: &str, start: usize, end: usize) -> Self {
        Self {
            file: self.file.clone(),
            start: self.start + start,
            end: self.start + end,
            line: self.line,
            column: self.column + text[..start].chars().count(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Diagnostic {
    pub code: String,
    pub message: String,
    pub span: Span,
}

impl Diagnostic {
    pub fn new(code: &str, message: impl Into<String>, span: &Span) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            span: span.clone(),
        }
    }
}

impl std::fmt::Display for Diagnostic {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "{}:{}:{}: {}: {}",
            self.span.file, self.span.line, self.span.column, self.code, self.message
        )
    }
}

impl std::error::Error for Diagnostic {}
pub type Result<T> = std::result::Result<T, Diagnostic>;
