use super::*;

// Narrow only the selected source path. Other aliases retain their declared
// contracts; runtime address guards protect the selected kind across calls.
fn narrow(ty: &mut Type, fields: &[String], kinds: &BTreeSet<String>) {
    if fields.is_empty() {
        let Type::OneOf(variants) = ty else {
            unreachable!("checked one-of path")
        };
        variants.retain(|kind, _| kinds.contains(kind));
    } else {
        match ty {
            Type::Record(record) => {
                narrow(record.get_mut(&fields[0]).unwrap(), &fields[1..], kinds)
            }
            Type::OneOf(variants) => {
                for record in variants.values_mut() {
                    narrow(record.get_mut(&fields[0]).unwrap(), &fields[1..], kinds);
                }
            }
            _ => unreachable!("checked record path"),
        }
    }
}

pub(super) fn compile(
    compiler: &mut Compiler,
    node: &Node,
    environment: &Environment,
    slots: &mut usize,
    return_type: Option<&Type>,
) -> Result<StatementKind> {
    let (text, span) = node.tail("DEPENDING ON ".len())?;
    let subject = expression(text, &span, environment)?;
    if !matches!(subject.expression.ty, Type::OneOf(_)) {
        return compile_values(compiler, node, subject, environment, slots, return_type);
    }
    let Type::OneOf(kinds) = &subject.expression.ty else {
        return Err(node.error(
            "depending_type",
            "native kind dispatch requires a one-of record",
        ));
    };
    if !matches!(&subject.expression.kind, Kind::Path { spelling, .. } if spelling == text) {
        return Err(node.error(
            "depending_path",
            "kind dispatch requires an explicit state path",
        ));
    }
    let location = place(text, &span, environment)?;
    let root = text.split('.').next().unwrap();
    let mut seen = BTreeSet::new();
    let mut arms = Vec::new();
    let mut otherwise = None;
    for branch in &node.children {
        if otherwise.is_some() {
            return Err(branch.error("depending_order", "ELSE must be the final kind branch"));
        }
        if branch.children.is_empty() {
            return Err(branch.error("empty_block", "kind branch requires a body"));
        }
        let (selected, kind) = if let Some(kind) = branch.text.strip_prefix("WHEN the kind is ") {
            program_source::name(kind, &branch.span)?;
            if !kinds.contains_key(kind) {
                return Err(branch.error("one_of_kind", format!("unknown kind '{kind}'")));
            }
            if !seen.insert(kind.to_string()) {
                return Err(branch.error("duplicate_kind", "kind branch is repeated"));
            }
            (BTreeSet::from([kind.to_string()]), Some(kind))
        } else if branch.text == "ELSE" {
            let remaining: BTreeSet<_> = kinds
                .keys()
                .filter(|k| !seen.contains(*k))
                .cloned()
                .collect();
            if remaining.is_empty() {
                return Err(branch.error(
                    "unreachable_else",
                    "all declared kinds already have branches",
                ));
            }
            (remaining, None)
        } else {
            return Err(branch.error(
                "depending_branch",
                "expected WHEN the kind is name or a final ELSE",
            ));
        };
        let mut local = environment.clone();
        narrow(
            &mut local.get_mut(root).unwrap().ty,
            &location.fields,
            &selected,
        );
        let body = compiler.body(&branch.children, &mut local, slots, return_type)?;
        if let Some(kind) = kind {
            arms.push((kind.into(), branch.span.clone(), body));
        } else {
            otherwise = Some((branch.span.clone(), body));
        }
    }
    if arms.is_empty() || (otherwise.is_none() && seen.len() != kinds.len()) {
        return Err(node.error(
            "incomplete_depending",
            "cover every declared kind or provide a final ELSE",
        ));
    }
    Ok(StatementKind::Depending {
        subject,
        location,
        arms,
        otherwise,
    })
}

