use crate::type_label::contract_label;
use std::collections::BTreeMap;

use crate::source::{Diagnostic, Result, Span};
use crate::value::{Type, Value, parse_number};

pub const MAX_SOURCE_BYTES: usize = 65_536;
pub const MAX_EXPRESSION_DEPTH: usize = 64;
pub const MAX_EXPRESSION_NODES: usize = 4096;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Op {
    Add,
    Subtract,
    Multiply,
    Divide,
    Equal,
    NotEqual,
    Greater,
    Less,
    AtLeast,
    AtMost,
    And,
    Or,
    Contains,
    Negate,
    Not,
}

impl Op {
    pub(crate) fn name(self) -> &'static str {
        match self {
            Self::Add => "+",
            Self::Subtract => "-",
            Self::Multiply => "*",
            Self::Divide => "/",
            Self::Equal => "==",
            Self::NotEqual => "!=",
            Self::Greater => ">",
            Self::Less => "<",
            Self::AtLeast => ">=",
            Self::AtMost => "<=",
            Self::And => "and",
            Self::Or => "or",
            Self::Contains => "contains",
            Self::Negate => "negate",
            Self::Not => "not",
        }
    }
}

#[derive(Clone, Debug)]
enum SyntaxKind {
    Literal(Value),
    List(Vec<Syntax>),
    Path(Vec<String>),
    Unary(Op, Box<Syntax>),
    Binary(Op, Box<Syntax>, Box<Syntax>),
    Presence(Box<Syntax>, bool),
}
#[derive(Clone, Debug)]
struct Syntax {
    kind: SyntaxKind,
    span: Span,
}

/// Checked one-of alternatives at each prefix of a source path. This retains
/// branch facts for navigation without copying entire record types per prefix.
pub(crate) type PathKinds = BTreeMap<usize, Vec<String>>;

pub(crate) fn record_path_kinds(ty: &Type, index: usize, kinds: &mut PathKinds) {
    if let Type::OneOf(variants) = ty {
        kinds.insert(index, variants.keys().cloned().collect());
    }
}

#[derive(Clone, Debug)]
pub(crate) enum Kind {
    Literal(Value),
    List(Vec<Expression>),
    Path {
        slot: usize,
        fields: Vec<String>,
        spelling: String,
        kinds: PathKinds,
    },
    Unary(Op, Box<Expression>),
    Binary(Op, Box<Expression>, Box<Expression>),
    Presence(Box<Expression>, bool),
}

/// Constructed only by the checker; execution cannot bypass type resolution.
#[derive(Clone, Debug)]
pub struct Expression {
    pub(crate) kind: Kind,
    pub(crate) ty: Type,
    pub(crate) span: Span,
}

impl Expression {
    pub fn result_type(&self) -> &Type {
        &self.ty
    }
    pub fn span(&self) -> &Span {
        &self.span
    }
}

#[derive(Clone, Debug, PartialEq)]
enum TokenKind {
    Word(String),
    Number(String),
    Text(String),
    Symbol(String),
    End,
}
#[derive(Clone, Debug)]
struct Token {
    kind: TokenKind,
    span: Span,
}

