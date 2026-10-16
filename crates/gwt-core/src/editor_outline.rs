//! Local source structure for an editor outline; never a semantic validity claim.
use crate::{
    program_source::{self, Node},
    source::{Result, Span},
};
use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OutlineSymbol {
    pub name: String,
    pub kind: &'static str,
    pub range: Span,
    pub selection_range: Span,
    pub children: Vec<OutlineSymbol>,
}

fn end(node: &Node) -> usize {
    node.children.last().map(end).unwrap_or(node.span.end)
}

fn symbol(node: &Node, name: &str, kind: &'static str, start: usize) -> OutlineSymbol {
    let mut range = node.span.clone();
    range.end = end(node);
    OutlineSymbol {
        name: name.into(),
        kind,
        range,
        selection_range: node.span.within(&node.text, start, start + name.len()),
        children: Vec::new(),
    }
}

fn fields(nodes: &[Node]) -> Vec<OutlineSymbol> {
    nodes
        .iter()
        .filter_map(|node| {
            let (name, _) = node.text.split_once(':')?;
            let name = name.trim_end();
            program_source::name(name, &node.span).ok()?;
            Some(symbol(node, name, "field", 0))
        })
        .collect()
}

/// Index local declarations and scenario sections without imports, type checking,
/// scenario expansion, or execution. Layout errors fail rather than guessing scopes.
/// Empty/comment-only documents have an empty outline.
pub fn outline_source(source: &str, file: &str) -> Result<Vec<OutlineSymbol>> {
    let nodes = match program_source::parse(source, file) {
        Ok(nodes) => nodes,
        Err(error) if error.code == "empty_program" => return Ok(Vec::new()),
        Err(error) => return Err(error),
    };
    let mut result: Vec<OutlineSymbol> = Vec::new();
    let mut section: Option<usize> = None;
    for node in nodes {
        let (word, tail) = node.text.split_once(' ').unwrap_or((&node.text, ""));
        let tail = tail.trim_start();
        let start = node.text.len() - tail.len();
        let declaration = match word {
            "PROGRAM" if !tail.is_empty() => Some(symbol(&node, tail, "program", start)),
            "RECORD" | "TYPE" if !tail.is_empty() => {
                let name = tail.split_whitespace().next().unwrap();
                let mut item = symbol(
                    &node,
                    name,
                    if word == "RECORD" { "record" } else { "type" },
                    start,
                );
                if word == "RECORD" {
                    item.children = fields(&node.children);
                }
                Some(item)
            }
            "WHEN" | "REQUEST"
                if !(tail.is_empty()
                    || node.children.is_empty()
                    || word == "WHEN" && tail.starts_with("LET ")) =>
            {
                Some(symbol(
                    &node,
                    tail,
                    if word == "WHEN" {
                        "behavior"
                    } else {
                        "request"
                    },
                    start,
                ))
            }
            _ => None,
        };
        if let Some(item) = declaration {
            // Declarations may occur between scenario steps. Close the preceding
            // outline section here so sibling ranges never overlap.
            section = None;
            result.push(item);
        } else if word == "SCENARIO" && !tail.is_empty() || node.text == "BACKGROUND" {
            let item = if node.text == "BACKGROUND" {
                symbol(&node, "BACKGROUND", "background", 0)
            } else {
                symbol(&node, tail, "scenario", start)
            };
            section = Some(result.len());
            result.push(item);
        } else if let Some(index) = section {
            result[index].range.end = end(&node);
            if node.text == "EXAMPLES" {
                result[index]
                    .children
                    .push(symbol(&node, "EXAMPLES", "examples", 0));
            }
        }
    }
    Ok(result)
}
