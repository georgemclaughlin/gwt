//! Fresh declaration completions, without executing or claiming to type-check edits.
use crate::{
    EditorQuery,
    bundle::load_editor_bundle,
    program_source::{self, Node},
    source::{Diagnostic, Span},
};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, path::Path};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CompletionItem {
    pub kind: &'static str,
    pub label: String,
    /// Plain source spelling. Angle-bracket parameters become editor tab stops.
    pub insert_text: String,
    pub detail: String,
    pub returns_value: bool,
    pub definition: Option<Span>,
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EditorCompletion {
    pub kind: &'static str,
    pub schema_version: u32,
    pub ok: bool,
    pub basis: &'static str,
    pub items: Vec<CompletionItem>,
    pub replacement: Option<Span>,
    pub truncated: bool,
    pub checked_sources: BTreeMap<String, String>,
    pub diagnostic: Option<Diagnostic>,
}

fn identifier(text: &str) -> bool {
    let span = Span {
        file: String::new(),
        start: 0,
        end: 0,
        line: 1,
        column: 1,
    };
    program_source::name(text, &span).is_ok()
}
fn word(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'_'
}

struct Context<'a> {
    kind: &'static str,
    returns_only: bool,
    prefix: &'a str,
    replacement: Span,
}

fn context<'a>(text: &'a str, query: &EditorQuery, nodes: &[Node]) -> Option<Context<'a>> {
    let at = query.byte_offset;
    let start = text[..at].rfind('\n').map_or(0, |n| n + 1);
    let end = text[at..].find(['\r', '\n']).map_or(text.len(), |n| at + n);
    let line = &text[start..end];
    let cursor = at - start;
    // No suggestions inside comments or quoted strings, including escaped quotes.
    let mut quoted = false;
    let mut escaped = false;
    for c in line[..cursor].chars() {
        if quoted && escaped {
            escaped = false;
            continue;
        }
        if quoted && c == '\\' {
            escaped = true;
            continue;
        }
        if c == '"' {
            quoted = !quoted;
        }
        if c == '#' && !quoted {
            return None;
        }
    }
    if quoted {
        return None;
    }
    let indent = line.len() - line.trim_start_matches(' ').len();
    if cursor < indent {
        return None;
    }
    let before = &line[indent..cursor];
    let owner = nodes.iter().rev().find(|n| n.span.start <= start + indent);
    let inside_behavior = indent > 0 && owner.is_some_and(|n| n.text.starts_with("WHEN "));
    let inside_record = indent > 0 && owner.is_some_and(|n| n.text.starts_with("RECORD "));
    let annotation = if let Some(tail) = before.strip_prefix("THEN returns ") {
        Some(tail)
    } else if ["GIVEN ", "AND ", "OUTPUT ", "TYPE "]
        .iter()
        .any(|p| before.starts_with(p))
    {
        before.split_once(" is ").map(|(_, tail)| tail)
    } else if inside_record {
        before.split_once(':').map(|(_, tail)| tail.trim_start())
    } else {
        None
    };
    let (kind, prefix, from) = if let Some(annotation) = annotation {
        // Recognize only a type-name position, optionally nested in known containers.
        let mut remaining = annotation;
        while let Some(tail) = remaining
            .strip_prefix("list<")
            .or_else(|| remaining.strip_prefix("optional<"))
        {
            remaining = tail;
        }
        if !remaining.bytes().all(word) {
            return None;
        }
        ("type", remaining, cursor - remaining.len())
    } else {
        let tail = if let Some(tail) = before.strip_prefix("REQUEST ") {
            if indent != 0 {
                return None;
            }
            ("request", tail)
        } else {
            let tail = if let Some(tail) = before.strip_prefix("WHEN ") {
                if inside_behavior {
                    return None;
                } // DECIDE arm condition, not a call.
                // A header with an existing body is a declaration, not a call.
                if indent == 0
                    && owner.is_some_and(|n| n.span.start == start && !n.children.is_empty())
                {
                    return None;
                }
                tail
            } else if inside_behavior {
                before
            } else {
                return None;
            };
            let tail = if let Some(local) = tail.strip_prefix("LET ") {
                let (name, value) = local.split_once(" be ")?;
                if !identifier(name) {
                    return None;
                }
                value
            } else {
                tail
            };
            if tail.split_whitespace().next().is_some_and(|w| {
                ["GIVEN", "AND", "THEN", "OUTPUT"].contains(&w)
                    || crate::vocabulary::statement_head(w)
            }) {
                return None;
            }
            ("behavior", tail)
        };
        if tail.1.contains(['<', '>', '"', '(', ')', '[', ']', '#']) {
            return None;
        }
        (tail.0, tail.1, cursor - tail.1.len())
    };
    let mut until = cursor;
    while until < line.len() && word(line.as_bytes()[until]) {
        until += 1;
    }
    if kind != "type" {
        let rest = line[until..].trim_start();
        if !rest.is_empty() && !rest.starts_with('#') {
            return None;
        }
    }
    Some(Context {
        kind,
        returns_only: before.starts_with("LET ") || before.starts_with("WHEN LET "),
        prefix,
        replacement: Span {
            file: query.path.clone(),
            start: start + from,
            end: start + until,
            line: text[..start].bytes().filter(|b| *b == b'\n').count() + 1,
            column: line[..from].chars().count() + 1,
        },
    })
}

