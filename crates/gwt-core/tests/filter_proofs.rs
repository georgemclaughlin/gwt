use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, capture_scenario, compare_case, compile_bundle,
    compile_program, explain_execution, replay_case, scenario_from_case, validate_bundle,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_filter_proofs/rules.gwt");
const BOX: &str = "RECORD Box\n  value: optional<integer>\n";
fn bundle(source: &str) -> SourceBundle {
    SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    }
}
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&bundle(source)).unwrap()
}
fn boxes(body: &str) -> String {
    format!(
        "{BOX}WHEN inspect <items> with <replacement>\n  GIVEN items is list<Box>\n  AND replacement is Box\n{body}REQUEST inspect\n  GIVEN items is list<Box>\n  GIVEN replacement is Box\n  WHEN inspect items with replacement\n  OUTPUT items is list<Box>\n"
    )
}

#[test]
fn pickup_policy_matches_ordered_independent_inputs_and_detects_unready_pickups() {
    let p = program(SOURCE);
    assert!(validate_bundle(&bundle(SOURCE), Default::default()).ok);
    assert_eq!(p.scenario_names().len(), 5);
    let methods = [
        Json::Null,
        json!({"kind":"courier","tracking":"T"}),
        json!({"kind":"counter","code":"","ready":false}),
        json!({"kind":"counter","code":"","ready":true}),
        json!({"kind":"counter","code":"A","ready":false}),
        json!({"kind":"counter","code":"A","ready":true}),
        json!({"kind":"counter","code":"B","ready":true}),
    ];
    let mut queues = vec![vec![]];
    for first in &methods {
        queues.push(vec![first]);
        for second in &methods {
            queues.push(vec![first, second]);
        }
    }
    let candidate = program(&SOURCE.replace(" and parcel.route.ready", ""));
    let mut changed = 0;
    assert_eq!(queues.len(), 57);
    for routes in queues {
        let input_items:Vec<_>=routes.iter().enumerate().map(|(index,route)|json!({"label":format!("parcel-{index}"),"route":route,"prepared":index%2==1})).collect();
        let mut expected_items = input_items.clone();
        let mut codes = Vec::new();
        for item in &mut expected_items {
            let route = &item["route"];
            if route["kind"] == "counter"
                && route["ready"] == true
                && route["code"].as_str().is_some_and(|code| !code.is_empty())
            {
                codes.push(route["code"].clone());
                item["prepared"] = json!(true);
            }
        }
        let expected = json!({"queue":{"parcels":expected_items},"dispatch":{"codes":codes,"first_code":codes.first().cloned().unwrap_or(json!(""))}});
        let case = capture_request(
            &p,
            "prepare pickups",
            &json!({"queue":{"parcels":input_items}}),
            Default::default(),
        )
        .unwrap();
        assert_eq!(case.observed()["ok"], true);
        assert_eq!(case.observed()["result"], expected);
        assert!(replay_case(&case).unwrap().verified);
        let change = compare_case(&case, &candidate)
            .unwrap()
            .changes
            .unwrap()
            .outcome;
        assert_eq!(
            change,
            routes.iter().any(|route| route["kind"] == "counter"
                && route["code"] == "A"
                && route["ready"] == false)
        );
        changed += usize::from(change);
        let generated = scenario_from_case(&case, "reviewed pickups").unwrap();
        assert!(
            compile_bundle(generated.source_bundle())
                .unwrap()
                .test_scenarios(Default::default())
                .iter()
                .all(|s| s.execution.ok)
        );
    }
    assert_eq!(changed, 14);
    for name in p.scenario_names() {
        let case = capture_scenario(&p, name, Default::default()).unwrap();
        assert_eq!(case.observed()["ok"], true);
        assert!(replay_case(&case).unwrap().verified);
    }
}

