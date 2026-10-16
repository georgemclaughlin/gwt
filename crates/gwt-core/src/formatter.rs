//! Layout formatting without executing source or resolving external contracts.
use crate::{
    program_source::{self, MAX_PROGRAM_BYTES, MAX_PROGRAM_NODES, Node},
    scenario_source,
    source::{Diagnostic, Result, Span},
};

#[derive(Debug)]
pub struct FormattedSource {
    pub text: String,
    pub changed: bool,
}

struct Line {
    text: String,
    indent: usize,
    comment: Option<String>,
    cells: Option<Vec<String>>,
    span: Span,
}

fn normalize_statement(text: &str) -> String {
    // Field names may also be keywords. A field declaration takes precedence.
    if let Some((name, value)) = text.split_once(':') {
        let name = name.trim_end();
        if !name.is_empty()
            && name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
        {
            let value = value.trim();
            return if value.is_empty() {
                format!("{name}:")
            } else {
                format!("{name}: {value}")
            };
        }
    }
    let (word, rest) = text.split_once(char::is_whitespace).unwrap_or((text, ""));
    if matches!(
        word,
        "PROGRAM"
            | "USE"
            | "TYPE"
            | "RECORD"
            | "REQUEST"
            | "OUTPUT"
            | "BACKGROUND"
            | "SCENARIO"
            | "EXAMPLES"
            | "GIVEN"
            | "WHEN"
            | "THEN"
            | "AND"
            | "LET"
            | "REQUIRE"
            | "IF"
            | "ELSE"
            | "FOR"
            | "FIND"
            | "DECIDE"
            | "RETURN"
            | "PASS"
            | "set"
            | "add"
            | "subtract"
            | "append"
            | "count"
            | "sum"
            | "divide"
            | "print"
    ) {
        let rest = rest.trim();
        // Only normalize a built-in verb after WHEN, never a domain phrase.
        let rest = if word == "WHEN" {
            let first = rest.split_whitespace().next().unwrap_or("");
            if matches!(
                first,
                "set" | "add" | "subtract" | "append" | "count" | "sum" | "divide" | "print"
            ) {
                normalize_statement(rest)
            } else {
                rest.into()
            }
        } else {
            rest.into()
        };
        if rest.is_empty() {
            word.into()
        } else {
            format!("{word} {rest}")
        }
    } else {
        text.into()
    }
}

fn lexically_closed(text: &str, span: &Span) -> Result<()> {
    let mut quoted = false;
    let mut escaped = false;
    let mut groups = Vec::new();
    let mut pipes = 0;
    for character in text.chars() {
        if character == '"' && !escaped {
            quoted = !quoted;
        }
        if !quoted {
            if character == '|' && text.starts_with('|') {
                pipes += 1;
                if pipes > 257 {
                    return Err(Diagnostic::new(
                        "format_limit",
                        "formatting supports at most 256 table columns",
                        span,
                    ));
                }
            }
            match character {
                '(' | '[' | '{' => groups.push(character),
                ')' | ']' | '}' => {
                    let expected = match character {
                        ')' => '(',
                        ']' => '[',
                        _ => '{',
                    };
                    if groups.pop() != Some(expected) {
                        return Err(Diagnostic::new(
                            "format_delimiter",
                            "unbalanced source delimiter",
                            span,
                        ));
                    }
                }
                _ => (),
            }
        }
        escaped = character == '\\' && !escaped;
    }
    if quoted || !groups.is_empty() {
        return Err(Diagnostic::new(
            "format_delimiter",
            "unterminated string or group",
            span,
        ));
    }
    Ok(())
}

fn line(raw: &str, file: &str, number: usize, offset: usize) -> Result<Line> {
    let raw = raw.trim_end_matches([' ', '\t']);
    let indent = raw.bytes().take_while(|byte| *byte == b' ').count();
    let span = Span {
        file: file.into(),
        start: offset + indent,
        end: offset + raw.len(),
        line: number,
        column: indent + 1,
    };
    let code = program_source::strip_comment(raw);
    if raw[indent..].starts_with('\t')
        || (!code.trim().is_empty() && (indent % 2 != 0 || indent > 128))
    {
        return Err(Diagnostic::new(
            "indentation",
            "indentation must use two spaces per level, at most 64 levels",
            &span,
        ));
    }
    let comment = raw
        .get(code.len()..)
        .filter(|text| !text.is_empty())
        .map(|text| {
            let body = text[1..].trim();
            if body.is_empty() {
                "#".into()
            } else {
                format!("# {body}")
            }
        });
    let text = code.trim();
    lexically_closed(text, &span)?;
    let cells = if text.starts_with('|') {
        Some(
            scenario_source::cells(&Node {
                text: text.into(),
                span: span.clone(),
                children: Vec::new(),
            })?
            .into_iter()
            .map(|cell| cell.text)
            .collect(),
        )
    } else {
        None
    };
    Ok(Line {
        text: normalize_statement(text),
        indent,
        comment,
        cells,
        span,
    })
}

fn append(output: &mut String, text: &str, span: &Span) -> Result<()> {
    if text.len() > MAX_PROGRAM_BYTES.saturating_sub(output.len()) {
        return Err(Diagnostic::new(
            "format_limit",
            "formatted source exceeds one MiB",
            span,
        ));
    }
    output.push_str(text);
    Ok(())
}

