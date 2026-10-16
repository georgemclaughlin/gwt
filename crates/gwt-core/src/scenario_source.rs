//! Scenario structure and bounded, source-mapped example expansion.
use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use crate::program_source::{self, Node};
use crate::source::{Diagnostic, Result, Span};

pub(crate) const MAX_SCENARIOS: usize = 1024;
const MAX_EXPANDED_NODES: usize = 65_536;
const MAX_EXPANDED_BYTES: usize = 4 * 1_048_576;
const EXPANSION_FILE: &str = "<gwt-example-expansion>";

#[derive(Clone, Debug)]
pub(crate) struct ExampleRow {
    pub index: usize,
    pub span: Span,
    pub cells: BTreeMap<Arc<str>, Cell>,
}
#[derive(Clone, Debug)]
pub(crate) struct Cell {
    pub text: String,
    pub span: Span,
}
pub(crate) struct ScenarioSource {
    pub name: String,
    pub span: Span,
    pub nodes: Vec<Node>,
    pub examples: Option<Vec<ExampleRow>>,
}
pub(crate) struct Sections {
    pub declarations: Vec<Node>,
    pub background: Vec<Node>,
    pub scenarios: Vec<ScenarioSource>,
}

/// Validate scenario layout even when an importer excludes scenario execution.
pub(crate) fn sections(nodes: Vec<Node>) -> Result<Sections> {
    let mut result = Sections {
        declarations: Vec::new(),
        background: Vec::new(),
        scenarios: Vec::new(),
    };
    let mut implicit = Vec::new();
    let mut background = None;
    let mut names = BTreeSet::new();
    for node in nodes {
        if node.text == "BACKGROUND" {
            node.leaf()?;
            if background.is_some() || !result.scenarios.is_empty() || !implicit.is_empty() {
                return Err(node.error("background_scope", "one BACKGROUND is allowed before explicit scenarios and without implicit steps"));
            }
            background = Some(node.span);
        } else if node.text.starts_with("SCENARIO ") {
            node.leaf()?;
            let name = node.text[9..].trim().to_string();
            if !names.insert(name.clone()) {
                return Err(node.error("duplicate_scenario", "scenario name must be unique"));
            }
            result.scenarios.push(ScenarioSource {
                name,
                span: node.span,
                nodes: Vec::new(),
                examples: None,
            });
        } else if node.text == "EXAMPLES" {
            let Some(scenario) = result.scenarios.last_mut() else {
                return Err(node.error("examples_scope", "EXAMPLES requires an explicit SCENARIO"));
            };
            if scenario.examples.is_some() {
                return Err(node.error("duplicate_examples", "a scenario has one EXAMPLES table"));
            }
            scenario.examples = Some(table(&node)?);
        } else if node.text.starts_with("PROGRAM ")
            || node.text.starts_with("TYPE ")
            || node.text.starts_with("RECORD ")
            || (((node.text.starts_with("WHEN ") && !node.text.starts_with("WHEN LET "))
                || node.text.starts_with("REQUEST "))
                && !node.children.is_empty())
        {
            if background.is_some() && result.scenarios.is_empty() && node.text.starts_with("WHEN ")
            {
                return Err(node.error(
                    "background_definition",
                    "BACKGROUND cannot define behavior; declare it before BACKGROUND",
                ));
            }
            result.declarations.push(node);
        } else if let Some(scenario) = result.scenarios.last_mut() {
            if scenario.examples.is_some() {
                return Err(node.error(
                    "examples_order",
                    "EXAMPLES must follow all steps of its scenario",
                ));
            }
            scenario.nodes.push(node);
        } else if background.is_some() {
            result.background.push(node);
        } else {
            implicit.push(node);
        }
    }
    if !implicit.is_empty() && !result.scenarios.is_empty() {
        return Err(implicit[0].error(
            "mixed_scenarios",
            "implicit steps cannot be mixed with explicit scenarios",
        ));
    }
    if let Some(span) = background {
        if result.background.is_empty() || result.scenarios.is_empty() {
            return Err(Diagnostic::new(
                "empty_background",
                "BACKGROUND requires shared steps and at least one explicit scenario",
                &span,
            ));
        }
    }
    if !implicit.is_empty() {
        result.scenarios.push(ScenarioSource {
            name: "Main".into(),
            span: implicit[0].span.clone(),
            nodes: implicit,
            examples: None,
        });
    }
    Ok(result)
}