fn lex(text: &str, base: &Span) -> Result<Vec<Token>> {
    if text.len() > MAX_SOURCE_BYTES {
        return Err(Diagnostic::new(
            "source_limit",
            "expression exceeds 65536 UTF-8 bytes",
            base,
        ));
    }
    if let Some(pos) = text.find(['\n', '\r']) {
        return Err(Diagnostic::new(
            "expression_layout",
            "an expression must occupy one source line",
            &base.within(text, pos, pos + 1),
        ));
    }
    let mut tokens = Vec::new();
    let mut pos = 0;
    while pos < text.len() {
        let ch = text[pos..].chars().next().expect("character boundary");
        if matches!(ch, '\n' | '\r') {
            return Err(Diagnostic::new(
                "expression_layout",
                "an expression must occupy one source line",
                &base.within(text, pos, pos + ch.len_utf8()),
            ));
        }
        if ch.is_whitespace() {
            pos += ch.len_utf8();
            continue;
        }
        if ch == '#' {
            break;
        }
        let start = pos;
        let kind = if ch == '"' {
            pos += 1;
            let mut escaped = false;
            let mut closed = false;
            while pos < text.len() {
                let c = text[pos..].chars().next().expect("character boundary");
                pos += c.len_utf8();
                if c == '"' && !escaped {
                    closed = true;
                    break;
                }
                escaped = c == '\\' && !escaped;
            }
            let span = base.within(text, start, pos);
            if !closed {
                return Err(Diagnostic::new(
                    "unterminated_text",
                    "text literal needs a closing quote",
                    &span,
                ));
            }
            TokenKind::Text(serde_json::from_str(&text[start..pos]).map_err(|_| {
                Diagnostic::new(
                    "invalid_text",
                    "text must use valid JSON string escapes",
                    &span,
                )
            })?)
        } else if ch.is_ascii_digit() {
            pos += 1;
            while pos < text.len() && text.as_bytes()[pos].is_ascii_digit() {
                pos += 1;
            }
            if text.as_bytes().get(pos) == Some(&b'.') {
                pos += 1;
                while pos < text.len() && text.as_bytes()[pos].is_ascii_digit() {
                    pos += 1;
                }
            }
            TokenKind::Number(text[start..pos].into())
        } else if ch.is_ascii_alphabetic() || ch == '_' {
            pos += 1;
            while pos < text.len()
                && (text.as_bytes()[pos].is_ascii_alphanumeric() || text.as_bytes()[pos] == b'_')
            {
                pos += 1;
            }
            TokenKind::Word(text[start..pos].into())
        } else if "+-*/()<>!=.[],".contains(ch) {
            pos += 1;
            if "<>!=".contains(ch) && text.as_bytes().get(pos) == Some(&b'=') {
                pos += 1;
            }
            TokenKind::Symbol(text[start..pos].into())
        } else {
            return Err(Diagnostic::new(
                "unexpected_character",
                format!("unexpected character {ch:?}"),
                &base.within(text, start, start + ch.len_utf8()),
            ));
        };
        tokens.push(Token {
            kind,
            span: base.within(text, start, pos),
        });
        if tokens.len() > MAX_EXPRESSION_NODES * 3 {
            return Err(Diagnostic::new(
                "expression_limit",
                "too many expression tokens",
                base,
            ));
        }
    }
    tokens.push(Token {
        kind: TokenKind::End,
        span: base.within(text, pos, pos),
    });
    Ok(tokens)
}

