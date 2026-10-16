use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, compare_case, compile_bundle, explain_execution,
    replay_case,
};
use serde_json::{Value, json};
use std::collections::BTreeMap;

const RULES: &str = include_str!("../../../examples/native_lookup/rules.gwt");

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

#[test]
fn three_lookup_contracts_match_independent_list_expectations() {
    let program = program(RULES);
    let inventories = [
        json!([]),
        json!([{"sku":"widget","available":5}]),
        json!([{"sku":"other","available":7},{"sku":"widget","available":5}]),
        json!([{"sku":"widget","available":5},{"sku":"widget","available":9}]),
        json!([{"sku":"other","available":7}]),
    ];
    let mut executions = 0;
    for items in inventories {
        for sku in ["widget", "other", "missing"] {
            let index = items
                .as_array()
                .unwrap()
                .iter()
                .position(|item| item["sku"] == sku);
            for available in [0, 2, 5, 9] {
                let input = json!({"inventory":{"items":items},"reading":{"sku":sku,"available":available}});
                let proposed = index.map(|_| json!({"sku":sku,"available":available}));
                let preview =
                    program.run_request("preview stock count", &input, ProgramLimits::default());
                assert!(preview.ok, "{:?}", preview.diagnostic);
                assert_eq!(
                    preview.result.unwrap(),
                    json!({"selection":{"item":proposed},"inventory":{"items":items}})
                );
                let mut adjusted = items.clone();
                if let Some(index) = index {
                    adjusted[index]["available"] = json!(available);
                }
                let recorded =
                    program.run_request("record stock count", &input, ProgramLimits::default());
                assert!(recorded.ok, "{:?}", recorded.diagnostic);
                assert_eq!(
                    recorded.result.unwrap(),
                    json!({"inventory":{"items":adjusted},"receipt":{"matched":index.is_some()}})
                );
                executions += 2;
            }
            for previous in [Value::Null, json!({"sku":"prior","available":13})] {
                let expected = index
                    .map(|index| items[index].clone())
                    .unwrap_or(previous.clone());
                let retained = program.run_request("retain stock selection", &json!({
                    "inventory":{"items":items},"query":{"sku":sku},"selection":{"item":previous}
                }), ProgramLimits::default());
                assert!(retained.ok, "{:?}", retained.diagnostic);
                assert_eq!(
                    retained.result.unwrap(),
                    json!({"selection":{"item":expected},"inventory":{"items":items}})
                );
                executions += 1;
            }
        }
    }
    assert_eq!(executions, 150);
    let scenarios = program.test_scenarios(ProgramLimits::default());
    assert_eq!(scenarios.len(), 7);
    assert!(scenarios.iter().all(|scenario| scenario.execution.ok));
}

#[test]
fn copied_destination_cannot_substitute_for_mutation_of_a_found_item() {
    let candidate = program(RULES);
    let unsafe_rewrite = RULES.replace(
        "    set item.available to reading.available",
        "    LET selected be item\n    set selected.available to reading.available",
    );
    assert_ne!(unsafe_rewrite, RULES);
    let baseline = program(&unsafe_rewrite);
    for (sku, available, changed) in [
        ("widget", 2, true),
        ("widget", 5, false),
        ("missing", 2, false),
    ] {
        let input = json!({"inventory":{"items":[{"sku":"widget","available":5},{"sku":"widget","available":9}]},"reading":{"sku":sku,"available":available}});
        let case = capture_request(
            &baseline,
            "record stock count",
            &input,
            ProgramLimits::default(),
        )
        .unwrap();
        assert!(replay_case(&case).unwrap().verified);
        let review = compare_case(&case, &candidate).unwrap();
        assert_eq!(review.changes.as_ref().unwrap().outcome, changed);
        let after = review.candidate.as_ref().unwrap();
        assert_eq!(
            after.state["inventory"]["items"][0]["available"],
            json!(if sku == "widget" { available } else { 5 })
        );
        assert_eq!(after.state["inventory"]["items"][1]["available"], json!(9));
        explain_execution(after, candidate.source_bundle().unwrap()).unwrap();
    }
}

#[test]
fn invalid_readings_fail_before_inventory_changes_and_optional_access_requires_proof() {
    let program = program(RULES);
    let inventory = json!({"items":[{"sku":"widget","available":5}]});
    for request in ["preview stock count", "record stock count"] {
        let failed = program.run_request(
            request,
            &json!({"inventory":inventory,"reading":{"sku":"widget","available":-1}}),
            ProgramLimits::default(),
        );
        assert!(!failed.ok);
        assert_eq!(failed.state["inventory"], inventory);
        assert!(failed.result.is_none());
    }
    let unguarded = RULES.replace(
        "  IF selection.item is present\n    set selection.item.available to reading.available",
        "  set selection.item.available to reading.available",
    );
    let error = gwt_core::compile_program(&unguarded, "unguarded.gwt").unwrap_err();
    assert_eq!(error.code, "invalid_path");
    assert!(error.message.contains("is present"));
}
