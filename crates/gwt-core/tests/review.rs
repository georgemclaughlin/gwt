use gwt_core::{
    Corpus, CorpusEntry, ExecutionCase, ProgramLimits, SourceBundle, capture_request,
    compile_bundle, explain_execution, render_review_html, review_corpus,
};
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
};

const BEFORE: &str = include_str!("../../../examples/refund_review/stage0.gwt");
const AFTER: &str = include_str!("../../../examples/refund_review/stage1.gwt");
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
fn facts(damaged: bool, receipt: bool) -> Json {
    json!({"facts":{"days":10,"damaged":damaged,"receipt":receipt,"clearance":false,"member":false}})
}
fn captured(source: &str, input: &Json) -> Json {
    json!(
        capture_request(
            &program(source),
            "assess refund",
            input,
            ProgramLimits::default()
        )
        .unwrap()
    )
}
fn entry(id: &str, case: Json) -> CorpusEntry {
    CorpusEntry {
        id: id.into(),
        label: id.into(),
        case,
    }
}
fn resign(mut case: Json) -> Json {
    case.as_object_mut().unwrap().remove("integrity");
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-case-sha256-v1\0");
    hash.update(serde_json::to_vec(&case).unwrap());
    case["integrity"] = json!(format!("sha256:{:x}", hash.finalize()));
    case
}
fn mixed_corpus() -> Corpus {
    let good = captured(BEFORE, &facts(true, false));
    let mut mismatch = good.clone();
    mismatch["record"]["observed"]["result"]["decision"]["reason"] = json!("forged");
    let mut corrupt = good.clone();
    corrupt["integrity"] = json!("corrupted");
    let mut engine = good.clone();
    engine["record"]["engine"]["profile"] = json!("different-engine");
    Corpus::new(vec![
        entry("changed", good),
        entry("preserved", captured(BEFORE, &facts(false, true))),
        entry("mismatch", resign(mismatch)),
        entry("corrupt", corrupt),
        entry("engine", resign(engine)),
        entry("invalid", Json::Null),
        entry("failure", captured(BEFORE, &json!({}))),
    ])
    .unwrap()
}

#[test]
fn corpus_retains_every_case_and_reconciles_failures_without_false_success() {
    let report = review_corpus(&mixed_corpus(), &program(AFTER)).unwrap();
    assert!(!report.complete);
    assert_eq!(report.totals.total, 7);
    assert_eq!(report.totals.compared, 3);
    assert_eq!(report.totals.baseline_mismatch, 1);
    assert_eq!(report.totals.unavailable, 3);
    assert_eq!(report.totals.candidate_failed, 1);
    assert_eq!(report.totals.outcome_changed, 1);
    assert_eq!(
        report.totals.total,
        report.totals.compared + report.totals.baseline_mismatch + report.totals.unavailable
    );
    assert_eq!(
        report
            .cases
            .iter()
            .map(|row| row.id.as_str())
            .collect::<Vec<_>>(),
        [
            "changed",
            "preserved",
            "mismatch",
            "corrupt",
            "engine",
            "invalid",
            "failure"
        ]
    );
    let mismatch = &report.cases[2];
    assert_eq!(mismatch.baseline_source, report.cases[0].baseline_source);
    assert_eq!(mismatch.status, "baseline_mismatch");
    assert!(mismatch.comparison.as_ref().unwrap().candidate.is_none());
    assert!(mismatch.baseline_explanation.is_none());
    for row in &report.cases[3..6] {
        assert_eq!(row.status, "unavailable");
        assert!(row.comparison.is_none());
        assert!(row.diagnostic.is_some());
    }
    assert_eq!(report.sources.len(), 2);
    assert!(report.cases[0].candidate_explanation.as_ref().unwrap().ok);
    assert!(!report.cases[6].candidate_explanation.as_ref().unwrap().ok);
}

