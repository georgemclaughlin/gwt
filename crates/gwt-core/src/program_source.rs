use crate::source::{Diagnostic, Result, Span};

pub(crate) const MAX_PROGRAM_BYTES: usize = 1_048_576;
pub(crate) const MAX_PROGRAM_NODES: usize = 16_384;

#[derive(Clone, Debug)]
pub(crate) struct Node {
    pub text: String,
    pub span: Span,
    pub children: Vec<Node>,
}

impl Node {
    pub fn error(&self, code: &str, message: impl Into<String>) -> Diagnostic {
        Diagnostic::new(code, message, &self.span)
    }
    pub fn tail(&self, prefix: usize) -> Result<(&str, Span)> {
        let text = self.text[prefix..].trim_start();
        if text.is_empty() {
            return Err(self.error("missing_operand", "expected an operand"));
        }
        let start = self.text.len() - text.len();
        Ok((text, self.span.within(&self.text, start, self.text.len())))
    }
    pub fn leaf(&self) -> Result<()> {
        if self.children.is_empty() {
            Ok(())
        } else {
            Err(self.error(
                "unexpected_block",
                "this statement does not accept an indented block",
            ))
        }
    }
}

pub(crate) fn parse(source: &str, file: &str) -> Result<Vec<Node>> {
    let origin = Span {
        file: file.into(),
        start: 0,
        end: 0,
        line: 1,
        column: 1,
    };
    if source.len() > MAX_PROGRAM_BYTES {
        return Err(Diagnostic::new(
            "source_limit",
            "program source exceeds one MiB",
            &origin,
        ));
    }
    let mut lines = Vec::new();
    let mut offset = 0;
    for (index, raw) in source.split_inclusive('\n').enumerate() {
        let line = raw.trim_end_matches(['\n', '\r']);
        let indent = line.bytes().take_while(|c| *c == b' ').count();
        let content = strip_comment(&line[indent..]).trim_end();
        if !content.is_empty() {
            let span = Span {
                file: file.into(),
                start: offset + indent,
                end: offset + indent + content.len(),
                line: index + 1,
                column: indent + 1,
            };
            if content.starts_with('\t') || indent % 2 != 0 {
                return Err(Diagnostic::new(
                    "indentation",
                    "indentation must use two spaces per level",
                    &span,
                ));
            }
            if indent > 128 {
                return Err(Diagnostic::new(
                    "source_limit",
                    "block nesting exceeds 64",
                    &span,
                ));
            }
            lines.push((
                indent,
                Node {
                    text: content.into(),
                    span,
                    children: Vec::new(),
                },
            ));
            if lines.len() > MAX_PROGRAM_NODES {
                return Err(Diagnostic::new(
                    "source_limit",
                    "program exceeds the source-node limit",
                    &origin,
                ));
            }
        }
        offset += raw.len();
    }
    let mut pos = 0;
    let result = block(&lines, &mut pos, 0)?;
    if result.is_empty() {
        return Err(Diagnostic::new(
            "empty_program",
            "program has no statements or declarations",
            &origin,
        ));
    }
    Ok(result)
}

fn block(lines: &[(usize, Node)], pos: &mut usize, indent: usize) -> Result<Vec<Node>> {
    let mut result = Vec::new();
    while let Some((actual, line)) = lines.get(*pos) {
        if *actual < indent {
            break;
        }
        if *actual != indent {
            return Err(line.error("indentation", "unexpected indentation level"));
        }
        let mut node = line.clone();
        *pos += 1;
        if lines.get(*pos).is_some_and(|(next, _)| *next > indent) {
            node.children = block(lines, pos, indent + 2)?;
        }
        result.push(node);
    }
    Ok(result)
}

pub(crate) fn strip_comment(text: &str) -> &str {
    let mut quoted = false;
    let mut escaped = false;
    for (index, ch) in text.char_indices() {
        if ch == '"' && !escaped {
            quoted = !quoted;
        }
        if ch == '#' && !quoted {
            return &text[..index];
        }
        escaped = ch == '\\' && !escaped;
    }
    text
}

