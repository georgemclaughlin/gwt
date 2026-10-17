use gwt_core::{
    Corpus, CorpusEntry, CorpusReview, ProgramLimits, ReviewDecisions, SourceBundle,
    assess_decisions, capture_request, compile_bundle, review_corpus, review_identity,
};
use serde_json::{Value as Json, json};
use std::{collections::BTreeMap, fs, process::Command};

const SOURCE: &str = include_str!("fixtures/invoice.gwt");
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
fn corpus(quantities: &[i64]) -> Corpus {
    let program = program(SOURCE);
    Corpus::new(
        quantities
            .iter()
            .enumerate()
            .map(|(index, quantity)| CorpusEntry {
                id: format!("case-{index}"),
                label: format!("Invoice quantity {quantity}"),
                case: json!(
                    capture_request(
                        &program,
                        "price invoice",
                        &json!({"invoice":{"unit_price":"19.95","quantity":quantity}}),
                        ProgramLimits::default()
                    )
                    .unwrap()
                ),
            })
            .collect(),
    )
    .unwrap()
}
fn report() -> CorpusReview {
    review_corpus(&corpus(&[1, 2]), &program(SOURCE)).unwrap()
}
fn template(report: &CorpusReview) -> Json {
    json!(ReviewDecisions::pending(report).unwrap())
}
fn decisions(value: &Json) -> ReviewDecisions {
    ReviewDecisions::from_json(&value.to_string()).unwrap()
}
fn accept_all(report: &CorpusReview) -> Json {
    let mut file = template(report);
    file["reviewer"] = json!("Synthetic test reviewer");
    for decision in file["decisions"].as_array_mut().unwrap() {
        decision["status"] = json!("accept");
    }
    file
}

#[test]
fn pending_is_default_and_every_case_requires_an_explicit_choice() {
    let report = report();
    let mut file = template(&report);
    let result = assess_decisions(&report, &decisions(&file)).unwrap();
    assert_eq!(result.pending, 2);
    assert!(!result.all_accepted);
    file["reviewer"] = json!("Synthetic test reviewer");
    file["decisions"][0]["status"] = json!("accept");
    let result = assess_decisions(&report, &decisions(&file)).unwrap();
    assert_eq!(result.accepted, 1);
    assert_eq!(result.pending, 1);
    assert!(!result.all_accepted);
    file["decisions"][1]["status"] = json!("needs_information");
    file["decisions"][1]["note"] = json!("Confirm the tax rate.");
    let result = assess_decisions(&report, &decisions(&file)).unwrap();
    assert_eq!(result.needs_information, 1);
    assert!(!result.all_accepted);
    file["decisions"][1]["status"] = json!("reject");
    assert_eq!(
        assess_decisions(&report, &decisions(&file))
            .unwrap()
            .rejected,
        1
    );
    file["decisions"][1]["status"] = json!("accept");
    let result = assess_decisions(&report, &decisions(&file)).unwrap();
    assert!(result.all_accepted);
    assert_eq!(result.accepted, 2);
}

#[test]
fn report_identity_has_an_independent_encoding_and_changes_with_evidence() {
    use sha2::{Digest, Sha256};
    let mut report = report();
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-review-sha256-v1\0");
    hash.update(serde_json::to_vec(&json!(report)).unwrap());
    let original = review_identity(&report).unwrap();
    assert_eq!(original.digest, format!("sha256:{:x}", hash.finalize()));
    report.cases[0].label.push_str(" changed label");
    assert_ne!(original, review_identity(&report).unwrap());
    report.cases.reverse();
    assert_ne!(original, review_identity(&report).unwrap());
    report.engine.profile.push_str(" new engine");
    assert_ne!(original, review_identity(&report).unwrap());
}

#[test]
fn decisions_cannot_silently_apply_to_changed_source_or_corpus() {
    let corpus = corpus(&[1, 2]);
    let before = review_corpus(&corpus, &program(SOURCE)).unwrap();
    let file = decisions(&accept_all(&before));
    let after = review_corpus(
        &corpus,
        &program(&(SOURCE.to_owned() + "\n# source moved\n")),
    )
    .unwrap();
    assert_eq!(
        assess_decisions(&after, &file).unwrap_err().code,
        "decisions_stale"
    );
    let after = review_corpus(&self::corpus(&[2, 1]), &program(SOURCE)).unwrap();
    assert_eq!(
        assess_decisions(&after, &file).unwrap_err().code,
        "decisions_stale"
    );
}

