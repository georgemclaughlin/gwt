//! Checked, source-located record collection setup. Cells are ordinary expressions.
use super::{Environment, Initializer, assignable, expression_as};
use crate::{
    program_source::Node,
    scenario_source,
    source::{Diagnostic, Result, Span},
    value::Type,
};
use std::collections::BTreeSet;

pub(super) fn compile(
    item_type: &Type,
    nodes: &[Node],
    environment: &Environment,
    span: &Span,
) -> Result<Initializer> {
    let error = |code, message| Diagnostic::new(code, message, span);
    let Type::Record(fields) = item_type else {
        return Err(error(
            "table_type",
            "typed setup tables require a record item type",
        ));
    };
    let Some(header) = nodes.first() else {
        return Err(error(
            "table_header",
            "typed setup table requires a header; a header alone creates an empty list",
        ));
    };
    if nodes.len() > 1025 {
        return Err(error(
            "table_limit",
            "typed setup table supports at most 1024 rows",
        ));
    }
    let cells = |node: &Node| {
        scenario_source::cells(node).map_err(|mut error| {
            error.code = error.code.replace("examples_", "table_");
            error.message = error.message.replace("example", "table");
            error
        })
    };
    let columns = cells(header)?;
    if columns.len() > 256 || columns.len() * nodes.len().saturating_sub(1) > 16384 {
        return Err(error(
            "table_limit",
            "typed setup table exceeds 256 columns or 16384 data cells",
        ));
    }
    let mut names = BTreeSet::new();
    for column in &columns {
        if !fields.contains_key(&column.text) {
            return Err(Diagnostic::new(
                "table_header",
                format!("record has no field '{}'", column.text),
                &column.span,
            ));
        }
        if !names.insert(column.text.as_str()) {
            return Err(Diagnostic::new(
                "table_header",
                "table column is repeated",
                &column.span,
            ));
        }
    }
    for (name, ty) in fields {
        if !names.contains(name.as_str()) && !matches!(ty, Type::Optional(_)) {
            return Err(header.error("table_header", format!("table requires column '{name}'")));
        }
    }
    let mut rows = Vec::new();
    for row in nodes.iter().skip(1) {
        let values = cells(row)?;
        if values.len() != columns.len() {
            return Err(row.error(
                "table_columns",
                "table row must have the same number of cells as its header",
            ));
        }
        let mut initializers = Vec::new();
        for (column, cell) in columns.iter().zip(values) {
            let ty = &fields[&column.text];
            let value = expression_as(&cell.text, &cell.span, environment, Some(ty))?;
            assignable(ty, &value.expression)?;
            initializers.push((column.text.clone(), Initializer::Expression(value)));
        }
        for name in fields.keys().filter(|name| !names.contains(name.as_str())) {
            initializers.push((name.clone(), Initializer::Absent));
        }
        rows.push((row.span.clone(), Initializer::Record(initializers)));
    }
    Ok(Initializer::Table {
        item_type: item_type.clone(),
        rows,
    })
}
