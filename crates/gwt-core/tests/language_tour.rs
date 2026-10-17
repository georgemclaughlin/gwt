use gwt_core::{
    SourceBundle, capture_request, compare_case, compile_bundle, explain_execution, replay_case,
    validate_bundle,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/language_tour/rules.gwt");
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
fn input(lines: &[(i64, bool)]) -> Json {
    json!({"report":{"employee":"Ada","policy_limit":100,"lines":lines.iter().enumerate().map(|(index,(amount,reimbursable))| json!({"description":format!("line {}",index+1),"amount":amount,"category":"other","reimbursable":reimbursable})).collect::<Vec<_>>()}})
}
fn expected(
    count: usize,
    submitted: i64,
    approved: i64,
    descriptions: &[&str],
    violation: Option<(&str, i64)>,
) -> Json {
    json!({"line_count":count.to_string(),"submitted_total":submitted.to_string(),"approved_total":approved.to_string(),"approved_descriptions":descriptions,"has_violation":violation.is_some(),"violation_description":violation.map_or("",|(description,_)|description),"violation_amount":violation.map_or(0,|(_,amount)|amount).to_string(),"status":if violation.is_some(){"needs_review"}else{"approved"},"reason":if violation.is_some(){"line_over_policy_limit"}else{"within_policy"}})
}
fn cases() -> Vec<(&'static str, Json, Json, bool)> {
    vec![
        ("empty", input(&[]), expected(0, 0, 0, &[], None), false),
        (
            "below",
            input(&[(42, true), (18, true)]),
            expected(2, 60, 60, &["line 1", "line 2"], None),
            false,
        ),
        (
            "equal limit",
            input(&[(100, true), (50, true)]),
            expected(2, 150, 150, &["line 1", "line 2"], None),
            true,
        ),
        (
            "first of two",
            input(&[(101, true), (102, true)]),
            expected(2, 203, 0, &[], Some(("line 1", 101))),
            false,
        ),
        (
            "reversed violations",
            input(&[(102, true), (101, true)]),
            expected(2, 203, 0, &[], Some(("line 1", 102))),
            false,
        ),
        (
            "nonreimbursable violation",
            input(&[(101, false), (50, true)]),
            expected(2, 151, 50, &["line 2"], Some(("line 1", 101))),
            false,
        ),
        (
            "second violation",
            input(&[(50, false), (101, true)]),
            expected(2, 151, 0, &[], Some(("line 2", 101))),
            false,
        ),
        (
            "both equal",
            input(&[(100, false), (100, true)]),
            expected(2, 200, 100, &["line 2"], None),
            true,
        ),
        (
            "zero amounts",
            input(&[(0, false), (0, true)]),
            expected(2, 0, 0, &["line 2"], None),
            false,
        ),
    ]
}

#[test]
fn explicit_find_matches_independent_boundary_and_precedence_expectations() {
    let program = program(SOURCE);
    for (name, input, expected, _) in cases() {
        let execution = program.run_request("review expense report", &input, Default::default());
        assert!(execution.ok, "{name}: {:?}", execution.diagnostic);
        assert_eq!(
            execution.result.as_ref().unwrap()["decision"],
            expected,
            "{name}"
        );
        let explanation = explain_execution(&execution, program.source_bundle().unwrap()).unwrap();
        assert!(
            explanation
                .steps
                .iter()
                .any(|step| step.operation == "enter collection"
                    && step.source.text.starts_with("FIND policy_violation"))
        );
    }
}

#[test]
fn tour_scenarios_cover_empty_input_and_clear_reused_decision_state() {
    let program = program(SOURCE);
    let report = validate_bundle(program.source_bundle().unwrap(), Default::default());
    assert!(report.ok);
    assert_eq!(report.results.len(), 8);
    assert_eq!(
        report
            .evidence
            .as_ref()
            .unwrap()
            .scenario_expectations
            .passed,
        72
    );
    let run = program.run_scenario(
        "reused decision clears a previous violation",
        Default::default(),
    );
    assert!(run.ok);
    assert_eq!(run.state["decision"], expected(0, 0, 0, &[], None));
    assert!(run.events.iter().any(|event| {
        event.operation == "set"
            && event.value["path"]
                .as_str()
                .is_some_and(|path| path.ends_with(".has_violation"))
            && event.value["after"] == true
    }));
    assert!(run.events.iter().any(|event| {
        event.operation == "set"
            && event.value["path"]
                .as_str()
                .is_some_and(|path| path.ends_with(".has_violation"))
            && event.value["before"] == true
            && event.value["after"] == false
    }));
    // A missing reset is observable on reuse even though fresh requests initialize false.
    let stale = program_from_without_reset();
    let failed = stale.run_scenario(
        "reused decision clears a previous violation",
        Default::default(),
    );
    assert!(!failed.ok);
    assert_eq!(failed.state["decision"]["has_violation"], true);
}
fn program_from_without_reset() -> gwt_core::CompiledProgram {
    program(&SOURCE.replace("    set decision.has_violation to false\n", ""))
}

#[test]
fn captured_inputs_replay_and_reveal_an_incorrect_inclusive_violation_boundary() {
    let baseline = program(SOURCE);
    let candidate = program(&SOURCE.replace(
        "policy_violation.amount > report.policy_limit",
        "policy_violation.amount >= report.policy_limit",
    ));
    let mut changes = 0;
    for (name, input, expected, should_change) in cases() {
        let case = capture_request(
            &baseline,
            "review expense report",
            &input,
            Default::default(),
        )
        .unwrap();
        let replay = replay_case(&case).unwrap();
        assert!(replay.verified, "{name}");
        assert_eq!(replay.actual.result.as_ref().unwrap()["decision"], expected);
        let comparison = compare_case(&case, &candidate).unwrap();
        assert_eq!(
            comparison.changes.as_ref().unwrap().outcome,
            should_change,
            "{name}"
        );
        changes += usize::from(should_change);
    }
    assert_eq!(changes, 2);
}