#[test]
fn changed_capture_budgets_stale_decisions_even_when_every_execution_byte_matches() {
    let program = program(SOURCE);
    let input = json!({"invoice":{"unit_price":"19.95","quantity":1}});
    let make = |limits| {
        let case = capture_request(&program, "price invoice", &input, limits).unwrap();
        let corpus = Corpus::new(vec![CorpusEntry {
            id: "fixed-id".into(),
            label: "fixed-label".into(),
            case: json!(case),
        }])
        .unwrap();
        let report = review_corpus(&corpus, &program).unwrap();
        (case, corpus, report)
    };
    let defaults = ProgramLimits::default();
    let (case, corpus, before) = make(defaults);
    assert_eq!(before.schema_version, 2);
    assert_eq!(before.corpus_integrity, gwt_core::corpus_integrity(&corpus));
    assert_eq!(
        before.cases[0].case_integrity.as_deref(),
        Some(case.integrity())
    );
    let choices = decisions(&accept_all(&before));
    assert!(assess_decisions(&before, &choices).unwrap().all_accepted);
    let mut budgets = [defaults; 4];
    budgets[0].execution.steps -= 1;
    budgets[1].execution.evidence_bytes -= 1;
    budgets[2].execution.text_bytes = 1;
    budgets[3].call_depth -= 1;
    for limits in budgets {
        let (other, _, after) = make(limits);
        assert_eq!(
            case.observed(),
            other.observed(),
            "the entire execution is identical"
        );
        assert_eq!(
            json!(before.cases[0].comparison),
            json!(after.cases[0].comparison)
        );
        assert_ne!(before.corpus_integrity, after.corpus_integrity);
        assert_ne!(
            review_identity(&before).unwrap(),
            review_identity(&after).unwrap()
        );
        assert_eq!(json!(after.cases[0].captured_limits), json!(limits));
        assert_eq!(
            assess_decisions(&after, &choices).unwrap_err().code,
            "decisions_stale"
        );
        let html = gwt_core::render_review_html(&after).unwrap();
        assert!(html.contains("data-captured-limits"));
        assert!(html.contains("Captured execution limits"));
        assert!(html.contains(other.integrity()));
        let embedded: Json = serde_json::from_str(
            html.split("<script type=application/json id=review-data>")
                .nth(1)
                .unwrap()
                .split("</script>")
                .next()
                .unwrap(),
        )
        .unwrap();
        assert_eq!(embedded, json!(after));
    }
}

#[test]
fn complete_corpus_identity_binds_unavailable_case_payloads_without_trusting_them() {
    use sha2::{Digest, Sha256};
    let make = |value| {
        let corpus = Corpus::new(vec![CorpusEntry {
            id: "unavailable".into(),
            label: "same diagnostic, distinct payload".into(),
            case: json!({"unsupported":value}),
        }])
        .unwrap();
        let report = review_corpus(&corpus, &program(SOURCE)).unwrap();
        // Independent encoding includes every raw case, even one that cannot load.
        let mut hash = Sha256::new();
        hash.update(b"gwt-native-corpus-sha256-v1\0");
        hash.update(serde_json::to_vec(&json!(corpus)).unwrap());
        assert_eq!(
            report.corpus_integrity,
            format!("sha256:{:x}", hash.finalize())
        );
        report
    };
    let before = make(1);
    let after = make(2);
    assert_eq!(before.cases[0].status, "unavailable");
    assert_eq!(json!(before.cases), json!(after.cases));
    assert!(after.cases[0].case_integrity.is_none());
    assert!(after.cases[0].captured_limits.is_none());
    assert_ne!(
        review_identity(&before).unwrap(),
        review_identity(&after).unwrap()
    );
    let file = decisions(&template(&before));
    assert_eq!(
        assess_decisions(&after, &file).unwrap_err().code,
        "decisions_stale"
    );
    assert!(!assess_decisions(&before, &file).unwrap().all_accepted);
}

#[test]
fn all_cases_must_be_present_once_and_status_values_are_closed() {
    let report = report();
    let mut file = template(&report);
    file["decisions"].as_array_mut().unwrap().pop();
    assert_eq!(
        assess_decisions(&report, &decisions(&file))
            .unwrap_err()
            .code,
        "decisions_coverage"
    );
    let mut file = template(&report);
    file["decisions"][0]["id"] = json!("unknown");
    assert_eq!(
        assess_decisions(&report, &decisions(&file))
            .unwrap_err()
            .code,
        "decisions_coverage"
    );
    let mut file = template(&report);
    file["decisions"][1]["id"] = json!("case-0");
    assert_eq!(
        ReviewDecisions::from_json(&file.to_string())
            .unwrap_err()
            .code,
        "decisions_duplicate"
    );
    for status in [
        json!("approved"),
        json!(["accept"]),
        json!(null),
        json!(true),
    ] {
        let mut file = template(&report);
        file["decisions"][0]["status"] = status;
        assert_eq!(
            ReviewDecisions::from_json(&file.to_string())
                .unwrap_err()
                .code,
            "decisions_format"
        );
    }
    let mut file = template(&report);
    file["unexpected"] = json!(true);
    assert_eq!(
        ReviewDecisions::from_json(&file.to_string())
            .unwrap_err()
            .code,
        "decisions_format"
    );
}

