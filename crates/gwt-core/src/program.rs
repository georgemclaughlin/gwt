use crate::type_label::contract_label;
use serde_json::Value as Json;
use std::collections::{BTreeMap, BTreeSet};

use crate::expression::{self, Expression, Kind};
use crate::program_source::{self, Node};
use crate::scenario_source::{self, ExampleRow, Expansion, ExpansionBudget};
use crate::source::{Diagnostic, Result, Span};
use crate::value::{Type, Value};
#[path = "depending.rs"]
mod depending;
#[path = "refinement.rs"]
mod refinement;
#[path = "setup_table.rs"]
mod setup_table;

#[derive(Clone, Debug)]
pub(crate) struct Binding {
    pub slot: usize,
    pub ty: Type,
    pub declared_ty: Type,
}
type Environment = BTreeMap<String, Binding>;

#[derive(Clone, Debug)]
pub(crate) struct BoundExpression {
    pub expression: Expression,
    pub slots: Vec<usize>,
}

#[derive(Clone, Debug)]
pub(crate) enum ProofGuard {
    Present(Place),
    Kinds(Place, BTreeSet<String>),
}

#[derive(Clone, Debug)]
pub(crate) struct ConditionalBranch {
    pub condition: BoundExpression,
    pub body: Vec<Statement>,
    pub guards: Vec<ProofGuard>,
}
#[derive(Clone, Debug)]
pub(crate) struct Place {
    pub slot: usize,
    pub fields: Vec<String>,
    pub ty: Type,
    pub spelling: String,
    pub span: Span,
    pub kinds: expression::PathKinds,
}
#[derive(Clone, Debug)]
pub(crate) enum Argument {
    Alias(Place),
    Value(BoundExpression),
}
#[derive(Clone, Debug)]
pub(crate) enum Initializer {
    Expression(BoundExpression),
    Record(Vec<(String, Initializer)>),
    Table {
        item_type: Type,
        rows: Vec<(Span, Initializer)>,
    },
    Absent,
}
#[derive(Clone, Debug)]
pub(crate) struct Statement {
    pub kind: StatementKind,
    pub span: Span,
    pub continuation_guards: Vec<ProofGuard>,
}
#[derive(Clone, Debug)]
pub(crate) struct Iteration {
    pub source: BoundExpression,
    pub location: Option<Place>,
    pub slot: usize,
    pub name: String,
    pub condition: Option<BoundExpression>,
    pub guards: Vec<ProofGuard>,
}
#[derive(Clone, Copy, Debug)]
pub(crate) enum Change {
    Add,
    Subtract,
    Append,
}
#[derive(Clone, Debug)]
pub(crate) enum StatementKind {
    RoundedDivision {
        left: BoundExpression,
        right: BoundExpression,
        scale: u32,
        mode: crate::rounded_division::Rounding,
        place: Place,
    },
    Change {
        operation: Change,
        place: Place,
        value: BoundExpression,
    },
    Aggregate {
        source: BoundExpression,
        projection: Option<Box<(usize, String, BoundExpression)>>,
        place: Place,
        sum: bool,
    },
    Traverse {
        iteration: Box<Iteration>,
        body: Vec<Statement>,
        otherwise: Option<(Span, Vec<Statement>)>,
    },
    Initialize {
        slot: usize,
        name: String,
        ty: Type,
        value: Initializer,
    },
    InitializeField {
        place: Place,
        value: Initializer,
    },
    Set {
        place: Place,
        value: BoundExpression,
    },
    Return {
        value: BoundExpression,
        ty: Type,
    },
    Assert(BoundExpression, Vec<ProofGuard>),
    Print(BoundExpression),
    ExpectPrints(Vec<Json>),
    ExpectFailure {
        action: Box<Statement>,
        code: String,
    },
    Pass,
    Branch {
        arms: Vec<ConditionalBranch>,
        otherwise: Vec<Statement>,
        otherwise_span: Option<Span>,
        otherwise_guards: Vec<ProofGuard>,
    },
    Depending {
        subject: BoundExpression,
        location: Place,
        arms: Vec<(String, Span, Vec<Statement>)>,
        otherwise: Option<(Span, Vec<Statement>)>,
    },
    ValueDepending {
        subject: BoundExpression,
        arms: Vec<(Value, Span, Vec<Statement>)>,
        otherwise: Option<(Span, Vec<Statement>)>,
    },
    Call {
        behavior: usize,
        arguments: Vec<Argument>,
        destination: Option<(usize, String)>,
    },
    Request {
        request: usize,
        inputs: Vec<usize>,
        outputs: Vec<usize>,
    },
}
#[derive(Clone, Debug)]
pub(crate) struct Parameter {
    pub name: String,
    pub ty: Type,
    pub span: Span,
}
#[derive(Clone, Debug)]
pub(crate) struct Behavior {
    pub signature: Vec<String>,
    pub parameters: Vec<Parameter>,
    pub returns: Option<Type>,
    pub return_site: Option<Span>,
    pub body: Vec<Statement>,
    pub slots: usize,
    pub span: Span,
}
#[derive(Clone, Debug)]
pub(crate) struct Request {
    pub name: String,
    pub inputs: Vec<(Parameter, usize)>,
    pub outputs: Vec<(Parameter, usize)>,
    pub body: Vec<Statement>,
    pub postconditions: Vec<Statement>,
    pub bindings: Environment,
    pub slots: usize,
    pub span: Span,
}
#[derive(Clone, Debug)]
pub(crate) struct Scenario {
    pub name: String,
    pub example: Option<ExampleRow>,
    pub body: Vec<Statement>,
    /// Indices of scenario/background THEN steps, excluding assertions inside
    /// WHEN actions, behavior bodies, and request contracts.
    pub expectations: Vec<usize>,
    pub bindings: Environment,
    pub slots: usize,
    pub span: Span,
    pub type_use_range: std::ops::Range<usize>,
}

#[derive(Clone, Debug)]
pub struct CompiledProgram {
    pub(crate) file: String,
    pub(crate) name: Option<String>,
    pub(crate) behaviors: Vec<Behavior>,
    pub(crate) requests: Vec<Request>,
    pub(crate) scenarios: Vec<Scenario>,
    pub(crate) span: Span,
    pub(crate) bundle: Option<crate::bundle::SourceBundle>,
    pub(crate) identity: Option<crate::bundle::ProgramIdentity>,
    pub(crate) type_declarations: Vec<(String, Type, Node)>,
    pub(crate) type_uses: Vec<TypeUse>,
}

#[derive(Clone, Debug)]
pub(crate) struct TypeUse {
    pub text: String,
    pub span: Span,
    pub site: Span,
}

struct Compiler {
    definitions: BTreeMap<String, Node>,
    types: BTreeMap<String, Type>,
    behaviors: Vec<Behavior>,
    requests: Vec<Request>,
    type_uses: Vec<TypeUse>,
}

pub fn compile_program(source: &str, file: &str) -> Result<CompiledProgram> {
    let nodes = program_source::parse(source, file)?;
    if let Some(node) = nodes
        .iter()
        .find(|node| node.text == "USE" || node.text.starts_with("USE "))
    {
        return Err(node.error(
            "imports_require_bundle",
            "compile imported sources with compile_bundle or compile_file",
        ));
    }
    compile_nodes(nodes, file)
}

