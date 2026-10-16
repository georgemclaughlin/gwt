use gwt_core::{
    SourceBundle, capture_request, compare_case, compile_bundle, explain_execution, replay_case,
    validate_bundle,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const ENGINE: &str = include_str!("../../../examples/minilang_spec/engine.gwt");
const SCENARIOS: &str = include_str!("../../../examples/minilang_spec/native_scenarios.gwt");
const INPUT: &str = include_str!("../../../examples/minilang_spec/request.json");

fn bundle(engine: &str, scenarios: Option<&str>) -> SourceBundle {
    let mut modules = BTreeMap::from([("engine.gwt".into(), engine.into())]);
    if let Some(scenarios) = scenarios {
        modules.insert("scenarios.gwt".into(), scenarios.into());
    }
    SourceBundle {
        entry: if scenarios.is_some() {
            "scenarios.gwt"
        } else {
            "engine.gwt"
        }
        .into(),
        modules,
    }
}
fn facts() -> Json {
    serde_json::from_str(INPUT).unwrap()
}

#[test]
fn shared_minilang_engine_matches_independent_outputs_and_ordered_errors() {
    let p = compile_bundle(&bundle(ENGINE, None)).unwrap();
    let mut cases = Vec::new();
    cases.push((
        "original",
        facts(),
        json!(["large"]),
        json!(["2", "4", "6", "8"]),
        json!([]),
    ));
    let mut equal = facts();
    equal["front_end"]["statements"][3]["threshold"] = json!(30);
    cases.push((
        "equal threshold",
        equal,
        json!(["small"]),
        json!(["2", "4", "6", "8"]),
        json!([]),
    ));
    let mut order = facts();
    order["front_end"]["statements"]
        .as_array_mut()
        .unwrap()
        .swap(2, 3);
    cases.push((
        "function after call",
        order,
        json!([]),
        json!(["2", "4", "6", "8"]),
        json!(["missing_function_add"]),
    ));
    let mut order = facts();
    order["front_end"]["statements"]
        .as_array_mut()
        .unwrap()
        .swap(0, 3);
    cases.push((
        "call before number",
        order,
        json!([]),
        json!(["2", "4", "6", "8"]),
        json!(["missing_function_add"]),
    ));
    let mut missing = facts();
    missing["runtime"]["bindings"]
        .as_array_mut()
        .unwrap()
        .remove(0);
    cases.push((
        "missing x",
        missing,
        json!([]),
        json!(["2", "4", "6", "8"]),
        json!(["missing_binding_x", "missing_binding_x"]),
    ));
    let mut missing = facts();
    missing["front_end"]["lists"] = json!([]);
    cases.push((
        "missing list",
        missing,
        json!(["large"]),
        json!([]),
        json!(["missing_list_literal_nums", "map_expected_number_list"]),
    ));
    let mut missing = facts();
    missing["front_end"]["statements"]
        .as_array_mut()
        .unwrap()
        .pop();
    cases.push((
        "parse failure",
        missing,
        json!([]),
        json!([]),
        json!(["parse_failed"]),
    ));
    for (name, input, output, mapped, errors) in cases {
        let run = p.run_request("run mini source", &input, Default::default());
        assert!(run.ok, "{name}: {:?}", run.diagnostic);
        let result = run.result.as_ref().unwrap();
        assert_eq!(result["runtime"]["outputs"], output, "{name}");
        assert_eq!(result["runtime"]["mapped_numbers"], mapped, "{name}");
        assert_eq!(result["runtime"]["errors"], errors, "{name}");
        assert_eq!(
            result["runtime"]["status"],
            if errors == json!([]) {
                "passed"
            } else {
                "failed"
            }
        );
        if name == "parse failure" {
            assert_eq!(
                result["front_end"]["errors"],
                json!(["missing_print_map_double", "unexpected_statement_count"])
            );
        }
        explain_execution(&run, p.source_bundle().unwrap()).unwrap();
        let case = capture_request(&p, "run mini source", &input, Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
    }
}

#[test]
fn native_scenarios_validate_and_reused_state_clears_prior_results() {
    let source = bundle(ENGINE, Some(SCENARIOS));
    let report = validate_bundle(&source, Default::default());
    assert!(report.ok, "{report:?}");
    let report = serde_json::to_value(report).unwrap();
    assert_eq!(report["evidence"]["scenarioExpectations"]["passed"], 15);
    let first = SCENARIOS.split("SCENARIO MiniLang parser").next().unwrap();
    let reused = format!(
        "{first}\nWHEN set front_end.statements to []\nREQUEST run mini source\nTHEN runtime.outputs == []\nAND runtime.mapped_numbers == []\nAND runtime.add_defined == false\nAND runtime.errors == [\"parse_failed\"]\nAND runtime.status == \"failed\"\n"
    );
    let p = compile_bundle(&bundle(ENGINE, Some(&reused))).unwrap();
    let result = p.test_scenarios(Default::default());
    assert_eq!(result.len(), 1);
    assert!(
        result[0].execution.ok,
        "{:?}",
        result[0].execution.diagnostic
    );
    let mutant = ENGINE.replace("set runtime.outputs to []", "PASS");
    let p = compile_bundle(&bundle(&mutant, Some(&reused))).unwrap();
    assert!(!p.test_scenarios(Default::default())[0].execution.ok);
}

#[test]
fn captured_boundary_detects_inclusive_comparison_without_changing_other_results() {
    let baseline = compile_bundle(&bundle(ENGINE, None)).unwrap();
    let candidate = compile_bundle(&bundle(
        &ENGINE.replace("> threshold", ">= threshold"),
        None,
    ))
    .unwrap();
    for threshold in [25, 30, 31] {
        let mut input = facts();
        input["front_end"]["statements"][3]["threshold"] = json!(threshold);
        let case =
            capture_request(&baseline, "run mini source", &input, Default::default()).unwrap();
        let comparison = compare_case(&case, &candidate).unwrap();
        assert_eq!(comparison.changes.unwrap().outcome, threshold == 30);
        assert_eq!(
            comparison
                .candidate
                .as_ref()
                .unwrap()
                .result
                .as_ref()
                .unwrap()["runtime"]["mapped_numbers"],
            json!(["2", "4", "6", "8"])
        );
    }
}
