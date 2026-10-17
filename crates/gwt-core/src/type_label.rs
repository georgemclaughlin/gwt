//! Bounded, language-facing type descriptions shared by navigation and errors.
use crate::value::Type;

// Keep even large structural types readable without unbounded hover output.
pub(crate) fn type_label(ty: &Type) -> String {
    label(ty, false)
}

pub(crate) fn contract_label(ty: &Type) -> String {
    label(ty, true)
}

fn label(ty: &Type, detailed: bool) -> String {
    fn render(ty: &Type, out: &mut String, detailed: bool, depth: usize) {
        if out.len() >= 1024 {
            return;
        }
        if depth > 64 {
            out.push('…');
            return;
        }
        match ty {
            Type::Boolean => out.push_str("boolean"),
            Type::Integer => out.push_str("integer"),
            Type::Decimal => out.push_str("decimal"),
            Type::Text => out.push_str("text"),
            Type::TextUnion(values) => {
                for (index, value) in values.iter().enumerate() {
                    if out.len() >= 1024 {
                        break;
                    }
                    if index > 0 {
                        out.push_str(" | ");
                    }
                    out.push('"');
                    for c in value.chars() {
                        if out.len() >= 1024 {
                            break;
                        }
                        out.extend(c.escape_debug());
                    }
                    out.push('"');
                }
            }
            Type::IntegerUnion(values) | Type::DecimalUnion(values) => {
                for (index, value) in values.iter().enumerate() {
                    if out.len() >= 1024 {
                        break;
                    }
                    if index > 0 {
                        out.push_str(" | ");
                    }
                    out.push_str(value);
                    if ty.decimal() && !value.contains('.') {
                        out.push_str(".0");
                    }
                }
            }
            Type::BooleanUnion(values) => {
                for (index, value) in values.iter().enumerate() {
                    if index > 0 {
                        out.push_str(" | ");
                    }
                    out.push_str(if *value { "true" } else { "false" });
                }
            }
            Type::List(inner) | Type::Optional(inner) => {
                out.push_str(if matches!(ty, Type::List(_)) {
                    "list<"
                } else {
                    "optional<"
                });
                render(inner, out, detailed, depth + 1);
                out.push('>');
            }
            Type::Record(fields) => {
                out.push_str("record { ");
                for (index, (name, ty)) in fields.iter().enumerate() {
                    if out.len() >= 1024 {
                        break;
                    }
                    if index > 0 {
                        out.push_str(", ");
                    }
                    out.extend(name.chars().take(128));
                    if name.len() > 128 {
                        out.push('…');
                    }
                    out.push_str(": ");
                    render(ty, out, detailed, depth + 1);
                }
                out.push_str(" }");
            }
            Type::OneOf(kinds) => {
                out.push_str("one of { ");
                for (index, (name, fields)) in kinds.iter().enumerate() {
                    if out.len() >= 1024 {
                        break;
                    }
                    if index > 0 {
                        out.push_str(", ");
                    }
                    out.extend(name.chars().take(128));
                    if name.len() > 128 {
                        out.push('…');
                    }
                    if detailed {
                        out.push_str(": { ");
                        for (index, (field, ty)) in fields.iter().enumerate() {
                            if out.len() >= 1024 {
                                break;
                            }
                            if index > 0 {
                                out.push_str(", ");
                            }
                            out.extend(field.chars().take(128));
                            if field.len() > 128 {
                                out.push('…');
                            }
                            out.push_str(": ");
                            render(ty, out, detailed, depth + 1);
                        }
                        out.push_str(" }");
                    }
                }
                out.push_str(" }");
            }
        }
    }
    let mut label = String::new();
    render(ty, &mut label, detailed, 0);
    if label.len() >= 1024 {
        let mut end = 1024;
        while !label.is_char_boundary(end) {
            end -= 1;
        }
        label.truncate(end);
        label.push('…');
    }
    label
}

/// A presence hint is applicable only when the optional value contains a record.
pub(crate) fn field_access_message(ty: &Type, path: &str, field: &str) -> String {
    if matches!(ty, Type::Optional(inner) if matches!(inner.as_ref(), Type::Record(_) | Type::OneOf(_)))
    {
        format!(
            "cannot access field '{field}' through optional path '{path}'; establish '{path} is present' before accessing fields"
        )
    } else {
        format!(
            "cannot access field '{field}' from '{path}' ({}); field access requires a record",
            contract_label(ty)
        )
    }
}
