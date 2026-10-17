//! An immutable validation report paired with the exact source it checked.
use crate::source::{Diagnostic, Result, Span};
use crate::{
    SourceBundle, ValidationOptions, ValidationReport, engine_identity, load_bundle,
    validate_bundle,
};
use serde::Serialize;
use std::{io::Write, path::Path};

pub const MAX_VALIDATION_HTML_BYTES: usize = 64 * 1_048_576;

/// Construct through validation, rather than attaching a report to arbitrary
/// current files. Neither rendering nor report access reloads or executes source.
pub struct ValidationDocument {
    report: ValidationReport,
    source: Option<SourceBundle>,
}

impl ValidationDocument {
    pub fn from_bundle(source: SourceBundle, options: ValidationOptions) -> Self {
        let report = validate_bundle(&source, options);
        // Even rejected in-memory input must not expand the presentation without
        // bound. Ordinary file loading already applies the native source bounds.
        let retain = source.modules.len() <= 256
            && source.entry.len() <= 4096
            && source
                .modules
                .iter()
                .all(|(path, text)| path.len() <= 4096 && text.len() <= 1_048_576)
            && source.modules.values().map(String::len).sum::<usize>() <= 4 * 1_048_576;
        Self {
            report,
            source: retain.then_some(source),
        }
    }

    pub fn report(&self) -> &ValidationReport {
        &self.report
    }
    pub fn source(&self) -> Option<&SourceBundle> {
        self.source.as_ref()
    }
    pub fn into_report(self) -> ValidationReport {
        self.report
    }
}

pub fn validate_file_document(
    entry: &Path,
    root: Option<&Path>,
    options: ValidationOptions,
) -> ValidationDocument {
    match load_bundle(entry, root) {
        Ok(source) => ValidationDocument::from_bundle(source, options),
        Err(error) => ValidationDocument {
            report: ValidationReport::load_failure(error, options),
            source: None,
        },
    }
}

struct HtmlBuffer {
    bytes: Vec<u8>,
    maximum: usize,
}
impl HtmlBuffer {
    fn raw(&mut self, text: &str) -> std::io::Result<()> {
        if text.len() > self.maximum.saturating_sub(self.bytes.len()) {
            return Err(std::io::Error::other(
                "validation HTML exceeds its byte limit",
            ));
        }
        self.bytes.extend_from_slice(text.as_bytes());
        Ok(())
    }
    fn json(&mut self, value: &impl Serialize) -> std::io::Result<()> {
        serde_json::to_writer(self, value).map_err(std::io::Error::other)
    }
}
impl Write for HtmlBuffer {
    // Escape while serializing, so neither a closing script tag nor an oversized
    // intermediate JSON string can escape the presentation's limits.
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        let extra = bytes
            .iter()
            .filter(|byte| matches!(byte, b'<' | b'>' | b'&'))
            .count()
            * 5;
        if bytes.len().saturating_add(extra) > self.maximum.saturating_sub(self.bytes.len()) {
            return Err(std::io::Error::other(
                "validation HTML exceeds its byte limit",
            ));
        }
        for byte in bytes {
            match byte {
                b'<' => self.bytes.extend_from_slice(b"\\u003c"),
                b'>' => self.bytes.extend_from_slice(b"\\u003e"),
                b'&' => self.bytes.extend_from_slice(b"\\u0026"),
                _ => self.bytes.push(*byte),
            }
        }
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

/// Self-contained, read-only HTML. Full traces and approval controls are outside
/// this report. JSON downloads retain the original exact native numeric tokens.
pub fn render_validation_html(document: &ValidationDocument) -> Result<String> {
    let mut html = HtmlBuffer {
        bytes: Vec::new(),
        maximum: MAX_VALIDATION_HTML_BYTES,
    };
    let mut render = || -> std::io::Result<()> {
        html.raw(include_str!("validation_view/page.html"))?;
        html.raw("<style>")?;
        html.raw(include_str!("validation_view/style.css"))?;
        html.raw("</style><script type=application/json id=validation-data>")?;
        html.json(document.report())?;
        html.raw("</script><script type=application/json id=source-data>")?;
        html.json(&document.source())?;
        html.raw("</script><script type=application/json id=metadata-data>")?;
        html.json(&serde_json::json!({
            "engine": engine_identity(),
            "limitsText": serde_json::to_string_pretty(&document.report.limits).expect("limits JSON"),
        }))?;
        html.raw("</script><script>")?;
        html.raw(include_str!("validation_view/view.js"))?;
        html.raw("</script></body></html>")
    };
    render().map_err(|error| {
        Diagnostic::new(
            "validation_report_limit",
            error.to_string(),
            &Span {
                file: document
                    .source
                    .as_ref()
                    .map_or("<validation>".into(), |source| source.entry.clone()),
                start: 0,
                end: 0,
                line: 1,
                column: 1,
            },
        )
    })?;
    Ok(String::from_utf8(html.bytes).expect("UTF-8 source and JSON"))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn escaped_json_is_bounded_during_serialization_and_preserves_unicode() {
        let mut html = HtmlBuffer {
            bytes: Vec::new(),
            maximum: 20,
        };
        html.json(&"😀<&").unwrap();
        assert_eq!(
            serde_json::from_slice::<String>(&html.bytes).unwrap(),
            "😀<&"
        );
        assert!(!html.bytes.contains(&b'<'));
        assert_eq!(html.bytes.len(), 18);
        assert!(html.raw("too long").is_err());
        assert_eq!(html.bytes.len(), 18);
        assert!(html.write(b"<").is_err());
        assert_eq!(html.bytes.len(), 18);
    }
}
