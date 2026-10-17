use gwt_core::{
    Corpus, CorpusEntry, ExecutionCase, ProgramLimits, RegressionScope, RegressionStatus,
    SourceBundle, capture_request, capture_scenario, compile_bundle, test_corpus,
};
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, path::PathBuf, process::Command};

const SOURCE: &str = include_str!("fixtures/invoice.gwt");
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "invoice.gwt".into(),
        modules: BTreeMap::from([("invoice.gwt".into(), source.into())]),
    })
    .unwrap()
}
fn facts() -> Json {
    json!({"invoice":{"quantity":3,"unit_price":"10.25"}})
}
fn capture(input: &Json, limits: ProgramLimits) -> ExecutionCase {
    capture_request(&program(SOURCE), "price invoice", input, limits).unwrap()
}
fn entry(id: &str, case: impl serde::Serialize) -> CorpusEntry {
    CorpusEntry {
        id: id.into(),
        label: id.into(),
        case: json!(case),
    }
}
fn corpus(case: ExecutionCase) -> Corpus {
    Corpus::new(vec![entry("observation", case)]).unwrap()
}

#[test]
fn successful_domain_boundary_and_resource_observations_remain_distinct_from_test_passes() {
    let defaults = ProgramLimits::default();
    let mut entries = vec![
        entry("success", capture(&facts(), defaults)),
        entry("boundary", capture(&json!({}), defaults)),
        entry(
            "domain",
            capture(
                &json!({"invoice":{"quantity":0,"unit_price":"10.25"}}),
                defaults,
            ),
        ),
        entry(
            "scenario",
            capture_scenario(&program(SOURCE), "three taxable units", defaults).unwrap(),
        ),
    ];
    for (id, limits) in [
        (
            "steps",
            ProgramLimits {
                execution: gwt_core::Limits {
                    steps: 0,
                    ..defaults.execution
                },
                ..defaults
            },
        ),
        (
            "evidence",
            ProgramLimits {
                execution: gwt_core::Limits {
                    evidence_bytes: 0,
                    ..defaults.execution
                },
                ..defaults
            },
        ),
        (
            "depth",
            ProgramLimits {
                call_depth: 0,
                ..defaults
            },
        ),
    ] {
        let case = capture(&facts(), limits);
        assert_eq!(case.observed()["ok"], false);
        entries.push(entry(id, case));
    }
    let corpus = Corpus::new(entries).unwrap();
    for scope in [
        RegressionScope::OutcomesAndState,
        RegressionScope::Execution,
    ] {
        let report = test_corpus(&corpus, &program(SOURCE), scope).unwrap();
        assert!(report.passed);
        assert_eq!(report.totals.total, 7);
        assert_eq!(report.totals.passed, 7);
        assert_eq!(report.review.totals.candidate_failed, 5);
        assert_eq!(report.cases[4].captured_limits.unwrap().execution.steps, 0);
        assert!(report.cases.iter().all(|row| row.case_integrity.is_some()));
        assert!(
            report
                .cases
                .iter()
                .all(|row| row.status == RegressionStatus::Passed)
        );
        assert_eq!(
            report.review.cases[0]
                .comparison
                .as_ref()
                .unwrap()
                .candidate
                .as_ref()
                .unwrap()
                .result
                .as_ref()
                .unwrap()["decision"]["total"],
            "36.9"
        );
        assert_eq!(
            report.expectation_basis,
            "verified_observation_not_approval"
        );
    }
}

#[test]
fn source_movement_is_visible_and_execution_scope_checks_evidence_positions() {
    let corpus = corpus(capture(&facts(), ProgramLimits::default()));
    let moved = program(&format!("# relocated source positions\n{SOURCE}"));
    let outcomes = test_corpus(&corpus, &moved, RegressionScope::OutcomesAndState).unwrap();
    assert!(outcomes.passed);
    let changes = outcomes.review.cases[0]
        .comparison
        .as_ref()
        .unwrap()
        .changes
        .as_ref()
        .unwrap();
    assert!(changes.source && changes.evidence);
    assert!(!changes.outcome && !changes.state);
    let strict = test_corpus(&corpus, &moved, RegressionScope::Execution).unwrap();
    assert!(!strict.passed);
    assert_eq!(strict.totals.changed, 1);
    // A source identity change alone is not an execution mismatch.
    let comment_only = program(&format!("{SOURCE}\n# trailing comment\n"));
    assert!(
        test_corpus(&corpus, &comment_only, RegressionScope::Execution)
            .unwrap()
            .passed
    );
}

