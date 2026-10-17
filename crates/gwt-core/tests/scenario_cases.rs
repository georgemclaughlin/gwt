use gwt_core::{
    Corpus, CorpusEntry, ExecutionCase, ProgramLimits, ReviewDecisions, SourceBundle,
    assess_decisions, capture_request, capture_scenario, compare_case, compile_bundle,
    compile_program, explain_execution, render_review_html, replay_case, review_corpus,
    scenario_from_case,
};
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, process::Command};

const SOURCE: &str = "REQUEST echo
  GIVEN value is integer
  WHEN print value
  OUTPUT value is integer

BACKGROUND
GIVEN counter is 0

SCENARIO accepted
WHEN add 1 to counter
WHEN print counter
THEN counter == 1

SCENARIO rejected
WHEN add 2 to counter
WHEN print counter
THEN counter == 0
";

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

fn resign(mut value: Json) -> String {
    value.as_object_mut().unwrap().remove("integrity");
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-case-sha256-v1\0");
    hash.update(serde_json::to_vec(&value).unwrap());
    value["integrity"] = json!(format!("sha256:{:x}", hash.finalize()));
    value.to_string()
}

#[test]
fn selected_scenarios_preserve_success_failure_prints_and_budgets() {
    let program = program(SOURCE);
    for (name, value, ok) in [("accepted", 1, true), ("rejected", 2, false)] {
        let case = capture_scenario(&program, name, ProgramLimits::default()).unwrap();
        assert_eq!(case.request(), None);
        assert_eq!(case.scenario(), Some(name));
        assert!(case.input().is_null());
        assert_eq!(case.observed()["ok"], ok);
        assert_eq!(case.observed()["state"]["counter"], value);
        assert_eq!(case.observed()["output"], json!([value]));
        assert!(case.observed()["request"].is_null());
        let payload = json!(case);
        assert_eq!(payload["schemaVersion"], 2);
        assert!(payload["record"].get("request").is_none());
        assert_eq!(
            ExecutionCase::from_json(&resign(payload))
                .unwrap()
                .to_json(),
            case.to_json()
        );
        let replay = replay_case(&case).unwrap();
        assert!(replay.verified);
        assert_eq!(replay.actual.ok, ok);
        explain_execution(&replay.actual, case.source()).unwrap();
        let suite = program.test_scenarios(ProgramLimits::default());
        let selected = &suite.iter().find(|row| row.name == name).unwrap().execution;
        assert_eq!(json!(selected), *case.observed());
        assert_eq!(
            scenario_from_case(&case, "copy").unwrap_err().code,
            "scenario_case_target"
        );
    }
    for code in ["execution_limit", "evidence_limit"] {
        let mut limits = ProgramLimits::default();
        if code == "execution_limit" {
            limits.execution.steps = 0;
        } else {
            limits.execution.evidence_bytes = 0;
        }
        let case = capture_scenario(&program, "accepted", limits).unwrap();
        assert_eq!(case.observed()["diagnostic"]["code"], code);
        assert!(replay_case(&case).unwrap().verified);
    }
}

#[test]
fn request_v1_shape_is_preserved_and_targets_cannot_be_ambiguous() {
    let program = program(SOURCE);
    let request = capture_request(
        &program,
        "echo",
        &json!({"value":3}),
        ProgramLimits::default(),
    )
    .unwrap();
    let old = json!(request);
    assert_eq!(old["schemaVersion"], 1);
    assert_eq!(old["record"]["request"], "echo");
    assert!(old["record"].get("scenario").is_none());
    assert!(
        replay_case(&ExecutionCase::from_json(&resign(old.clone())).unwrap())
            .unwrap()
            .verified
    );

    let scenario = json!(capture_scenario(&program, "accepted", ProgramLimits::default()).unwrap());
    let mut invalid = Vec::new();
    let mut both = scenario.clone();
    both["record"]["request"] = json!("echo");
    invalid.push(both);
    let mut v1_scenario = scenario.clone();
    v1_scenario["schemaVersion"] = json!(1);
    invalid.push(v1_scenario);
    let mut v2_request = old;
    let mut null_scenario = v2_request.clone();
    null_scenario["record"]["scenario"] = Json::Null;
    invalid.push(null_scenario);
    let mut null_request = scenario.clone();
    null_request["record"]["request"] = Json::Null;
    invalid.push(null_request);
    v2_request["schemaVersion"] = json!(2);
    invalid.push(v2_request);
    for input in [json!({}), json!({"value":3}), json!([1])] {
        let mut value = scenario.clone();
        value["record"]["input"] = input;
        invalid.push(value);
    }
    for name in [Json::Null, json!(""), json!("x".repeat(4097))] {
        let mut value = scenario.clone();
        value["record"]["scenario"] = name;
        invalid.push(value);
    }
    for value in invalid {
        assert_eq!(
            ExecutionCase::from_json(&resign(value)).unwrap_err().code,
            "case_format"
        );
    }
    let mut wrong_version = scenario;
    wrong_version["schemaVersion"] = json!(4);
    assert_eq!(
        ExecutionCase::from_json(&resign(wrong_version))
            .unwrap_err()
            .code,
        "case_version"
    );
}

