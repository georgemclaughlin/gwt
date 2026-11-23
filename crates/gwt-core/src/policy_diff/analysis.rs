//! Accept only checked operations whose outcome is constant inside a partition cell.
use super::{Axes, Axis, unsupported};
use crate::expression::{Expression, Kind, Op};
use crate::program::{
    Argument, BoundExpression, CompiledProgram, Initializer, Request, Statement, StatementKind,
};
use crate::source::{Result, Span};
use crate::value::{Type, Value};
use num_bigint::BigInt;
use std::collections::BTreeMap;

// Only input-derived aliases need tracking: every other accepted write is constant.
type Aliases = BTreeMap<usize, Vec<String>>;

pub(super) fn inputs(request: &Request) -> Result<Axes> {
    fn fields(axes: &mut Axes, path: Vec<String>, ty: &Type, span: &Span) -> Result<()> {
        let axis = match ty {
            Type::Integer => Axis::Integer(Default::default()),
            Type::Boolean => Axis::Boolean,
            Type::Record(fields_) if !fields_.is_empty() => {
                for (name, field) in fields_ {
                    let mut child = path.clone();
                    child.push(name.clone());
                    fields(axes, child, field, span)?;
                }
                return Ok(());
            }
            _ => {
                return Err(unsupported(
                    span,
                    "inputs must be integers, booleans, or records of those types",
                ));
            }
        };
        axes.insert(path, axis);
        if axes.len() > 32 {
            return Err(unsupported(span, "comparison exceeds 32 input fields"));
        }
        Ok(())
    }
    let mut axes = Axes::new();
    for (param, _) in &request.inputs {
        fields(&mut axes, vec![param.name.clone()], &param.ty, &param.span)?;
    }
    Ok(axes)
}

fn input_path(aliases: &Aliases, slot: usize, fields: &[String]) -> Option<Vec<String>> {
    let mut path = aliases.get(&slot)?.clone();
    path.extend_from_slice(fields);
    Some(path)
}

fn integer(expr: &Expression) -> Option<BigInt> {
    match &expr.kind {
        Kind::Literal(Value::Integer(value)) => Some(value.clone()),
        Kind::Unary(Op::Negate, inner) => integer(inner).map(|value| -value),
        _ => None,
    }
}

fn fixed(expr: &Expression) -> bool {
    matches!(expr.kind, Kind::Literal(_)) || integer(expr).is_some()
}

fn fixed_initializer(init: &Initializer) -> bool {
    match init {
        Initializer::Expression(e) => fixed(&e.expression),
        Initializer::Record(fields) => fields.iter().all(|(_, v)| fixed_initializer(v)),
        Initializer::Absent => true,
        Initializer::Table { .. } => false,
    }
}

// Boundaries are the first integers of new half-open bands. Equality isolates n.
fn threshold_cuts<T>(op: Op, reversed: bool, n: T, successor: T) -> (T, Option<T>) {
    match (op, reversed) {
        (Op::Equal | Op::NotEqual, _) => (n, Some(successor)),
        (Op::Less | Op::AtLeast, false) | (Op::Greater | Op::AtMost, true) => (n, None),
        (Op::Greater | Op::AtMost, false) | (Op::Less | Op::AtLeast, true) => (successor, None),
        _ => unreachable!("expected a comparison"),
    }
}

struct Scan<'a> {
    program: &'a CompiledProgram,
    axes: &'a mut Axes,
    calls: Vec<usize>,
    remaining: usize,
}