#[test]
fn optional_items_and_fields_refine_in_for_and_first_match_bodies_only() {
    let source = "RECORD State\n  items: list<optional<integer>>\n  total: integer\n  first: integer\nWHEN inspect <state>\n  GIVEN state is State\n  FOR item in state.items WHERE item is present\n    add item to state.total\n    add 1 to item\n  FIND item in state.items WHERE not (item is absent)\n    set state.first to item\n  ELSE\n    set state.first to -1\nREQUEST inspect\n  GIVEN state is State\n  WHEN inspect state\n  OUTPUT state is State\n";
    let p = program(source);
    for (items, after, total, first) in [
        (json!([null, 0, 2]), json!([null, 1, 3]), 2, 1),
        (json!([null]), json!([null]), 0, -1),
        (json!([]), json!([]), 0, -1),
    ] {
        let run = p.run_request(
            "inspect",
            &json!({"state":{"items":items,"total":0,"first":99}}),
            Default::default(),
        );
        assert_eq!(
            run.result,
            Some(json!({"state":{"items":after,"total":total,"first":first}}))
        );
    }
    for body in [
        "  FOR item in items WHERE item.value is present or true\n    add 1 to item.value\n",
        "  FIND item in items WHERE item.value is absent\n    add 1 to item.value\n  ELSE\n    PASS\n",
        "  FIND item in items WHERE replacement.value is present\n    PASS\n  ELSE\n    add 1 to replacement.value\n",
        "  FOR item in items WHERE replacement.value is present\n    PASS\n  add 1 to replacement.value\n",
        "  FIND item in items WHERE item.value is present\n    PASS\n  ELSE\n    print item.value\n",
    ] {
        assert!(compile_program(&boxes(body), "bad.gwt").is_err(), "{body}");
    }
}

#[test]
fn nested_alias_writes_cannot_clear_selected_item_or_its_present_child() {
    for mutation in [
        "set alias.value to replacement.value",
        "set alias to replacement",
    ] {
        let source = boxes(&format!(
            "  FOR selected in items WHERE selected.value is present\n    FIND alias in items WHERE true\n      {mutation}\n    ELSE\n      PASS\n    add 1 to selected.value\n"
        ));
        let p = program(&source);
        let run = p.run_request(
            "inspect",
            &json!({"items":[{"value":1}],"replacement":{}}),
            Default::default(),
        );
        assert_eq!(run.diagnostic.unwrap().code, "presence_mutation");
        assert_eq!(run.state["items"], json!([{"value":1}]));
        assert!(!run.events.iter().any(|e| e.operation == "set"));
        assert_eq!(
            p.run_request(
                "inspect",
                &json!({"items":[{"value":1}],"replacement":{"value":9}}),
                Default::default()
            )
            .result,
            Some(json!({"items":[{"value":10}]}))
        );
    }
    let p = program(&boxes(
        "  FOR selected in items WHERE selected.value is present\n    append replacement to items\n",
    ));
    assert_eq!(
        p.run_request(
            "inspect",
            &json!({"items":[{"value":1}],"replacement":{}}),
            Default::default()
        )
        .diagnostic
        .unwrap()
        .code,
        "collection_mutation"
    );
}

#[test]
fn kind_filters_protect_the_allowed_set_and_keep_exact_helper_contracts() {
    let source = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\n  pickup:\n    number: text\nWHEN inspect <items> with <replacement>\n  GIVEN items is list<Contact>\n  AND replacement is Contact\n  FOR selected in items WHERE selected.kind != \"email\"\n    FIND alias in items WHERE true\n      set alias to replacement\n    ELSE\n      PASS\n    print selected.number\nREQUEST inspect\n  GIVEN items is list<Contact>\n  GIVEN replacement is Contact\n  WHEN inspect items with replacement\n  OUTPUT items is list<Contact>\n";
    for kind in ["phone", "pickup", "email"] {
        let replacement = if kind == "email" {
            json!({"kind":kind,"address":"new"})
        } else {
            json!({"kind":kind,"number":"new"})
        };
        let run = program(source).run_request(
            "inspect",
            &json!({"items":[{"kind":"phone","number":"old"}],"replacement":replacement}),
            Default::default(),
        );
        if kind == "email" {
            assert_eq!(run.diagnostic.unwrap().code, "kind_mutation");
            assert_eq!(run.state["items"], json!([{"kind":"phone","number":"old"}]));
            assert!(run.output.is_empty());
        } else {
            assert_eq!(run.result, Some(json!({"items":[replacement]})));
            assert_eq!(run.output, vec![json!("new")]);
        }
    }
    let helpers = "WHEN increase <value>\n  GIVEN value is integer\n  add 1 to value\nWHEN optional <value>\n  GIVEN value is optional<integer>\n  PASS\n";
    for call in ["increase item.value", "optional (item.value)"] {
        let p = program(
            &(boxes(&format!(
                "  FOR item in items WHERE item.value is present\n    {call}\n"
            )) + helpers),
        );
        assert!(
            p.run_request(
                "inspect",
                &json!({"items":[{}, {"value":0}],"replacement":{}}),
                Default::default()
            )
            .ok
        );
    }
    assert!(
        compile_program(
            &(boxes("  FOR item in items WHERE item.value is present\n    optional item.value\n")
                + helpers),
            "bad.gwt"
        )
        .is_err()
    );
}

