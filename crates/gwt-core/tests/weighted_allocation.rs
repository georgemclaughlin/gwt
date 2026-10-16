use gwt_core::{ProgramLimits, compile_program, format_source};
use serde_json::{Value, json};

const SOURCE: &str = include_str!("../../../examples/native_weighted_allocation/rules.gwt");

#[test]
fn allocation_matches_independent_rational_quota_and_sort_oracle() {
    let program = compile_program(SOURCE, "rules.gwt").unwrap();
    let fixture: Value =
        serde_json::from_str(include_str!("fixtures/weighted_allocation.json")).unwrap();
    let cases = fixture["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 1004);
    for (i, row) in cases.iter().enumerate() {
        let result =
            program.run_request("allocate budget", &row["input"], ProgramLimits::default());
        if let Some(code) = row["expected"]["failure"].as_str() {
            assert!(!result.ok, "case {i}");
            assert_eq!(result.diagnostic.as_ref().unwrap().code, code, "case {i}");
            assert_eq!(
                result.state["allocation"],
                json!({"shares":[],"total":"0"}),
                "case {i}"
            );
        } else {
            assert!(result.ok, "case {i}: {:?}", result.diagnostic);
            assert_eq!(result.result, Some(row["expected"].clone()), "case {i}");
        }
    }
}

#[test]
fn allocation_scenarios_format_and_host_contract_stay_executable() {
    assert_eq!(format_source(SOURCE, "rules.gwt").unwrap().text, SOURCE);
    let program = compile_program(SOURCE, "rules.gwt").unwrap();
    let scenarios = program.test_scenarios(ProgramLimits::default());
    assert_eq!(scenarios.len(), 11);
    assert!(
        scenarios.iter().all(|run| run.execution.ok),
        "{scenarios:?}"
    );
    let input: Value = serde_json::from_str(include_str!(
        "../../../examples/native_weighted_allocation/request.json"
    ))
    .unwrap();
    let result = program.run_request("allocate budget", &input, ProgramLimits::default());
    assert!(result.ok, "{:?}", result.diagnostic);
    let amounts: Vec<_> = result.result.as_ref().unwrap()["allocation"]["shares"]
        .as_array()
        .unwrap()
        .iter()
        .map(|row| row["amount"].clone())
        .collect();
    assert_eq!(amounts, vec![json!("0.34"), json!("0.33"), json!("0.33")]);
}
