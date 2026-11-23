use gwt_core::{compare_policies, compile_file};
use serde_json::{Value, json};
use std::{error::Error, fmt::Write, path::Path};

pub(super) fn run(args: &[String]) -> Result<(bool, String), Box<dyn Error>> {
    let (baseline, candidate, flag, request, text) = match args {
        [a, b, flag, request] => (a, b, flag, request, false),
        [a, b, flag, request, mode] if mode == "--text" => (a, b, flag, request, true),
        _ => {
            return Err(
                "usage: gwt policy-diff BASELINE.gwt CANDIDATE.gwt --request NAME [--text]".into(),
            );
        }
    };
    if flag != "--request" {
        return Err("policy-diff requires --request NAME".into());
    }
    let compile = |file: &str| {
        compile_file(Path::new(file), None).map_err(|mut d| {
            d.message = format!("{file}: {}", d.message);
            d
        })
    };
    let result = compile(baseline)
        .and_then(|a| compile(candidate).and_then(|b| compare_policies(&a, &b, request)));
    match result {
        Ok(report) if text => Ok((true, summary(&report))),
        Ok(report) => Ok((true, report.to_string())),
        Err(d) if text => Ok((false, d.to_string())),
        Err(d) => Ok((
            false,
            json!({"kind":"gwt.policy-diff","schemaVersion":1,"ok":false,"diagnostic":d})
                .to_string(),
        )),
    }
}

fn summary(report: &Value) -> String {
    let mut out = format!(
        "{} — {} of {} regions changed",
        report["request"].as_str().unwrap(),
        report["changedRegions"],
        report["regionsCompared"]
    );
    for change in report["changes"].as_array().unwrap() {
        let conditions: Vec<_> = change["where"]
            .as_array()
            .unwrap()
            .iter()
            .map(|condition| {
                let field = condition["field"].as_str().unwrap();
                if let Some(flag) = condition["equals"].as_bool() {
                    return format!("{field} = {flag}");
                }
                match (condition["min"].as_str(), condition["max"].as_str()) {
                    (Some(lo), Some(hi)) if lo == hi => format!("{field} = {lo}"),
                    (Some(lo), Some(hi)) => format!("{lo} <= {field} <= {hi}"),
                    (None, Some(hi)) => format!("{field} <= {hi}"),
                    (Some(lo), None) => format!("{field} >= {lo}"),
                    (None, None) => format!("{field} (any integer)"),
                }
            })
            .collect();
        write!(
            out,
            "\n\n{}",
            if conditions.is_empty() {
                "All inputs".into()
            } else {
                conditions.join(" and ")
            }
        )
        .unwrap();
        for side in ["baseline", "candidate"] {
            write!(out, "\n  {side}  {}", change[side]).unwrap();
            for rule in change["rules"][side].as_array().unwrap() {
                let span = &rule["span"];
                let selected = match rule["operation"].as_str() {
                    Some("branch") => rule["value"]["selected"].as_bool(),
                    Some("assert") => rule["value"].as_bool(),
                    _ => None,
                };
                let suffix = selected.map(|b| format!(" -> {b}")).unwrap_or_default();
                write!(
                    out,
                    "\n    {}:{}  {}{}",
                    span["file"].as_str().unwrap(),
                    span["line"],
                    rule["text"]
                        .as_str()
                        .unwrap_or_else(|| rule["operation"].as_str().unwrap()),
                    suffix
                )
                .unwrap();
            }
        }
        for input in change["witnesses"].as_array().unwrap() {
            write!(out, "\n  witness  {input}").unwrap();
        }
    }
    out
}