#[test]
fn external_proofs_are_body_local_and_filters_observe_live_state() {
    let source = "RECORD Box\n  value: optional<integer>\n  enabled: boolean\nWHEN inspect <box> with <alias> and <replacement>\n  GIVEN box is Box\n  AND alias is Box\n  AND replacement is Box\n  FOR item in [1, 2] WHERE box.value is present and box.enabled\n    add item to box.value\n    set box.enabled to false\n  set alias to replacement\nREQUEST inspect\n  GIVEN box is Box\n  GIVEN replacement is Box\n  WHEN inspect box with box and replacement\n  OUTPUT box is Box\n";
    let input = json!({"box":{"value":0,"enabled":true},"replacement":{"enabled":false}});
    let run = program(source).run_request("inspect", &input, Default::default());
    assert_eq!(
        run.result,
        Some(json!({"box":{"value":null,"enabled":false}}))
    );
    let selections: Vec<_> = run
        .events
        .iter()
        .filter(|e| e.operation == "collection selection")
        .map(|e| e.value["selected"].clone())
        .collect();
    assert_eq!(selections, vec![json!(true), json!(false)]);
    assert_eq!(
        run.events.iter().filter(|e| e.operation == "add").count(),
        1
    );
    let blocked = source.replace(
        "    add item to box.value",
        "    set alias to replacement\n    add item to box.value",
    );
    assert_eq!(
        program(&blocked)
            .run_request("inspect", &input, Default::default())
            .diagnostic
            .unwrap()
            .code,
        "presence_mutation"
    );
    let live = boxes(
        "  FOR selected in items WHERE selected.value is present\n    IF selected.value == 1\n      FIND later in items WHERE later.value is present and later.value == 2\n        set later.value to 9\n      ELSE\n        PASS\n    print selected.value\n",
    );
    assert_eq!(
        program(&live)
            .run_request(
                "inspect",
                &json!({"items":[{"value":1},{"value":2}],"replacement":{}}),
                Default::default()
            )
            .output,
        vec![json!(1), json!(9)]
    );
}

#[test]
fn loop_exit_return_and_caught_failure_release_guards_without_releasing_callers() {
    let source = boxes(
        "  FOR item in items WHERE item.value is present\n    add 1 to item.value\n  FOR item in items\n    set item to replacement\n",
    );
    assert_eq!(
        program(&source)
            .run_request(
                "inspect",
                &json!({"items":[{"value":1},{}],"replacement":{}}),
                Default::default()
            )
            .result,
        Some(json!({"items":[{"value":null},{"value":null}]}))
    );
    let source = format!(
        "{BOX}WHEN first in <items>\n  GIVEN items is list<Box>\n  THEN returns integer\n  FIND item in items WHERE item.value is present\n    RETURN item.value\n  ELSE\n    RETURN -1\nWHEN refuse <items>\n  GIVEN items is list<Box>\n  FOR item in items WHERE item.value is present\n    add 1 to item.value\n    REQUIRE false\nGIVEN item is Box\n  value: 1\nGIVEN items is [item]\nWHEN LET first be first in items\nTHEN first == 1\nWHEN refuse items\nTHEN fails with \"assertion_failed\"\nWHEN append item to items\nTHEN first == 1\n"
    );
    // First mutation persists across the caught failure; appended item is a copy
    // of the original root binding, not an alias of the changed collection entry.
    let run = program(&source).run_scenario("Main", Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.state["items"], json!([{"value":2},{"value":1}]));
    let caller = boxes(
        "  REQUIRE replacement.value is present\n  FOR item in items WHERE item.value is present\n    PASS\n  erase (items) with replacement and replacement\n",
    ) + "WHEN erase <items> with <selected> and <alias>\n  GIVEN items is list<Box>\n  AND selected is Box\n  AND alias is Box\n  FIND empty in items WHERE true\n    set alias to empty\n  ELSE\n    PASS\n";
    // The caller's refined record cannot be passed as a wider shared contract.
    assert!(compile_program(&caller, "bad.gwt").is_err());
}