pub(crate) fn name(text: &str, span: &Span) -> Result<String> {
    let mut chars = text.chars();
    if !chars
        .next()
        .is_some_and(|c| c.is_ascii_alphabetic() || c == '_')
        || !chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
    {
        return Err(Diagnostic::new(
            "invalid_name",
            format!("expected an identifier, got '{text}'"),
            span,
        ));
    }
    if matches!(
        text,
        "true" | "false" | "not" | "and" | "or" | "is" | "contains" | "present" | "absent"
    ) {
        return Err(Diagnostic::new(
            "invalid_name",
            format!("'{text}' is reserved"),
            span,
        ));
    }
    Ok(text.into())
}

/// Split type unions without treating a quoted pipe as a delimiter.
pub(crate) fn union_parts(text: &str) -> Vec<&str> {
    let mut parts = Vec::new();
    let mut start = 0;
    let mut quote = false;
    let mut escape = false;
    let mut depth = 0;
    for (index, ch) in text.char_indices() {
        if ch == '"' && !escape {
            quote = !quote;
        }
        if !quote {
            if ch == '<' {
                depth += 1;
            }
            if ch == '>' {
                depth -= 1;
            }
            if ch == '|' && depth == 0 {
                parts.push(text[start..index].trim());
                start = index + 1;
            }
        }
        escape = ch == '\\' && !escape;
    }
    parts.push(text[start..].trim());
    parts
}

/// Find a step separator outside quoted text and nested expressions.
pub(crate) fn split_step<'a>(text: &'a str, separator: &str) -> Option<(&'a str, &'a str)> {
    let mut quoted = false;
    let mut escaped = false;
    let mut depth = 0_i32;
    for (index, ch) in text.char_indices() {
        if !quoted && depth == 0 && text[index..].starts_with(separator) {
            return Some((&text[..index], &text[index + separator.len()..]));
        }
        if ch == '"' && !escaped {
            quoted = !quoted;
        }
        if !quoted {
            match ch {
                '[' | '(' => depth += 1,
                ']' | ')' => depth -= 1,
                _ => (),
            }
        }
        escaped = ch == '\\' && !escaped;
    }
    None
}

/// Split a call at whitespace outside JSON strings, lists and grouped expressions.
/// Keep exact text and UTF-8 spans; quoting never turns a literal into a name.
pub(crate) fn call_words<'a>(text: &'a str, span: &Span) -> Result<Vec<(&'a str, Span)>> {
    let mut words = Vec::new();
    let mut start = None;
    let mut quoted = false;
    let mut escaped = false;
    let mut groups = Vec::new();
    for (index, ch) in text.char_indices() {
        if !quoted && groups.is_empty() && ch.is_whitespace() {
            if let Some(begin) = start.take() {
                words.push((&text[begin..index], span.within(text, begin, index)));
            }
            continue;
        }
        start.get_or_insert(index);
        if ch == '"' && !escaped {
            quoted = !quoted;
        } else if !quoted {
            match ch {
                '(' | '[' => {
                    groups.push(ch);
                    if groups.len() > crate::expression::MAX_EXPRESSION_DEPTH {
                        return Err(Diagnostic::new(
                            "expression_limit",
                            "call argument nesting exceeds 64",
                            &span.within(text, index, index + 1),
                        ));
                    }
                }
                ')' | ']' => {
                    let expected = if ch == ')' { '(' } else { '[' };
                    let actual = groups.pop();
                    if actual != Some(expected) {
                        return Err(Diagnostic::new(
                            "argument_syntax",
                            "mismatched argument delimiter",
                            &span.within(text, index, index + 1),
                        ));
                    }
                }
                _ => (),
            }
        }
        escaped = quoted && ch == '\\' && !escaped;
    }
    if quoted || !groups.is_empty() {
        return Err(Diagnostic::new(
            "argument_syntax",
            "unterminated string or grouped argument",
            span,
        ));
    }
    if let Some(begin) = start {
        words.push((&text[begin..], span.within(text, begin, text.len())));
    }
    Ok(words)
}