pub(crate) fn compile_nodes(nodes: Vec<Node>, file: &str) -> Result<CompiledProgram> {
    let span = nodes[0].span.clone();
    let mut compiler = Compiler {
        definitions: BTreeMap::new(),
        types: BTreeMap::new(),
        behaviors: Vec::new(),
        requests: Vec::new(),
        type_uses: Vec::new(),
    };
    let mut behaviors = Vec::new();
    let mut requests = Vec::new();
    let sections = scenario_source::sections(nodes)?;
    let mut program_name = None;
    for node in sections.declarations {
        if node.text.starts_with("PROGRAM ") {
            node.leaf()?;
            if program_name.is_some() {
                return Err(node.error("duplicate_program", "only one PROGRAM header is allowed"));
            }
            program_name = Some(node.text[8..].trim().to_owned());
        } else if node.text.starts_with("RECORD ") || node.text.starts_with("TYPE ") {
            let key = node.text.split_whitespace().nth(1).unwrap();
            let key = program_source::name(key, &node.span)?;
            if matches!(
                key.as_str(),
                "integer" | "decimal" | "number" | "boolean" | "text" | "list" | "optional" | "any"
            ) {
                return Err(node.error(
                    "reserved_type",
                    "a declaration cannot replace a built-in type",
                ));
            }
            if compiler
                .definitions
                .insert(key.clone(), node.clone())
                .is_some()
            {
                return Err(node.error("duplicate_type", format!("duplicate type '{key}'")));
            }
        } else if node.text.starts_with("WHEN ") && !node.children.is_empty() {
            behaviors.push(node);
        } else if node.text.starts_with("REQUEST ") && !node.children.is_empty() {
            requests.push(node);
        }
    }
    let names: Vec<_> = compiler.definitions.keys().cloned().collect();
    for name in names {
        compiler.resolve_type(&name, &span, &mut BTreeSet::new(), 0)?;
    }
    for node in &behaviors {
        let behavior = compiler.behavior_header(node)?;
        // Reject overlapping literal/parameter patterns to make call resolution unambiguous.
        if compiler
            .behaviors
            .iter()
            .any(|other| patterns_overlap(&other.signature, &behavior.signature))
        {
            return Err(node.error(
                "ambiguous_behavior",
                "behavior signature overlaps an existing signature",
            ));
        }
        compiler.behaviors.push(behavior);
    }
    for (id, node) in behaviors.iter().enumerate() {
        let header = compiler.behaviors[id].clone();
        let mut environment = Environment::new();
        let mut slots = 0;
        for parameter in &header.parameters {
            declare(
                &mut environment,
                &mut slots,
                &parameter.name,
                parameter.ty.clone(),
                &parameter.span,
            )?;
        }
        let body_nodes: Vec<_> = node
            .children
            .iter()
            .skip_while(|n| behavior_contract(n))
            .cloned()
            .collect();
        if body_nodes.is_empty() {
            return Err(node.error("empty_behavior", "behavior requires an executable step"));
        }
        let body = compiler.body(
            &body_nodes,
            &mut environment,
            &mut slots,
            header.returns.as_ref(),
        )?;
        if header.returns.is_some() && !always_exits(&body) {
            return Err(node.error(
                "missing_return",
                "a returning behavior must return a value or explicitly fail on every path",
            ));
        }
        compiler.behaviors[id].body = body;
        compiler.behaviors[id].slots = slots;
    }
    for node in &requests {
        let request = compiler.request(node)?;
        if compiler
            .requests
            .iter()
            .any(|other| other.name == request.name)
        {
            return Err(node.error("duplicate_request", "request name must be unique"));
        }
        compiler.requests.push(request);
    }
    let mut compiled_scenarios = Vec::new();
    let mut budget = ExpansionBudget::default();
    let mut names = BTreeSet::new();
    for scenario in sections.scenarios {
        if scenario.nodes.is_empty() {
            return Err(Diagnostic::new(
                "empty_scenario",
                "scenario requires executable steps",
                &scenario.span,
            ));
        }
        let rows = scenario
            .examples
            .map_or_else(|| vec![None], |rows| rows.into_iter().map(Some).collect());
        for example in rows {
            let name = example.as_ref().map_or_else(
                || scenario.name.clone(),
                |row| format!("{} example {}", scenario.name, row.index),
            );
            budget.scenario(&name, &scenario.span)?;
            if !names.insert(name.clone()) {
                return Err(Diagnostic::new(
                    "duplicate_scenario",
                    "expanded scenario names must be unique",
                    &scenario.span,
                ));
            }
            budget.include(&sections.background)?;
            let mut environment = Environment::new();
            let mut slots = 0;
            let scenario_type_start = compiler.type_uses.len();
            let (mut body, mut expectations) =
                compiler.scenario(&sections.background, &mut environment, &mut slots)?;
            let mut expansion = Expansion::default();
            let type_use_start = compiler.type_uses.len();
            let (mut steps, step_expectations) = if let Some(row) = &example {
                budget.example(row)?;
                let nodes = expansion.expand(&scenario.nodes, row, &mut budget)?;
                compiler
                    .scenario(&nodes, &mut environment, &mut slots)
                    .map_err(|error| expansion.diagnostic(error, &name))?
            } else {
                budget.include(&scenario.nodes)?;
                compiler.scenario(&scenario.nodes, &mut environment, &mut slots)?
            };
            expansion.statements(&mut steps);
            for usage in &mut compiler.type_uses[type_use_start..] {
                expansion.span(&mut usage.span);
                expansion.span(&mut usage.site);
            }
            expectations.extend(
                step_expectations
                    .into_iter()
                    .map(|index| index + body.len()),
            );
            body.extend(steps);
            compiled_scenarios.push(Scenario {
                name,
                example,
                span: scenario.span.clone(),
                body,
                expectations,
                bindings: environment,
                slots,
                type_use_range: scenario_type_start..compiler.type_uses.len(),
            });
        }
    }
    Ok(CompiledProgram {
        file: file.into(),
        name: program_name,
        behaviors: compiler.behaviors,
        requests: compiler.requests,
        scenarios: compiled_scenarios,
        span,
        bundle: None,
        identity: None,
        type_uses: compiler.type_uses,
        type_declarations: compiler
            .definitions
            .into_iter()
            .map(|(name, node)| {
                let ty = compiler.types.remove(&name).expect("resolved declaration");
                (name, ty, node)
            })
            .collect(),
    })
}

impl CompiledProgram {
    pub fn identity(&self) -> Option<&crate::bundle::ProgramIdentity> {
        self.identity.as_ref()
    }
    pub fn source_bundle(&self) -> Option<&crate::bundle::SourceBundle> {
        self.bundle.as_ref()
    }
    pub fn request_names(&self) -> Vec<&str> {
        self.requests
            .iter()
            .map(|request| request.name.as_str())
            .collect()
    }
    pub fn scenario_names(&self) -> Vec<&str> {
        self.scenarios
            .iter()
            .map(|scenario| scenario.name.as_str())
            .collect()
    }

    /// Select the sole entry scenario without executing it. Imported scenarios
    /// are excluded by compilation; expanded example rows count individually.
    /// Hosts must make an explicit choice when the entry has zero or many.
    pub fn single_scenario(&self) -> Result<&str> {
        match self.scenarios.as_slice() {
            [scenario] => Ok(&scenario.name),
            [] => Err(Diagnostic::new(
                "scenario_selection",
                "entry has no executable scenario; select a public request with JSON input",
                &self.span,
            )),
            scenarios => Err(Diagnostic::new(
                "scenario_selection",
                format!(
                    "entry has {} scenarios; select one with --scenario or run all with test",
                    scenarios.len()
                ),
                &self.span,
            )),
        }
    }
}

fn patterns_overlap(first: &[String], second: &[String]) -> bool {
    first.len() == second.len()
        && first
            .iter()
            .zip(second)
            .all(|(a, b)| a == b || a.starts_with('<') || b.starts_with('<'))
}

fn declare(
    environment: &mut Environment,
    slots: &mut usize,
    name: &str,
    ty: Type,
    span: &Span,
) -> Result<usize> {
    program_source::name(name, span)?;
    if environment.contains_key(name) {
        return Err(Diagnostic::new(
            "duplicate_binding",
            format!("binding '{name}' is already declared"),
            span,
        ));
    }
    if *slots >= 4096 {
        return Err(Diagnostic::new(
            "binding_limit",
            "scope exceeds 4096 bindings",
            span,
        ));
    }
    let slot = *slots;
    *slots += 1;
    environment.insert(
        name.into(),
        Binding {
            slot,
            declared_ty: ty.clone(),
            ty,
        },
    );
    Ok(slot)
}