#[test]
fn identical_and_mixed_baselines_keep_their_own_source_snapshots() {
    let corpus = Corpus::new(vec![
        entry("old", captured(BEFORE, &facts(true, false))),
        entry("current", captured(AFTER, &facts(true, false))),
    ])
    .unwrap();
    let report = review_corpus(&corpus, &program(AFTER)).unwrap();
    assert!(report.complete);
    assert_eq!(report.totals.compared, 2);
    assert_eq!(report.totals.unchanged, 1);
    assert_eq!(report.cases[0].status, "outcome_changed");
    assert_eq!(report.cases[1].status, "unchanged");
    assert_ne!(
        report.cases[0].baseline_source,
        report.cases[1].baseline_source
    );
    assert_eq!(
        report.cases[1].baseline_source.as_ref().unwrap(),
        &report.candidate_identity.digest
    );
}

#[test]
fn explanations_preserve_actual_conditions_skips_writes_and_operands() {
    let program = program(AFTER);
    let execution = program.run_request(
        "assess refund",
        &facts(true, false),
        ProgramLimits::default(),
    );
    let explanation = explain_execution(&execution, program.source_bundle().unwrap()).unwrap();
    assert_eq!(explanation.steps.len(), execution.events.len());
    let selected = explanation
        .steps
        .iter()
        .find(|step| step.operation == "branch" && step.value["selected"] == true)
        .unwrap();
    assert_eq!(selected.source.text, "facts.damaged");
    assert_eq!(selected.summary, "Condition matched; branch selected.");
    for step in explanation
        .steps
        .iter()
        .filter(|step| step.operation == "branch skipped")
    {
        assert_eq!(step.summary, "Branch was not evaluated.");
        assert!(step.value.is_null());
        assert!(step.operands.is_empty());
        assert!(step.skipped.is_some());
    }
    let write = explanation
        .steps
        .iter()
        .find(|step| step.operation == "set" && step.value["path"] == "decision.status")
        .unwrap();
    assert_eq!(write.value["before"], "rejected");
    assert_eq!(write.value["after"], "approved");
    for step in &explanation.steps {
        assert_eq!(
            step.source.text,
            program.source_bundle().unwrap().modules[&step.source.span.file]
                [step.source.span.start..step.source.span.end]
        );
        assert!(step.operands.iter().all(|id| *id > 0 && *id < step.event));
    }
    assert!(explanation.steps.iter().any(|step| {
        step.operation == "enter behavior"
            && step
                .definition
                .as_ref()
                .unwrap()
                .text
                .starts_with("WHEN assess")
    }));
}

#[test]
fn explanation_rejects_invalid_source_positions_dependencies_and_condition_values() {
    let program = program(AFTER);
    let source = program.source_bundle().unwrap();
    let run = || {
        program.run_request(
            "assess refund",
            &facts(true, false),
            ProgramLimits::default(),
        )
    };
    let mut execution = run();
    execution.events[0].span.start = usize::MAX;
    assert_eq!(
        explain_execution(&execution, source).unwrap_err().code,
        "evidence_source"
    );
    let mut execution = run();
    execution.events[0].span.column += 1;
    assert_eq!(
        explain_execution(&execution, source).unwrap_err().code,
        "evidence_source"
    );
    let mut execution = run();
    execution.events[0].inputs = vec![1];
    assert_eq!(
        explain_execution(&execution, source).unwrap_err().code,
        "evidence_dependency"
    );
    let mut execution = run();
    execution
        .events
        .iter_mut()
        .find(|event| event.operation == "branch")
        .unwrap()
        .value = json!({"selected":"yes"});
    assert_eq!(
        explain_execution(&execution, source).unwrap_err().code,
        "evidence_value"
    );
    let other = super_program();
    assert_eq!(
        explain_execution(&run(), other.source_bundle().unwrap())
            .unwrap_err()
            .code,
        "evidence_source"
    );
}
fn super_program() -> gwt_core::CompiledProgram {
    program(&format!("# different bytes\n{AFTER}"))
}