struct Parser {
    tokens: Vec<Token>,
    pos: usize,
    nodes: usize,
}
impl Parser {
    fn peek(&self) -> &Token {
        &self.tokens[self.pos]
    }
    fn take(&mut self) -> Token {
        let token = self.peek().clone();
        if token.kind != TokenKind::End {
            self.pos += 1;
        }
        token
    }
    fn node(&mut self, kind: SyntaxKind, span: Span) -> Result<Syntax> {
        self.nodes += 1;
        if self.nodes > MAX_EXPRESSION_NODES {
            return Err(Diagnostic::new(
                "expression_limit",
                "too many expression nodes",
                &span,
            ));
        }
        Ok(Syntax { kind, span })
    }
    fn parse(&mut self, min: u8, depth: usize) -> Result<Syntax> {
        if depth > MAX_EXPRESSION_DEPTH {
            return Err(Diagnostic::new(
                "expression_limit",
                "expression nesting exceeds 64",
                &self.peek().span,
            ));
        }
        let token = self.take();
        let mut left = match token.kind {
            TokenKind::Symbol(ref symbol) if symbol == "[" => {
                let mut items = Vec::new();
                while self.peek().kind != TokenKind::Symbol("]".into()) {
                    items.push(self.parse(0, depth + 1)?);
                    if self.peek().kind != TokenKind::Symbol(",".into()) {
                        break;
                    }
                    self.take();
                }
                let closing = self.take();
                if closing.kind != TokenKind::Symbol("]".into()) {
                    return Err(Diagnostic::new(
                        "expected_bracket",
                        "expected ']' after list items",
                        &closing.span,
                    ));
                }
                self.node(SyntaxKind::List(items), joined(&token.span, &closing.span))?
            }
            TokenKind::Number(text) => self.node(
                SyntaxKind::Literal(parse_number(&text, &token.span)?),
                token.span,
            )?,
            TokenKind::Text(text) => {
                self.node(SyntaxKind::Literal(Value::Text(text)), token.span)?
            }
            TokenKind::Word(ref word) if word == "true" || word == "false" => self.node(
                SyntaxKind::Literal(Value::Boolean(word == "true")),
                token.span,
            )?,
            TokenKind::Word(ref word) if word == "not" => {
                let inner = self.parse(5, depth + 1)?;
                let span = joined(&token.span, &inner.span);
                self.node(SyntaxKind::Unary(Op::Not, Box::new(inner)), span)?
            }
            TokenKind::Symbol(ref symbol) if symbol == "-" => {
                let inner = self.parse(13, depth + 1)?;
                let span = joined(&token.span, &inner.span);
                self.node(SyntaxKind::Unary(Op::Negate, Box::new(inner)), span)?
            }
            TokenKind::Symbol(ref symbol) if symbol == "(" => {
                let mut inner = self.parse(0, depth + 1)?;
                let closing = self.take();
                if closing.kind != TokenKind::Symbol(")".into()) {
                    return Err(Diagnostic::new(
                        "expected_parenthesis",
                        "expected ')'",
                        &closing.span,
                    ));
                }
                inner.span = joined(&token.span, &closing.span);
                inner
            }
            TokenKind::Word(word) => {
                let mut path = vec![word];
                let mut span = token.span;
                while self.peek().kind == TokenKind::Symbol(".".into()) {
                    self.take();
                    let field = self.take();
                    let TokenKind::Word(name) = field.kind else {
                        return Err(Diagnostic::new(
                            "expected_field",
                            "expected a field name after '.'",
                            &field.span,
                        ));
                    };
                    span = joined(&span, &field.span);
                    path.push(name);
                }
                self.node(SyntaxKind::Path(path), span)?
            }
            _ => {
                return Err(Diagnostic::new(
                    "expected_expression",
                    "expected a value, path, or parenthesized expression",
                    &token.span,
                ));
            }
        };
        loop {
            if self.peek().kind == TokenKind::Word("is".into()) && min <= 7 {
                self.take();
                let token = self.take();
                let present = match &token.kind {
                    TokenKind::Word(word) if word == "present" => true,
                    TokenKind::Word(word) if word == "absent" => false,
                    _ => {
                        return Err(Diagnostic::new(
                            "expected_presence",
                            "expected 'present' or 'absent'",
                            &token.span,
                        ));
                    }
                };
                let span = joined(&left.span, &token.span);
                left = self.node(SyntaxKind::Presence(Box::new(left), present), span)?;
                continue;
            }
            let Some((op, precedence)) = binary(&self.peek().kind) else {
                break;
            };
            if precedence < min {
                break;
            }
            self.take();
            let right = self.parse(precedence + 1, depth + 1)?;
            let span = joined(&left.span, &right.span);
            left = self.node(
                SyntaxKind::Binary(op, Box::new(left), Box::new(right)),
                span,
            )?;
        }
        Ok(left)
    }
}

fn joined(first: &Span, last: &Span) -> Span {
    Span {
        end: last.end,
        ..first.clone()
    }
}
fn binary(kind: &TokenKind) -> Option<(Op, u8)> {
    let (TokenKind::Word(text) | TokenKind::Symbol(text)) = kind else {
        return None;
    };
    Some(match text.as_str() {
        "or" => (Op::Or, 1),
        "and" => (Op::And, 3),
        "==" => (Op::Equal, 5),
        "!=" => (Op::NotEqual, 5),
        ">" => (Op::Greater, 7),
        "<" => (Op::Less, 7),
        ">=" => (Op::AtLeast, 7),
        "<=" => (Op::AtMost, 7),
        "contains" => (Op::Contains, 7),
        "+" => (Op::Add, 9),
        "-" => (Op::Subtract, 9),
        "*" => (Op::Multiply, 11),
        "/" => (Op::Divide, 11),
        _ => return None,
    })
}

pub(crate) fn compile(
    text: &str,
    span: &Span,
    bindings: &BTreeMap<String, Type>,
) -> Result<Expression> {
    compile_as(text, span, bindings, None)
}