fn expression(text: &str, span: &Span, environment: &Environment) -> Result<BoundExpression> {
    expression_as(text, span, environment, None)
}
fn expression_as(
    text: &str,
    span: &Span,
    environment: &Environment,
    expected: Option<&Type>,
) -> Result<BoundExpression> {
    let types = environment
        .iter()
        .map(|(name, binding)| (name.clone(), binding.ty.clone()))
        .collect();
    let expression = expression::compile_as(text, span, &types, expected)?;
    Ok(BoundExpression {
        expression,
        slots: environment.values().map(|binding| binding.slot).collect(),
    })
}

fn condition(node: &Node, prefix: usize, environment: &Environment) -> Result<BoundExpression> {
    let (text, span) = node.tail(prefix)?;
    let expression = expression(text, &span, environment)?;
    if !expression.expression.ty.boolean() {
        return Err(node.error(
            "condition_type",
            format!(
                "a condition must be boolean; found {}",
                contract_label(&expression.expression.ty)
            ),
        ));
    }
    Ok(expression)
}

fn place(text: &str, span: &Span, environment: &Environment) -> Result<Place> {
    let parts: Vec<_> = text.split('.').collect();
    for part in &parts {
        program_source::name(part, span)?;
    }
    let Some(root) = environment.get(parts[0]) else {
        return Err(Diagnostic::new(
            "unknown_name",
            format!("unknown binding '{}'", parts[0]),
            span,
        ));
    };
    let mut ty = root.ty.clone();
    let mut kinds = expression::PathKinds::new();
    expression::record_path_kinds(&ty, 0, &mut kinds);
    for (index, field) in parts[1..].iter().enumerate() {
        if !matches!(ty, Type::Record(_) | Type::OneOf(_)) {
            return Err(Diagnostic::new(
                "invalid_path",
                crate::type_label::field_access_message(&ty, &parts[..=index].join("."), field),
                span,
            ));
        }
        if *field == "kind" && matches!(ty, Type::OneOf(_)) {
            return Err(Diagnostic::new(
                "kind_readonly",
                "a one-of kind cannot be a mutation target or shared-state argument; replace the complete value to change its kind",
                span,
            ));
        }
        ty = ty.field(field).ok_or_else(|| {
            if matches!(ty, Type::OneOf(_)) {
                return Diagnostic::new("one_of_field", format!("field '{field}' is not available with the same type in every kind; kind-specific access requires narrowing"), span);
            }
            Diagnostic::new("unknown_field", format!("unknown field '{field}'"), span)
        })?;
        expression::record_path_kinds(&ty, index + 1, &mut kinds);
    }
    Ok(Place {
        slot: root.slot,
        fields: parts[1..].iter().map(|s| (*s).into()).collect(),
        ty,
        spelling: text.into(),
        span: span.clone(),
        kinds,
    })
}

fn assignable(ty: &Type, expression: &Expression) -> Result<()> {
    expression::assignable(ty, expression)
}

fn part_span(node: &Node, part: &str) -> Span {
    let start = part.as_ptr() as usize - node.text.as_ptr() as usize;
    node.span.within(&node.text, start, start + part.len())
}

fn collection(text: &str, node: &Node, environment: &Environment) -> Result<BoundExpression> {
    let value = expression(text.trim(), &part_span(node, text.trim()), environment)?;
    if !matches!(value.expression.ty, Type::List(_)) {
        return Err(node.error(
            "collection_type",
            format!(
                "collection operation requires a list; found {}",
                contract_label(&value.expression.ty)
            ),
        ));
    }
    Ok(value)
}

fn iteration(
    node: &Node,
    prefix: usize,
    environment: &Environment,
    slots: &mut usize,
    find: bool,
) -> Result<(Iteration, Environment)> {
    let (name, rhs) = program_source::split_step(&node.text[prefix..], " in ")
        .ok_or_else(|| node.error("iteration_syntax", "expected name in collection"))?;
    let name = name.trim();
    let filtered = program_source::split_step(rhs, " WHERE ")
        .or_else(|| program_source::split_step(rhs, " where "));
    if find && filtered.is_none() {
        return Err(node.error("find_condition", "FIND requires a WHERE condition"));
    }
    let source = collection(
        filtered.map_or(rhs, |(source, _)| source),
        node,
        environment,
    )?;
    let location = if let Kind::Path {
        slot,
        fields,
        spelling,
        kinds,
    } = &source.expression.kind
    {
        Some(Place {
            slot: source.slots[*slot],
            fields: fields.clone(),
            ty: source.expression.ty.clone(),
            spelling: spelling.clone(),
            span: source.expression.span.clone(),
            kinds: kinds.clone(),
        })
    } else {
        None
    };
    let Type::List(item_type) = &source.expression.ty else {
        unreachable!("checked list");
    };
    let mut local = environment.clone();
    let slot = declare(
        &mut local,
        slots,
        name,
        item_type.as_ref().clone(),
        &part_span(node, name),
    )?;
    let condition = if let Some((_, text)) = filtered {
        let value = expression(text.trim(), &part_span(node, text.trim()), &local)?;
        if !value.expression.ty.boolean() {
            return Err(node.error("condition_type", "WHERE requires a boolean condition"));
        }
        Some(value)
    } else {
        None
    };
    let guards = if let Some(condition) = &condition {
        let (selected, guards) = refinement::refine(condition, true, &local)?;
        local = selected;
        guards
    } else {
        Vec::new()
    };
    Ok((
        Iteration {
            source,
            location,
            slot,
            name: name.into(),
            condition,
            guards,
        },
        local,
    ))
}

impl Compiler {
    fn resolve_type(
        &mut self,
        text: &str,
        span: &Span,
        visiting: &mut BTreeSet<String>,
        depth: usize,
    ) -> Result<Type> {
        if depth > 64 {
            return Err(Diagnostic::new(
                "type_limit",
                "type nesting exceeds 64",
                span,
            ));
        }
        let text = text.trim();
        let primitive = match text {
            "boolean" => Some(Type::Boolean),
            "integer" => Some(Type::Integer),
            "decimal" | "number" => Some(Type::Decimal),
            "text" => Some(Type::Text),
            _ => None,
        };
        if let Some(ty) = primitive {
            return Ok(ty);
        }
        if let Some(ty) = self.types.get(text) {
            return Ok(ty.clone());
        }
        for (prefix, optional) in [("optional<", true), ("list<", false)] {
            if let Some(inner) = text.strip_prefix(prefix).and_then(|s| s.strip_suffix('>')) {
                let inner = Box::new(self.resolve_type(inner, span, visiting, depth + 1)?);
                return Ok(if optional {
                    Type::Optional(inner)
                } else {
                    Type::List(inner)
                });
            }
        }
        let parts = program_source::union_parts(text);
        if parts.len() > 1
            || text.starts_with('"')
            || text == "true"
            || text == "false"
            || text.starts_with(|c: char| c.is_ascii_digit() || c == '-')
        {
            return crate::literal_types::resolve(&parts, span);
        }
        if let Some((base, kind)) = text.split_once(" of kind ") {
            program_source::name(base, span)?;
            program_source::name(kind, span)?;
            let Type::OneOf(mut kinds) = self.resolve_type(base, span, visiting, depth + 1)? else {
                return Err(Diagnostic::new(
                    "kind_type",
                    "of kind requires a named one-of record or alias",
                    span,
                ));
            };
            let fields = kinds.remove(kind).ok_or_else(|| {
                Diagnostic::new(
                    "one_of_kind",
                    format!("type '{base}' has no kind '{kind}'"),
                    span,
                )
            })?;
            return Ok(Type::OneOf(BTreeMap::from([(kind.into(), fields)])));
        }
        let Some(node) = self.definitions.get(text).cloned() else {
            return Err(Diagnostic::new(
                "unknown_type",
                format!("unknown or unsupported type '{text}'"),
                span,
            ));
        };
        if !visiting.insert(text.into()) {
            return Err(Diagnostic::new(
                "recursive_type",
                format!("type '{text}' recursively depends on itself"),
                span,
            ));
        }
        let ty = if node.text.starts_with("TYPE ") {
            node.leaf()?;
            let expected = format!("TYPE {text} is ");
            let Some(target) = node.text.strip_prefix(&expected) else {
                return Err(node.error("type_syntax", "expected TYPE Name is Type"));
            };
            self.note_type(target, &node);
            self.resolve_type(target, &node.span, visiting, depth + 1)?
        } else if node.text == format!("RECORD {text} is one of") {
            if node.children.is_empty() {
                return Err(node.error("empty_one_of", "one-of record requires named kinds"));
            }
            let mut kinds = BTreeMap::new();
            for case in &node.children {
                let name = case
                    .text
                    .strip_suffix(':')
                    .ok_or_else(|| case.error("kind_syntax", "one-of kind must use name:"))?;
                let name = program_source::name(name, &case.span)?;
                let fields = self.record_fields(&case.children, visiting, depth + 1, &case.span)?;
                if fields.contains_key("kind") {
                    return Err(case.error(
                        "kind_field",
                        "one-of kind cannot declare the automatic 'kind' field",
                    ));
                }
                if kinds.insert(name, fields).is_some() {
                    return Err(case.error("duplicate_kind", "one-of kind must be unique"));
                }
            }
            Type::OneOf(kinds)
        } else if node.text != format!("RECORD {text}") {
            return Err(node.error(
                "record_syntax",
                "expected RECORD Name or RECORD Name is one of",
            ));
        } else {
            Type::Record(self.record_fields(&node.children, visiting, depth + 1, &node.span)?)
        };
        visiting.remove(text);
        let mut remaining = 4096;
        crate::validate_type(&ty, span, 0, &mut remaining)?;
        self.types.insert(text.into(), ty.clone());
        Ok(ty)
    }