fn validate_layout(text: &str, file: &str) -> Result<Vec<Node>> {
    if text
        .lines()
        .all(|line| program_source::strip_comment(line).trim().is_empty())
    {
        return Ok(Vec::new());
    }
    let nodes = program_source::parse(text, file)?;
    // Use normalized prefixes to check EXAMPLES/BACKGROUND structure without
    // turning formatter validation into type checking or import loading.
    fn normalize(nodes: &mut [Node]) {
        for node in nodes {
            node.text = normalize_statement(&node.text);
            normalize(&mut node.children);
        }
    }
    let mut normalized = nodes.clone();
    normalize(&mut normalized);
    // The bundle loader removes module imports before scenario partitioning.
    // Keep them in the preserved source tree, but not among executable steps.
    normalized.retain(|node| node.text != "USE" && !node.text.starts_with("USE "));
    scenario_source::sections(normalized)?;
    Ok(nodes)
}

fn same_layout(before: &[Node], after: &[Node]) -> Result<bool> {
    if before.len() != after.len() {
        return Ok(false);
    }
    for (before, after) in before.iter().zip(after) {
        let equal = if before.text.starts_with('|') && after.text.starts_with('|') {
            scenario_source::cells(before)?
                .iter()
                .map(|cell| &cell.text)
                .eq(scenario_source::cells(after)?.iter().map(|cell| &cell.text))
        } else {
            normalize_statement(&before.text) == normalize_statement(&after.text)
        };
        if !equal || !same_layout(&before.children, &after.children)? {
            return Ok(false);
        }
    }
    Ok(true)
}

pub fn format_source(source: &str, file: &str) -> Result<FormattedSource> {
    format_inner(source, file).map_err(|mut error| {
        // Layout parsing uses LF text; return diagnostics in the original UTF-8
        // snapshot, including CR bytes, just as native checking does.
        let mut removed = Vec::new();
        let bytes = source.as_bytes();
        for index in 0..bytes.len().saturating_sub(1) {
            if bytes[index] == b'\r' && bytes[index + 1] == b'\n' {
                removed.push(index - removed.len());
            }
        }
        let original = |offset| offset + removed.partition_point(|position| *position < offset);
        error.span.start = original(error.span.start);
        error.span.end = original(error.span.end);
        error
    })
}

fn format_inner(source: &str, file: &str) -> Result<FormattedSource> {
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
            "source exceeds one MiB",
            &origin,
        ));
    }
    // CRLF is accepted; a lone CR would split a source token in the native parser.
    let normalized = source.replace("\r\n", "\n");
    if normalized.contains('\r') {
        return Err(Diagnostic::new(
            "format_newline",
            "use LF or CRLF line endings",
            &origin,
        ));
    }
    let mut lines = Vec::new();
    let mut offset = 0;
    for (index, raw) in normalized.split_inclusive('\n').enumerate() {
        if index >= MAX_PROGRAM_NODES {
            return Err(Diagnostic::new(
                "format_limit",
                "formatting supports at most 16384 physical lines",
                &origin,
            ));
        }
        lines.push(line(raw.trim_end_matches('\n'), file, index + 1, offset)?);
        offset += raw.len();
    }
    let before = validate_layout(&normalized, file)?;
    let mut widths = vec![None; lines.len()];
    let mut index = 0;
    while index < lines.len() {
        if lines[index].cells.is_none() {
            index += 1;
            continue;
        }
        let mut rows = Vec::new();
        let mut columns = Vec::<usize>::new();
        let indent = lines[index].indent;
        while index < lines.len() {
            let line = &lines[index];
            if let Some(cells) = &line.cells {
                if line.indent != indent {
                    break;
                }
                columns.resize(columns.len().max(cells.len()), 0);
                for (column, cell) in cells.iter().enumerate() {
                    columns[column] = columns[column].max(cell.chars().count());
                }
                rows.push(index);
            } else if !line.text.is_empty() {
                break;
            }
            index += 1;
        }
        let columns = std::sync::Arc::new(columns);
        for row in rows {
            widths[row] = Some(columns.clone());
        }
    }
    let mut output = String::new();
    let mut pending_blank = false;
    for (index, line) in lines.iter().enumerate() {
        if line.text.is_empty() && line.comment.is_none() {
            pending_blank = !output.is_empty();
            continue;
        }
        if pending_blank {
            append(&mut output, "\n", &line.span)?;
            pending_blank = false;
        }
        append(&mut output, &" ".repeat(line.indent), &line.span)?;
        if let Some(cells) = &line.cells {
            let widths = widths[index].as_ref().expect("table widths");
            append(&mut output, "| ", &line.span)?;
            for (column, cell) in cells.iter().enumerate() {
                if column > 0 {
                    append(&mut output, " | ", &line.span)?;
                }
                append(&mut output, cell, &line.span)?;
                append(
                    &mut output,
                    &" ".repeat(widths[column] - cell.chars().count()),
                    &line.span,
                )?;
            }
            append(&mut output, " |", &line.span)?;
        } else {
            append(&mut output, &line.text, &line.span)?;
        }
        if let Some(comment) = &line.comment {
            if !line.text.is_empty() {
                append(&mut output, "  ", &line.span)?;
            }
            append(&mut output, comment, &line.span)?;
        }
        append(&mut output, "\n", &line.span)?;
    }
    let after = validate_layout(&output, file).map_err(|error| {
        Diagnostic::new(
            "format_structure",
            format!("formatted layout failed validation: {}", error.message),
            &origin,
        )
    })?;
    if !same_layout(&before, &after)? {
        return Err(Diagnostic::new(
            "format_structure",
            "formatting would change statement structure or table values",
            &origin,
        ));
    }
    if source.contains("\r\n") && !source.replace("\r\n", "").contains('\n') {
        if output.len() + output.bytes().filter(|byte| *byte == b'\n').count() > MAX_PROGRAM_BYTES {
            return Err(Diagnostic::new(
                "format_limit",
                "formatted source exceeds one MiB",
                &origin,
            ));
        }
        output = output.replace('\n', "\r\n");
    }
    Ok(FormattedSource {
        changed: output != source,
        text: output,
    })
}