// Numeric keys use the same exact value equality as native ==, including
// integer/decimal equality. Text and booleans remain distinct categories.
fn literal_key(value: &Value) -> (u8, String) {
    match value {
        Value::Boolean(value) => (0, value.to_string()),
        Value::Text(value) => (1, value.clone()),
        Value::Integer(_) | Value::Decimal(_) => (2, value.rational().unwrap().to_string()),
        _ => unreachable!("checked scalar literal"),
    }
}

fn compile_values(
    compiler: &mut Compiler,
    node: &Node,
    subject: BoundExpression,
    environment: &Environment,
    slots: &mut usize,
    return_type: Option<&Type>,
) -> Result<StatementKind> {
    let ty = &subject.expression.ty;
    let finite: Option<BTreeSet<_>> = match ty {
        Type::Boolean => Some(
            [false, true]
                .map(|v| literal_key(&Value::Boolean(v)))
                .into(),
        ),
        Type::TextUnion(values) => Some(
            values
                .iter()
                .map(|v| literal_key(&Value::Text(v.clone())))
                .collect(),
        ),
        Type::IntegerUnion(_) | Type::DecimalUnion(_) | Type::BooleanUnion(_) => Some(
            crate::literal_types::values(ty, &node.span)?
                .iter()
                .map(literal_key)
                .collect(),
        ),
        Type::Integer | Type::Decimal | Type::Text => None,
        _ => {
            return Err(node.error(
                "depending_type",
                "DEPENDING ON requires a scalar value or a one-of record",
            ));
        }
    };
    let mut seen = BTreeSet::new();
    let mut arms = Vec::new();
    let mut otherwise = None;
    for branch in &node.children {
        if otherwise.is_some() {
            return Err(branch.error("depending_order", "ELSE must be the final value branch"));
        }
        if branch.children.is_empty() {
            return Err(branch.error("empty_block", "value branch requires a body"));
        }
        if branch.text == "ELSE" {
            if finite.as_ref().is_some_and(|values| values == &seen) {
                return Err(branch.error(
                    "unreachable_else",
                    "all possible values already have branches",
                ));
            }
            otherwise = Some((
                branch.span.clone(),
                compiler.body(
                    &branch.children,
                    &mut environment.clone(),
                    slots,
                    return_type,
                )?,
            ));
            continue;
        }
        if !branch.text.starts_with("WHEN the value is ") {
            return Err(branch.error(
                "depending_branch",
                "expected WHEN the value is literal or a final ELSE",
            ));
        }
        let (text, span) = branch.tail("WHEN the value is ".len())?;
        let literal = expression(text, &span, &Environment::new())?;
        let value = expression::scalar_literal(&literal.expression).ok_or_else(|| {
            branch.error(
                "depending_literal",
                "value branches require a scalar literal, optionally with a numeric minus sign",
            )
        })?;
        if !ty.comparable(&literal.expression.ty) {
            return Err(branch.error(
                "depending_value_type",
                "branch literal is not comparable with the subject type",
            ));
        }
        let key = literal_key(&value);
        if finite.as_ref().is_some_and(|values| !values.contains(&key))
            || (ty.integer() && !value.rational().unwrap().is_integer())
        {
            return Err(branch.error(
                "unreachable_value",
                "branch literal is outside the subject's possible values",
            ));
        }
        if !seen.insert(key) {
            return Err(branch.error("duplicate_value", "branch literal repeats an equal value"));
        }
        arms.push((
            value,
            branch.span.clone(),
            compiler.body(
                &branch.children,
                &mut environment.clone(),
                slots,
                return_type,
            )?,
        ));
    }
    if arms.is_empty()
        || (otherwise.is_none() && finite.as_ref().is_none_or(|values| values != &seen))
    {
        return Err(node.error(
            "incomplete_depending",
            "cover every possible finite value, or provide a final ELSE",
        ));
    }
    Ok(StatementKind::ValueDepending {
        subject,
        arms,
        otherwise,
    })
}