#[test]
fn output_partial_state_prints_and_diagnostic_changes_fail_preservation() {
    let valid = corpus(capture(&facts(), ProgramLimits::default()));
    for source in [
        SOURCE.replace("subtotal * 0.2", "subtotal * 0.3"),
        SOURCE.replace("  LET subtotal", "  print \"audit\"\n  LET subtotal"),
        SOURCE.replace(
            "  REQUIRE invoice.quantity > 0",
            "  REQUIRE invoice.quantity > 10",
        ),
    ] {
        let report =
            test_corpus(&valid, &program(&source), RegressionScope::OutcomesAndState).unwrap();
        assert!(!report.passed);
        assert_eq!(report.totals.changed, 1);
        assert!(
            report.review.cases[0]
                .comparison
                .as_ref()
                .unwrap()
                .changes
                .as_ref()
                .unwrap()
                .outcome
        );
    }
    let failed = corpus(capture(
        &json!({"invoice":{"quantity":0,"unit_price":"10.25"}}),
        ProgramLimits::default(),
    ));
    let mutation = SOURCE.replace(
        "  REQUIRE invoice.quantity > 0",
        "  set decision.status to \"priced\"\n  REQUIRE invoice.quantity > 0",
    );
    let report = test_corpus(
        &failed,
        &program(&mutation),
        RegressionScope::OutcomesAndState,
    )
    .unwrap();
    assert!(!report.passed);
    let changes = report.review.cases[0]
        .comparison
        .as_ref()
        .unwrap()
        .changes
        .as_ref()
        .unwrap();
    assert!(!changes.outcome, "same failure message and absent result");
    assert!(
        changes.state,
        "state committed before rejection must be compared"
    );
    let different_message = SOURCE
        .split("SCENARIO")
        .next()
        .unwrap()
        .replacen("GIVEN invoice is", "GIVEN bill is", 1)
        .replace(
            "WHEN price invoice into decision",
            "WHEN price bill into decision",
        );
    let boundary = corpus(capture(&json!({}), ProgramLimits::default()));
    let report = test_corpus(
        &boundary,
        &program(&different_message),
        RegressionScope::OutcomesAndState,
    )
    .unwrap();
    assert!(
        !report.passed,
        "diagnostic messages are part of the selected outcome"
    );
    let comparison = report.review.cases[0].comparison.as_ref().unwrap();
    assert_eq!(
        comparison.baseline.actual.diagnostic.as_ref().unwrap().code,
        comparison
            .candidate
            .as_ref()
            .unwrap()
            .diagnostic
            .as_ref()
            .unwrap()
            .code
    );
}

#[test]
fn paired_budget_probes_detect_lost_success_and_observed_failure_becoming_success() {
    let p = program(SOURCE);
    let defaults = ProgramLimits::default();
    let run = p.run_request("price invoice", &facts(), defaults);
    let tight = ProgramLimits {
        execution: gwt_core::Limits {
            steps: run.steps,
            ..defaults.execution
        },
        ..defaults
    };
    let below = ProgramLimits {
        execution: gwt_core::Limits {
            steps: run.steps - 1,
            ..defaults.execution
        },
        ..defaults
    };
    let success = capture(&facts(), tight);
    let failure = capture(&facts(), below);
    assert_eq!(success.observed()["ok"], true);
    assert_eq!(failure.observed()["diagnostic"]["code"], "execution_limit");
    let cases = Corpus::new(vec![
        entry("at-budget", success),
        entry("below-budget", failure),
    ])
    .unwrap();
    assert!(
        test_corpus(&cases, &p, RegressionScope::Execution)
            .unwrap()
            .passed
    );
    let slower = program(&SOURCE.replace("  LET subtotal", "  REQUIRE true\n  LET subtotal"));
    let report = test_corpus(&cases, &slower, RegressionScope::OutcomesAndState).unwrap();
    assert!(!report.passed);
    assert_eq!(report.cases[0].status, RegressionStatus::Changed);
    assert!(
        !report.review.cases[0]
            .comparison
            .as_ref()
            .unwrap()
            .candidate
            .as_ref()
            .unwrap()
            .ok
    );
    let faster = program(&SOURCE.replace("  REQUIRE invoice.quantity > 0\n", ""));
    let report = test_corpus(&cases, &faster, RegressionScope::OutcomesAndState).unwrap();
    assert!(
        !report.passed,
        "a changed captured failure also needs review"
    );
    assert_eq!(report.cases[1].status, RegressionStatus::Changed);
    assert!(
        report.review.cases[1]
            .comparison
            .as_ref()
            .unwrap()
            .candidate
            .as_ref()
            .unwrap()
            .ok
    );
}