#[test]
fn filter_evidence_short_circuits_and_maps_expanded_unicode_sources() {
    let source="RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\nSCENARIO café 😀\nGIVEN contact is Contact\n  kind: \"email\"\n  address: \"<address>\"\nGIVEN contacts is [contact]\nWHEN emit emails in contacts\nTHEN prints [\"<address>\"]\nEXAMPLES\n  | address |\n  | first |\n  | second |\nWHEN emit emails in <contacts>\n  GIVEN contacts is list<Contact>\n  FOR contact in contacts WHERE contact.kind == \"email\"\n    print contact.address\n".replace('\n',"\r\n");
    let p = program(&source);
    for name in p.scenario_names() {
        let run = p.run_scenario(name, Default::default());
        assert!(run.ok);
        let selection = run
            .events
            .iter()
            .find(|e| e.operation == "collection selection")
            .unwrap();
        assert_eq!(
            &source[selection.span.start..selection.span.end],
            "contact.kind == \"email\""
        );
        assert_eq!(selection.value["selected"], true);
        explain_execution(&run, p.source_bundle().unwrap()).unwrap();
        assert!(
            replay_case(&capture_scenario(&p, name, Default::default()).unwrap())
                .unwrap()
                .verified
        );
    }
    let p = program(SOURCE);
    let input = json!({"queue":{"parcels":[{"label":"missing","route":null,"prepared":false}]}});
    let run = p.run_request("prepare pickups", &input, Default::default());
    assert!(run.ok);
    assert!(
        !run.events
            .iter()
            .any(|e| e.operation.starts_with("read parcel.route."))
    );
    assert!(!run.events.iter().any(|e| e.operation == "assert"));
    for steps in 0..=run.steps {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let case = capture_request(&p, "prepare pickups", &input, limits).unwrap();
        assert_eq!(case.observed()["ok"], steps == run.steps);
        assert!(replay_case(&case).unwrap().verified);
    }
}

#[test]
fn ending_filter_proofs_preserves_caller_guards_and_failed_search_adds_none() {
    let source = format!(
        "{BOX}WHEN inspect <box> through <alias> with <empty>\n  GIVEN box is Box\n  AND alias is Box\n  AND empty is Box\n  REQUIRE box.value is present\n  FOR item in [1, 2] WHERE alias.value is present\n    PASS\n  set alias to empty\nREQUEST inspect\n  GIVEN box is Box\n  GIVEN empty is Box\n  WHEN inspect box through box with empty\n  OUTPUT box is Box\n"
    );
    let run = program(&source).run_request(
        "inspect",
        &json!({"box":{"value":1},"empty":{}}),
        Default::default(),
    );
    assert_eq!(run.diagnostic.unwrap().code, "presence_mutation");
    assert_eq!(run.state["box"], json!({"value":1}));
    let fallback = boxes(
        "  FIND item in items WHERE replacement.value is present\n    add 1 to replacement.value\n  ELSE\n    append replacement to items\n",
    );
    let run = program(&fallback).run_request(
        "inspect",
        &json!({"items":[{}],"replacement":{}}),
        Default::default(),
    );
    assert_eq!(
        run.result,
        Some(json!({"items":[{"value":null},{"value":null}]}))
    );
}