    fn record_fields(
        &mut self,
        nodes: &[Node],
        visiting: &mut BTreeSet<String>,
        depth: usize,
        span: &Span,
    ) -> Result<BTreeMap<String, Type>> {
        if depth > 64 {
            return Err(Diagnostic::new(
                "type_limit",
                "record nesting exceeds 64",
                span,
            ));
        }
        if nodes.is_empty() {
            return Err(Diagnostic::new(
                "empty_record",
                "record requires fields",
                span,
            ));
        }
        let mut fields = BTreeMap::new();
        for node in nodes {
            let Some((name, text)) = node.text.split_once(':') else {
                return Err(node.error("field_syntax", "expected field: Type"));
            };
            let name = program_source::name(name.trim(), &node.span)?;
            let ty = if text.trim().is_empty() {
                Type::Record(self.record_fields(&node.children, visiting, depth + 1, &node.span)?)
            } else {
                node.leaf()?;
                self.note_type(text.trim(), node);
                self.resolve_type(text.trim(), &node.span, visiting, depth + 1)?
            };
            if fields.insert(name, ty).is_some() {
                return Err(node.error("duplicate_field", "record field must be unique"));
            }
        }
        Ok(fields)
    }

    fn note_type(&mut self, text: &str, node: &Node) {
        self.type_uses.push(TypeUse {
            text: text.into(),
            span: part_span(node, text),
            site: node.span.clone(),
        });
    }

    fn ty(&mut self, text: &str, span: &Span, node: &Node) -> Result<Type> {
        self.note_type(text, node);
        self.resolve_type(text, span, &mut BTreeSet::new(), 0)
    }

    fn behavior_header(&mut self, node: &Node) -> Result<Behavior> {
        let signature: Vec<String> = node.text[5..]
            .split_whitespace()
            .map(str::to_owned)
            .collect();
        if signature.is_empty()
            || signature[0].starts_with('<')
            || matches!(
                signature[0].as_str(),
                "set"
                    | "add"
                    | "subtract"
                    | "append"
                    | "count"
                    | "sum"
                    | "divide"
                    | "find"
                    | "exists"
                    | "print"
                    | "LET"
                    | "RETURN"
                    | "PASS"
                    | "REQUIRE"
                    | "IF"
                    | "ELSE"
                    | "FOR"
                    | "FIND"
                    | "DECIDE"
                    | "DEPENDING"
            )
        {
            return Err(node.error(
                "behavior_name",
                "behavior must start with a non-reserved domain name",
            ));
        }
        let mut names = Vec::new();
        for part in &signature {
            if part.starts_with('<') {
                let Some(name) = part.strip_prefix('<').and_then(|s| s.strip_suffix('>')) else {
                    return Err(node.error("signature", "parameter must use <name>"));
                };
                let name = program_source::name(name, &node.span)?;
                if names.contains(&name) {
                    return Err(node.error("duplicate_parameter", "parameter name must be unique"));
                }
                names.push(name);
            } else if part.contains(['<', '>', '"', '(', ')', '[', ']']) {
                return Err(node.error(
                    "signature",
                    "signature words cannot contain argument delimiters; parameters use a complete <name> token",
                ));
            }
        }
        let mut contracts = BTreeMap::new();
        let mut returns = None;
        let mut return_site = None;
        for child in node.children.iter().take_while(|n| behavior_contract(n)) {
            child.leaf()?;
            if let Some(ty) = child.text.strip_prefix("THEN returns ") {
                if returns.is_some() {
                    return Err(
                        child.error("duplicate_return_contract", "return contract is repeated")
                    );
                }
                returns = Some(self.ty(ty, &child.span, child)?);
                return_site = Some(child.span.clone());
                continue;
            }
            if returns.is_some() {
                return Err(child.error(
                    "contract_order",
                    "parameter contracts must precede the return contract",
                ));
            }
            let (_, rest) = child.text.split_once(' ').unwrap();
            let Some((name, ty)) = rest.split_once(" is ") else {
                return Err(child.error("contract", "expected GIVEN parameter is Type"));
            };
            if !names.iter().any(|n| n == name) {
                return Err(child.error(
                    "unknown_parameter",
                    "contract names a parameter outside the signature",
                ));
            }
            let ty = self.ty(ty, &child.span, child)?;
            if contracts
                .insert(name.to_string(), (ty, child.span.clone()))
                .is_some()
            {
                return Err(child.error("duplicate_contract", "parameter contract is repeated"));
            }
        }
        let parameters = names
            .into_iter()
            .map(|name| {
                let Some((ty, span)) = contracts.remove(&name) else {
                    return Err(node.error(
                        "parameter_contract",
                        format!(
                            "native behavior parameter '{name}' requires a GIVEN type contract"
                        ),
                    ));
                };
                Ok(Parameter { name, ty, span })
            })
            .collect::<Result<_>>()?;
        Ok(Behavior {
            signature,
            parameters,
            returns,
            return_site,
            body: Vec::new(),
            slots: 0,
            span: node.span.clone(),
        })
    }

