use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, compare_case, compile_bundle, compile_program,
    explain_execution, replay_case, scenario_from_case,
};
use serde_json::json;
use std::collections::BTreeMap;

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

#[test]
fn returning_lookup_preserves_first_match_failures_state_and_evidence() {
    let source = "RECORD State\n  attempts: integer\nWHEN first positive in <items> with <state>\n  GIVEN items is list<integer>\n  AND state is State\n  THEN returns integer\n  add 1 to state.attempts\n  print \"search\"\n  FIND item in items WHERE item > 0\n    RETURN item\n  ELSE\n    REQUIRE false\nREQUEST lookup\n  GIVEN items is list<integer>\n  GIVEN state is State\n  WHEN LET answer be first positive in items with state\n  OUTPUT answer is integer\n  OUTPUT state is State\n";
    let p = program(source);
    let faulty = program(&source.replace("item > 0", "item >= 0"));
    for (items, expected) in [
        (json!([]), None),
        (json!([-2, 0]), None),
        (json!([0, 2, 7]), Some(2)),
        (json!([7, 2]), Some(7)),
        (json!([-1, 4, 4]), Some(4)),
    ] {
        let input = json!({"items":items,"state":{"attempts":3}});
        let case = capture_request(&p, "lookup", &input, Default::default()).unwrap();
        assert_eq!(case.observed()["ok"], expected.is_some());
        assert_eq!(case.observed()["state"]["state"]["attempts"], 4);
        assert_eq!(case.observed()["output"], json!(["search"]));
        if let Some(answer) = expected {
            assert_eq!(case.observed()["result"]["answer"], answer);
        } else {
            assert_eq!(case.observed()["diagnostic"]["code"], "assertion_failed");
            assert!(case.observed()["state"].get("answer").is_none());
            assert!(case.observed()["result"].is_null());
        }
        assert!(replay_case(&case).unwrap().verified);
        let run = p.run_request("lookup", &input, Default::default());
        explain_execution(&run, p.source_bundle().unwrap()).unwrap();
        assert_eq!(
            run.events
                .iter()
                .filter(|e| e.operation == "return")
                .count(),
            usize::from(expected.is_some())
        );
        let generated = scenario_from_case(&case, "lookup observation").unwrap();
        assert!(
            compile_bundle(generated.source_bundle())
                .unwrap()
                .test_scenarios(Default::default())[0]
                .execution
                .ok
        );
        assert_eq!(
            compare_case(&case, &faulty)
                .unwrap()
                .changes
                .unwrap()
                .outcome,
            items.as_array().unwrap().iter().any(|n| n == 0)
        );
    }
}

#[test]
fn exit_analysis_covers_branches_but_does_not_evaluate_arbitrary_expressions() {
    for body in [
        "  REQUIRE false\n",
        "  REQUIRE (false)\n",
        "  IF flag\n    RETURN 7\n  ELSE\n    REQUIRE false\n",
        "  DECIDE\n    WHEN flag\n      RETURN 7\n    ELSE\n      REQUIRE false\n",
        "  DEPENDING ON flag\n    WHEN the value is true\n      RETURN 7\n    WHEN the value is false\n      REQUIRE false\n",
        "  FIND item in items WHERE item == 7\n    RETURN item\n  ELSE\n    REQUIRE false\n",
        "  IF flag\n    REQUIRE false\n  REQUIRE false\n",
    ] {
        let source = format!(
            "WHEN choose <flag> from <items>\n  GIVEN flag is boolean\n  AND items is list<integer>\n  THEN returns integer\n{body}REQUEST choose\n  GIVEN flag is boolean\n  GIVEN items is list<integer>\n  WHEN LET answer be choose flag from items\n  OUTPUT answer is integer\n"
        );
        let p = program(&source);
        for flag in [true, false] {
            for items in [json!([]), json!([7])] {
                let run = p.run_request(
                    "choose",
                    &json!({"flag":flag,"items":items}),
                    Default::default(),
                );
                if run.ok {
                    assert_eq!(run.result, Some(json!({"answer":7})));
                } else {
                    assert_eq!(run.diagnostic.unwrap().code, "assertion_failed");
                }
            }
        }
    }
    for body in [
        "  REQUIRE true\n",
        "  REQUIRE not true\n",
        "  REQUIRE 1 == 2\n",
        "  REQUIRE flag\n",
        "  FOR item in [7]\n    REQUIRE false\n",
        "  IF flag\n    REQUIRE false\n",
        "  FIND item in [7] WHERE item > 0\n    RETURN item\n  ELSE\n    PASS\n",
    ] {
        let source =
            format!("WHEN choose <flag>\n  GIVEN flag is boolean\n  THEN returns integer\n{body}");
        assert_eq!(
            compile_program(&source, "bad.gwt").unwrap_err().code,
            "missing_return",
            "{body}"
        );
    }
    // A helper failure is not inferred across calls, and unreachable source is
    // still checked. No fabricated proof escapes a branch with no survivors.
    for source in [
        "WHEN fail\n  REQUIRE false\nWHEN choose\n  THEN returns integer\n  fail\n",
        "WHEN choose\n  THEN returns integer\n  REQUIRE false\n  RETURN unknown\n",
        "WHEN choose <value>\n  GIVEN value is optional<integer>\n  THEN returns integer\n  IF value is absent\n    REQUIRE false\n  ELSE\n    REQUIRE false\n  RETURN value\n",
    ] {
        assert!(compile_program(source, "bad.gwt").is_err());
    }
}