fn resign(mut case: Json) -> Json {
    case.as_object_mut().unwrap().remove("integrity");
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-case-sha256-v1\0");
    hash.update(serde_json::to_vec(&case).unwrap());
    case["integrity"] = json!(format!("sha256:{:x}", hash.finalize()));
    case
}

#[test]
fn corrupted_forged_foreign_engine_and_missing_target_cases_cannot_pass() {
    let good = json!(capture(&facts(), ProgramLimits::default()));
    let mut mismatch = good.clone();
    mismatch["record"]["observed"]["result"]["decision"]["total"] = json!("99");
    let mut corrupt = good.clone();
    corrupt["integrity"] = json!("corrupt");
    let mut foreign = good.clone();
    foreign["record"]["engine"]["profile"] = json!("other-engine");
    let corpus = Corpus::new(vec![
        entry("good", good),
        entry("mismatch", resign(mismatch)),
        entry("corrupt", corrupt),
        entry("foreign", resign(foreign)),
        entry("invalid", Json::Null),
    ])
    .unwrap();
    let report = test_corpus(&corpus, &program(SOURCE), RegressionScope::OutcomesAndState).unwrap();
    assert!(!report.passed);
    assert_eq!(
        (
            report.totals.total,
            report.totals.passed,
            report.totals.changed,
            report.totals.baseline_mismatch,
            report.totals.unavailable
        ),
        (5, 1, 0, 1, 3)
    );
    assert!(
        report.review.cases[1]
            .comparison
            .as_ref()
            .unwrap()
            .candidate
            .is_none()
    );
    let missing = program(&SOURCE.replace("REQUEST price invoice", "REQUEST calculate invoice"));
    let report = test_corpus(&corpus, &missing, RegressionScope::OutcomesAndState).unwrap();
    assert!(!report.passed);
    assert_eq!(report.cases[0].status, RegressionStatus::Changed);
}

struct Fixture(PathBuf);
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn cli_requires_explicit_scope_preserves_files_and_reports_nonzero_regressions() {
    let f = Fixture(std::env::temp_dir().join(format!("gwt-regressions-{}", std::process::id())));
    fs::create_dir(&f.0).unwrap();
    fs::write(f.0.join("invoice.gwt"), SOURCE).unwrap();
    let cases = corpus(capture(&facts(), ProgramLimits::default())).to_json();
    fs::write(f.0.join("corpus.json"), &cases).unwrap();
    let command = |args: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .current_dir(&f.0)
            .args(args)
            .output()
            .unwrap()
    };
    let args = [
        "test-cases",
        "corpus.json",
        "--candidate",
        "invoice.gwt",
        "--match",
        "execution",
        "--import-root",
        ".",
    ];
    let output = command(&args);
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["kind"], "gwt.native-regression");
    assert_eq!(report["passed"], true);
    fs::write(
        f.0.join("invoice.gwt"),
        SOURCE.replace("subtotal * 0.2", "subtotal * 0.3"),
    )
    .unwrap();
    let output = command(&args);
    assert!(!output.status.success());
    let report: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["passed"], false);
    assert_eq!(report["review"]["complete"], true);
    // The existing review command still measures comparison coverage.
    assert!(
        command(&["review", "corpus.json", "--candidate", "invoice.gwt"])
            .status
            .success()
    );
    for suffix in [
        vec![],
        vec!["--match", "outcome"],
        vec!["--match", "execution", "--match", "execution"],
        vec!["--match", "execution", "--limits", "limits.json"],
        vec!["--match", "execution", "--decisions", "decisions.json"],
        vec!["--match"],
    ] {
        let mut args = vec!["test-cases", "corpus.json", "--candidate", "invoice.gwt"];
        args.extend(suffix);
        let output = command(&args);
        assert!(
            !output.status.success() && output.stdout.is_empty(),
            "{args:?}"
        );
    }
    assert_eq!(fs::read_to_string(f.0.join("corpus.json")).unwrap(), cases);
    fs::write(f.0.join("invoice.gwt"), "not a program").unwrap();
    let output = command(&args);
    assert!(!output.status.success());
    let report: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["phase"], "candidate-check");
    fs::write(f.0.join("corpus.json"), "{}").unwrap();
    let output = command(&args);
    assert!(!output.status.success());
    let report: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["phase"], "corpus");
}