pub(crate) fn compile_as(
    text: &str,
    span: &Span,
    bindings: &BTreeMap<String, Type>,
    expected: Option<&Type>,
) -> Result<Expression> {
    let mut parser = Parser {
        tokens: lex(text, span)?,
        pos: 0,
        nodes: 0,
    };
    let syntax = parser.parse(0, 0)?;
    if parser.peek().kind != TokenKind::End {
        return Err(Diagnostic::new(
            "unexpected_token",
            "unexpected token after expression",
            &parser.peek().span,
        ));
    }
    check_as(&syntax, bindings, &BTreeMap::new(), 0, expected)
}

fn check(
    syntax: &Syntax,
    bindings: &BTreeMap<String, Type>,
    refined: &BTreeMap<Vec<String>, Type>,
    depth: usize,
) -> Result<Expression> {
    check_as(syntax, bindings, refined, depth, None)
}

fn empty_shape(syntax: &Syntax) -> bool {
    matches!(&syntax.kind, SyntaxKind::List(items) if items.iter().all(empty_shape))
}

/// Source literals, including a single numeric minus; no constant folding.
pub(crate) fn scalar_literal(expression: &Expression) -> Option<Value> {
    match &expression.kind {
        Kind::Literal(
            value @ (Value::Text(_) | Value::Integer(_) | Value::Decimal(_) | Value::Boolean(_)),
        ) => Some(value.clone()),
        Kind::Unary(Op::Negate, inner) => match &inner.kind {
            Kind::Literal(Value::Integer(value)) => Some(Value::Integer(-value)),
            Kind::Literal(Value::Decimal(value)) => Some(Value::Decimal(-value)),
            _ => None,
        },
        _ => None,
    }
}

pub(crate) fn assignable(ty: &Type, expression: &Expression) -> Result<()> {
    if ty.accepts(&expression.ty) {
        return Ok(());
    }
    if let Some(value) = scalar_literal(expression) {
        if crate::value::normalize(ty, Some(&value.json()), &expression.span).is_ok() {
            return Ok(());
        }
    }
    Err(Diagnostic::new(
        "assignment_type",
        format!(
            "cannot assign {}; expected {}",
            contract_label(&expression.ty),
            contract_label(ty)
        ),
        &expression.span,
    ))
}

