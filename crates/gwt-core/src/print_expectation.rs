//! Exact serialized output expectations, deliberately separate from typed expressions.
use std::collections::BTreeSet;

use serde_json::Value as Json;

use crate::source::{Diagnostic, Result, Span};
use crate::value::{MAX_DIGITS, MAX_VALUE_DEPTH, MAX_VALUE_NODES};

pub(crate) fn parse(text: &str, span: &Span) -> Result<Vec<Json>> {
    let syntax = || {
        Diagnostic::new(
            "print_expectation",
            "THEN prints requires a JSON array of expected output values",
            span,
        )
    };
    // Preflight before recursive JSON parsing. Scan strings as units so braces,
    // colons, and escaped quotes within text do not affect nesting or key checks.
    // JSON parsing below establishes grammatical validity; this pass additionally
    // prevents silently overwritten duplicate object keys and excessive nesting.
    let bytes = text.as_bytes();
    let mut containers: Vec<Option<BTreeSet<String>>> = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'"' => {
                let start = index;
                index += 1;
                while index < bytes.len() && bytes[index] != b'"' {
                    if bytes[index] == b'\\' {
                        index += 1;
                    }
                    index += 1;
                }
                if index >= bytes.len() {
                    return Err(syntax());
                }
                index += 1;
                let end = index;
                while index < bytes.len() && bytes[index].is_ascii_whitespace() {
                    index += 1;
                }
                if bytes.get(index) == Some(&b':') {
                    let key: String =
                        serde_json::from_str(&text[start..end]).map_err(|_| syntax())?;
                    if let Some(Some(keys)) = containers.last_mut() {
                        if !keys.insert(key) {
                            return Err(Diagnostic::new(
                                "print_expectation",
                                "printed-output expectations cannot contain duplicate object keys",
                                span,
                            ));
                        }
                    }
                }
                continue;
            }
            b'[' | b'{' => {
                containers.push((bytes[index] == b'{').then(BTreeSet::new));
                // One extra level is the output sequence, not an emitted value.
                if containers.len() > MAX_VALUE_DEPTH + 1 {
                    return Err(Diagnostic::new(
                        "print_expectation_limit",
                        "printed-output expectation exceeds depth 64",
                        span,
                    ));
                }
            }
            b']' | b'}' => {
                containers.pop();
            }
            _ => (),
        }
        index += 1;
    }
    let value: Json = serde_json::from_str(text).map_err(|_| syntax())?;
    let Json::Array(values) = value else {
        return Err(syntax());
    };
    let mut pending: Vec<_> = values.iter().map(|value| (value, 1)).collect();
    let mut count = 0;
    while let Some((value, depth)) = pending.pop() {
        count += 1;
        if count > MAX_VALUE_NODES || depth > MAX_VALUE_DEPTH {
            return Err(Diagnostic::new(
                "print_expectation_limit",
                "printed-output expectation exceeds 16384 values or depth 64",
                span,
            ));
        }
        match value {
            Json::Array(items) => pending.extend(items.iter().map(|value| (value, depth + 1))),
            Json::Object(fields) => pending.extend(fields.values().map(|value| (value, depth + 1))),
            Json::Number(number) => {
                let literal = number.to_string();
                if literal.contains(['.', 'e', 'E'])
                    || literal.trim_start_matches('-').len() > MAX_DIGITS
                {
                    return Err(Diagnostic::new(
                        "print_expectation_number",
                        "printed integers have at most 512 digits; printed decimals use exact JSON strings",
                        span,
                    ));
                }
            }
            _ => (),
        }
    }
    Ok(values)
}
