//! Branch-local presence/kind proofs and the mutable paths they protect.
use super::*;
use crate::expression::Op;

fn narrow(ty: &mut Type, fields: &[String], present: &Type) {
    if fields.is_empty() {
        *ty = present.clone();
        return;
    }
    match ty {
        Type::Record(record) => narrow(record.get_mut(&fields[0]).unwrap(), &fields[1..], present),
        Type::OneOf(kinds) => {
            for record in kinds.values_mut() {
                narrow(record.get_mut(&fields[0]).unwrap(), &fields[1..], present);
            }
        }
        _ => unreachable!("checked path with present optional ancestors"),
    }
}

fn apply(local: &mut Environment, path: &str, ty: Type) {
    let path: Vec<_> = path.split('.').map(str::to_string).collect();
    narrow(&mut local.get_mut(&path[0]).unwrap().ty, &path[1..], &ty);
}

fn facts(
    test: &Expression,
    truth: bool,
    local: &mut Environment,
    guards: &mut Vec<ProofGuard>,
) -> Result<()> {
    match &test.kind {
        Kind::Presence(inner, present) if *present == truth => {
            if let (Kind::Path { spelling, .. }, Type::Optional(ty)) = (&inner.kind, &inner.ty) {
                apply(local, spelling, (**ty).clone());
                guards.push(ProofGuard::Present(place(spelling, &inner.span, local)?));
            }
        }
        Kind::Binary(op @ (Op::Equal | Op::NotEqual), left, right) => {
            let pair = match (&left.kind, &right.kind) {
                (Kind::Path { spelling, .. }, Kind::Literal(Value::Text(kind))) => {
                    Some((spelling, kind, left))
                }
                (Kind::Literal(Value::Text(kind)), Kind::Path { spelling, .. }) => {
                    Some((spelling, kind, right))
                }
                _ => None,
            };
            if let Some((path, kind, original)) = pair {
                if let Some(parent) = path.strip_suffix(".kind") {
                    let location = place(parent, &original.span, local)?;
                    if let Some(ty) =
                        expression::select_kinds(&location.ty, kind, (*op == Op::Equal) == truth)
                    {
                        let Type::OneOf(kinds) = &ty else {
                            unreachable!("kind refinement")
                        };
                        let selected = kinds.keys().cloned().collect();
                        apply(local, parent, ty);
                        guards.push(ProofGuard::Kinds(
                            place(parent, &original.span, local)?,
                            selected,
                        ));
                    }
                }
            }
        }
        Kind::Unary(Op::Not, inner) => facts(inner, !truth, local, guards)?,
        Kind::Binary(Op::And, left, right) if truth => {
            facts(left, truth, local, guards)?;
            facts(right, truth, local, guards)?;
        }
        Kind::Binary(Op::Or, left, right) if !truth => {
            facts(left, truth, local, guards)?;
            facts(right, truth, local, guards)?;
        }
        _ => (),
    }
    Ok(())
}

pub(super) fn refine(
    condition: &BoundExpression,
    truth: bool,
    environment: &Environment,
) -> Result<(Environment, Vec<ProofGuard>)> {
    let mut local = environment.clone();
    let mut guards = Vec::new();
    facts(&condition.expression, truth, &mut local, &mut guards)?;
    Ok((local, guards))
}

fn location(guard: &ProofGuard) -> &Place {
    match guard {
        ProofGuard::Present(place) | ProofGuard::Kinds(place, _) => place,
    }
}

// Intersect successive restrictions within one path; alternatives are joined
// below by union. A normal body exit also carries its successful REQUIRE and
// nested-continuation proofs; their runtime guards protect them until that exit.
fn restrictions(guards: Vec<ProofGuard>) -> BTreeMap<(String, u8), ProofGuard> {
    let mut result: BTreeMap<_, ProofGuard> = BTreeMap::new();
    for guard in guards {
        let key = (
            location(&guard).spelling.clone(),
            u8::from(matches!(guard, ProofGuard::Kinds(..))),
        );
        if let (Some(ProofGuard::Kinds(_, previous)), ProofGuard::Kinds(_, selected)) =
            (result.get_mut(&key), &guard)
        {
            previous.retain(|kind| selected.contains(kind));
        } else {
            result.insert(key, guard);
        }
    }
    result
}