impl Scan<'_> {
    fn predicate(&mut self, bound: &BoundExpression, aliases: &Aliases) -> Result<()> {
        self.expr(&bound.expression, &bound.slots, aliases)
    }

    fn expr(&mut self, expr: &Expression, slots: &[usize], aliases: &Aliases) -> Result<()> {
        let path = |e: &Expression| match &e.kind {
            Kind::Path { slot, fields, .. } => input_path(aliases, slots[*slot], fields),
            _ => None,
        };
        match &expr.kind {
            _ if fixed(expr) => Ok(()),
            Kind::Path { .. } if path(expr).is_none() || expr.ty == Type::Boolean => Ok(()),
            Kind::Unary(Op::Not, inner) => self.expr(inner, slots, aliases),
            Kind::Binary(Op::And | Op::Or, l, r) => {
                self.expr(l, slots, aliases)?;
                self.expr(r, slots, aliases)
            }
            Kind::Binary(
                op @ (Op::Equal | Op::NotEqual | Op::Less | Op::AtMost | Op::Greater | Op::AtLeast),
                l,
                r,
            ) => {
                for (field, constant, reversed) in [(l, r, false), (r, l, true)] {
                    let Some(p) = path(field) else { continue };
                    let Some(Axis::Integer(starts)) = self.axes.get_mut(&p) else {
                        continue;
                    };
                    if let Some(n) = integer(constant) {
                        let successor = &n + 1;
                        let (first, second) = threshold_cuts(*op, reversed, n, successor);
                        starts.insert(first);
                        starts.extend(second);
                        // At most two cuts can coincide with the numeric domain edges.
                        if starts.len() > super::MAX_REGIONS + 1 {
                            return Err(unsupported(&expr.span, "partition exceeds 1024 regions"));
                        }
                        return Ok(());
                    }
                }
                self.expr(l, slots, aliases)?;
                self.expr(r, slots, aliases)
            }
            _ => Err(unsupported(
                &expr.span,
                "expected a Boolean flag, fixed value, or input integer compared with a literal threshold",
            )),
        }
    }

    fn body(&mut self, statements: &[Statement], aliases: &Aliases) -> Result<()> {
        for statement in statements {
            let span = &statement.span;
            self.remaining = self
                .remaining
                .checked_sub(1)
                .ok_or_else(|| unsupported(span, "expanded policy exceeds 4096 statements"))?;
            match &statement.kind {
                StatementKind::Pass => {}
                StatementKind::Assert(test, _) => self.predicate(test, aliases)?,
                StatementKind::Initialize { slot, value, .. }
                    if !aliases.contains_key(slot) && fixed_initializer(value) => {}
                StatementKind::InitializeField { place, value }
                    if !aliases.contains_key(&place.slot) && fixed_initializer(value) => {}
                StatementKind::Set { place, value }
                    if !aliases.contains_key(&place.slot) && fixed(&value.expression) => {}
                StatementKind::Branch {
                    arms, otherwise, ..
                } => {
                    for arm in arms {
                        self.predicate(&arm.condition, aliases)?;
                        self.body(&arm.body, aliases)?;
                    }
                    self.body(otherwise, aliases)?;
                }
                StatementKind::Call {
                    behavior,
                    arguments,
                    destination: None,
                } => {
                    if self.calls.contains(behavior) || self.calls.len() >= 64 {
                        return Err(unsupported(
                            span,
                            "recursive or deeply nested behavior calls",
                        ));
                    }
                    let mut callee = Aliases::new();
                    for (index, arg) in arguments.iter().enumerate() {
                        match arg {
                            Argument::Alias(place) => {
                                if let Some(path) = input_path(aliases, place.slot, &place.fields) {
                                    callee.insert(index, path);
                                }
                            }
                            Argument::Value(expr) if fixed(&expr.expression) => {}
                            _ => {
                                return Err(unsupported(
                                    span,
                                    "expected alias or literal call arguments",
                                ));
                            }
                        }
                    }
                    self.calls.push(*behavior);
                    self.body(&self.program.behaviors[*behavior].body, &callee)?;
                    self.calls.pop();
                }
                _ => {
                    return Err(unsupported(
                        span,
                        "expected constant assignments to local/output state, assertions, decisions, or behavior calls",
                    ));
                }
            }
        }
        Ok(())
    }
}

pub(super) fn analyze(program: &CompiledProgram, request: &Request, axes: &mut Axes) -> Result<()> {
    let aliases: Aliases = request
        .inputs
        .iter()
        .map(|(p, s)| (*s, vec![p.name.clone()]))
        .collect();
    if let Some((p, _)) = request
        .outputs
        .iter()
        .find(|(_, s)| aliases.contains_key(s))
    {
        return Err(unsupported(
            &p.span,
            "returning input-dependent values directly is unsupported",
        ));
    }
    let mut scan = Scan {
        program,
        axes,
        calls: vec![],
        remaining: 4096,
    };
    scan.body(&request.body, &aliases)?;
    scan.body(&request.postconditions, &aliases)
}

#[cfg(kani)]
mod proofs {
    use super::{Op, threshold_cuts};

    #[kani::proof]
    fn comparison_is_constant_between_its_cuts() {
        let (threshold, x, y): (i8, i8, i8) = kani::any();
        let [n, x, y] = [threshold, x, y].map(i16::from);
        let ops = [
            Op::Less,
            Op::AtMost,
            Op::Equal,
            Op::NotEqual,
            Op::AtLeast,
            Op::Greater,
        ];
        let index: usize = kani::any();
        kani::assume(index < ops.len());
        let op = ops[index];
        let reversed = kani::any();
        let (first, second) = threshold_cuts(op, reversed, n, n + 1);
        let same_side = |cut| (x < cut) == (y < cut);
        kani::assume(same_side(first) && second.is_none_or(same_side));
        let outcome = |input| {
            let (left, right) = if reversed { (n, input) } else { (input, n) };
            match op {
                Op::Less => left < right,
                Op::AtMost => left <= right,
                Op::Equal => left == right,
                Op::NotEqual => left != right,
                Op::AtLeast => left >= right,
                Op::Greater => left > right,
                _ => unreachable!(),
            }
        };
        assert_eq!(outcome(x), outcome(y));
        kani::cover!(
            x != y && reversed && outcome(x),
            "distinct inputs satisfying a reversed comparison"
        );
    }
}
