use num_traits::Zero;
use serde::{Deserialize, Serialize};
use serde_json::Value as Json;

use crate::expression::{Expression, Kind, Op};
use crate::source::{Diagnostic, Result, Span};
use crate::value::{Value, checked_numeric};

#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Limits {
    pub steps: usize,
    pub evidence_bytes: usize,
    pub text_bytes: usize,
}
impl Default for Limits {
    fn default() -> Self {
        Self {
            steps: 4096,
            evidence_bytes: 1_048_576,
            text_bytes: 1_048_576,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct Event {
    pub sequence: usize,
    pub span: Span,
    pub operation: String,
    pub inputs: Vec<usize>,
    pub value: Json,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub skipped: Option<Span>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Evaluation {
    pub kind: &'static str,
    pub schema_version: u32,
    pub ok: bool,
    pub result: Option<Json>,
    pub diagnostic: Option<Diagnostic>,
    pub steps: usize,
    pub events: Vec<Event>,
}

pub(crate) struct Context {
    limits: Limits,
    pub(crate) steps: usize,
    evidence_bytes: usize,
    pub(crate) events: Vec<Event>,
}

pub(crate) fn evaluate(expression: &Expression, slots: &[Value], limits: Limits) -> Evaluation {
    let mut context = Context::new(limits);
    let result = context.eval(expression, &|slot, fields, span| {
        read_fields(&slots[slot], fields, span)
    });
    let (result, diagnostic) = match result {
        Ok((value, _)) => (Some(value.json()), None),
        Err(error) => (None, Some(error)),
    };
    Evaluation {
        kind: "gwt.native-expression",
        schema_version: 1,
        ok: diagnostic.is_none(),
        result,
        diagnostic,
        steps: context.steps,
        events: context.events,
    }
}

/// Traverse the checked path before cloning, so sibling fields are not copied.
/// Optional guards are handled by the evaluator before this function is called.
pub(crate) fn read_fields(value: &Value, fields: &[String], span: &Span) -> Result<Value> {
    let mut value = value;
    for field in fields {
        let Value::Record(record) = value else {
            return Err(Diagnostic::new(
                "internal_invariant",
                "checked path does not refer to a record",
                span,
            ));
        };
        value = record.get(field).ok_or_else(|| {
            Diagnostic::new(
                "internal_invariant",
                "checked field is missing from normalized record",
                span,
            )
        })?;
    }
    Ok(value.clone())
}

impl Context {
    pub(crate) fn new(limits: Limits) -> Self {
        Self {
            limits,
            steps: 0,
            evidence_bytes: 0,
            events: Vec::new(),
        }
    }
    pub(crate) fn charge(&mut self, span: &Span) -> Result<()> {
        if self.steps >= self.limits.steps {
            return Err(Diagnostic::new(
                "execution_limit",
                "execution step budget exceeded",
                span,
            ));
        }
        self.steps += 1;
        Ok(())
    }
    pub(crate) fn eval(
        &mut self,
        expression: &Expression,
        read: &impl Fn(usize, &[String], &Span) -> Result<Value>,
    ) -> Result<(Value, usize)> {
        if self.steps >= self.limits.steps {
            return Err(Diagnostic::new(
                "execution_limit",
                "expression step budget exceeded",
                &expression.span,
            ));
        }
        self.steps += 1;
        let mut inputs = Vec::new();
        let mut skipped = None;
        let (value, operation) = match &expression.kind {
            Kind::List(items) => {
                let crate::Type::List(item_type) = &expression.ty else {
                    unreachable!("checked list");
                };
                let mut values = Vec::new();
                let mut budget = crate::value::ValueBudget::new();
                for item in items {
                    let (value, event) = self.eval(item, read)?;
                    let value =
                        crate::value::normalize(item_type, Some(&value.json()), &item.span)?;
                    budget.include(&value, None, &item.span)?;
                    values.push(value);
                    inputs.push(event);
                }
                let value = Value::List(values);
                let value =
                    crate::value::normalize(&expression.ty, Some(&value.json()), &expression.span)?;
                (value, "list".into())
            }
            Kind::Literal(value) => (value.clone(), "literal".to_owned()),
            Kind::Path {
                slot,
                fields,
                spelling,
                ..
            } => (
                read(*slot, fields, &expression.span)?,
                format!("read {spelling}"),
            ),
            Kind::Unary(op, inner) => {
                let (value, event) = self.eval(inner, read)?;
                inputs.push(event);
                let value = match (op, value) {
                    (Op::Not, Value::Boolean(value)) => Value::Boolean(!value),
                    (Op::Negate, value) => checked_numeric(
                        -value.rational().expect("checked number"),
                        &expression.ty,
                        &expression.span,
                    )?,
                    _ => unreachable!("checked unary expression"),
                };
                (value, op.name().to_owned())
            }
            Kind::Presence(inner, present) => {
                let (value, event) = self.eval(inner, read)?;
                inputs.push(event);
                (
                    Value::Boolean((value != Value::Absent) == *present),
                    if *present { "is present" } else { "is absent" }.to_owned(),
                )
            }
            Kind::Binary(op, left, right) => {
                let (first, event) = self.eval(left, read)?;
                inputs.push(event);
                let short = matches!(
                    (op, &first),
                    (Op::And, Value::Boolean(false)) | (Op::Or, Value::Boolean(true))
                );
                if short {
                    skipped = Some(right.span.clone());
                    (first, op.name().to_owned())
                } else {
                    let (second, event) = self.eval(right, read)?;
                    inputs.push(event);
                    let value = self.binary(*op, first, second, expression)?;
                    (value, op.name().to_owned())
                }
            }
        };
        let sequence = self.record(&expression.span, operation, inputs, value.json(), skipped)?;
        Ok((value, sequence))
    }

    pub(crate) fn record(
        &mut self,
        span: &Span,
        operation: String,
        inputs: Vec<usize>,
        value: Json,
        skipped: Option<Span>,
    ) -> Result<usize> {
        let sequence = self.events.len() + 1;
        let event = Event {
            sequence,
            span: span.clone(),
            operation,
            inputs,
            value,
            skipped,
        };
        let bytes = serde_json::to_vec(&event)
            .expect("serializable event")
            .len();
        if bytes
            > self
                .limits
                .evidence_bytes
                .saturating_sub(self.evidence_bytes)
        {
            return Err(Diagnostic::new(
                "evidence_limit",
                "execution evidence exceeds the byte budget",
                span,
            ));
        }
        self.evidence_bytes += bytes;
        self.events.push(event);
        Ok(sequence)
    }

    fn binary(
        &mut self,
        op: Op,
        first: Value,
        second: Value,
        expression: &Expression,
    ) -> Result<Value> {
        let span = &expression.span;
        match op {
            Op::And | Op::Or => {
                let (Value::Boolean(a), Value::Boolean(b)) = (first, second) else {
                    unreachable!("checked booleans")
                };
                Ok(Value::Boolean(if op == Op::And { a && b } else { a || b }))
            }
            Op::Equal | Op::NotEqual => Ok(Value::Boolean(
                self.equal(&first, &second, span)? == (op == Op::Equal),
            )),
            Op::Contains => {
                let found = match (&first, &second) {
                    (Value::Text(a), Value::Text(b)) => a.contains(b),
                    (Value::List(items), value) => {
                        let mut found = false;
                        for item in items {
                            if self.steps >= self.limits.steps {
                                return Err(Diagnostic::new(
                                    "execution_limit",
                                    "collection scan exceeded the step budget",
                                    span,
                                ));
                            }
                            self.steps += 1;
                            if equal(item, value) {
                                found = true;
                                break;
                            }
                        }
                        found
                    }
                    _ => unreachable!("checked contains"),
                };
                Ok(Value::Boolean(found))
            }
            Op::Add if matches!(first, Value::Text(_)) => {
                let (Value::Text(mut a), Value::Text(b)) = (first, second) else {
                    unreachable!("checked text")
                };
                if a.len().saturating_add(b.len()) > self.limits.text_bytes {
                    return Err(Diagnostic::new(
                        "text_limit",
                        "text result exceeds the byte budget",
                        span,
                    ));
                }
                a.push_str(&b);
                Ok(Value::Text(a))
            }
            _ => {
                let a = first.rational().expect("checked number");
                let b = second.rational().expect("checked number");
                let number = match op {
                    Op::Greater => return Ok(Value::Boolean(a > b)),
                    Op::Less => return Ok(Value::Boolean(a < b)),
                    Op::AtLeast => return Ok(Value::Boolean(a >= b)),
                    Op::AtMost => return Ok(Value::Boolean(a <= b)),
                    Op::Add => a + b,
                    Op::Subtract => a - b,
                    Op::Multiply => a * b,
                    Op::Divide => {
                        if b.is_zero() {
                            return Err(Diagnostic::new(
                                "division_by_zero",
                                "division by zero",
                                span,
                            ));
                        }
                        a / b
                    }
                    _ => unreachable!("checked numeric expression"),
                };
                checked_numeric(number, &expression.ty, span)
            }
        }
    }

    fn equal(&mut self, first: &Value, second: &Value, span: &Span) -> Result<bool> {
        match (first, second) {
            (Value::List(a), Value::List(b)) => {
                if a.len() != b.len() {
                    return Ok(false);
                }
                for (a, b) in a.iter().zip(b) {
                    self.charge(span)?;
                    if !self.equal(a, b, span)? {
                        return Ok(false);
                    }
                }
                Ok(true)
            }
            (Value::Record(a), Value::Record(b)) => {
                if a.len() != b.len() {
                    return Ok(false);
                }
                for (key, a) in a {
                    self.charge(span)?;
                    let Some(b) = b.get(key) else {
                        return Ok(false);
                    };
                    if !self.equal(a, b, span)? {
                        return Ok(false);
                    }
                }
                Ok(true)
            }
            _ => Ok(equal(first, second)),
        }
    }
}

pub(crate) fn equal(first: &Value, second: &Value) -> bool {
    match (first.rational(), second.rational()) {
        (Some(first), Some(second)) => first == second,
        _ => first == second,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Type, compile_expression};
    use std::{cell::RefCell, collections::BTreeMap};

    #[test]
    fn literal_and_skipped_paths_do_not_request_bindings() {
        for source in [
            "true",
            "true or facts.value > 0",
            "false and facts.value > 0",
        ] {
            let compiled = compile_expression(
                source,
                "reads.gwt",
                BTreeMap::from([(
                    "facts".into(),
                    Type::Record(BTreeMap::from([("value".into(), Type::Integer)])),
                )]),
            )
            .unwrap();
            let mut context = Context::new(Limits::default());
            let (value, _) = context
                .eval(compiled.expression(), &|_, _, _| {
                    panic!("unused binding read")
                })
                .unwrap();
            assert_eq!(value.json(), !source.starts_with("false"));
            assert!(
                context
                    .events
                    .iter()
                    .all(|event| !event.operation.starts_with("read "))
            );
        }
    }

    #[test]
    fn guarded_paths_are_read_in_source_order_with_leaf_spans() {
        let source = "facts.extra is present and -facts.extra.value < facts.extra.value";
        let types = BTreeMap::from([
            ("archive".into(), Type::List(Box::new(Type::Integer))),
            (
                "facts".into(),
                Type::Record(BTreeMap::from([(
                    "extra".into(),
                    Type::Optional(Box::new(Type::Record(BTreeMap::from([(
                        "value".into(),
                        Type::Integer,
                    )])))),
                )])),
            ),
        ]);
        let compiled = compile_expression(source, "reads.gwt", types).unwrap();
        for present in [false, true] {
            let reads = RefCell::new(Vec::new());
            let root = Value::Record(BTreeMap::from([(
                "extra".into(),
                if present {
                    Value::Record(BTreeMap::from([("value".into(), Value::Integer(3.into()))]))
                } else {
                    Value::Absent
                },
            )]));
            let mut context = Context::new(Limits::default());
            let (value, _) = context
                .eval(compiled.expression(), &|slot, fields, span| {
                    assert_eq!(slot, 1, "the unrelated archive must never be read");
                    let spelling = format!("facts.{}", fields.join("."));
                    assert_eq!(&source[span.start..span.end], spelling);
                    reads.borrow_mut().push(spelling);
                    read_fields(&root, fields, span)
                })
                .unwrap();
            assert_eq!(value.json(), present);
            assert_eq!(
                *reads.borrow(),
                if present {
                    vec!["facts.extra", "facts.extra.value", "facts.extra.value"]
                } else {
                    vec!["facts.extra"]
                }
            );
            let evidence: Vec<_> = context
                .events
                .iter()
                .filter_map(|event| event.operation.strip_prefix("read "))
                .collect();
            assert_eq!(evidence, *reads.borrow());
        }
    }

    #[test]
    fn execution_budget_is_checked_before_reading_paths() {
        let compiled = compile_expression(
            "amount + 1",
            "reads.gwt",
            BTreeMap::from([("amount".into(), Type::Integer)]),
        )
        .unwrap();
        for steps in [0, 1] {
            let mut context = Context::new(Limits {
                steps,
                ..Limits::default()
            });
            let error = context
                .eval(compiled.expression(), &|_, _, _| {
                    panic!("read after budget exhaustion")
                })
                .unwrap_err();
            assert_eq!(error.code, "execution_limit");
            assert_eq!(context.steps, steps);
            assert!(context.events.is_empty());
        }
    }
}