    fn initialize(
        &mut self,
        node: &Node,
        prefix: usize,
        environment: &mut Environment,
        slots: &mut usize,
        allow_input: bool,
    ) -> Result<(Parameter, usize, Option<Statement>)> {
        let (rest, _) = node.tail(prefix)?;
        if let Some((name, item_type)) = rest
            .split_once(" are ")
            .filter(|(name, _)| !name.trim().chars().any(char::is_whitespace))
        {
            let name = name.trim();
            let item_type = item_type.trim();
            let type_span = node.span.within(
                &node.text,
                node.text.len() - item_type.len(),
                node.text.len(),
            );
            let item_type = self.ty(item_type, &type_span, node)?;
            let value = setup_table::compile(&item_type, &node.children, environment, &node.span)?;
            let ty = Type::List(Box::new(item_type));
            let (slot, kind) = if name.contains('.') {
                let start = node.text.len() - rest.len();
                let target = place(
                    name,
                    &node.span.within(&node.text, start, start + name.len()),
                    environment,
                )?;
                if target.ty != ty {
                    return Err(node.error(
                        "table_target_type",
                        "table item type must match the existing collection field",
                    ));
                }
                (
                    target.slot,
                    StatementKind::InitializeField {
                        place: target,
                        value,
                    },
                )
            } else {
                program_source::name(name, &node.span)?;
                let slot = declare(environment, slots, name, ty.clone(), &node.span)?;
                (
                    slot,
                    StatementKind::Initialize {
                        slot,
                        name: name.into(),
                        ty: ty.clone(),
                        value,
                    },
                )
            };
            return Ok((
                Parameter {
                    name: name.into(),
                    ty,
                    span: node.span.clone(),
                },
                slot,
                Some(Statement {
                    continuation_guards: Vec::new(),
                    kind,
                    span: node.span.clone(),
                }),
            ));
        }
        let Some((name, rhs)) = rest.split_once(" is ") else {
            return Err(node.error("given_syntax", "expected GIVEN name is expression or Type"));
        };
        let name = program_source::name(name.trim(), &node.span)?;
        let rhs = rhs.trim();
        let rhs_start = node.text.len() - rhs.len();
        let rhs_span = node.span.within(&node.text, rhs_start, node.text.len());
        let known_type = self.definitions.contains_key(rhs)
            || rhs
                .split_once(" of kind ")
                .is_some_and(|(base, _)| self.definitions.contains_key(base))
            || matches!(rhs, "integer" | "decimal" | "number" | "boolean" | "text")
            || rhs.starts_with("optional<")
            || rhs.starts_with("list<");
        let (ty, initializer) = if !node.children.is_empty() {
            let ty = self.ty(rhs, &rhs_span, node)?;
            let value = Self::record_initializer(&ty, &node.children, environment, &node.span)?;
            (ty, Some(value))
        } else if known_type {
            if !allow_input {
                return Err(node.error(
                    "missing_initializer",
                    "scenario GIVEN requires a value or record initializer",
                ));
            }
            (self.ty(rhs, &rhs_span, node)?, None)
        } else {
            let expression = expression(rhs, &rhs_span, environment)?;
            (
                expression.expression.ty.clone(),
                Some(Initializer::Expression(expression)),
            )
        };
        let slot = declare(environment, slots, &name, ty.clone(), &node.span)?;
        let statement = initializer.map(|value| Statement {
            continuation_guards: Vec::new(),
            kind: StatementKind::Initialize {
                slot,
                name: name.clone(),
                ty: ty.clone(),
                value,
            },
            span: node.span.clone(),
        });
        Ok((
            Parameter {
                name,
                ty,
                span: node.span.clone(),
            },
            slot,
            statement,
        ))
    }

    fn record_initializer(
        ty: &Type,
        nodes: &[Node],
        environment: &Environment,
        span: &Span,
    ) -> Result<Initializer> {
        // Supplying a record body constructs a present value. The enclosing
        // declared contract still normalizes it as optional at the boundary.
        if let Type::Optional(inner) = ty {
            return Self::record_initializer(inner, nodes, environment, span);
        }
        if matches!(ty, Type::OneOf(_)) {
            let kind = nodes
                .iter()
                .find_map(|node| {
                    node.text
                        .split_once(':')
                        .filter(|(name, _)| name.trim() == "kind")
                        .map(|(_, value)| (node, value.trim()))
                })
                .ok_or_else(|| {
                    Diagnostic::new(
                        "kind_initializer",
                        "one-of initialization requires an explicit quoted kind",
                        span,
                    )
                })?;
            kind.0.leaf()?;
            let name: String = serde_json::from_str(kind.1).map_err(|_| {
                kind.0.error(
                    "kind_initializer",
                    "one-of kind must be a quoted literal naming the initialized shape",
                )
            })?;
            let fields = ty.fields_for_kind(&name).ok_or_else(|| {
                kind.0
                    .error("one_of_kind", format!("unknown one-of kind '{name}'"))
            })?;
            return Self::record_initializer(&Type::Record(fields), nodes, environment, span);
        }
        let Type::Record(fields) = ty else {
            return Err(Diagnostic::new(
                "initializer_type",
                "indented initialization requires a record type",
                span,
            ));
        };
        let mut supplied = BTreeSet::new();
        let mut values = Vec::new();
        for node in nodes {
            let Some((name, rhs)) = node.text.split_once(':') else {
                return Err(node.error("initializer_syntax", "expected field: value"));
            };
            let name = name.trim();
            let Some(field_type) = fields.get(name) else {
                return Err(node.error("unknown_field", format!("record has no field '{name}'")));
            };
            if !supplied.insert(name.to_string()) {
                return Err(node.error("duplicate_field", "initializer field is repeated"));
            }
            let rhs = rhs.trim();
            let initializer = if rhs.is_empty() {
                Self::record_initializer(field_type, &node.children, environment, &node.span)?
            } else {
                node.leaf()?;
                let expression = expression_as(
                    rhs,
                    &node
                        .span
                        .within(&node.text, node.text.len() - rhs.len(), node.text.len()),
                    environment,
                    Some(field_type),
                )?;
                assignable(field_type, &expression.expression)?;
                Initializer::Expression(expression)
            };
            values.push((name.to_string(), initializer));
        }
        for (name, ty) in fields {
            if !supplied.contains(name) {
                if matches!(ty, Type::Optional(_)) {
                    values.push((name.clone(), Initializer::Absent));
                } else {
                    return Err(Diagnostic::new(
                        "missing_field",
                        format!("record initializer requires '{name}'"),
                        span,
                    ));
                }
            }
        }
        Ok(Initializer::Record(values))
    }

    fn request(&mut self, node: &Node) -> Result<Request> {
        let name = node.text[8..].trim().to_string();
        if name.is_empty() {
            return Err(node.error("request_name", "request requires a name"));
        }
        let mut environment = Environment::new();
        let mut slots = 0;
        let mut inputs = Vec::new();
        let mut outputs = Vec::new();
        let mut body = Vec::new();
        let mut postconditions = Vec::new();
        let mut previous = "";
        let mut executed = false;
        let mut post = false;
        for child in &node.children {
            let (verb, prefix) = verb(child, previous)?;
            previous = verb;
            match verb {
                "GIVEN" => {
                    if executed || post {
                        return Err(child.error(
                            "request_order",
                            "request GIVEN setup must precede execution",
                        ));
                    }
                    let (parameter, slot, initializer) =
                        self.initialize(child, prefix, &mut environment, &mut slots, true)?;
                    if let Some(initializer) = initializer {
                        body.push(initializer);
                    } else {
                        inputs.push((parameter, slot));
                    }
                }
                "WHEN" => {
                    if post {
                        return Err(child
                            .error("request_order", "request WHEN must precede OUTPUT and THEN"));
                    }
                    executed = true;
                    let (text, span) = child.tail(prefix)?;
                    if !(text.starts_with("LET ") && text.ends_with(':')) {
                        child.leaf()?;
                    }
                    body.extend(self.body(
                        &[Node {
                            text: text.into(),
                            span,
                            children: child.children.clone(),
                        }],
                        &mut environment,
                        &mut slots,
                        None,
                    )?);
                }
                "OUTPUT" => {
                    child.leaf()?;
                    post = true;
                    let (rest, _) = child.tail(prefix)?;
                    let Some((name, type_text)) = rest.split_once(" is ") else {
                        return Err(child.error("output_syntax", "expected OUTPUT name is Type"));
                    };
                    program_source::name(name, &child.span)?;
                    let Some(binding) = environment.get(name) else {
                        return Err(child.error(
                            "unknown_output",
                            format!("output '{name}' is not initialized"),
                        ));
                    };
                    let ty = self.ty(type_text, &child.span, child)?;
                    if ty != binding.declared_ty {
                        return Err(child.error(
                            "output_type",
                            "output contract must match the declared state type",
                        ));
                    }
                    if outputs
                        .iter()
                        .any(|(parameter, _): &(Parameter, usize)| parameter.name == name)
                    {
                        return Err(child.error("duplicate_output", "output name is repeated"));
                    }
                    outputs.push((
                        Parameter {
                            name: name.into(),
                            ty,
                            span: child.span.clone(),
                        },
                        binding.slot,
                    ));
                }
                "THEN" => {
                    child.leaf()?;
                    post = true;
                    postconditions.push(Statement {
                        continuation_guards: Vec::new(),
                        kind: StatementKind::Assert(
                            condition(child, prefix, &environment)?,
                            Vec::new(),
                        ),
                        span: child.span.clone(),
                    });
                }
                _ => {
                    return Err(child.error(
                        "request_statement",
                        "expected GIVEN, WHEN, OUTPUT, or THEN in request",
                    ));
                }
            }
        }
        if !executed {
            return Err(node.error(
                "missing_execution",
                "request requires at least one WHEN step",
            ));
        }
        Ok(Request {
            name,
            inputs,
            outputs,
            body,
            postconditions,
            bindings: environment,
            slots,
            span: node.span.clone(),
        })
    }