#[test]
fn comparisons_preserve_target_and_refuse_forged_baselines() {
    let old = program(SOURCE);
    let case = capture_scenario(&old, "accepted", ProgramLimits::default()).unwrap();
    let unchanged = compare_case(&case, &old).unwrap();
    let changes = unchanged.changes.unwrap();
    assert!(!changes.source && !changes.outcome && !changes.state && !changes.evidence);
    let candidate = program(&SOURCE.replace("WHEN print counter", "WHEN print counter + 10"));
    let changed = compare_case(&case, &candidate).unwrap();
    assert!(changed.baseline.verified);
    assert!(changed.changes.unwrap().outcome);
    assert_eq!(changed.candidate.unwrap().output, vec![json!(11)]);

    let removed = program(&SOURCE.replace("SCENARIO accepted", "SCENARIO renamed"));
    let changed = compare_case(&case, &removed).unwrap();
    assert_eq!(
        changed.candidate.unwrap().diagnostic.unwrap().code,
        "unknown_scenario"
    );
    let mut forged = json!(case);
    forged["record"]["scenario"] = json!("rejected");
    let forged = ExecutionCase::from_json(&resign(forged)).unwrap();
    let refused = compare_case(&forged, &candidate).unwrap();
    assert_eq!(refused.status, "baseline_mismatch");
    assert!(refused.candidate.is_none());
}

#[test]
fn example_row_capture_keeps_original_source_and_compares_candidate_setup() {
    let source = include_str!("../../../examples/native_delivery/rules.gwt");
    let program = program(source);
    let name = "weight and membership determine the quote example 3";
    let case = capture_scenario(&program, name, ProgramLimits::default()).unwrap();
    assert_eq!(case.observed()["state"]["quote"]["fee"], 9);
    assert_eq!(case.observed()["events"][0]["operation"], "example row");
    let replay = replay_case(&case).unwrap();
    let explanation = explain_execution(&replay.actual, case.source()).unwrap();
    assert!(json!(explanation).to_string().contains("1001"));
    assert_eq!(case.source().modules.len(), 1);
    // Candidate scenarios include candidate setup and assertions. They do not
    // freeze host input like request cases. This change still passes its test.
    let candidate = compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([(
            "rules.gwt".into(),
            source.replace(
                "| 1001   | false  | \"standard\" | 9   |",
                "| 1000   | false  | \"standard\" | 5   |",
            ),
        )]),
    })
    .unwrap();
    let comparison = compare_case(&case, &candidate).unwrap();
    let run = comparison.candidate.unwrap();
    assert!(run.ok);
    assert_eq!(run.state["parcel"]["weight_grams"], 1000);
    assert_eq!(run.state["quote"]["fee"], 5);
    assert!(comparison.changes.unwrap().outcome);
}

#[test]
fn imports_are_frozen_and_invalid_capture_targets_fail_explicitly() {
    let bundle = SourceBundle {
        entry: "main.gwt".into(),
        modules: BTreeMap::from([
            ("main.gwt".into(), "USE \"lib.gwt\"\nSCENARIO explicit\nGIVEN value is 3\nWHEN echo value\nTHEN value == 3\n".into()),
            ("lib.gwt".into(), "WHEN echo <value>\n  GIVEN value is integer\n  print value\nSCENARIO excluded\nTHEN false\n".into()),
        ]),
    };
    let program = compile_bundle(&bundle).unwrap();
    let case = capture_scenario(&program, "explicit", ProgramLimits::default()).unwrap();
    let replay = replay_case(&case).unwrap();
    assert_eq!(replay.actual.output, vec![json!(3)]);
    explain_execution(&replay.actual, case.source()).unwrap();
    for name in ["excluded", "absent"] {
        assert_eq!(
            capture_scenario(&program, name, ProgramLimits::default())
                .unwrap_err()
                .code,
            "unknown_scenario"
        );
    }
    let mut limits = ProgramLimits::default();
    limits.execution.steps += 1;
    assert_eq!(
        capture_scenario(&program, "explicit", limits)
            .unwrap_err()
            .code,
        "case_limits"
    );
    let direct = compile_program("THEN true\n", "direct.gwt").unwrap();
    assert_eq!(
        capture_scenario(&direct, "Main", ProgramLimits::default())
            .unwrap_err()
            .code,
        "case_source"
    );
    let implicit = program_for_implicit();
    assert!(
        replay_case(&capture_scenario(&implicit, "Main", ProgramLimits::default()).unwrap())
            .unwrap()
            .verified
    );
}