#[test]
fn reviewer_notes_and_utf8_limits_are_validated_without_losing_text() {
    let report = report();
    let mut file = accept_all(&report);
    file["reviewer"] = json!("\u{85} ");
    assert_eq!(
        ReviewDecisions::from_json(&file.to_string())
            .unwrap_err()
            .code,
        "decisions_reviewer"
    );
    file["reviewer"] = json!("é".repeat(128));
    file["decisions"][0]["status"] = json!("reject");
    assert_eq!(
        ReviewDecisions::from_json(&file.to_string())
            .unwrap_err()
            .code,
        "decisions_note"
    );
    file["decisions"][0]["note"] = json!("é".repeat(2048));
    let loaded = decisions(&file);
    assert_eq!(
        serde_json::from_str::<Json>(&loaded.to_json()).unwrap(),
        file
    );
    file["decisions"][0]["note"] = json!("é".repeat(2049));
    assert_eq!(
        ReviewDecisions::from_json(&file.to_string())
            .unwrap_err()
            .code,
        "decisions_limit"
    );
    assert_eq!(
        ReviewDecisions::from_json(&" ".repeat(gwt_core::MAX_DECISIONS_BYTES + 1))
            .unwrap_err()
            .code,
        "decisions_limit"
    );
}

#[test]
fn unverified_rows_cannot_be_accepted_but_expected_execution_failures_can() {
    let corpus = Corpus::new(vec![CorpusEntry {
        id: "invalid".into(),
        label: "Unavailable fixture".into(),
        case: Json::Null,
    }])
    .unwrap();
    let report = review_corpus(&corpus, &program(SOURCE)).unwrap();
    assert_eq!(
        assess_decisions(&report, &decisions(&accept_all(&report)))
            .unwrap_err()
            .code,
        "decisions_unverified"
    );
    let mut file = accept_all(&report);
    file["decisions"][0]["status"] = json!("reject");
    file["decisions"][0]["note"] = json!("Restore the missing evidence.");
    let result = assess_decisions(&report, &decisions(&file)).unwrap();
    assert_eq!(result.rejected, 1);
    assert!(!result.all_accepted);
    let report = review_corpus(&self::corpus(&[0]), &program(SOURCE)).unwrap();
    assert_eq!(report.cases[0].status, "candidate_failed");
    let mut file = accept_all(&report);
    file["decisions"][0]["note"] = json!("Synthetic expectation: zero quantity must fail.");
    assert!(
        assess_decisions(&report, &decisions(&file))
            .unwrap()
            .all_accepted
    );
}

#[test]
fn cli_regenerates_the_report_before_assessing_decisions() {
    let root = std::env::temp_dir().join(format!("gwt-decision-cli-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let corpus = corpus(&[1]);
    fs::write(root.join("corpus.json"), corpus.to_json()).unwrap();
    fs::write(root.join("rules.gwt"), SOURCE).unwrap();
    let invoke = |command: &str, tail: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .current_dir(&root)
            .args([command, "corpus.json", "--candidate", "rules.gwt"])
            .args(tail)
            .output()
            .unwrap()
    };
    let output = invoke("review", &["--decisions-template", "decisions.json"]);
    assert!(output.status.success());
    let output = invoke("assess-review", &["--decisions", "decisions.json"]);
    assert!(!output.status.success());
    let assessment: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(assessment["pending"], 1);
    let report = review_corpus(&corpus, &program(SOURCE)).unwrap();
    fs::write(root.join("decisions.json"), accept_all(&report).to_string()).unwrap();
    let output = invoke("assess-review", &["--decisions", "decisions.json"]);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stdout)
    );
    let assessment: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(assessment["allAccepted"], true);
    let mut limits = ProgramLimits::default();
    limits.execution.steps -= 1;
    let changed_budget = Corpus::new(vec![CorpusEntry {
        id: "case-0".into(),
        label: "Invoice quantity 1".into(),
        case: json!(
            capture_request(
                &program(SOURCE),
                "price invoice",
                &json!({"invoice":{"unit_price":"19.95","quantity":1}}),
                limits
            )
            .unwrap()
        ),
    }])
    .unwrap();
    fs::write(root.join("corpus.json"), changed_budget.to_json()).unwrap();
    let stale = invoke("assess-review", &["--decisions", "decisions.json"]);
    assert!(!stale.status.success());
    assert_eq!(
        serde_json::from_slice::<Json>(&stale.stdout).unwrap()["diagnostic"]["code"],
        "decisions_stale"
    );
    fs::write(root.join("corpus.json"), corpus.to_json()).unwrap();
    assert!(
        !invoke("review", &["--decisions-template", "decisions.json"])
            .status
            .success()
    );
    fs::write(
        root.join("rules.gwt"),
        SOURCE.to_owned() + "\n# source revision\n",
    )
    .unwrap();
    let output = invoke("assess-review", &["--decisions", "decisions.json"]);
    assert!(!output.status.success());
    let failure: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(failure["diagnostic"]["code"], "decisions_stale");
    fs::remove_dir_all(root).unwrap();
}
