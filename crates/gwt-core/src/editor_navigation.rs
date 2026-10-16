//! Read-only navigation over resolved compiler nodes, never source-name guesses.
use crate::{
    CompiledProgram,
    editor_types::{Origin, Origins, kind_token, type_token},
    expression::{Expression, Kind, PathKinds},
    program::{Argument, BoundExpression, Initializer, Place, Statement, StatementKind},
    source::Span,
    type_label::type_label,
    value::Type,
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EditorQuery {
    pub path: String,
    pub byte_offset: usize,
}

#[derive(Debug, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct EditorNavigation {
    pub symbols: Vec<EditorSymbol>,
    pub truncated: bool,
}

#[derive(Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct EditorSymbol {
    pub kind: &'static str,
    pub label: String,
    pub context: String,
    pub span: Span,
    pub definition: Option<Span>,
}

struct Binding<'a> {
    name: &'a str,
    ty: &'a Type,
    definition: Span,
    origin: Origin<'a>,
}
type Bindings<'a> = BTreeMap<usize, Binding<'a>>;

struct PathView<'a> {
    spelling: &'a str,
    ty: &'a Type,
    span: &'a Span,
    slot: usize,
    kinds: &'a PathKinds,
}

fn selected_type(ty: &Type, kinds: Option<&Vec<String>>) -> Type {
    let Some(kinds) = kinds else {
        return ty.clone();
    };
    let mut ty = ty;
    while let Type::Optional(inner) = ty {
        ty = inner;
    }
    match ty {
        Type::OneOf(variants) => Type::OneOf(
            variants
                .iter()
                .filter(|(kind, _)| kinds.contains(kind))
                .map(|(kind, fields)| (kind.clone(), fields.clone()))
                .collect(),
        ),
        _ => ty.clone(),
    }
}

struct Navigator<'a> {
    program: &'a CompiledProgram,
    query: &'a EditorQuery,
    sources: &'a BTreeMap<String, String>,
    result: EditorNavigation,
    type_scope: Option<(usize, usize)>,
}

impl<'a> Navigator<'a> {
    fn text(&self, span: &Span) -> Option<&str> {
        self.sources.get(&span.file)?.get(span.start..span.end)
    }

    // These are compiler-selected declaration sites. Restrict the selection to
    // its actual name when the original source still has a literal declaration.
    // Expanded placeholders and implicit request outputs keep their source site.
    fn binding_span(&self, span: &Span, name: &str) -> Span {
        if let Some(text) = self.text(span) {
            let rest = ["GIVEN ", "AND ", "LET ", "FOR ", "FIND ", "OUTPUT "]
                .iter()
                .find_map(|prefix| text.strip_prefix(prefix))
                .unwrap_or(text);
            if rest
                .strip_prefix(name)
                .is_some_and(|suffix| suffix.is_empty() || suffix.starts_with([' ', '.', ':']))
            {
                let start = text.len() - rest.len();
                return span.within(text, start, start + name.len());
            }
        }
        span.clone()
    }

    fn contains(&self, span: &Span) -> bool {
        span.file == self.query.path
            && self.query.byte_offset >= span.start
            && self.query.byte_offset < span.end
    }
    fn offer(
        &mut self,
        kind: &'static str,
        label: String,
        context: &str,
        span: &Span,
        definition: Option<&Span>,
    ) {
        if !self.contains(span) {
            return;
        }
        let width = span.end - span.start;
        if let Some(first) = self.result.symbols.first() {
            let previous = first.span.end - first.span.start;
            if width > previous {
                return;
            }
            if width < previous {
                self.result = EditorNavigation::default();
            }
        }
        let bounded = |text: &str, limit| {
            let mut end = text.len().min(limit);
            while !text.is_char_boundary(end) {
                end -= 1;
            }
            format!(
                "{}{}",
                &text[..end],
                if end < text.len() { "…" } else { "" }
            )
        };
        let symbol = EditorSymbol {
            kind,
            label: bounded(&label, 4096),
            context: bounded(context, 512),
            span: span.clone(),
            definition: definition.cloned(),
        };
        if self.result.symbols.contains(&symbol) {
            return;
        }
        if self.result.symbols.len() == 64 {
            self.result.truncated = true;
        } else {
            self.result.symbols.push(symbol);
        }
    }