fn declaration(node: &Node) -> Option<(String, CompletionItem)> {
    let (word, rest) = node.text.split_once(' ')?;
    let rest = rest.trim();
    let (kind, label, key) = match word {
        "TYPE" | "RECORD" => {
            let name = rest.split_whitespace().next()?;
            if !identifier(name) {
                return None;
            }
            ("type", name.to_owned(), format!("type:{name}"))
        }
        "WHEN" if !node.children.is_empty() => {
            let mut canonical = Vec::new();
            let mut parameters = Vec::new();
            for token in rest.split_whitespace() {
                if let Some(name) = token.strip_prefix('<').and_then(|t| t.strip_suffix('>')) {
                    if !identifier(name) || parameters.contains(&name) {
                        return None;
                    }
                    parameters.push(name);
                    canonical.push("<parameter>");
                } else {
                    if token.contains(['<', '>', '"', '(', ')', '[', ']']) {
                        return None;
                    }
                    canonical.push(token);
                }
            }
            if canonical.is_empty()
                || canonical[0] == "<parameter>"
                || crate::vocabulary::reserved_behavior(canonical[0])
            {
                return None;
            }
            (
                "behavior",
                rest.split_whitespace().collect::<Vec<_>>().join(" "),
                format!("behavior:{}", canonical.join(" ")),
            )
        }
        "REQUEST" if !node.children.is_empty() => {
            ("request", rest.to_owned(), format!("request:{rest}"))
        }
        _ => return None,
    };
    // Do not transmit bodies or unlimited documentation. Source is plain text.
    let mut detail = format!("Declared {kind} in {}\n{}", node.span.file, node.text);
    for child in &node.children {
        if ["GIVEN ", "AND ", "THEN returns ", "OUTPUT "]
            .iter()
            .any(|p| child.text.starts_with(p))
        {
            if detail.len() + child.text.len() + 1 > 4096 {
                break;
            }
            detail.push('\n');
            detail.push_str(&child.text);
        }
    }
    if label.len() > 1024 || detail.len() > 4096 {
        return None;
    }
    Some((
        key,
        CompletionItem {
            kind,
            insert_text: label.clone(),
            label,
            detail,
            returns_value: kind == "behavior"
                && node
                    .children
                    .iter()
                    .any(|n| n.text.starts_with("THEN returns ")),
            definition: Some(node.span.clone()),
        },
    ))
}

pub fn complete_editor(
    entry: &Path,
    root: Option<&Path>,
    overlays: &BTreeMap<String, String>,
    query: &EditorQuery,
) -> EditorCompletion {
    let mut observed = BTreeMap::new();
    let mut report = EditorCompletion {
        kind: "gwt.native-completion",
        schema_version: 1,
        ok: false,
        basis: "declarations",
        items: Vec::new(),
        replacement: None,
        truncated: false,
        checked_sources: BTreeMap::new(),
        diagnostic: None,
    };
    let result = (|| {
        let bundle = load_editor_bundle(entry, root, overlays, Some(&mut observed))?;
        let site = Span {
            file: query.path.clone(),
            start: 0,
            end: 0,
            line: 1,
            column: 1,
        };
        let source = bundle
            .modules
            .get(&query.path)
            .filter(|s| s.is_char_boundary(query.byte_offset))
            .ok_or_else(|| {
                Diagnostic::new(
                    "editor_query",
                    "query must name a loaded module and a valid UTF-8 byte offset",
                    &site,
                )
            })?;
        let nodes = program_source::parse(source, &query.path)?;
        let Some(context) = context(source, query, &nodes) else {
            return Ok(());
        };
        report.replacement = Some(context.replacement);
        // Duplicate declaration keys are ambiguous, even when parameter names differ.
        let mut candidates: BTreeMap<String, Option<CompletionItem>> = BTreeMap::new();
        for (path, source) in &bundle.modules {
            for node in program_source::parse(source, path)? {
                if let Some((key, item)) = declaration(&node) {
                    candidates
                        .entry(key)
                        .and_modify(|item| *item = None)
                        .or_insert(Some(item));
                }
            }
        }
        if context.kind == "type" {
            for name in crate::vocabulary::primitive_types() {
                candidates
                    .entry(format!("type:{name}"))
                    .and_modify(|item| *item = None)
                    .or_insert(Some(CompletionItem {
                        kind: "type",
                        label: name.into(),
                        insert_text: name.into(),
                        detail: "Native built-in type".into(),
                        returns_value: false,
                        definition: None,
                    }));
            }
        }
        for item in candidates.into_values().flatten() {
            if item.kind == context.kind
                && item.label.starts_with(context.prefix)
                && (!context.returns_only || item.returns_value)
            {
                if report.items.len() == 128 {
                    report.truncated = true;
                    break;
                }
                report.items.push(item);
            }
        }
        Ok(())
    })();
    report.checked_sources = observed
        .iter()
        .map(|(p, s)| {
            (
                p.clone(),
                format!("sha256:{:x}", Sha256::digest(s.as_bytes())),
            )
        })
        .collect();
    match result {
        Ok(()) => report.ok = true,
        Err(error) => report.diagnostic = Some(error),
    }
    report
}