    fn scenario(
        &mut self,
        nodes: &[Node],
        environment: &mut Environment,
        slots: &mut usize,
    ) -> Result<(Vec<Statement>, Vec<usize>)> {
        let mut previous = "";
        let mut body = Vec::new();
        let mut expectations = Vec::new();
        let mut action_environment = None;
        for node in nodes {
            let preceding_action_environment = action_environment.take();
            let (verb, prefix) = verb(node, previous)?;
            previous = verb;
            if matches!(verb, "WHEN" | "REQUEST") {
                action_environment = Some(environment.clone());
            }
            match verb {
                "GIVEN" => {
                    let (_, _, statement) =
                        self.initialize(node, prefix, environment, slots, false)?;
                    body.push(statement.expect("scenario initialized"));
                }
                "WHEN" => {
                    let (text, span) = node.tail(prefix)?;
                    if !(text.starts_with("LET ") && text.ends_with(':')) {
                        node.leaf()?;
                    }
                    body.extend(self.body(
                        &[Node {
                            text: text.into(),
                            span,
                            children: node.children.clone(),
                        }],
                        environment,
                        slots,
                        None,
                    )?);
                }
                "THEN" => {
                    node.leaf()?;
                    let (text, span) = node.tail(prefix)?;
                    let kind = if let Some(expected) = text.strip_prefix("fails with ") {
                        let before = preceding_action_environment.ok_or_else(|| node.error("failure_expectation_scope", "THEN fails with must immediately follow one WHEN or REQUEST action in the same scenario or background"))?;
                        let code = crate::failure_expectation::parse(expected, &span)?;
                        let action = Box::new(body.pop().expect("preceding action compiled"));
                        // An expected failure cannot initialize new caller bindings.
                        // Keep allocated slots for the action, including unexpected success.
                        *environment = before;
                        StatementKind::ExpectFailure { action, code }
                    } else if let Some(expected) = text
                        .strip_prefix("prints ")
                        .filter(|text| text.trim_start().starts_with('['))
                    {
                        StatementKind::ExpectPrints(crate::print_expectation::parse(
                            expected, &span,
                        )?)
                    } else {
                        StatementKind::Assert(condition(node, prefix, environment)?, Vec::new())
                    };
                    expectations.push(body.len());
                    body.push(Statement {
                        continuation_guards: Vec::new(),
                        kind,
                        span: node.span.clone(),
                    });
                }
                "REQUEST" => {
                    node.leaf()?;
                    let (name, _) = node.tail(prefix)?;
                    let Some((id, request)) = self
                        .requests
                        .iter()
                        .enumerate()
                        .find(|(_, request)| request.name == name)
                    else {
                        return Err(
                            node.error("unknown_request", format!("unknown request '{name}'"))
                        );
                    };
                    let mut inputs = Vec::new();
                    let mut outputs = Vec::new();
                    for (parameter, _) in &request.inputs {
                        let Some(binding) = environment.get(&parameter.name) else {
                            return Err(node.error(
                                "missing_request_input",
                                format!("request '{name}' requires '{}'", parameter.name),
                            ));
                        };
                        if parameter.ty != binding.ty {
                            return Err(node.error(
                                "request_input_type",
                                format!("request input '{}' has the wrong type", parameter.name),
                            ));
                        }
                        inputs.push(binding.slot);
                    }
                    for (parameter, _) in &request.outputs {
                        let slot = if let Some(binding) = environment.get(&parameter.name) {
                            if binding.ty != parameter.ty {
                                return Err(node.error(
                                    "request_output_type",
                                    "request output conflicts with existing state type",
                                ));
                            }
                            binding.slot
                        } else {
                            declare(
                                environment,
                                slots,
                                &parameter.name,
                                parameter.ty.clone(),
                                &node.span,
                            )?
                        };
                        outputs.push(slot);
                    }
                    body.push(Statement {
                        continuation_guards: Vec::new(),
                        kind: StatementKind::Request {
                            request: id,
                            inputs,
                            outputs,
                        },
                        span: node.span.clone(),
                    });
                }
                _ => {
                    return Err(node.error(
                        "unsupported_statement",
                        format!("unsupported top-level statement '{}'", node.text),
                    ));
                }
            }
        }
        Ok((body, expectations))
    }

    fn call(
        &self,
        text: &str,
        span: &Span,
        environment: &Environment,
    ) -> Result<Option<(usize, Vec<Argument>)>> {
        let words = program_source::call_words(text, span)?;
        let Some((id, behavior)) = self.behaviors.iter().enumerate().find(|(_, behavior)| {
            behavior.signature.len() == words.len()
                && behavior
                    .signature
                    .iter()
                    .zip(&words)
                    .all(|(part, (word, _))| part.starts_with('<') || part == word)
        }) else {
            return Ok(None);
        };
        let mut arguments = Vec::new();
        for ((_, (word, argument_span)), parameter) in behavior
            .signature
            .iter()
            .zip(words)
            .filter(|(part, _)| part.starts_with('<'))
            .zip(&behavior.parameters)
        {
            let value = expression_as(word, &argument_span, environment, Some(&parameter.ty))?;
            if matches!(&value.expression.kind, Kind::Path { spelling, .. } if word == spelling) {
                let argument = place(word, &argument_span, environment)?;
                if argument.ty != parameter.ty {
                    return Err(Diagnostic::new(
                        "argument_type",
                        format!(
                            "parameter '{}' requires {}; argument '{}' has {}; shared state arguments must have matching types{}",
                            parameter.name,
                            contract_label(&parameter.ty),
                            word,
                            contract_label(&argument.ty),
                            if parameter.ty.accepts(&argument.ty) {
                                format!(
                                    "; to pass a copy instead, write ({word}); changes to the copy do not update the original"
                                )
                            } else {
                                String::new()
                            }
                        ),
                        &argument_span,
                    ));
                }
                arguments.push(Argument::Alias(argument));
            } else {
                let literal = matches!(&value.expression.kind, Kind::Literal(_) | Kind::List(_))
                    || matches!(&value.expression.kind, Kind::Unary(expression::Op::Negate, inner) if matches!(inner.kind, Kind::Literal(_)));
                if !word.starts_with('(') && !literal {
                    return Err(Diagnostic::new(
                        "argument_group",
                        "wrap a computed argument in parentheses",
                        &argument_span,
                    ));
                }
                assignable(&parameter.ty, &value.expression)?;
                arguments.push(Argument::Value(value));
            }
        }
        Ok(Some((id, arguments)))
    }