fn check_as(
    syntax: &Syntax,
    bindings: &BTreeMap<String, Type>,
    refined: &BTreeMap<Vec<String>, Type>,
    depth: usize,
    expected: Option<&Type>,
) -> Result<Expression> {
    if depth > MAX_EXPRESSION_DEPTH {
        return Err(Diagnostic::new(
            "expression_limit",
            "expression tree depth exceeds 64",
            &syntax.span,
        ));
    }
    let error = |message: &str| Diagnostic::new("type_mismatch", message, &syntax.span);
    let (kind, ty) = match &syntax.kind {
        SyntaxKind::List(items) => {
            let expected = match expected {
                Some(Type::Optional(inner)) => Some(inner.as_ref()),
                other => other,
            };
            let mut item_type = if let Some(Type::List(item)) = expected {
                Some(item.as_ref().clone())
            } else {
                None
            };
            let contextual = item_type.is_some();
            let mut preliminary = Vec::new();
            for item in items {
                let checked = if contextual || empty_shape(item) {
                    None
                } else {
                    Some(check(item, bindings, refined, depth + 1)?)
                };
                if let Some(value) = &checked {
                    let ty = value.ty.clone();
                    item_type = Some(match item_type {
                        None => ty,
                        Some(previous) if previous.accepts(&ty) => previous,
                        Some(previous) if ty.accepts(&previous) => ty,
                        _ => return Err(error("list items must have a common type")),
                    });
                }
                preliminary.push(checked);
            }
            let item_type = item_type.ok_or_else(|| {
                Diagnostic::new(
                    "empty_list_type",
                    "an empty list needs a typed destination or a typed comparison operand",
                    &syntax.span,
                )
            })?;
            let mut checked = Vec::new();
            for (item, preliminary) in items.iter().zip(preliminary) {
                let value = match preliminary {
                    Some(value) => value,
                    None => check_as(item, bindings, refined, depth + 1, Some(&item_type))?,
                };
                assignable(&item_type, &value)?;
                checked.push(value);
            }
            (Kind::List(checked), Type::List(Box::new(item_type)))
        }
        SyntaxKind::Literal(value) => (
            Kind::Literal(value.clone()),
            match value {
                Value::Integer(_) => Type::Integer,
                Value::Decimal(_) => Type::Decimal,
                Value::Boolean(_) => Type::Boolean,
                Value::Text(_) => Type::Text,
                _ => unreachable!("parser literal"),
            },
        ),
        SyntaxKind::Path(path) => {
            let Some((slot, (_, root))) = bindings
                .iter()
                .enumerate()
                .find(|(_, (key, _))| *key == &path[0])
            else {
                return Err(Diagnostic::new(
                    "unknown_name",
                    format!("unknown input '{}'", path[0]),
                    &syntax.span,
                ));
            };
            let mut ty = refined.get(&path[..1]).unwrap_or(root).clone();
            let mut kinds = PathKinds::new();
            record_path_kinds(&ty, 0, &mut kinds);
            for index in 1..path.len() {
                if !matches!(ty, Type::Record(_) | Type::OneOf(_)) {
                    return Err(error(&crate::type_label::field_access_message(
                        &ty,
                        &path[..index].join("."),
                        &path[index],
                    )));
                }
                ty = ty.field(&path[index]).ok_or_else(|| {
                    if matches!(ty, Type::OneOf(_)) {
                        return Diagnostic::new("one_of_field", format!("field '{}' is not available with the same type in every kind; kind-specific access requires narrowing", path[index]), &syntax.span);
                    }
                    Diagnostic::new(
                        "unknown_field",
                        format!("unknown field '{}'", path[index]),
                        &syntax.span,
                    )
                })?;
                if let Some(narrowed) = refined.get(&path[..=index]) {
                    ty = narrowed.clone();
                }
                record_path_kinds(&ty, index, &mut kinds);
            }
            (
                Kind::Path {
                    slot,
                    fields: path[1..].to_vec(),
                    spelling: path.join("."),
                    kinds,
                },
                ty,
            )
        }
        SyntaxKind::Unary(op, inner) => {
            let checked = check(inner, bindings, refined, depth + 1)?;
            let ty = match op {
                Op::Not if checked.ty.boolean() => Type::Boolean,
                Op::Negate if checked.ty.numeric() => {
                    if checked.ty.integer() {
                        Type::Integer
                    } else {
                        Type::Decimal
                    }
                }
                _ => {
                    return Err(error(&format!(
                        "operator '{}' requires {}; found {}",
                        if *op == Op::Not { "not" } else { "-" },
                        if *op == Op::Not {
                            "boolean"
                        } else {
                            "a number"
                        },
                        contract_label(&checked.ty),
                    )));
                }
            };
            (Kind::Unary(*op, Box::new(checked)), ty)
        }
        SyntaxKind::Presence(inner, present) => {
            let checked = check(inner, bindings, refined, depth + 1)?;
            if !matches!(checked.ty, Type::Optional(_)) {
                return Err(error(&format!(
                    "presence checks require an optional value; found {}",
                    contract_label(&checked.ty)
                )));
            }
            (Kind::Presence(Box::new(checked), *present), Type::Boolean)
        }
        SyntaxKind::Binary(op, left, right) => {
            let comparison = matches!(op, Op::Equal | Op::NotEqual);
            let preliminary_right = if comparison && empty_shape(left) {
                Some(check(right, bindings, refined, depth + 1)?)
            } else {
                None
            };
            let hint = preliminary_right.as_ref().map(|value| &value.ty);
            let checked_left = check_as(left, bindings, refined, depth + 1, hint)?;
            let mut right_refined = refined.clone();
            if matches!(op, Op::And | Op::Or) {
                refine(
                    left,
                    *op == Op::And,
                    bindings,
                    &mut right_refined,
                    depth + 1,
                )?;
            }
            let checked_right = match preliminary_right {
                Some(value) => value,
                None => check_as(
                    right,
                    bindings,
                    &right_refined,
                    depth + 1,
                    if comparison && empty_shape(right) {
                        Some(&checked_left.ty)
                    } else {
                        None
                    },
                )?,
            };
            let l = &checked_left.ty;
            let r = &checked_right.ty;
            let numeric = l.numeric() && r.numeric();
            let ty = match op {
                Op::And | Op::Or if l.boolean() && r.boolean() => Type::Boolean,
                Op::Equal | Op::NotEqual if l.comparable(r) => Type::Boolean,
                Op::Greater | Op::Less | Op::AtLeast | Op::AtMost if numeric => Type::Boolean,
                Op::Add if l.text() && r.text() => Type::Text,
                Op::Add | Op::Subtract | Op::Multiply | Op::Divide if numeric => {
                    if *op == Op::Divide || l.decimal() || r.decimal() {
                        Type::Decimal
                    } else {
                        Type::Integer
                    }
                }
                Op::Contains if l.text() && r.text() => Type::Boolean,
                Op::Contains if matches!(l, Type::List(item) if (item.numeric() && r.numeric()) || (item.text() && r.text()) || (item.boolean() && r.boolean())) => {
                    Type::Boolean
                }
                _ => {
                    return Err(error(&format!(
                        "operator '{}' does not accept {} and {}",
                        op.name(),
                        contract_label(l),
                        contract_label(r)
                    )));
                }
            };
            (
                Kind::Binary(*op, Box::new(checked_left), Box::new(checked_right)),
                ty,
            )
        }
    };
    Ok(Expression {
        kind,
        ty,
        span: syntax.span.clone(),
    })
}