#[test]
fn corpus_validation_prevents_ambiguous_or_empty_coverage() {
    assert!(Corpus::new(vec![]).is_err());
    assert_eq!(
        Corpus::new(vec![entry("same", Json::Null), entry("same", Json::Null)])
            .unwrap_err()
            .code,
        "corpus_duplicate"
    );
    assert_eq!(
        Corpus::new(
            (0..257)
                .map(|i| entry(&i.to_string(), Json::Null))
                .collect()
        )
        .unwrap_err()
        .code,
        "corpus_limit"
    );
    assert_eq!(
        Corpus::new(vec![entry("", Json::Null)]).unwrap_err().code,
        "corpus_format"
    );
    assert_eq!(
        Corpus::from_json(r#"{"kind":"gwt.native-corpus","schemaVersion":2,"cases":[]}"#)
            .unwrap_err()
            .code,
        "corpus_version"
    );
    assert_eq!(
        Corpus::from_json(
            r#"{"kind":"gwt.native-corpus","schemaVersion":1,"cases":[],"extra":true}"#
        )
        .unwrap_err()
        .code,
        "corpus_format"
    );
    let mut value = Json::Null;
    for _ in 0..100 {
        value = json!([value]);
    }
    assert_eq!(
        Corpus::new(vec![entry("deep", value)]).unwrap_err().code,
        "case_limit"
    );
}

#[test]
fn html_escapes_source_and_labels_and_preserves_exact_integer_tokens() {
    let source = format!(
        "# </script><script>globalThis.injected=true</script>\n{}",
        include_str!("fixtures/invoice.gwt")
    );
    let program = program(&source);
    let input = json!({"invoice":{"quantity":9007199254740993_i64,"unit_price":"0"}});
    let case =
        capture_request(&program, "price invoice", &input, ProgramLimits::default()).unwrap();
    let corpus = Corpus::new(vec![entry("<img src=x onerror=alert(1)>", json!(case))]).unwrap();
    let report = review_corpus(&corpus, &program).unwrap();
    let html = render_review_html(&report).unwrap();
    assert!(!html.contains("<img src=x"));
    assert!(!html.contains("<script>globalThis.injected"));
    assert!(html.contains("&lt;img src=x"));
    assert!(html.contains("9007199254740993"));
    let data = html
        .split("<script type=application/json id=review-data>")
        .nth(1)
        .unwrap()
        .split("</script>")
        .next()
        .unwrap();
    let saved: Json = serde_json::from_str(data).unwrap();
    assert_eq!(
        saved["cases"][0]["input"]["invoice"]["quantity"],
        json!(9007199254740993_i64)
    );
    assert_eq!(saved, json!(report));
    assert!(html.contains("data-operand"));
    assert!(html.contains("data-all-events"));
    // The decision metadata contains only strings and a small schema version;
    // parsing it must remain separate from the exact-value review download.
    let decisions = html
        .split("<script type=application/json id=decision-data>")
        .nth(1)
        .unwrap()
        .split("</script>")
        .next()
        .unwrap();
    let pending = gwt_core::ReviewDecisions::from_json(decisions).unwrap();
    let assessment = gwt_core::assess_decisions(&report, &pending).unwrap();
    assert_eq!(assessment.pending, 1);
    assert!(!assessment.all_accepted);
}

#[test]
fn every_independent_refund_probe_has_a_review_row_and_source_backed_explanation() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../evaluations/maintenance");
    let manifest: Json =
        serde_json::from_str(&fs::read_to_string(root.join("manifest.json")).unwrap()).unwrap();
    let mut total = 0;
    for task in manifest["cases"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| task["kind"] == "maintain")
    {
        let before_source =
            fs::read_to_string(root.join(task["starter"]["gwt"].as_str().unwrap())).unwrap();
        let before = program(&before_source);
        let after =
            program(&fs::read_to_string(root.join(task["gold"]["gwt"].as_str().unwrap())).unwrap());
        let probes = task["probes"].as_array().unwrap();
        let corpus = Corpus::new(
            probes
                .iter()
                .enumerate()
                .map(|(i, probe)| {
                    entry(
                        &i.to_string(),
                        json!(
                            capture_request(
                                &before,
                                task["request"].as_str().unwrap(),
                                &probe["input"],
                                ProgramLimits::default()
                            )
                            .unwrap()
                        ),
                    )
                })
                .collect(),
        )
        .unwrap();
        let report = review_corpus(&Corpus::from_json(&corpus.to_json()).unwrap(), &after).unwrap();
        assert!(report.complete);
        assert_eq!(report.totals.total, probes.len());
        assert_eq!(
            report.totals.outcome_changed,
            probes.iter().filter(|p| p["kind"] == "changed").count()
        );
        for (row, probe) in report.cases.iter().zip(probes) {
            assert!(row.baseline_explanation.is_some());
            assert!(row.candidate_explanation.is_some());
            assert_eq!(
                row.comparison
                    .as_ref()
                    .unwrap()
                    .candidate
                    .as_ref()
                    .unwrap()
                    .result
                    .as_ref(),
                Some(&probe["expected"])
            );
            assert_eq!(
                row.comparison
                    .as_ref()
                    .unwrap()
                    .changes
                    .as_ref()
                    .unwrap()
                    .outcome,
                probe["kind"] == "changed"
            );
        }
        total += report.totals.total;
    }
    assert_eq!(total, 336);
}

