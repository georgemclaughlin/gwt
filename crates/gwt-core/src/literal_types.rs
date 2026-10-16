//! Closed scalar domains. Numbers retain exact values and a declared numeric base.
use crate::{
    expression,
    source::{Diagnostic, Result, Span},
    value::{Type, Value, decimal_text, parse_number},
};
use std::collections::BTreeMap;

pub(crate) fn resolve(parts: &[&str], span: &Span) -> Result<Type> {
    let error = || {
        Diagnostic::new(
            "unsupported_type",
            "literal contracts require only text, only booleans, or only numbers",
            span,
        )
    };
    let mut literals = Vec::new();
    for part in parts {
        let checked = expression::compile(part, span, &BTreeMap::new()).map_err(|_| error())?;
        literals.push(expression::scalar_literal(&checked).ok_or_else(error)?);
    }
    let mut ty = match literals.first() {
        Some(Value::Text(_)) => Type::TextUnion(Vec::new()),
        Some(Value::Boolean(_)) => Type::BooleanUnion(Vec::new()),
        Some(Value::Integer(_) | Value::Decimal(_)) => {
            if literals.iter().any(|v| matches!(v, Value::Decimal(_))) {
                Type::DecimalUnion(Vec::new())
            } else {
                Type::IntegerUnion(Vec::new())
            }
        }
        _ => return Err(error()),
    };
    for literal in literals {
        let duplicate = match (&mut ty, literal) {
            (Type::TextUnion(values), Value::Text(value)) => insert(values, value),
            (Type::BooleanUnion(values), Value::Boolean(value)) => insert(values, value),
            (
                Type::IntegerUnion(values) | Type::DecimalUnion(values),
                value @ (Value::Integer(_) | Value::Decimal(_)),
            ) => insert(
                values,
                decimal_text(&value.rational().expect("number")).expect("finite literal"),
            ),
            _ => return Err(error()),
        };
        if duplicate {
            return Err(Diagnostic::new(
                "duplicate_literal",
                "literal union contains a repeated equal value",
                span,
            ));
        }
    }
    // The two-value boolean domain is exactly the ordinary boolean type.
    if matches!(&ty, Type::BooleanUnion(values) if values.len() == 2) {
        return Ok(Type::Boolean);
    }
    Ok(ty)
}

fn insert<T: Ord>(values: &mut Vec<T>, value: T) -> bool {
    match values.binary_search(&value) {
        Ok(_) => true,
        Err(at) => {
            values.insert(at, value);
            false
        }
    }
}

pub(crate) fn values(ty: &Type, span: &Span) -> Result<Vec<Value>> {
    match ty {
        Type::BooleanUnion(values) => Ok(values.iter().copied().map(Value::Boolean).collect()),
        Type::IntegerUnion(values) | Type::DecimalUnion(values) => {
            values.iter().map(|v| parse_number(v, span)).collect()
        }
        _ => unreachable!("finite scalar type"),
    }
}

pub(crate) fn validate(ty: &Type, span: &Span) -> Result<()> {
    let error = || {
        Diagnostic::new(
            "invalid_type",
            "finite scalar contract requires distinct canonical literals of its declared base",
            span,
        )
    };
    match ty {
        Type::BooleanUnion(values) => {
            if values.len() != 1 {
                return Err(error());
            }
        }
        Type::IntegerUnion(values) | Type::DecimalUnion(values) => {
            if values.is_empty() {
                return Err(error());
            }
            let mut seen = std::collections::BTreeSet::new();
            for text in values {
                let value = parse_number(text, span).map_err(|_| error())?;
                let canonical =
                    decimal_text(&value.rational().expect("number")).ok_or_else(error)?;
                if canonical != *text
                    || (ty.integer() && !matches!(value, Value::Integer(_)))
                    || !seen.insert(text)
                {
                    return Err(error());
                }
            }
        }
        _ => unreachable!("finite scalar type"),
    }
    Ok(())
}