fn join(survivors: Vec<Vec<ProofGuard>>, environment: &mut Environment) -> Vec<ProofGuard> {
    let mut paths = survivors.into_iter();
    let Some(first) = paths.next() else {
        // All paths exit. Continue checking unreachable source without
        // manufacturing facts from an impossible state.
        return Vec::new();
    };
    let mut common = restrictions(first);
    for path in paths {
        let path = restrictions(path);
        common.retain(|key, guard| match (guard, path.get(key)) {
            (ProofGuard::Present(_), Some(ProofGuard::Present(_))) => true,
            (ProofGuard::Kinds(_, union), Some(ProofGuard::Kinds(_, selected))) => {
                union.extend(selected.iter().cloned());
                true
            }
            _ => false,
        });
    }
    let mut common: Vec<_> = common.into_values().collect();
    // Establish ancestors before children, and presence before kind at one path.
    common.sort_by_key(|guard| {
        let place = location(guard);
        (
            place.fields.len(),
            place.spelling.clone(),
            u8::from(matches!(guard, ProofGuard::Kinds(..))),
        )
    });
    let mut guards = Vec::new();
    for guard in common {
        let original = location(&guard);
        let Ok(current) = place(&original.spelling, &original.span, environment) else {
            // A FIND item, branch-local binding, or kind-specific path that is
            // not common to the joined parent cannot escape its scope.
            continue;
        };
        if current.slot != original.slot {
            continue;
        }
        match (guard, current.ty) {
            (ProofGuard::Present(_), Type::Optional(inner)) => {
                apply(environment, &current.spelling, *inner);
                let proven = place(&current.spelling, &current.span, environment)
                    .expect("refined checked presence path");
                guards.push(ProofGuard::Present(proven));
            }
            (ProofGuard::Kinds(_, allowed), Type::OneOf(mut variants)) => {
                let before = variants.len();
                variants.retain(|kind, _| allowed.contains(kind));
                if !variants.is_empty() && variants.len() < before {
                    let allowed = variants.keys().cloned().collect();
                    apply(environment, &current.spelling, Type::OneOf(variants));
                    let proven = place(&current.spelling, &current.span, environment)
                        .expect("refined checked kind path");
                    guards.push(ProofGuard::Kinds(proven, allowed));
                }
            }
            _ => (),
        }
    }
    guards
}

// These guards remain active through normal exit. Child-body proofs have
// already been joined into each statement's continuation guards; do not descend
// into arbitrary branches or possibly empty loops here. Local slots are removed
// by join when resolving the proof against the containing environment.
fn exit_facts(body: &[Statement], mut entry: Vec<ProofGuard>) -> Vec<ProofGuard> {
    for statement in body {
        if let StatementKind::Assert(_, guards) = &statement.kind {
            entry.extend(guards.iter().cloned());
        }
        entry.extend(statement.continuation_guards.iter().cloned());
    }
    entry
}

pub(super) fn continuation(
    statement: &StatementKind,
    environment: &mut Environment,
) -> Vec<ProofGuard> {
    let mut survivors = Vec::new();
    match statement {
        StatementKind::Branch {
            arms,
            otherwise,
            otherwise_guards,
            ..
        } => {
            for arm in arms {
                if !always_exits(&arm.body) {
                    survivors.push(exit_facts(&arm.body, arm.guards.clone()));
                }
            }
            if !always_exits(otherwise) {
                survivors.push(exit_facts(otherwise, otherwise_guards.clone()));
            }
        }
        StatementKind::Depending {
            location,
            arms,
            otherwise,
            ..
        } => {
            let Type::OneOf(kinds) = &location.ty else {
                unreachable!("checked kind dispatch")
            };
            for (kind, _, body) in arms {
                if !always_exits(body) {
                    survivors.push(exit_facts(
                        body,
                        vec![ProofGuard::Kinds(
                            location.clone(),
                            BTreeSet::from([kind.clone()]),
                        )],
                    ));
                }
            }
            if let Some((_, body)) = otherwise {
                if !always_exits(body) {
                    let remaining = kinds
                        .keys()
                        .filter(|kind| !arms.iter().any(|(selected, _, _)| kind == &selected))
                        .cloned()
                        .collect();
                    survivors.push(exit_facts(
                        body,
                        vec![ProofGuard::Kinds(location.clone(), remaining)],
                    ));
                }
            }
        }
        StatementKind::ValueDepending {
            arms, otherwise, ..
        } => {
            for (_, _, body) in arms {
                if !always_exits(body) {
                    survivors.push(exit_facts(body, Vec::new()));
                }
            }
            if let Some((_, body)) = otherwise {
                if !always_exits(body) {
                    survivors.push(exit_facts(body, Vec::new()));
                }
            }
        }
        StatementKind::Traverse {
            iteration,
            body,
            otherwise: Some((_, missing)),
        } => {
            if !always_exits(body) {
                survivors.push(exit_facts(body, iteration.guards.clone()));
            }
            if !always_exits(missing) {
                // No false filter proof: no match can also mean an empty list.
                survivors.push(exit_facts(missing, Vec::new()));
            }
        }
        _ => (),
    }
    join(survivors, environment)
}