#[test]
fn cli_review_emits_an_incomplete_report_instead_of_dropping_invalid_entries() {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let dir = std::env::temp_dir().join(format!(
        "gwt-review-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir(&dir).unwrap();
    let good = dir.join("good.json");
    let bad = dir.join("bad.json");
    let candidate = dir.join("candidate.gwt");
    let corpus_path = dir.join("corpus.json");
    let html_path = dir.join("review.html");
    fs::write(&good, captured(BEFORE, &facts(true, false)).to_string()).unwrap();
    fs::write(&bad, "not valid JSON").unwrap();
    fs::write(&candidate, AFTER).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("corpus")
        .arg(&good)
        .arg(&bad)
        .output()
        .unwrap();
    assert!(output.status.success());
    fs::write(&corpus_path, output.stdout).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("review")
        .arg(&corpus_path)
        .arg("--candidate")
        .arg(&candidate)
        .arg("--html")
        .arg(&html_path)
        .output()
        .unwrap();
    assert!(!output.status.success());
    let report: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["totals"]["total"], 2);
    assert_eq!(report["totals"]["compared"], 1);
    assert_eq!(report["totals"]["unavailable"], 1);
    let html = fs::read_to_string(html_path).unwrap();
    assert!(html.contains("Review coverage is incomplete"));
    assert!(html.contains("Comparison unavailable"));
    let duplicate = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("corpus")
        .arg(&good)
        .arg(&good)
        .output()
        .unwrap();
    assert!(!duplicate.status.success());
    let case = ExecutionCase::from_json(&fs::read_to_string(good).unwrap()).unwrap();
    assert_eq!(case.request(), Some("assess refund"));
    fs::remove_dir_all(dir).unwrap();
}

#[test]
fn imported_definitions_and_failures_explain_against_their_frozen_module() {
    let source = include_str!("fixtures/invoice.gwt");
    let start = source.find("WHEN price <").unwrap();
    let end = source.find("SCENARIO ").unwrap();
    let bundle = SourceBundle {
        entry: "main.gwt".into(),
        modules: BTreeMap::from([
            (
                "main.gwt".into(),
                format!(
                    "USE \"pricing.gwt\"\n{}{}",
                    &source[..start],
                    &source[end..]
                ),
            ),
            ("pricing.gwt".into(), source[start..end].into()),
        ]),
    };
    let program = compile_bundle(&bundle).unwrap();
    let run = program.run_request(
        "price invoice",
        &json!({"invoice":{"quantity":0,"unit_price":"10"}}),
        ProgramLimits::default(),
    );
    let explanation = explain_execution(&run, &bundle).unwrap();
    assert!(!explanation.ok);
    let failure = explanation.failure.unwrap();
    assert_eq!(failure.span.file, "pricing.gwt");
    assert_eq!(failure.text, "REQUIRE invoice.quantity > 0");
    let enter = explanation
        .steps
        .iter()
        .find(|step| step.operation == "enter behavior")
        .unwrap();
    assert_eq!(enter.source.span.file, "main.gwt");
    assert_eq!(enter.definition.as_ref().unwrap().span.file, "pricing.gwt");
    assert_eq!(
        explanation
            .steps
            .iter()
            .filter(|step| step.operation == "assert" && step.value == false)
            .count(),
        1
    );
}