// Keep a nonempty subset only. An impossible comparison remains an ordinary
// boolean expression; unreachable bodies are still checked without a bottom type.
pub(crate) fn select_kinds(ty: &Type, kind: &str, equal: bool) -> Option<Type> {
    let Type::OneOf(kinds) = ty else { return None };
    let selected: BTreeMap<_, _> = kinds
        .iter()
        .filter(|(name, _)| (name.as_str() == kind) == equal)
        .map(|(name, fields)| (name.clone(), fields.clone()))
        .collect();
    (!selected.is_empty() && selected.len() < kinds.len()).then_some(Type::OneOf(selected))
}

/// Only logically established presence/kind facts flow across short-circuit edges.
fn refine(
    syntax: &Syntax,
    truth: bool,
    bindings: &BTreeMap<String, Type>,
    refined: &mut BTreeMap<Vec<String>, Type>,
    depth: usize,
) -> Result<()> {
    if depth > MAX_EXPRESSION_DEPTH {
        return Err(Diagnostic::new(
            "expression_limit",
            "guard depth exceeds 64",
            &syntax.span,
        ));
    }
    match &syntax.kind {
        SyntaxKind::Presence(inner, present) if *present == truth => {
            if let SyntaxKind::Path(path) = &inner.kind {
                let checked = check(inner, bindings, refined, depth + 1)?;
                if let Type::Optional(ty) = checked.ty {
                    refined.insert(path.clone(), *ty);
                }
            }
        }
        SyntaxKind::Binary(op @ (Op::Equal | Op::NotEqual), left, right) => {
            let pair = match (&left.kind, &right.kind) {
                (SyntaxKind::Path(path), SyntaxKind::Literal(Value::Text(kind))) => {
                    Some((path, kind, left))
                }
                (SyntaxKind::Literal(Value::Text(kind)), SyntaxKind::Path(path)) => {
                    Some((path, kind, right))
                }
                _ => None,
            };
            if let Some((path, kind, original)) = pair {
                if path.len() > 1 && path.last().is_some_and(|field| field == "kind") {
                    let parent = path[..path.len() - 1].to_vec();
                    let syntax = Syntax {
                        kind: SyntaxKind::Path(parent.clone()),
                        span: original.span.clone(),
                    };
                    let checked = check(&syntax, bindings, refined, depth + 1)?;
                    if let Some(ty) = select_kinds(&checked.ty, kind, (*op == Op::Equal) == truth) {
                        refined.insert(parent, ty);
                    }
                }
            }
        }
        SyntaxKind::Unary(Op::Not, inner) => refine(inner, !truth, bindings, refined, depth + 1)?,
        SyntaxKind::Binary(Op::And, left, right) if truth => {
            refine(left, truth, bindings, refined, depth + 1)?;
            refine(right, truth, bindings, refined, depth + 1)?;
        }
        SyntaxKind::Binary(Op::Or, left, right) if !truth => {
            refine(left, truth, bindings, refined, depth + 1)?;
            refine(right, truth, bindings, refined, depth + 1)?;
        }
        _ => {}
    }
    Ok(())
}
