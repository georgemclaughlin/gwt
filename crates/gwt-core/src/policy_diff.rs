//! Compare declared request outputs and domain rejections on constant-outcome regions.
mod analysis;
mod partition;

use crate::ProgramLimits;
use crate::program::{CompiledProgram, Request};
use crate::source::{Diagnostic, Result, Span};
use num_bigint::BigInt;
use serde_json::{Value as Json, json};
use std::collections::{BTreeMap, BTreeSet};

#[derive(PartialEq, Eq)]
enum Axis {
    Boolean,
    Integer(BTreeSet<BigInt>),
}
const MAX_REGIONS: usize = 1024;
type Axes = BTreeMap<Vec<String>, Axis>;

fn unsupported(span: &Span, reason: &str) -> Diagnostic {
    Diagnostic::new("policy_diff_unsupported", reason, span)
}

fn request<'a>(program: &'a CompiledProgram, name: &str) -> Result<&'a Request> {
    program
        .requests
        .iter()
        .find(|r| r.name == name)
        .ok_or_else(|| {
            Diagnostic::new(
                "unknown_request",
                format!("unknown request '{name}'"),
                &program.span,
            )
        })
}

fn revision<T>(side: &str, result: Result<T>) -> Result<T> {
    result.map_err(|mut diagnostic| {
        diagnostic.message = format!("{side}: {}", diagnostic.message);
        diagnostic
    })
}

struct Observation {
    outcome: Json,
    rules: Vec<Json>,
}

fn observe(
    program: &CompiledProgram,
    name: &str,
    input: &Json,
    trace: bool,
) -> Result<Observation> {
    let run = program.run_request(name, input, ProgramLimits::default());
    let outcome = match run.diagnostic {
        None => json!({"output":run.result}),
        Some(d) if d.code == "assertion_failed" => json!({"rejection":d.code}),
        Some(d) => {
            return Err(Diagnostic::new(
                "policy_diff_inconclusive",
                format!("witness execution stopped: {}: {}", d.code, d.message),
                &d.span,
            ));
        }
    };
    let rules = run
        .events
        .into_iter()
        .filter(|e| {
            trace
                && matches!(
                    e.operation.as_str(),
                    "branch" | "else selected" | "set" | "assert"
                )
        })
        .map(|e| {
            let text = program.source_bundle().and_then(|bundle| {
                bundle
                    .modules
                    .get(&e.span.file)?
                    .get(e.span.start..e.span.end)
            });
            json!({"operation":e.operation,"span":e.span,"text":text,"value":e.value})
        })
        .collect();
    Ok(Observation { outcome, rules })
}

/// Compare one request in two compiled revisions using their common normalized input domain.
pub fn compare_policies(
    baseline: &CompiledProgram,
    candidate: &CompiledProgram,
    name: &str,
) -> Result<Json> {
    let before = revision("baseline", request(baseline, name))?;
    let after = revision("candidate", request(candidate, name))?;
    let mut axes = revision("baseline", analysis::inputs(before))?;
    if axes != revision("candidate", analysis::inputs(after))? {
        return Err(unsupported(&after.span, "request input contracts differ"));
    }
    revision("baseline", analysis::analyze(baseline, before, &mut axes))?;
    revision("candidate", analysis::analyze(candidate, after, &mut axes))?;
    let partition = partition::Partition::new(axes, &before.span)?;
    let mut changes = vec![];
    let mut report_bytes = 0;
    for i in 0..partition.count {
        let cell = partition.cell(i);
        let old = revision("baseline", observe(baseline, name, &cell.witness, true))?;
        let new = revision("candidate", observe(candidate, name, &cell.witness, true))?;
        let changed = old.outcome != new.outcome;
        let mut witnesses = vec![&cell.witness];
        // A large integer can cost more evidence bytes than a compact witness.
        // Check the coordinate-wise widest input even for an unchanged region.
        let mut checks = Vec::new();
        if cell.longest != cell.witness {
            checks.push(&cell.longest);
        }
        if changed && cell.edge != cell.witness && cell.edge != cell.longest {
            checks.push(&cell.edge);
        }
        for input in checks {
            if old.outcome != revision("baseline", observe(baseline, name, input, false))?.outcome
                || new.outcome
                    != revision("candidate", observe(candidate, name, input, false))?.outcome
            {
                return Err(Diagnostic::new(
                    "policy_diff_inconclusive",
                    "native outcomes varied inside a proposed region",
                    &before.span,
                ));
            }
        }
        if changed {
            if cell.edge != cell.witness {
                witnesses.push(&cell.edge);
            }
            let change = json!({"where":cell.conditions, "baseline":old.outcome, "candidate":new.outcome,
                "witnesses":witnesses,"rules":{"baseline":old.rules,"candidate":new.rules}});
            report_bytes += serde_json::to_vec(&change).expect("JSON change").len();
            if report_bytes > 8 * 1024 * 1024 {
                return Err(unsupported(&before.span, "change report exceeds eight MiB"));
            }
            changes.push(change);
        }
    }
    Ok(
        json!({"kind":"gwt.policy-diff","schemaVersion":1,"ok":true,"request":name,
        "baseline":baseline.identity(),"candidate":candidate.identity(),"integerDigits":crate::value::MAX_DIGITS,
        "regionsCompared":partition.count,"changedRegions":changes.len(),"changes":changes}),
    )
}