pub(crate) fn cells(node: &Node) -> Result<Vec<Cell>> {
    node.leaf()?;
    let text = &node.text;
    if !text.starts_with('|') || !text.ends_with('|') || text.len() < 2 {
        return Err(node.error("examples_table", "table rows must start and end with |"));
    }
    let mut ranges = Vec::new();
    let mut start = 1;
    let mut quoted = false;
    let mut escaped = false;
    for (index, ch) in text.char_indices().skip(1) {
        if ch == '"' && !escaped {
            quoted = !quoted;
        }
        if ch == '|' && !quoted {
            let raw = &text[start..index];
            let cell = raw.trim();
            if cell.is_empty() {
                return Err(node.error(
                    "examples_cell",
                    "example cells cannot be empty; quote empty text",
                ));
            }
            let begin = start + raw.len() - raw.trim_start().len();
            ranges.push(Cell {
                text: cell.into(),
                span: node.span.within(text, begin, begin + cell.len()),
            });
            start = index + 1;
        }
        escaped = ch == '\\' && !escaped;
    }
    if quoted || start != text.len() {
        return Err(node.error(
            "examples_table",
            "table contains an unterminated quoted cell",
        ));
    }
    Ok(ranges)
}
fn table(node: &Node) -> Result<Vec<ExampleRow>> {
    if node.children.len() < 2 {
        return Err(node.error(
            "examples_rows",
            "EXAMPLES requires a header and at least one data row",
        ));
    }
    if node.children.len() > MAX_SCENARIOS + 1 {
        return Err(node.error("scenario_limit", "EXAMPLES exceeds 1024 rows"));
    }
    let header = cells(&node.children[0])?;
    let mut names = BTreeSet::new();
    for cell in &header {
        program_source::name(&cell.text, &cell.span)?;
        if !names.insert(&cell.text) {
            return Err(Diagnostic::new(
                "examples_header",
                "EXAMPLES headers must be unique",
                &cell.span,
            ));
        }
    }
    let names: Vec<Arc<str>> = header
        .iter()
        .map(|cell| Arc::from(cell.text.as_str()))
        .collect();
    node.children
        .iter()
        .skip(1)
        .enumerate()
        .map(|(index, row)| {
            let cells = cells(row)?;
            if cells.len() != header.len() {
                return Err(row.error(
                    "examples_cells",
                    "EXAMPLES row has the wrong number of cells",
                ));
            }
            Ok(ExampleRow {
                index: index + 1,
                span: row.span.clone(),
                cells: names.iter().cloned().zip(cells).collect(),
            })
        })
        .collect()
}

#[derive(Default)]
pub(crate) struct ExpansionBudget {
    nodes: usize,
    bytes: usize,
    scenarios: usize,
}
impl ExpansionBudget {
    pub fn scenario(&mut self, name: &str, span: &Span) -> Result<()> {
        self.scenarios += 1;
        self.bytes += name.len();
        if self.scenarios > MAX_SCENARIOS {
            return Err(Diagnostic::new(
                "scenario_limit",
                "program exceeds 1024 expanded scenarios",
                span,
            ));
        }
        if self.bytes > MAX_EXPANDED_BYTES {
            return Err(Diagnostic::new(
                "scenario_limit",
                "scenario expansion and names exceed four MiB",
                span,
            ));
        }
        Ok(())
    }
    pub fn example(&mut self, row: &ExampleRow) -> Result<()> {
        self.bytes += row
            .cells
            .iter()
            .map(|(name, cell)| name.len() + cell.text.len())
            .sum::<usize>();
        if self.bytes > MAX_EXPANDED_BYTES {
            return Err(Diagnostic::new(
                "scenario_limit",
                "scenario expansion and row values exceed four MiB",
                &row.span,
            ));
        }
        Ok(())
    }
    pub fn include(&mut self, nodes: &[Node]) -> Result<()> {
        for node in nodes {
            self.nodes += 1;
            self.bytes += node.text.len();
            if self.nodes > MAX_EXPANDED_NODES || self.bytes > MAX_EXPANDED_BYTES {
                return Err(node.error(
                    "scenario_limit",
                    "scenario expansion exceeds 65536 nodes or four MiB",
                ));
            }
            self.include(&node.children)?;
        }
        Ok(())
    }
}