fn program_for_implicit() -> gwt_core::CompiledProgram {
    program("WHEN print \"implicit\"\nTHEN true\n")
}

#[test]
fn mixed_request_and_scenario_corpora_have_explicit_review_targets() {
    let program = program(SOURCE);
    let cases = [
        capture_request(
            &program,
            "echo",
            &json!({"value":3}),
            ProgramLimits::default(),
        )
        .unwrap(),
        capture_scenario(&program, "accepted", ProgramLimits::default()).unwrap(),
        capture_scenario(&program, "rejected", ProgramLimits::default()).unwrap(),
    ];
    let corpus = Corpus::new(
        cases
            .iter()
            .enumerate()
            .map(|(index, case)| CorpusEntry {
                id: index.to_string(),
                label: "mixed cases".into(),
                case: json!(case),
            })
            .collect(),
    )
    .unwrap();
    let report = review_corpus(&corpus, &program).unwrap();
    assert!(report.complete);
    assert_eq!(report.totals.compared, 3);
    assert_eq!(report.totals.candidate_failed, 1);
    assert_eq!(report.cases[0].request.as_deref(), Some("echo"));
    assert!(report.cases[0].scenario.is_none());
    assert_eq!(report.cases[1].scenario.as_deref(), Some("accepted"));
    assert!(report.cases[1].request.is_none());
    assert!(report.cases[1].input.is_none());
    let html = render_review_html(&report).unwrap();
    assert!(html.contains("Scenario: <strong>accepted</strong>"));
    assert!(html.contains("Request: <strong>echo</strong>"));
    let decisions = ReviewDecisions::pending(&report).unwrap();
    let assessment = assess_decisions(&report, &decisions).unwrap();
    assert_eq!(json!(assessment)["pending"], 3);
}

#[test]
fn cli_captures_replays_compares_and_reviews_failed_scenarios() {
    let dir = std::env::temp_dir().join(format!("gwt-scenario-case-{}", std::process::id()));
    fs::create_dir(&dir).unwrap();
    let source = dir.join("rules.gwt");
    fs::write(&source, SOURCE).unwrap();
    let source = source.to_str().unwrap();
    let run = |args: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .args(args)
            .output()
            .unwrap()
    };
    let failed = run(&["run", source, "--scenario", "rejected"]);
    assert!(!failed.status.success());
    let capture = run(&["capture", source, "--scenario", "rejected"]);
    assert!(capture.status.success());
    let case = dir.join("failed.json");
    fs::write(&case, &capture.stdout).unwrap();
    let case = case.to_str().unwrap();
    let replay = run(&["replay", case]);
    assert!(replay.status.success());
    let payload: Json = serde_json::from_slice(&replay.stdout).unwrap();
    assert_eq!(payload["verified"], true);
    assert_eq!(payload["actual"]["ok"], false);
    assert!(
        run(&["compare", case, "--candidate", source])
            .status
            .success()
    );
    let corpus = run(&["corpus", case]);
    assert!(corpus.status.success());
    let path = dir.join("corpus.json");
    fs::write(&path, corpus.stdout).unwrap();
    let html = dir.join("review.html");
    assert!(
        run(&[
            "review",
            path.to_str().unwrap(),
            "--candidate",
            source,
            "--html",
            html.to_str().unwrap()
        ])
        .status
        .success()
    );
    assert!(
        fs::read_to_string(html)
            .unwrap()
            .contains("Scenario: <strong>rejected</strong>")
    );
    for args in [
        vec!["capture", source, "--scenario", "missing"],
        vec!["capture", source, "--scenario", "accepted", "--input", case],
        vec![
            "run",
            source,
            "--scenario",
            "accepted",
            "--scenario",
            "rejected",
        ],
    ] {
        assert!(!run(&args).status.success());
    }
    fs::remove_dir_all(dir).unwrap();
}