    fn body(
        &mut self,
        nodes: &[Node],
        environment: &mut Environment,
        slots: &mut usize,
        return_type: Option<&Type>,
    ) -> Result<Vec<Statement>> {
        let mut result = Vec::new();
        let mut index = 0;
        while index < nodes.len() {
            let original = &nodes[index];
            index += 1;
            let continued;
            let node = if original.text.starts_with("AND ") {
                let (text, span) = original.tail(4)?;
                continued = Node {
                    text: text.into(),
                    span,
                    children: original.children.clone(),
                };
                &continued
            } else {
                original
            };
            let kind = if node.text == "PASS" {
                node.leaf()?;
                StatementKind::Pass
            } else if node.text == "RETURN" || node.text.starts_with("RETURN ") {
                node.leaf()?;
                let ty = return_type.ok_or_else(|| {
                    node.error(
                        "return_contract",
                        "RETURN requires a behavior with THEN returns Type",
                    )
                })?;
                let (text, span) = node.tail(6)?;
                let value = expression_as(text, &span, environment, Some(ty))?;
                assignable(ty, &value.expression)?;
                StatementKind::Return {
                    value,
                    ty: ty.clone(),
                }
            } else if node.text.starts_with("FOR ") || node.text.starts_with("FIND ") {
                if node.children.is_empty() {
                    return Err(node.error("empty_block", "collection traversal requires a body"));
                }
                let find = node.text.starts_with("FIND ");
                let (iteration, mut local) =
                    iteration(node, if find { 5 } else { 4 }, environment, slots, find)?;
                let body = self.body(&node.children, &mut local, slots, return_type)?;
                let otherwise = if find {
                    let next = nodes
                        .get(index)
                        .filter(|next| next.text == "ELSE")
                        .ok_or_else(|| {
                            node.error("missing_else", "FIND requires an explicit ELSE body")
                        })?;
                    if next.children.is_empty() {
                        return Err(next.error("empty_block", "ELSE requires a body"));
                    }
                    index += 1;
                    Some((
                        next.span.clone(),
                        self.body(&next.children, &mut environment.clone(), slots, return_type)?,
                    ))
                } else {
                    None
                };
                StatementKind::Traverse {
                    iteration: Box::new(iteration),
                    body,
                    otherwise,
                }
            } else if node.text.starts_with("divide ") {
                node.leaf()?;
                let syntax = || {
                    node.error("rounding_syntax", "expected divide numerator by denominator rounded to SCALE places using MODE into destination")
                };
                let (left, rest) =
                    program_source::split_step(&node.text[7..], " by ").ok_or_else(syntax)?;
                let (right, rest) =
                    program_source::split_step(rest, " rounded to ").ok_or_else(syntax)?;
                let (scale, rest) =
                    program_source::split_step(rest, " places using ").ok_or_else(syntax)?;
                let (mode, target) =
                    program_source::split_step(rest, " into ").ok_or_else(syntax)?;
                let scale_text = scale.trim();
                let scale =
                    if !scale_text.is_empty() && scale_text.bytes().all(|b| b.is_ascii_digit()) {
                        scale_text.parse::<u32>().ok().filter(|scale| *scale <= 512)
                    } else {
                        None
                    }
                    .ok_or_else(|| {
                        node.error(
                            "rounding_scale",
                            "rounding scale must be an integer literal from 0 through 512",
                        )
                    })?;
                let mode = crate::rounded_division::Rounding::parse(mode.trim()).ok_or_else(|| node.error("rounding_mode", "rounding mode must be half_even, half_away_from_zero, toward_zero, floor, or ceiling"))?;
                let left = expression(left.trim(), &part_span(node, left.trim()), environment)?;
                let right = expression(right.trim(), &part_span(node, right.trim()), environment)?;
                let place = place(target.trim(), &part_span(node, target.trim()), environment)?;
                if !left.expression.ty.numeric()
                    || !right.expression.ty.numeric()
                    || place.ty != Type::Decimal
                {
                    return Err(node.error(
                        "rounding_type",
                        "rounded division requires numeric operands and a decimal destination",
                    ));
                }
                StatementKind::RoundedDivision {
                    left,
                    right,
                    scale,
                    mode,
                    place,
                }
            } else if ["add ", "subtract ", "append "]
                .iter()
                .any(|prefix| node.text.starts_with(prefix))
            {
                node.leaf()?;
                let (operation, prefix, separator) = if node.text.starts_with("add ") {
                    (Change::Add, 4, " to ")
                } else if node.text.starts_with("subtract ") {
                    (Change::Subtract, 9, " from ")
                } else {
                    (Change::Append, 7, " to ")
                };
                let (rhs, path) = program_source::split_step(&node.text[prefix..], separator)
                    .ok_or_else(|| {
                        node.error("mutation_syntax", "expected a value and destination path")
                    })?;
                let target = place(path.trim(), &part_span(node, path.trim()), environment)?;
                let expected =
                    match (&operation, &target.ty) {
                        (Change::Append, Type::List(item)) => item.as_ref(),
                        (Change::Add | Change::Subtract, ty) if ty.numeric() => ty,
                        _ => return Err(node.error(
                            "mutation_type",
                            "append requires a list; add/subtract require a numeric destination",
                        )),
                    };
                let value = expression_as(
                    rhs.trim(),
                    &part_span(node, rhs.trim()),
                    environment,
                    Some(expected),
                )?;
                if !matches!(operation, Change::Append) && target.ty.finite_numeric() {
                    return Err(node.error("mutation_type", "arithmetic mutation requires an unrestricted numeric destination; assign an allowed literal or declared finite value instead"));
                }
                if !matches!(operation, Change::Append) && !value.expression.ty.numeric() {
                    return Err(node.error(
                        "mutation_type",
                        "arithmetic mutation requires a numeric expression",
                    ));
                }
                assignable(expected, &value.expression)?;
                StatementKind::Change {
                    operation,
                    place: target,
                    value,
                }
            } else if node.text.starts_with("count ") || node.text.starts_with("sum ") {
                node.leaf()?;
                let sum = node.text.starts_with("sum ");
                let prefix = if sum { 4 } else { 6 };
                let (rhs, path) = program_source::split_step(&node.text[prefix..], " into ")
                    .ok_or_else(|| {
                        node.error("aggregate_syntax", "expected collection into destination")
                    })?;
                let target = place(path.trim(), &part_span(node, path.trim()), environment)?;
                if !target.ty.numeric() || target.ty.finite_numeric() {
                    return Err(
                        node.error("aggregate_type", "count/sum require a numeric destination")
                    );
                }
                let projected = if sum {
                    program_source::split_step(rhs, " in ")
                } else {
                    None
                };
                let source = collection(
                    projected.map_or(rhs, |(_, source)| source),
                    node,
                    environment,
                )?;
                let Type::List(item_type) = &source.expression.ty else {
                    unreachable!("checked list");
                };
                let projection = if let Some((field, _)) = projected {
                    let field = field.trim();
                    let (name, _) = field.split_once('.').ok_or_else(|| {
                        node.error(
                            "sum_projection",
                            "projected sum requires name.field in collection",
                        )
                    })?;
                    let mut local = environment.clone();
                    let slot = declare(
                        &mut local,
                        slots,
                        name,
                        item_type.as_ref().clone(),
                        &part_span(node, field),
                    )?;
                    // A projected sum reads one field path, rather than introducing
                    // an implicit mapping expression into the collection syntax.
                    place(field, &part_span(node, field), &local)?;
                    let value = expression(field, &part_span(node, field), &local)?;
                    if !value.expression.ty.numeric() || !target.ty.accepts(&value.expression.ty) {
                        return Err(node.error(
                            "aggregate_type",
                            "sum projection and destination must have compatible numeric types",
                        ));
                    }
                    Some(Box::new((slot, name.into(), value)))
                } else {
                    if sum && (!item_type.numeric() || !target.ty.accepts(item_type)) {
                        return Err(node.error(
                            "aggregate_type",
                            "sum requires a numeric list compatible with its destination",
                        ));
                    }
                    None
                };
                StatementKind::Aggregate {
                    source,
                    projection,
                    place: target,
                    sum,
                }
            } else if node.text.starts_with("set ") {
                node.leaf()?;
                let Some((path, rhs)) = node.text[4..].split_once(" to ") else {
                    return Err(node.error("set_syntax", "expected set path to expression"));
                };
                let target = place(
                    path.trim(),
                    &node.span.within(&node.text, 4, 4 + path.len()),
                    environment,
                )?;
                let rhs = rhs.trim();
                let value = expression_as(
                    rhs,
                    &node
                        .span
                        .within(&node.text, node.text.len() - rhs.len(), node.text.len()),
                    environment,
                    Some(&target.ty),
                )?;
                assignable(&target.ty, &value.expression)?;
                StatementKind::Set {
                    place: target,
                    value,
                }
            } else if node.text.starts_with("LET ") {
                let Some((name, rhs)) = node.text[4..].split_once(" be ") else {
                    return Err(node.error("let_syntax", "expected LET name be expression"));
                };
                let rhs = rhs.trim();
                let span = part_span(node, rhs);
                if let Some(annotation) = rhs.strip_suffix(':') {
                    let annotation = annotation.trim();
                    let ty = self.ty(annotation, &part_span(node, annotation), node)?;
                    let value =
                        Self::record_initializer(&ty, &node.children, environment, &node.span)?;
                    let slot = declare(environment, slots, name, ty.clone(), &node.span)?;
                    StatementKind::Initialize {
                        slot,
                        name: name.into(),
                        ty,
                        value,
                    }
                } else {
                    node.leaf()?;
                    match expression(rhs, &span, environment) {
                        Ok(value) => {
                            let ty = value.expression.ty.clone();
                            let slot = declare(environment, slots, name, ty.clone(), &node.span)?;
                            StatementKind::Initialize {
                                slot,
                                name: name.into(),
                                ty,
                                value: Initializer::Expression(value),
                            }
                        }
                        Err(expression_error) => {
                            let Some((id, arguments)) = self.call(rhs, &span, environment)? else {
                                return Err(expression_error);
                            };
                            let ty = self.behaviors[id].returns.clone().ok_or_else(|| {
                                node.error(
                                    "void_call",
                                    "LET requires a behavior with an explicit return contract",
                                )
                            })?;
                            let slot = declare(environment, slots, name, ty, &node.span)?;
                            StatementKind::Call {
                                behavior: id,
                                arguments,
                                destination: Some((slot, name.into())),
                            }
                        }
                    }
                }
            } else if node.text.starts_with("REQUIRE ") {
                node.leaf()?;
                let test = condition(node, 8, environment)?;
                let (proven, guards) = refinement::refine(&test, true, environment)?;
                *environment = proven;
                StatementKind::Assert(test, guards)
            } else if node.text.starts_with("print ") {
                node.leaf()?;
                let (text, span) = node.tail(6)?;
                StatementKind::Print(expression(text, &span, environment)?)
            } else if node.text.starts_with("DEPENDING ON ") {
                depending::compile(self, node, environment, slots, return_type)?
            } else if node.text.starts_with("IF ") {
                if node.children.is_empty() {
                    return Err(node.error("empty_block", "IF requires an indented body"));
                }
                let test = condition(node, 3, environment)?;
                let (mut selected, guards) = refinement::refine(&test, true, environment)?;
                let then_body = self.body(&node.children, &mut selected, slots, return_type)?;
                let (mut missing, otherwise_guards) =
                    refinement::refine(&test, false, environment)?;
                let mut otherwise = Vec::new();
                let mut otherwise_span = None;
                if let Some(next) = nodes.get(index).filter(|next| next.text == "ELSE") {
                    if next.children.is_empty() {
                        return Err(next.error("empty_block", "ELSE requires an indented body"));
                    }
                    index += 1;
                    otherwise_span = Some(next.span.clone());
                    otherwise = self.body(&next.children, &mut missing, slots, return_type)?;
                }
                StatementKind::Branch {
                    arms: vec![ConditionalBranch {
                        condition: test,
                        body: then_body,
                        guards,
                    }],
                    otherwise,
                    otherwise_span,
                    otherwise_guards,
                }
            } else if node.text == "DECIDE" {
                let mut arms = Vec::new();
                let mut otherwise = None;
                let mut otherwise_span = None;
                // Later conditions and the final fallback know every earlier
                // condition was false. Conditions themselves have no effects.
                let mut remaining = environment.clone();
                let mut otherwise_guards = Vec::new();
                for branch in &node.children {
                    if branch.children.is_empty() {
                        return Err(branch.error("empty_block", "DECIDE branch requires a body"));
                    }
                    if otherwise.is_some() {
                        return Err(
                            branch.error("decision_order", "ELSE must be the final DECIDE branch")
                        );
                    }
                    if branch.text.starts_with("WHEN ") {
                        let test = condition(branch, 5, &remaining)?;
                        let (mut selected, mut guards) =
                            refinement::refine(&test, true, &remaining)?;
                        guards.extend(otherwise_guards.iter().cloned());
                        let body =
                            self.body(&branch.children, &mut selected, slots, return_type)?;
                        let (next, missing) = refinement::refine(&test, false, &remaining)?;
                        remaining = next;
                        otherwise_guards.extend(missing);
                        arms.push(ConditionalBranch {
                            condition: test,
                            body,
                            guards,
                        });
                    } else if branch.text == "ELSE" {
                        otherwise = Some(self.body(
                            &branch.children,
                            &mut remaining.clone(),
                            slots,
                            return_type,
                        )?);
                        otherwise_span = Some(branch.span.clone());
                    } else {
                        return Err(branch.error(
                            "decision_branch",
                            "DECIDE accepts WHEN conditions and a final ELSE",
                        ));
                    }
                }
                if arms.is_empty() || otherwise.is_none() {
                    return Err(node.error(
                        "incomplete_decision",
                        "DECIDE requires at least one WHEN and a final ELSE",
                    ));
                }
                StatementKind::Branch {
                    arms,
                    otherwise: otherwise.unwrap(),
                    otherwise_span,
                    otherwise_guards,
                }
            } else {
                node.leaf()?;
                let Some((id, arguments)) = self.call(&node.text, &node.span, environment)? else {
                    return Err(node.error(
                        "unknown_behavior",
                        format!("unknown or unsupported behavior step '{}'", node.text),
                    ));
                };
                StatementKind::Call {
                    behavior: id,
                    arguments,
                    destination: None,
                }
            };
            let continuation_guards = refinement::continuation(&kind, environment);
            result.push(Statement {
                continuation_guards,
                kind,
                span: node.span.clone(),
            });
        }
        Ok(result)
    }
}