struct Piece {
    start: usize,
    end: usize,
    text: String,
    source: Span,
}
struct Line {
    start: usize,
    end: usize,
    source: Span,
    pieces: Vec<Piece>,
}
#[derive(Default)]
pub(crate) struct Expansion {
    lines: Vec<Line>,
    offset: usize,
}
impl Expansion {
    pub fn expand(
        &mut self,
        nodes: &[Node],
        row: &ExampleRow,
        budget: &mut ExpansionBudget,
    ) -> Result<Vec<Node>> {
        nodes
            .iter()
            .map(|node| {
                budget.nodes += 1;
                if budget.nodes > MAX_EXPANDED_NODES {
                    return Err(
                        node.error("scenario_limit", "scenario expansion exceeds 65536 nodes")
                    );
                }
                let mut text = String::new();
                let mut pieces = Vec::new();
                let mut pos = 0;
                let original = &node.text;
                while pos < original.len() {
                    let tail = &original[pos..];
                    if pieces.len() >= crate::expression::MAX_EXPRESSION_NODES {
                        return Err(node
                            .error("scenario_limit", "expanded line exceeds 4096 source pieces"));
                    }
                    let placeholder = tail.strip_prefix('<').and_then(|tail| {
                        let length = tail
                            .bytes()
                            .take_while(|c| c.is_ascii_alphanumeric() || *c == b'_')
                            .count();
                        (length > 0
                            && !tail.as_bytes()[0].is_ascii_digit()
                            && tail.as_bytes().get(length) == Some(&b'>'))
                        .then(|| &tail[..length])
                    });
                    let (value, source, next) = if let Some(name) = placeholder {
                        let Some(cell) = row.cells.get(name) else {
                            return Err(Diagnostic::new(
                                "example_placeholder",
                                format!("EXAMPLES has no value for <{name}>"),
                                &node.span.within(original, pos, pos + name.len() + 2),
                            ));
                        };
                        (cell.text.as_str(), cell.span.clone(), pos + name.len() + 2)
                    } else {
                        // Keep ordinary runs together so their subspans map exactly.
                        let end = pos
                            + tail[tail.chars().next().unwrap().len_utf8()..]
                                .find('<')
                                .map_or(tail.len(), |i| {
                                    i + tail.chars().next().unwrap().len_utf8()
                                });
                        (
                            &original[pos..end],
                            node.span.within(original, pos, end),
                            end,
                        )
                    };
                    if text.len() + value.len() > program_source::MAX_PROGRAM_BYTES {
                        return Err(
                            node.error("scenario_limit", "expanded source line exceeds one MiB")
                        );
                    }
                    budget.bytes += value.len();
                    if budget.bytes > MAX_EXPANDED_BYTES {
                        return Err(
                            node.error("scenario_limit", "scenario expansion exceeds four MiB")
                        );
                    }
                    let start = text.len();
                    text.push_str(value);
                    pieces.push(Piece {
                        start: self.offset + start,
                        end: self.offset + text.len(),
                        text: value.into(),
                        source,
                    });
                    pos = next;
                }
                let span = Span {
                    file: EXPANSION_FILE.into(),
                    start: self.offset,
                    end: self.offset + text.len(),
                    line: self.lines.len() + 1,
                    column: 1,
                };
                self.lines.push(Line {
                    start: span.start,
                    end: span.end,
                    source: node.span.clone(),
                    pieces,
                });
                self.offset = span.end + 1;
                let children = self.expand(&node.children, row, budget)?;
                Ok(Node {
                    text,
                    span,
                    children,
                })
            })
            .collect()
    }
    pub fn span(&self, span: &mut Span) {
        if span.file != EXPANSION_FILE {
            return;
        }
        let index = self.lines.partition_point(|line| line.start <= span.start);
        let Some(line) = index
            .checked_sub(1)
            .and_then(|index| self.lines.get(index))
            .filter(|line| span.end <= line.end)
        else {
            return;
        };
        if let Some(piece) = line
            .pieces
            .iter()
            .find(|piece| piece.start <= span.start && span.end <= piece.end)
        {
            *span = piece.source.within(
                &piece.text,
                span.start - piece.start,
                span.end - piece.start,
            );
        } else {
            *span = line.source.clone();
        }
    }
    pub fn diagnostic(&self, mut error: Diagnostic, name: &str) -> Diagnostic {
        self.span(&mut error.span);
        error.message = format!("{name}: {}", error.message);
        error
    }
}