#[test]
fn failed_paths_do_not_dilute_presence_or_kind_proofs_and_guards_remain_live() {
    let source = "RECORD Box\n  value: optional<integer>\nWHEN choose <selected> with <alias> and <replacement>\n  GIVEN selected is Box\n  AND alias is Box\n  AND replacement is Box\n  THEN returns integer\n  IF selected.value is absent\n    REQUIRE false\n  set alias to replacement\n  RETURN selected.value\nREQUEST choose\n  GIVEN box is Box\n  GIVEN replacement is Box\n  WHEN LET answer be choose box with box and replacement\n  OUTPUT answer is integer\n  OUTPUT box is Box\n";
    let p = program(source);
    for (value, replacement, diagnostic, answer) in [
        (
            json!(null),
            json!({"value":7}),
            Some("assertion_failed"),
            None,
        ),
        (json!(2), json!({}), Some("presence_mutation"), None),
        (json!(2), json!({"value":7}), None, Some(7)),
    ] {
        let run = p.run_request(
            "choose",
            &json!({"box":{"value":value},"replacement":replacement}),
            Default::default(),
        );
        assert_eq!(run.diagnostic.as_ref().map(|d| d.code.as_str()), diagnostic);
        if let Some(answer) = answer {
            assert_eq!(run.result, Some(json!({"answer":answer,"box":{"value":7}})));
        } else {
            assert_eq!(run.state["box"]["value"], value);
            assert!(!run.events.iter().any(|e| e.operation == "set"));
        }
    }
    let kind_source = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\nWHEN address for <contact>\n  GIVEN contact is Contact\n  THEN returns text\n  DEPENDING ON contact\n    WHEN the kind is email\n      PASS\n    ELSE\n      REQUIRE false\n  RETURN contact.address\nREQUEST address\n  GIVEN contact is Contact\n  WHEN LET address be address for contact\n  OUTPUT address is text\n";
    let p = program(kind_source);
    let run = p.run_request(
        "address",
        &json!({"contact":{"kind":"email","address":"a@b"}}),
        Default::default(),
    );
    assert_eq!(run.result, Some(json!({"address":"a@b"})));
    let run = p.run_request(
        "address",
        &json!({"contact":{"kind":"phone","number":"555"}}),
        Default::default(),
    );
    assert_eq!(run.diagnostic.unwrap().code, "assertion_failed");
    // The proof must not remain registered after a normally returning helper.
    let release = source.replace("  set alias to replacement\n", "").replace(
        "  OUTPUT answer is integer\n",
        "  WHEN set box to replacement\n  OUTPUT answer is integer\n",
    );
    let run = program(&release).run_request(
        "choose",
        &json!({"box":{"value":2},"replacement":{}}),
        Default::default(),
    );
    assert_eq!(run.result, Some(json!({"answer":2,"box":{"value":null}})));
    let failed_scope = "RECORD Box\n  value: optional<integer>\nWHEN fail after guarding <box>\n  GIVEN box is Box\n  THEN returns integer\n  IF box.value is absent\n    REQUIRE false\n  REQUIRE false\nGIVEN box is Box\n  value: 2\nWHEN LET empty be Box:\nWHEN LET answer be fail after guarding box\nTHEN fails with \"assertion_failed\"\nWHEN set box to empty\nTHEN box.value is absent\n";
    let p = program(failed_scope);
    assert!(p.test_scenarios(Default::default())[0].execution.ok);
}

#[test]
fn inventory_entry_preserves_policy_and_inspects_copied_first_matches() {
    let bundle = SourceBundle {
        entry: "native_scenarios.gwt".into(),
        modules: BTreeMap::from([
            (
                "rules.gwt".into(),
                include_str!("../../../examples/inventory_allocation_spike/rules.gwt").into(),
            ),
            (
                "native_scenarios.gwt".into(),
                include_str!("../../../examples/inventory_allocation_spike/native_scenarios.gwt")
                    .into(),
            ),
        ]),
    };
    let p = compile_bundle(&bundle).unwrap();
    let scenarios = p.test_scenarios(Default::default());
    assert_eq!(scenarios.len(), 5);
    assert!(scenarios.iter().all(|s| s.execution.ok));
    for available in [0, 1, 2, 3, 7] {
        for quantity in [1, 2, 4] {
            let input = json!({"order":{"order_id":"test","payment_status":"paid","fraud_score":0,"expedited":false,"items":[{"sku":"widget","quantity":quantity},{"sku":"widget","quantity":quantity}]},"inventory":{"items":[{"sku":"widget","available":available,"reserved":0},{"sku":"widget","available":100,"reserved":0}]}});
            let reserved = available.min(quantity * 2);
            let case =
                capture_request(&p, "fulfill order", &input, ProgramLimits::default()).unwrap();
            assert_eq!(case.observed()["ok"], true);
            assert_eq!(
                case.observed()["result"]["fulfillment"]["reserved_units"],
                reserved.to_string()
            );
            assert_eq!(
                case.observed()["result"]["fulfillment"]["backordered_units"],
                (quantity * 2 - reserved).to_string()
            );
            assert_eq!(
                case.observed()["result"]["inventory"]["items"][0]["available"],
                (available - reserved).to_string()
            );
            assert_eq!(
                case.observed()["result"]["inventory"]["items"][1]["available"],
                "100"
            );
            assert!(replay_case(&case).unwrap().verified);
        }
    }
    let faulty = SourceBundle {
        modules: bundle
            .modules
            .iter()
            .map(|(name, source)| {
                (
                    name.clone(),
                    source.replace("item.sku == sku", "item.sku != sku"),
                )
            })
            .collect(),
        ..bundle
    };
    assert!(
        compile_bundle(&faulty)
            .unwrap()
            .test_scenarios(Default::default())
            .iter()
            .any(|s| !s.execution.ok)
    );
}