    fn bind<'b>(
        &self,
        bindings: &mut Bindings<'b>,
        slot: usize,
        name: &'b str,
        ty: &'b Type,
        span: &Span,
    ) {
        bindings.entry(slot).or_insert_with(|| Binding {
            name,
            ty,
            definition: self.binding_span(span, name),
            origin: Origin::Unknown,
        });
    }

    fn bound_origin<'b>(
        &self,
        expression: &'b BoundExpression,
        bindings: &Bindings<'b>,
    ) -> Origin<'b>
    where
        'a: 'b,
    {
        self.expression_origin(&expression.expression, &expression.slots, bindings)
    }

    fn expression_origin<'b>(
        &self,
        expression: &'b Expression,
        slots: &[usize],
        bindings: &Bindings<'b>,
    ) -> Origin<'b>
    where
        'a: 'b,
    {
        match &expression.kind {
            Kind::Path {
                slot,
                fields,
                kinds,
                ..
            } => {
                let mut origin = bindings
                    .get(&slots[*slot])
                    .map_or(Origin::Unknown, |binding| binding.origin.clone());
                for (index, field) in fields.iter().enumerate() {
                    origin = Origins(self.program, self.type_scope)
                        .field(origin, field, kinds.get(&index))
                        .map_or(Origin::Unknown, |(origin, _)| origin);
                }
                origin
            }
            Kind::List(items) => {
                let Some(first) = items.first() else {
                    return Origin::Unknown;
                };
                let origin = self.expression_origin(first, slots, bindings);
                if items
                    .iter()
                    .skip(1)
                    .all(|item| self.expression_origin(item, slots, bindings) == origin)
                {
                    Origin::List(Box::new(origin))
                } else {
                    Origin::Unknown
                }
            }
            _ => Origin::Unknown,
        }
    }

    fn declarations<'b>(&self, body: &'b [Statement], bindings: &mut Bindings<'b>)
    where
        'a: 'b,
    {
        for statement in body {
            match &statement.kind {
                StatementKind::Initialize {
                    slot,
                    name,
                    ty,
                    value,
                } => {
                    let mut origin =
                        Origins(self.program, self.type_scope).annotation(&statement.span);
                    if matches!(value, Initializer::Table { .. }) {
                        origin = Origin::List(Box::new(origin));
                    }
                    if matches!(origin, Origin::Unknown) {
                        if let Initializer::Expression(expression) = value {
                            origin = self.bound_origin(expression, bindings);
                        }
                    }
                    self.bind(bindings, *slot, name, ty, &statement.span);
                    bindings.get_mut(slot).unwrap().origin = origin;
                }
                StatementKind::Call {
                    behavior,
                    destination: Some((slot, name)),
                    ..
                } => {
                    self.bind(
                        bindings,
                        *slot,
                        name,
                        self.program.behaviors[*behavior].returns.as_ref().unwrap(),
                        &statement.span,
                    );
                    bindings.get_mut(slot).unwrap().origin = self.program.behaviors[*behavior]
                        .return_site
                        .as_ref()
                        .map_or(Origin::Unknown, |span| {
                            Origins(self.program, self.type_scope).annotation(span)
                        });
                }
                StatementKind::Request {
                    request, outputs, ..
                } => {
                    for ((parameter, _), slot) in
                        self.program.requests[*request].outputs.iter().zip(outputs)
                    {
                        let existing = bindings.contains_key(slot);
                        self.bind(
                            bindings,
                            *slot,
                            &parameter.name,
                            &parameter.ty,
                            &statement.span,
                        );
                        if !existing {
                            bindings.get_mut(slot).unwrap().origin =
                                Origins(self.program, self.type_scope).annotation(&parameter.span);
                        }
                    }
                }
                StatementKind::Traverse {
                    iteration,
                    body,
                    otherwise,
                } => {
                    if let Type::List(ty) = &iteration.source.expression.ty {
                        let origin = Origins(self.program, self.type_scope)
                            .element(self.bound_origin(&iteration.source, bindings));
                        self.bind(
                            bindings,
                            iteration.slot,
                            &iteration.name,
                            ty,
                            &statement.span,
                        );
                        bindings.get_mut(&iteration.slot).unwrap().origin = origin;
                    }
                    self.declarations(body, bindings);
                    if let Some((_, body)) = otherwise {
                        self.declarations(body, bindings);
                    }
                }
                StatementKind::Aggregate {
                    source,
                    projection: Some(projection),
                    ..
                } => {
                    if let Type::List(ty) = &source.expression.ty {
                        let origin = Origins(self.program, self.type_scope)
                            .element(self.bound_origin(source, bindings));
                        self.bind(
                            bindings,
                            projection.0,
                            &projection.1,
                            ty,
                            &projection.2.expression.span,
                        );
                        bindings.get_mut(&projection.0).unwrap().origin = origin;
                    }
                }
                StatementKind::Branch {
                    arms, otherwise, ..
                } => {
                    for arm in arms {
                        self.declarations(&arm.body, bindings);
                    }
                    self.declarations(otherwise, bindings);
                }
                StatementKind::ExpectFailure { action, .. } => {
                    self.declarations(std::slice::from_ref(action), bindings)
                }
                StatementKind::Depending {
                    arms, otherwise, ..
                } => {
                    for (_, _, body) in arms {
                        self.declarations(body, bindings);
                    }
                    if let Some((_, body)) = otherwise {
                        self.declarations(body, bindings);
                    }
                }
                StatementKind::ValueDepending {
                    arms, otherwise, ..
                } => {
                    for (_, _, body) in arms {
                        self.declarations(body, bindings);
                    }
                    if let Some((_, body)) = otherwise {
                        self.declarations(body, bindings);
                    }
                }
                _ => (),
            }
        }
    }

    fn path(&mut self, path: PathView<'_>, bindings: &Bindings<'_>, context: &str) {
        let PathView {
            spelling,
            ty,
            span,
            slot,
            kinds,
        } = path;
        if !self.contains(span) {
            return;
        }
        let binding = bindings.get(&slot);
        let root = binding.map_or("binding", |binding| binding.name);
        if let Some(binding) = binding {
            if self.text(span) == Some(spelling) {
                let mut origin = binding.origin.clone();
                let mut field_type = selected_type(binding.ty, kinds.get(&0));
                let mut offset = 0;
                for (index, part) in spelling.split('.').enumerate() {
                    let selected = span.within(spelling, offset, offset + part.len());
                    if index == 0 {
                        if self.contains(&selected) {
                            self.offer(
                                "binding",
                                format!(
                                    "{part}: {}\nBinding: {root}",
                                    type_label(if spelling.contains('.') {
                                        &field_type
                                    } else {
                                        ty
                                    })
                                ),
                                context,
                                &selected,
                                Some(&binding.definition),
                            );
                            return;
                        }
                    } else {
                        while let Type::Optional(inner) = field_type {
                            field_type = *inner;
                        }
                        if let Some(ty) = field_type.field(part) {
                            field_type = selected_type(&ty, kinds.get(&index));
                        } else {
                            break;
                        }
                        if let Some((next, definition)) = Origins(self.program, self.type_scope)
                            .field(origin.clone(), part, kinds.get(&(index - 1)))
                        {
                            origin = next;
                            if self.contains(&selected) {
                                self.offer(
                                    "field",
                                    format!(
                                        "{}: {}",
                                        &spelling[..offset + part.len()],
                                        type_label(if offset + part.len() == spelling.len() {
                                            ty
                                        } else {
                                            &field_type
                                        })
                                    ),
                                    context,
                                    &selected,
                                    Some(&definition),
                                );
                                return;
                            }
                        } else {
                            break;
                        }
                    }
                    offset += part.len() + 1;
                }
            }
        }
        self.offer(
            "binding",
            format!("{spelling}: {}\nBinding: {root}", type_label(ty)),
            context,
            span,
            binding.map(|binding| &binding.definition),
        );
    }

    fn expression(
        &mut self,
        expression: &Expression,
        slots: &[usize],
        bindings: &Bindings<'_>,
        context: &str,
    ) {
        match &expression.kind {
            Kind::Path {
                slot,
                spelling,
                kinds,
                ..
            } => self.path(
                PathView {
                    spelling,
                    ty: &expression.ty,
                    span: &expression.span,
                    slot: slots[*slot],
                    kinds,
                },
                bindings,
                context,
            ),
            Kind::List(items) => {
                for item in items {
                    self.expression(item, slots, bindings, context);
                }
            }
            Kind::Unary(_, inner) | Kind::Presence(inner, _) => {
                self.expression(inner, slots, bindings, context)
            }
            Kind::Binary(_, left, right) => {
                self.expression(left, slots, bindings, context);
                self.expression(right, slots, bindings, context);
            }
            Kind::Literal(_) => (),
        }
    }
    fn bound(&mut self, expression: &BoundExpression, bindings: &Bindings<'_>, context: &str) {
        self.expression(&expression.expression, &expression.slots, bindings, context);
    }
    fn place(&mut self, place: &Place, bindings: &Bindings<'_>, context: &str) {
        self.path(
            PathView {
                spelling: &place.spelling,
                ty: &place.ty,
                span: &place.span,
                slot: place.slot,
                kinds: &place.kinds,
            },
            bindings,
            context,
        );
    }
    fn initializer(&mut self, value: &Initializer, bindings: &Bindings<'_>, context: &str) {
        match value {
            Initializer::Table { rows, .. } => {
                for (_, row) in rows {
                    self.initializer(row, bindings, context);
                }
            }
            Initializer::Expression(expression) => self.bound(expression, bindings, context),
            Initializer::Record(fields) => {
                for (_, value) in fields {
                    self.initializer(value, bindings, context);
                }
            }
            Initializer::Absent => (),
        }
    }
    fn behavior_label(&self, index: usize) -> String {
        let behavior = &self.program.behaviors[index];
        let mut label = format!("WHEN {}", behavior.signature.join(" "));
        for parameter in &behavior.parameters {
            label.push_str(&format!(
                "\nGIVEN {} is {}",
                parameter.name,
                type_label(&parameter.ty)
            ));
        }
        if let Some(ty) = &behavior.returns {
            label.push_str(&format!("\nTHEN returns {}", type_label(ty)));
        }
        label
    }
    fn statements(&mut self, body: &[Statement], bindings: &Bindings<'_>, context: &str) {
        for statement in body {
            match &statement.kind {
                StatementKind::Initialize { value, .. } => {
                    self.initializer(value, bindings, context)
                }
                StatementKind::InitializeField { place, value } => {
                    self.place(place, bindings, context);
                    self.initializer(value, bindings, context);
                }
                StatementKind::RoundedDivision {
                    left, right, place, ..
                } => {
                    self.bound(left, bindings, context);
                    self.bound(right, bindings, context);
                    self.place(place, bindings, context);
                }
                StatementKind::Set { place, value }
                | StatementKind::Change { place, value, .. } => {
                    self.place(place, bindings, context);
                    self.bound(value, bindings, context);
                }
                StatementKind::Return { value, .. }
                | StatementKind::Assert(value, _)
                | StatementKind::Print(value) => self.bound(value, bindings, context),
                StatementKind::Aggregate {
                    source,
                    projection,
                    place,
                    ..
                } => {
                    self.bound(source, bindings, context);
                    self.place(place, bindings, context);
                    if let Some(projection) = projection {
                        self.bound(&projection.2, bindings, context);
                    }
                }
                StatementKind::Traverse {
                    iteration,
                    body,
                    otherwise,
                } => {
                    self.bound(&iteration.source, bindings, context);
                    if let Some(condition) = &iteration.condition {
                        self.bound(condition, bindings, context);
                    }
                    self.statements(body, bindings, context);
                    if let Some((_, body)) = otherwise {
                        self.statements(body, bindings, context);
                    }
                }
                StatementKind::Branch {
                    arms, otherwise, ..
                } => {
                    for arm in arms {
                        self.bound(&arm.condition, bindings, context);
                        self.statements(&arm.body, bindings, context);
                    }
                    self.statements(otherwise, bindings, context);
                }
                StatementKind::Depending {
                    subject,
                    arms,
                    otherwise,
                    ..
                } => {
                    self.bound(subject, bindings, context);
                    for (_, _, body) in arms {
                        self.statements(body, bindings, context);
                    }
                    if let Some((_, body)) = otherwise {
                        self.statements(body, bindings, context);
                    }
                }
                StatementKind::ValueDepending {
                    subject,
                    arms,
                    otherwise,
                } => {
                    self.bound(subject, bindings, context);
                    for (_, _, body) in arms {
                        self.statements(body, bindings, context);
                    }
                    if let Some((_, body)) = otherwise {
                        self.statements(body, bindings, context);
                    }
                }
                StatementKind::Call {
                    behavior,
                    arguments,
                    ..
                } => {
                    if self.contains(&statement.span) {
                        self.offer(
                            "behavior",
                            self.behavior_label(*behavior),
                            context,
                            &statement.span,
                            Some(&self.program.behaviors[*behavior].span),
                        );
                    }
                    for argument in arguments {
                        match argument {
                            Argument::Alias(place) => self.place(place, bindings, context),
                            Argument::Value(value) => self.bound(value, bindings, context),
                        }
                    }
                }
                StatementKind::Request { request, .. } => {
                    let request = &self.program.requests[*request];
                    self.offer(
                        "request",
                        format!("REQUEST {}", request.name),
                        context,
                        &statement.span,
                        Some(&request.span),
                    );
                }
                StatementKind::ExpectFailure { action, .. } => {
                    self.statements(std::slice::from_ref(action), bindings, context)
                }
                StatementKind::Pass | StatementKind::ExpectPrints(_) => (),
            }
        }
    }
    fn binding_declarations(&mut self, bindings: &Bindings<'_>, context: &str) {
        for binding in bindings.values() {
            // Implicit outputs have no name at their request call site.
            if self.text(&binding.definition) == Some(binding.name) {
                self.path(
                    PathView {
                        spelling: binding.name,
                        ty: binding.ty,
                        span: &binding.definition,
                        slot: 0,
                        kinds: &PathKinds::new(),
                    },
                    &BTreeMap::from([(
                        0,
                        Binding {
                            name: binding.name,
                            ty: binding.ty,
                            definition: binding.definition.clone(),
                            origin: binding.origin.clone(),
                        },
                    )]),
                    context,
                );
            }
        }
    }

    fn field_declarations(
        &mut self,
        nodes: &[crate::program_source::Node],
        ty: &Type,
        context: &str,
    ) {
        if let Type::OneOf(kinds) = ty {
            for node in nodes {
                let name = node.text.strip_suffix(':').expect("checked kind");
                self.field_declarations(
                    &node.children,
                    &Type::Record(kinds[name].clone()),
                    context,
                );
            }
            return;
        }
        let Type::Record(fields) = ty else {
            return;
        };
        for node in nodes {
            let (name, _) = node.text.split_once(':').expect("checked field");
            let name = name.trim();
            let ty = &fields[name];
            let span = node.span.within(&node.text, 0, name.len());
            if self.contains(&span) {
                self.offer(
                    "field",
                    format!("{name}: {}", type_label(ty)),
                    context,
                    &span,
                    Some(&span),
                );
            }
            self.field_declarations(&node.children, ty, context);
        }
    }
}