fn behavior_contract(node: &Node) -> bool {
    node.text.starts_with("GIVEN ")
        || node.text.starts_with("AND ")
        || node.text.starts_with("THEN returns ")
}

/// No normal fallthrough: a return or a literal-false assertion exits the body.
/// Do not evaluate conditions or infer failures from calls/arithmetic here.
/// Loops may be empty. FIND has exactly one selected-body or missing-body path.
fn always_exits(body: &[Statement]) -> bool {
    body.iter().any(|statement| match &statement.kind {
        StatementKind::Return { .. } => true,
        StatementKind::Assert(test, _) => {
            matches!(test.expression.kind, Kind::Literal(Value::Boolean(false)))
        }
        StatementKind::Branch {
            arms, otherwise, ..
        } => arms.iter().all(|arm| always_exits(&arm.body)) && always_exits(otherwise),
        StatementKind::Depending {
            arms, otherwise, ..
        } => {
            arms.iter().all(|(_, _, body)| always_exits(body))
                && otherwise
                    .as_ref()
                    .is_none_or(|(_, body)| always_exits(body))
        }
        StatementKind::ValueDepending {
            arms, otherwise, ..
        } => {
            arms.iter().all(|(_, _, body)| always_exits(body))
                && otherwise
                    .as_ref()
                    .is_none_or(|(_, body)| always_exits(body))
        }
        StatementKind::Traverse {
            body,
            otherwise: Some((_, missing)),
            ..
        } => always_exits(body) && always_exits(missing),
        _ => false,
    })
}

fn verb<'a>(node: &'a Node, previous: &'a str) -> Result<(&'a str, usize)> {
    let Some((head, _)) = node.text.split_once(' ') else {
        return Err(node.error(
            "unsupported_statement",
            format!("unsupported statement '{}'", node.text),
        ));
    };
    if head == "AND" {
        if previous.is_empty() {
            return Err(node.error("orphan_and", "AND requires a preceding step"));
        }
        Ok((previous, 4))
    } else {
        Ok((head, head.len() + 1))
    }
}