impl Expansion {
    fn expression(&self, expression: &mut crate::expression::Expression) {
        use crate::expression::Kind;
        self.span(&mut expression.span);
        match &mut expression.kind {
            Kind::List(items) => items.iter_mut().for_each(|item| self.expression(item)),
            Kind::Unary(_, inner) | Kind::Presence(inner, _) => self.expression(inner),
            Kind::Binary(_, left, right) => {
                self.expression(left);
                self.expression(right);
            }
            Kind::Literal(_) | Kind::Path { .. } => (),
        }
    }
    fn bound(&self, expression: &mut crate::program::BoundExpression) {
        self.expression(&mut expression.expression);
    }
    fn initializer(&self, initializer: &mut crate::program::Initializer) {
        use crate::program::Initializer;
        match initializer {
            Initializer::Table { rows, .. } => {
                for (span, row) in rows {
                    self.span(span);
                    self.initializer(row);
                }
            }
            Initializer::Expression(expression) => self.bound(expression),
            Initializer::Record(fields) => fields
                .iter_mut()
                .for_each(|(_, value)| self.initializer(value)),
            Initializer::Absent => (),
        }
    }
    pub fn statements(&self, statements: &mut [crate::program::Statement]) {
        use crate::program::StatementKind;
        for statement in statements {
            self.span(&mut statement.span);
            for guard in &mut statement.continuation_guards {
                let (crate::program::ProofGuard::Present(place)
                | crate::program::ProofGuard::Kinds(place, _)) = guard;
                self.span(&mut place.span);
            }
            match &mut statement.kind {
                StatementKind::ExpectFailure { action, .. } => {
                    self.statements(std::slice::from_mut(action.as_mut()))
                }
                StatementKind::Initialize { value, .. } => self.initializer(value),
                StatementKind::InitializeField { place, value } => {
                    self.span(&mut place.span);
                    self.initializer(value);
                }
                StatementKind::RoundedDivision {
                    left, right, place, ..
                } => {
                    self.bound(left);
                    self.bound(right);
                    self.span(&mut place.span);
                }
                StatementKind::Set { place, value }
                | StatementKind::Change { place, value, .. } => {
                    self.span(&mut place.span);
                    self.bound(value);
                }
                StatementKind::Aggregate {
                    source,
                    projection,
                    place,
                    ..
                } => {
                    self.bound(source);
                    if let Some((_, _, expression)) = projection.as_deref_mut() {
                        self.bound(expression);
                    }
                    self.span(&mut place.span);
                }
                StatementKind::Traverse {
                    iteration,
                    body,
                    otherwise,
                } => {
                    self.bound(&mut iteration.source);
                    if let Some(place) = &mut iteration.location {
                        self.span(&mut place.span);
                    }
                    if let Some(condition) = &mut iteration.condition {
                        self.bound(condition);
                    }
                    for guard in &mut iteration.guards {
                        let (crate::program::ProofGuard::Present(place)
                        | crate::program::ProofGuard::Kinds(place, _)) = guard;
                        self.span(&mut place.span);
                    }
                    self.statements(body);
                    if let Some((span, body)) = otherwise {
                        self.span(span);
                        self.statements(body);
                    }
                }
                StatementKind::Assert(expression, guards) => {
                    self.bound(expression);
                    for guard in guards {
                        let (crate::program::ProofGuard::Present(place)
                        | crate::program::ProofGuard::Kinds(place, _)) = guard;
                        self.span(&mut place.span);
                    }
                }
                StatementKind::Print(expression)
                | StatementKind::Return {
                    value: expression, ..
                } => self.bound(expression),
                StatementKind::Branch {
                    arms,
                    otherwise,
                    otherwise_span,
                    otherwise_guards,
                } => {
                    for arm in arms {
                        self.bound(&mut arm.condition);
                        self.statements(&mut arm.body);
                        for guard in &mut arm.guards {
                            let (crate::program::ProofGuard::Present(place)
                            | crate::program::ProofGuard::Kinds(place, _)) = guard;
                            self.span(&mut place.span);
                        }
                    }
                    for guard in otherwise_guards {
                        let (crate::program::ProofGuard::Present(place)
                        | crate::program::ProofGuard::Kinds(place, _)) = guard;
                        self.span(&mut place.span);
                    }
                    self.statements(otherwise);
                    if let Some(span) = otherwise_span {
                        self.span(span);
                    }
                }
                StatementKind::Depending {
                    subject,
                    location,
                    arms,
                    otherwise,
                } => {
                    self.bound(subject);
                    self.span(&mut location.span);
                    for (_, span, body) in arms {
                        self.span(span);
                        self.statements(body);
                    }
                    if let Some((span, body)) = otherwise {
                        self.span(span);
                        self.statements(body);
                    }
                }
                StatementKind::ValueDepending {
                    subject,
                    arms,
                    otherwise,
                } => {
                    self.bound(subject);
                    for (_, span, body) in arms {
                        self.span(span);
                        self.statements(body);
                    }
                    if let Some((span, body)) = otherwise {
                        self.span(span);
                        self.statements(body);
                    }
                }
                StatementKind::Call { arguments, .. } => {
                    for argument in arguments {
                        match argument {
                            crate::program::Argument::Alias(place) => self.span(&mut place.span),
                            crate::program::Argument::Value(expression) => self.bound(expression),
                        }
                    }
                }
                StatementKind::Request { .. }
                | StatementKind::Pass
                | StatementKind::ExpectPrints(_) => (),
            }
        }
    }
}