pub(crate) fn navigate(
    program: &CompiledProgram,
    query: &EditorQuery,
    sources: &BTreeMap<String, String>,
) -> EditorNavigation {
    let mut nav = Navigator {
        program,
        query,
        sources,
        result: EditorNavigation::default(),
        type_scope: None,
    };
    for (name, ty, node) in &program.type_declarations {
        if nav.contains(&node.span) {
            nav.offer(
                "type",
                format!("{name}: {}", type_label(ty)),
                "types",
                &node.span,
                Some(&node.span),
            );
        }
        nav.field_declarations(&node.children, ty, name);
    }
    for usage in &program.type_uses {
        if nav.text(&usage.span) == Some(usage.text.as_str()) {
            if let Some((base, kind, span)) = kind_token(&usage.text, &usage.span) {
                if nav.contains(&span) {
                    if let Some(node) = Origins(program, None).kind_declaration(base, kind) {
                        nav.offer(
                            "kind",
                            format!("{base} of kind {kind}"),
                            "kind contract",
                            &span,
                            Some(&node.span),
                        );
                    }
                }
            }
        }
        let (name, mut span) = type_token(&usage.text, &usage.span);
        if nav.text(&usage.span) != Some(usage.text.as_str()) {
            span = usage.span.clone();
        }
        if nav.contains(&span) {
            if let Some((_, ty, node)) = program
                .type_declarations
                .iter()
                .find(|(candidate, _, _)| candidate == &name)
            {
                nav.offer(
                    "type",
                    format!("{name}: {}", type_label(ty)),
                    "type reference",
                    &span,
                    Some(&node.span),
                );
            }
        }
    }
    for (index, behavior) in program.behaviors.iter().enumerate() {
        let context = format!("WHEN {}", behavior.signature.join(" "));
        if nav.contains(&behavior.span) {
            nav.offer(
                "behavior",
                nav.behavior_label(index),
                &context,
                &behavior.span,
                Some(&behavior.span),
            );
        }
        let mut bindings = BTreeMap::new();
        for (slot, parameter) in behavior.parameters.iter().enumerate() {
            nav.bind(
                &mut bindings,
                slot,
                &parameter.name,
                &parameter.ty,
                &parameter.span,
            );
            bindings.get_mut(&slot).unwrap().origin =
                Origins(program, nav.type_scope).annotation(&parameter.span);
        }
        nav.declarations(&behavior.body, &mut bindings);
        nav.binding_declarations(&bindings, &context);
        nav.statements(&behavior.body, &bindings, &context);
    }
    for request in &program.requests {
        let context = format!("REQUEST {}", request.name);
        nav.offer(
            "request",
            context.clone(),
            &context,
            &request.span,
            Some(&request.span),
        );
        let mut bindings = BTreeMap::new();
        for (parameter, slot) in &request.inputs {
            nav.bind(
                &mut bindings,
                *slot,
                &parameter.name,
                &parameter.ty,
                &parameter.span,
            );
            bindings.get_mut(slot).unwrap().origin =
                Origins(program, nav.type_scope).annotation(&parameter.span);
        }
        nav.declarations(&request.body, &mut bindings);
        nav.binding_declarations(&bindings, &context);
        nav.statements(&request.body, &bindings, &context);
        nav.statements(&request.postconditions, &bindings, &context);
        for (parameter, slot) in &request.outputs {
            nav.path(
                PathView {
                    spelling: &parameter.name,
                    ty: &parameter.ty,
                    span: &nav.binding_span(&parameter.span, &parameter.name),
                    slot: *slot,
                    kinds: &PathKinds::new(),
                },
                &bindings,
                &context,
            );
        }
    }
    for scenario in &program.scenarios {
        nav.type_scope = Some((scenario.type_use_range.start, scenario.type_use_range.end));
        let context = format!("SCENARIO {}", scenario.name);
        let mut bindings = BTreeMap::new();
        nav.declarations(&scenario.body, &mut bindings);
        nav.binding_declarations(&bindings, &context);
        nav.statements(&scenario.body, &bindings, &context);
    }
    nav.result
}
