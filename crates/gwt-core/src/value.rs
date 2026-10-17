use std::collections::BTreeMap;
use std::str::FromStr;

use num_bigint::BigInt;
use num_rational::BigRational;
use num_traits::{One, Signed, Zero};
use serde::{Deserialize, Serialize};
use serde_json::Value as Json;

use crate::source::{Diagnostic, Result, Span};

/// Explicit execution limits, independent of the host integer width or decimal context.
pub const MAX_DIGITS: usize = 512;
pub const MAX_VALUE_DEPTH: usize = 64;
pub const MAX_VALUE_NODES: usize = 16_384;
pub const MAX_VALUE_BYTES: usize = 1_048_576;

/// Account for constructed containers before retaining another copied value.
pub(crate) struct ValueBudget {
    nodes: usize,
    bytes: usize,
}
impl ValueBudget {
    pub fn new() -> Self {
        Self { nodes: 1, bytes: 2 }
    }
    pub fn include(&mut self, value: &Value, key: Option<&str>, span: &Span) -> Result<()> {
        let (nodes, bytes) = value_size(value, 1, span)?;
        let key_bytes = key.map_or(0, |key| {
            serde_json::to_vec(key).expect("key JSON").len() + 1
        });
        let separator = usize::from(self.nodes > 1);
        if nodes > MAX_VALUE_NODES.saturating_sub(self.nodes)
            || bytes + key_bytes + separator > MAX_VALUE_BYTES.saturating_sub(self.bytes)
        {
            return Err(Diagnostic::new(
                "value_limit",
                "constructed value exceeds 16384 nodes or one MiB of JSON",
                span,
            ));
        }
        self.nodes += nodes;
        self.bytes += bytes + key_bytes + separator;
        Ok(())
    }
}

pub(crate) fn value_size(
    value: &Value,
    initial_depth: usize,
    span: &Span,
) -> Result<(usize, usize)> {
    let error = || {
        Diagnostic::new(
            "value_limit",
            "constructed value exceeds depth, node, or one-MiB JSON limits",
            span,
        )
    };
    let mut pending = vec![(value, initial_depth)];
    let mut nodes = 0;
    let mut raw_bytes = 0;
    while let Some((value, depth)) = pending.pop() {
        nodes += 1;
        if nodes > MAX_VALUE_NODES || depth > MAX_VALUE_DEPTH {
            return Err(error());
        }
        match value {
            Value::Text(text) => raw_bytes += text.len(),
            Value::List(items) => pending.extend(items.iter().map(|item| (item, depth + 1))),
            Value::Record(fields) => {
                raw_bytes += fields.keys().map(String::len).sum::<usize>();
                pending.extend(fields.values().map(|item| (item, depth + 1)));
            }
            _ => (),
        }
        if raw_bytes > MAX_VALUE_BYTES {
            return Err(error());
        }
    }
    // Structural/raw-text limits bound this serialization even for escaped strings.
    let bytes = serde_json::to_vec(&value.json()).expect("value JSON").len();
    if bytes > MAX_VALUE_BYTES {
        return Err(error());
    }
    Ok((nodes, bytes))
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum Type {
    Boolean,
    Integer,
    Decimal,
    Text,
    TextUnion(Vec<String>),
    IntegerUnion(Vec<String>),
    DecimalUnion(Vec<String>),
    BooleanUnion(Vec<bool>),
    List(Box<Type>),
    Optional(Box<Type>),
    Record(BTreeMap<String, Type>),
    OneOf(BTreeMap<String, BTreeMap<String, Type>>),
}

impl Type {
    /// Fields available without selecting a kind: the discriminator and fields
    /// with exactly the same contract in every kind. Never guess a payload shape.
    pub(crate) fn field(&self, name: &str) -> Option<Type> {
        match self {
            Self::Record(fields) => fields.get(name).cloned(),
            Self::OneOf(kinds) if name == "kind" => {
                Some(Self::TextUnion(kinds.keys().cloned().collect()))
            }
            Self::OneOf(kinds) => {
                let first = kinds.values().next()?.get(name)?;
                kinds
                    .values()
                    .all(|fields| fields.get(name) == Some(first))
                    .then(|| first.clone())
            }
            _ => None,
        }
    }

    pub(crate) fn fields_for_kind(&self, kind: &str) -> Option<BTreeMap<String, Type>> {
        let Self::OneOf(kinds) = self else {
            return None;
        };
        let mut fields = kinds.get(kind)?.clone();
        fields.insert("kind".into(), Self::TextUnion(vec![kind.into()]));
        Some(fields)
    }

    pub fn numeric(&self) -> bool {
        self.integer() || self.decimal()
    }

    pub fn integer(&self) -> bool {
        matches!(self, Self::Integer | Self::IntegerUnion(_))
    }

    pub fn decimal(&self) -> bool {
        matches!(self, Self::Decimal | Self::DecimalUnion(_))
    }

    pub fn boolean(&self) -> bool {
        matches!(self, Self::Boolean | Self::BooleanUnion(_))
    }

    pub(crate) fn finite_numeric(&self) -> bool {
        matches!(self, Self::IntegerUnion(_) | Self::DecimalUnion(_))
    }

    pub fn accepts(&self, other: &Type) -> bool {
        self.accepts_refinement(other)
            || matches!(
                (self, other),
                (Self::Integer, Self::IntegerUnion(_))
                    | (Self::Decimal, Self::IntegerUnion(_) | Self::DecimalUnion(_))
                    | (Self::Boolean, Self::BooleanUnion(_))
            )
            || matches!((self, other), (Self::IntegerUnion(a), Self::IntegerUnion(b)) | (Self::DecimalUnion(a), Self::DecimalUnion(b) | Self::IntegerUnion(b)) if b.iter().all(|v| a.contains(v)))
            || matches!((self, other), (Self::BooleanUnion(a), Self::BooleanUnion(b)) if b.iter().all(|v| a.contains(v)))
            || matches!(
                (self, other),
                (Self::Decimal, Self::Integer) | (Self::Text, Self::TextUnion(_))
            )
            || matches!((self, other), (Self::TextUnion(a), Self::TextUnion(b)) if b.iter().all(|value| a.contains(value)))
            || matches!((self, other), (Self::List(a), Self::List(b)) if a.accepts(b))
            || matches!(self, Self::Optional(inner) if inner.accepts(other))
    }

    // Branch refinement can reduce possible kinds or prove optional presence
    // anywhere in a copied value.
    // It does not widen ordinary record fields or mutable alias contracts.
    fn accepts_refinement(&self, other: &Type) -> bool {
        fn fields(a: &BTreeMap<String, Type>, b: &BTreeMap<String, Type>) -> bool {
            a.len() == b.len()
                && a.iter().all(|(name, ty)| {
                    b.get(name)
                        .is_some_and(|other| ty.accepts_refinement(other))
                })
        }
        self == other
            || match (self, other) {
                (Self::OneOf(a), Self::OneOf(b)) => {
                    !b.is_empty()
                        && b.iter().all(|(kind, payload)| {
                            a.get(kind)
                                .is_some_and(|expected| fields(expected, payload))
                        })
                }
                (Self::Record(a), Self::Record(b)) => fields(a, b),
                (Self::Optional(a), Self::Optional(b)) | (Self::List(a), Self::List(b)) => {
                    a.accepts_refinement(b)
                }
                (Self::Optional(a), b) => a.accepts_refinement(b),
                _ => false,
            }
    }

    pub(crate) fn comparable(&self, other: &Type) -> bool {
        // Whole records may be compared to their refined shapes, but a direct
        // optional operand still requires a presence guard before scalar use.
        if matches!(self, Self::Optional(_)) != matches!(other, Self::Optional(_)) {
            return false;
        }
        if self.accepts_refinement(other) || other.accepts_refinement(self) {
            return true;
        }
        match (self, other) {
            (Self::List(a), Self::List(b)) | (Self::Optional(a), Self::Optional(b)) => {
                a.comparable(b)
            }
            (Self::Record(a), Self::Record(b)) => {
                a.len() == b.len()
                    && a.iter()
                        .all(|(key, ty)| b.get(key).is_some_and(|other| ty.comparable(other)))
            }
            (Self::OneOf(a), Self::OneOf(b)) => {
                a.len() == b.len()
                    && a.iter().all(|(kind, fields)| {
                        b.get(kind).is_some_and(|other| {
                            fields.len() == other.len()
                                && fields.iter().all(|(name, ty)| {
                                    other.get(name).is_some_and(|other| ty.comparable(other))
                                })
                        })
                    })
            }
            _ => {
                (self.numeric() && other.numeric())
                    || (self.text() && other.text())
                    || (self.boolean() && other.boolean())
            }
        }
    }

    pub fn text(&self) -> bool {
        matches!(self, Self::Text | Self::TextUnion(_))
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Value {
    Boolean(bool),
    Integer(BigInt),
    Decimal(BigRational),
    Text(String),
    List(Vec<Value>),
    Absent,
    Record(BTreeMap<String, Value>),
}

impl Value {
    pub fn json(&self) -> Json {
        match self {
            Self::Boolean(value) => Json::Bool(*value),
            Self::Integer(value) => Json::Number(
                serde_json::Number::from_str(&value.to_string()).expect("integer JSON"),
            ),
            Self::Decimal(value) => {
                Json::String(decimal_text(value).expect("finite checked decimal"))
            }
            Self::Text(value) => Json::String(value.clone()),
            Self::Absent => Json::Null,
            Self::List(values) => Json::Array(values.iter().map(Self::json).collect()),
            Self::Record(values) => Json::Object(
                values
                    .iter()
                    .map(|(key, value)| (key.clone(), value.json()))
                    .collect(),
            ),
        }
    }

    pub fn rational(&self) -> Option<BigRational> {
        match self {
            Self::Integer(value) => Some(BigRational::from_integer(value.clone())),
            Self::Decimal(value) => Some(value.clone()),
            _ => None,
        }
    }
}

pub fn parse_number(text: &str, span: &Span) -> Result<Value> {
    let unsigned = text.strip_prefix('-').unwrap_or(text);
    let parts: Vec<_> = unsigned.split('.').collect();
    if parts.len() > 2
        || parts
            .iter()
            .any(|part| part.is_empty() || !part.bytes().all(|c| c.is_ascii_digit()))
    {
        return Err(Diagnostic::new(
            "invalid_number",
            "expected an integer or finite base-10 decimal without exponent notation",
            span,
        ));
    }
    let digits = parts.concat();
    if digits.len() > MAX_DIGITS {
        return Err(Diagnostic::new(
            "numeric_limit",
            format!("numbers are limited to {MAX_DIGITS} decimal digits"),
            span,
        ));
    }
    let mut numerator = BigInt::from_str(&digits).expect("validated digits");
    if text.starts_with('-') {
        numerator = -numerator;
    }
    if parts.len() == 1 {
        Ok(Value::Integer(numerator))
    } else {
        Ok(Value::Decimal(BigRational::new(
            numerator,
            BigInt::from(10).pow(parts[1].len() as u32),
        )))
    }
}

/// A rational has a finite decimal expansion iff its reduced denominator has
/// only factors two and five. No host rounding mode participates.
pub fn decimal_text(value: &BigRational) -> Option<String> {
    let mut denominator = value.denom().clone();
    let mut twos = 0;
    let mut fives = 0;
    while (&denominator % 2_u8).is_zero() {
        denominator /= 2_u8;
        twos += 1;
    }
    while (&denominator % 5_u8).is_zero() {
        denominator /= 5_u8;
        fives += 1;
    }
    if denominator != BigInt::one() {
        return None;
    }
    let scale = twos.max(fives);
    if scale > MAX_DIGITS as u32 {
        return None;
    }
    let coefficient =
        value.numer() * BigInt::from(2).pow(scale - twos) * BigInt::from(5).pow(scale - fives);
    let mut digits = coefficient.abs().to_string();
    if digits.len().max(scale as usize) > MAX_DIGITS {
        return None;
    }
    let sign = if coefficient.is_negative() { "-" } else { "" };
    if scale == 0 {
        return Some(format!("{sign}{digits}"));
    }
    while digits.len() <= scale as usize {
        digits.insert(0, '0');
    }
    digits.insert(digits.len() - scale as usize, '.');
    Some(format!("{sign}{digits}"))
}

pub fn checked_numeric(value: BigRational, ty: &Type, span: &Span) -> Result<Value> {
    if ty.integer() {
        let integer = value.to_integer();
        if integer.abs().to_string().len() > MAX_DIGITS {
            return Err(Diagnostic::new(
                "numeric_limit",
                "integer result exceeds the digit limit",
                span,
            ));
        }
        Ok(Value::Integer(integer))
    } else {
        if decimal_text(&value).is_none() {
            let mut denominator = value.denom().clone();
            while (&denominator % 2_u8).is_zero() {
                denominator /= 2_u8;
            }
            while (&denominator % 5_u8).is_zero() {
                denominator /= 5_u8;
            }
            let (code, message) = if denominator == BigInt::one() {
                ("numeric_limit", "decimal result exceeds the digit limit")
            } else {
                (
                    "nonterminating_decimal",
                    "division has no finite exact decimal result; a domain rounding policy is required",
                )
            };
            return Err(Diagnostic::new(code, message, span));
        }
        Ok(Value::Decimal(value))
    }
}

pub fn normalize(ty: &Type, value: Option<&Json>, span: &Span) -> Result<Value> {
    let mut remaining = MAX_VALUE_NODES;
    normalize_inner(ty, value, span, 0, &mut remaining)
}

fn normalize_inner(
    ty: &Type,
    value: Option<&Json>,
    span: &Span,
    depth: usize,
    remaining: &mut usize,
) -> Result<Value> {
    if depth > MAX_VALUE_DEPTH || *remaining == 0 {
        return Err(Diagnostic::new(
            "input_limit",
            "input exceeds the nesting or value-count limit",
            span,
        ));
    }
    *remaining -= 1;
    if let Type::Optional(inner) = ty {
        return match value {
            None | Some(Json::Null) => Ok(Value::Absent),
            _ => normalize_inner(inner, value, span, depth + 1, remaining),
        };
    }
    let Some(value) = value else {
        return Err(crate::input_diagnostics::missing(ty, span));
    };
    let mismatch = || crate::input_diagnostics::mismatch(ty, value, span);
    match (ty, value) {
        (Type::BooleanUnion(allowed), Json::Bool(value)) if allowed.contains(value) => {
            Ok(Value::Boolean(*value))
        }
        (Type::IntegerUnion(allowed), _) | (Type::DecimalUnion(allowed), _) => {
            let base = if ty.integer() {
                Type::Integer
            } else {
                Type::Decimal
            };
            let normalized = normalize_inner(&base, Some(value), span, depth, remaining)?;
            let text = decimal_text(&normalized.rational().expect("normalized number"))
                .expect("finite number");
            if allowed.contains(&text) {
                Ok(normalized)
            } else {
                Err(mismatch())
            }
        }
        (Type::Boolean, Json::Bool(value)) => Ok(Value::Boolean(*value)),
        (Type::Text, Json::String(value)) => Ok(Value::Text(value.clone())),
        (Type::TextUnion(allowed), Json::String(value)) if allowed.contains(value) => {
            Ok(Value::Text(value.clone()))
        }
        (Type::Integer, Json::Number(number)) => match parse_number(&number.to_string(), span)? {
            value @ Value::Integer(_) => Ok(value),
            _ => Err(mismatch()),
        },
        (Type::Decimal, Json::String(text)) => {
            let number = parse_number(text, span)?;
            Ok(Value::Decimal(number.rational().expect("number")))
        }
        (Type::Decimal, Json::Number(number)) => match parse_number(&number.to_string(), span)? {
            Value::Integer(value) => Ok(Value::Decimal(BigRational::from_integer(value))),
            _ => Err(mismatch()),
        },
        (Type::List(item), Json::Array(values)) => Ok(Value::List(
            values
                .iter()
                .enumerate()
                .map(|(index, value)| {
                    normalize_inner(item, Some(value), span, depth + 1, remaining).map_err(
                        |mut error| {
                            error.message = format!("item {index}: {}", error.message);
                            error
                        },
                    )
                })
                .collect::<Result<_>>()?,
        )),
        (Type::Record(fields), Json::Object(values)) => {
            normalize_record(fields, values, span, depth, remaining)
        }
        (Type::OneOf(_), Json::Object(values)) => {
            let kind = values
                .get("kind")
                .and_then(Json::as_str)
                .ok_or_else(|| crate::input_diagnostics::missing_kind(values.get("kind"), span))?;
            let fields = ty
                .fields_for_kind(kind)
                .ok_or_else(|| crate::input_diagnostics::unknown_kind(kind, ty, span))?;
            normalize_record(&fields, values, span, depth, remaining)
        }
        _ => Err(mismatch()),
    }
}

fn normalize_record(
    fields: &BTreeMap<String, Type>,
    values: &serde_json::Map<String, Json>,
    span: &Span,
    depth: usize,
    remaining: &mut usize,
) -> Result<Value> {
    if let Some(key) = values.keys().find(|key| !fields.contains_key(*key)) {
        return Err(crate::input_diagnostics::unknown_field(key, span));
    }
    Ok(Value::Record(
        fields
            .iter()
            .map(|(name, ty)| {
                Ok((
                    name.clone(),
                    normalize_inner(ty, values.get(name), span, depth + 1, remaining).map_err(
                        |mut error| {
                            error.message = format!("field '{name}': {}", error.message);
                            error
                        },
                    )?,
                ))
            })
            .collect::<Result<_>>()?,
    ))
}
