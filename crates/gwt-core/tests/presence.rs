use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, capture_scenario, compare_case, compile_bundle,
    compile_program, explain_execution, format_source, replay_case, scenario_from_case,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_presence/rules.gwt");
const BOX: &str = "RECORD Box\n  value: optional<integer>\n";

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

fn aliased(body: &str, helpers: &str) -> String {
    format!(
        "{BOX}REQUEST examine\n  GIVEN box is Box\n  GIVEN replacement is Box\n  WHEN examine box with box and replacement\n  OUTPUT box is Box\nWHEN examine <box> with <alias> and <replacement>\n  GIVEN box is Box\n  AND alias is Box\n  AND replacement is Box\n{body}{helpers}"
    )
}

#[test]
fn reimbursement_policy_covers_missing_null_false_zero_and_present_values() {
    let p = program(SOURCE);
    let example_input: Json = serde_json::from_str(include_str!(
        "../../../examples/native_presence/request.json"
    ))
    .unwrap();
    assert_eq!(
        p.run_request("review reimbursement", &example_input, Default::default())
            .result,
        Some(
            json!({"decision":{"status":"approved","reason":"within_limit","payable":100,"reference":"R-1"}})
        )
    );
    let candidate = program(&SOURCE.replace(
        "facts.amount > facts.policy.limit",
        "facts.amount >= facts.policy.limit",
    ));
    let mut changed = 0;
    for amount in [0, 50, 100, 101] {
        for policy in [
            Json::Null,
            json!({"limit":0}),
            json!({"limit":50}),
            json!({"limit":100}),
        ] {
            for receipt in [
                Json::Null,
                json!({"verified":false,"reference":"R"}),
                json!({"verified":true}),
                json!({"verified":true,"reference":""}),
                json!({"verified":true,"reference":"R"}),
            ] {
                let (status, reason) = if policy.is_null() {
                    ("review", "missing_policy")
                } else if receipt.is_null() {
                    ("review", "missing_receipt")
                } else if receipt["verified"] == false {
                    ("denied", "unverified_receipt")
                } else if amount > policy["limit"].as_i64().unwrap() {
                    ("denied", "over_limit")
                } else {
                    ("approved", "within_limit")
                };
                let expected = json!({"decision":{"status":status,"reason":reason,"payable":if status=="approved" {amount} else {0},"reference":receipt.get("reference").and_then(Json::as_str).unwrap_or("not recorded")}});
                let input = json!({"facts":{"amount":amount,"policy":policy,"receipt":receipt}});
                let case = capture_request(&p, "review reimbursement", &input, Default::default())
                    .unwrap();
                assert!(
                    case.observed()["ok"].as_bool().unwrap(),
                    "{input}: {:?}",
                    case.observed()
                );
                assert_eq!(case.observed()["result"], expected, "{input}");
                assert!(replay_case(&case).unwrap().verified);
                let comparison = compare_case(&case, &candidate).unwrap();
                let boundary = status == "approved" && policy["limit"] == amount;
                assert_eq!(comparison.changes.unwrap().outcome, boundary);
                changed += usize::from(boundary);
                let generated = scenario_from_case(&case, "reviewed reimbursement").unwrap();
                assert!(
                    compile_bundle(generated.source_bundle())
                        .unwrap()
                        .test_scenarios(Default::default())
                        .iter()
                        .all(|s| s.execution.ok)
                );
            }
        }
    }
    assert_eq!(changed, 9);
    let omitted = p.run_request(
        "review reimbursement",
        &json!({"facts":{"amount":0}}),
        Default::default(),
    );
    let explicit_null = p.run_request(
        "review reimbursement",
        &json!({"facts":{"amount":0,"policy":null,"receipt":null}}),
        Default::default(),
    );
    assert_eq!(omitted.result, explicit_null.result);
    for input in [
        json!({"facts":{"amount":-1}}),
        json!({"facts":{"amount":1,"policy":{"limit":-1}}}),
    ] {
        let run = p.run_request("review reimbursement", &input, Default::default());
        assert_eq!(run.diagnostic.unwrap().code, "assertion_failed");
    }
    let rows = p.test_scenarios(Default::default());
    assert_eq!(rows.len(), 6);
    assert!(rows.iter().all(|s| s.execution.ok));
    assert!(!format_source(SOURCE, "rules.gwt").unwrap().changed);
}

#[test]
fn direct_negated_conjunction_and_false_disjunction_proofs_stay_in_scope() {
    for body in [
        "  IF box.value is present\n    add 1 to box.value\n",
        "  IF box.value is absent\n    PASS\n  ELSE\n    add 1 to box.value\n",
        "  IF not (box.value is absent)\n    add 1 to box.value\n",
        "  IF box.value is present and box.value >= 0\n    add 1 to box.value\n",
        "  IF box.value is absent or replacement.value is absent\n    PASS\n  ELSE\n    add replacement.value to box.value\n",
    ] {
        let p = program(&aliased(body, ""));
        for value in [Json::Null, json!(0), json!(4)] {
            let run = p.run_request(
                "examine",
                &json!({"box":{"value":value},"replacement":{"value":1}}),
                Default::default(),
            );
            assert!(run.ok, "{body}: {:?}", run.diagnostic);
            assert_eq!(
                run.result.unwrap()["box"]["value"],
                value.as_i64().map(|n| json!(n + 1)).unwrap_or(Json::Null)
            );
        }
    }
    for body in [
        "  IF box.value is present or true\n    add 1 to box.value\n",
        "  IF box.value is present and false\n    PASS\n  ELSE\n    add 1 to box.value\n",
        "  IF box.value is present\n    PASS\n  add 1 to box.value\n",
        "  IF box.value is present\n    add 1 to alias.value\n",
        "  REQUIRE box.value == 1\n",
    ] {
        assert!(
            compile_program(&aliased(body, ""), "bad.gwt").is_err(),
            "{body}"
        );
    }
}

#[test]
fn aliases_and_ancestors_cannot_clear_an_active_presence_proof() {
    for mutation in [
        "set alias.value to replacement.value",
        "set alias to replacement",
        "replace alias with replacement",
    ] {
        let source = aliased(
            &format!("  IF box.value is present\n    {mutation}\n    add 1 to box.value\n"),
            "WHEN replace <target> with <replacement>\n  GIVEN target is Box\n  AND replacement is Box\n  set target to replacement\n",
        );
        let p = program(&source);
        let cleared = p.run_request(
            "examine",
            &json!({"box":{"value":4},"replacement":{}}),
            Default::default(),
        );
        assert_eq!(cleared.diagnostic.unwrap().code, "presence_mutation");
        assert_eq!(cleared.state["box"]["value"], 4);
        assert!(!cleared.events.iter().any(|e| e.operation == "set"));
        let updated = p.run_request(
            "examine",
            &json!({"box":{"value":4},"replacement":{"value":10}}),
            Default::default(),
        );
        assert_eq!(updated.result, Some(json!({"box":{"value":11}})));
    }
}

#[test]
fn nested_optional_ancestors_and_remaining_decision_proofs_are_guarded() {
    let source = "RECORD Inner\n  value: optional<integer>\nRECORD Outer\n  inner: optional<Inner>\nREQUEST examine\n  GIVEN outer is Outer\n  GIVEN replacement is Outer\n  WHEN examine outer with outer and replacement\n  OUTPUT outer is Outer\nWHEN examine <outer> with <alias> and <replacement>\n  GIVEN outer is Outer\n  AND alias is Outer\n  AND replacement is Outer\n  DECIDE\n    WHEN outer.inner is absent\n      PASS\n    WHEN outer.inner.value is absent\n      PASS\n    ELSE\n      set alias to replacement\n      add 1 to outer.inner.value\n";
    let p = program(source);
    for replacement in [json!({}), json!({"inner":{}})] {
        let run = p.run_request(
            "examine",
            &json!({"outer":{"inner":{"value":5}},"replacement":replacement}),
            Default::default(),
        );
        assert_eq!(run.diagnostic.unwrap().code, "presence_mutation");
        assert_eq!(run.state["outer"]["inner"]["value"], 5);
    }
    let run = p.run_request(
        "examine",
        &json!({"outer":{"inner":{"value":5}},"replacement":{"inner":{"value":10}}}),
        Default::default(),
    );
    assert_eq!(run.result, Some(json!({"outer":{"inner":{"value":11}}})));
    let compound = source.replace("  DECIDE\n    WHEN outer.inner is absent\n      PASS\n    WHEN outer.inner.value is absent\n      PASS\n    ELSE", "  IF outer.inner is present and outer.inner.value is present").replace("      set alias", "    set alias").replace("      add 1", "    add 1");
    assert!(
        program(&compound)
            .run_request(
                "examine",
                &json!({"outer":{},"replacement":{}}),
                Default::default()
            )
            .ok
    );
}

#[test]
fn proven_values_support_exact_shared_helpers_and_isolated_optional_copies() {
    let body = "  IF box.value is present\n    increment box.value\n    clear (box.value) using replacement.value\n    REQUIRE box.value == 5\n";
    let helpers = "WHEN increment <value>\n  GIVEN value is integer\n  add 1 to value\nWHEN clear <value> using <replacement>\n  GIVEN value is optional<integer>\n  AND replacement is optional<integer>\n  set value to replacement\n";
    let p = program(&aliased(body, helpers));
    let run = p.run_request(
        "examine",
        &json!({"box":{"value":4},"replacement":{}}),
        Default::default(),
    );
    assert_eq!(run.result, Some(json!({"box":{"value":5}})));
    let invalid = aliased(
        &body.replace("clear (box.value)", "clear box.value"),
        helpers,
    );
    assert_eq!(
        compile_program(&invalid, "bad.gwt").unwrap_err().code,
        "argument_type"
    );
    let root = "REQUEST increment\n  GIVEN amount is optional<integer>\n  WHEN increment amount\n  OUTPUT amount is optional<integer>\nWHEN increment <amount>\n  GIVEN amount is optional<integer>\n  IF amount is present\n    add 1 to amount\n";
    assert_eq!(
        program(root)
            .run_request("increment", &json!({"amount":0}), Default::default())
            .result,
        Some(json!({"amount":1}))
    );
}

#[test]
fn whole_record_returns_preserve_contracts_and_guards_release_after_return_or_failure() {
    let source = "RECORD Box\n  tag: text\n  value: optional<integer>\nWHEN choose <box>\n  GIVEN box is Box\n  THEN returns Box\n  IF box.value is present\n    add 1 to box.value\n    RETURN box\n  ELSE\n    RETURN box\nWHEN refuse <box>\n  GIVEN box is Box\n  IF box.value is present\n    add 1 to box.value\n    REQUIRE false\nWHEN replace <box> with <replacement>\n  GIVEN box is Box\n  AND replacement is Box\n  set box to replacement\nGIVEN box is Box\n  tag: \"box\"\n  value: 1\nGIVEN empty is Box\n  tag: \"empty\"\nWHEN LET copied be choose box\nTHEN copied.value is present and copied.value == 2\nWHEN refuse box\nTHEN fails with \"assertion_failed\"\nAND box.value is present and box.value == 3\nWHEN replace box with empty\nTHEN box.value is absent\n";
    let p = program(source);
    let case = capture_scenario(&p, "Main", Default::default()).unwrap();
    assert!(
        case.observed()["ok"].as_bool().unwrap(),
        "{:?}",
        case.observed()
    );
    assert!(replay_case(&case).unwrap().verified);
    assert_eq!(case.observed()["state"]["box"]["value"], Json::Null);
}

#[test]
fn list_items_and_one_of_payloads_keep_independent_presence_and_kind_guards() {
    let lists = "RECORD Batch\n  values: list<optional<integer>>\n  total: integer\nREQUEST total\n  GIVEN batch is Batch\n  WHEN total batch\n  OUTPUT batch is Batch\nWHEN total <batch>\n  GIVEN batch is Batch\n  FOR item in batch.values\n    IF item is present\n      add 1 to item\n      add item to batch.total\n";
    let run = program(lists).run_request(
        "total",
        &json!({"batch":{"values":[null,0,2],"total":0}}),
        Default::default(),
    );
    assert_eq!(
        run.result,
        Some(json!({"batch":{"values":[null,1,3],"total":4}}))
    );
    let kinds = "RECORD Contact is one of\n  email:\n    address: optional<text>\n  phone:\n    number: text\nREQUEST show\n  GIVEN contact is optional<Contact>\n  WHEN show contact\n  OUTPUT contact is optional<Contact>\nWHEN show <contact>\n  GIVEN contact is optional<Contact>\n  IF contact is present\n    DEPENDING ON contact\n      WHEN the kind is email\n        IF contact.address is present\n          print contact.address\n      WHEN the kind is phone\n        print contact.number\n";
    for (contact, output) in [
        (Json::Null, vec![]),
        (json!({"kind":"email"}), vec![]),
        (json!({"kind":"email","address":""}), vec![json!("")]),
        (json!({"kind":"phone","number":"555"}), vec![json!("555")]),
    ] {
        let run =
            program(kinds).run_request("show", &json!({"contact":contact}), Default::default());
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(run.output, output);
    }
}

#[test]
fn resource_failures_never_publish_a_presence_invalidating_write() {
    let p = program(&aliased(
        "  IF box.value is present\n    set alias to replacement\n",
        "",
    ));
    for steps in 0..30 {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let run = p.run_request(
            "examine",
            &json!({"box":{"value":4},"replacement":{}}),
            limits,
        );
        assert!(!run.ok);
        assert!(matches!(
            run.diagnostic.unwrap().code.as_str(),
            "execution_limit" | "presence_mutation"
        ));
        if let Some(value) = run.state.get("box") {
            assert_eq!(value["value"], 4);
        }
        assert!(!run.events.iter().any(|e| e.operation == "set"));
    }
}

#[test]
fn nested_calls_keep_outer_guards_and_false_is_a_present_optional_value() {
    let source = aliased(
        "  IF box.value is present\n    LET observed be inspect alias\n    REQUIRE observed == box.value\n    set alias to replacement\n",
        "WHEN inspect <box>\n  GIVEN box is Box\n  THEN returns integer\n  IF box.value is present\n    RETURN box.value\n  ELSE\n    RETURN 0\n",
    );
    let run = program(&source).run_request(
        "examine",
        &json!({"box":{"value":4},"replacement":{}}),
        Default::default(),
    );
    assert_eq!(run.diagnostic.unwrap().code, "presence_mutation");
    assert_eq!(run.state["box"]["value"], 4);
    let source = "REQUEST flip\n  GIVEN flag is optional<boolean>\n  GIVEN replacement is optional<boolean>\n  WHEN flip flag with flag and replacement\n  OUTPUT flag is optional<boolean>\nWHEN flip <flag> with <alias> and <replacement>\n  GIVEN flag is optional<boolean>\n  AND alias is optional<boolean>\n  AND replacement is optional<boolean>\n  IF flag is present\n    print not flag\n    set alias to replacement\n";
    let p = program(source);
    let changed = p.run_request(
        "flip",
        &json!({"flag":false,"replacement":true}),
        Default::default(),
    );
    assert_eq!(changed.output, vec![json!(true)]);
    assert_eq!(changed.result, Some(json!({"flag":true})));
    let cleared = p.run_request(
        "flip",
        &json!({"flag":false,"replacement":null}),
        Default::default(),
    );
    assert_eq!(cleared.diagnostic.unwrap().code, "presence_mutation");
    assert_eq!(cleared.state["flag"], false);
}

#[test]
fn expanded_presence_branches_retain_original_unicode_crlf_evidence() {
    let source = "# café 😀\nRECORD Reading\n  value: optional<integer>\nWHEN emit <reading>\n  GIVEN reading is Reading\n  IF reading.value is present\n    print reading.value + 1\nSCENARIO reading <value>\nGIVEN reading is Reading\n  value: <value>\nWHEN emit reading\nTHEN prints [<expected>]\nEXAMPLES\n  | value | expected |\n  | 0 | 1 |\n  | 4 | 5 |\n".replace('\n', "\r\n");
    let p = program(&source);
    for row in p.test_scenarios(Default::default()) {
        assert!(row.execution.ok);
        let event = row
            .execution
            .events
            .iter()
            .find(|e| e.operation == "is present")
            .unwrap();
        assert_eq!(
            &source[event.span.start..event.span.end],
            "reading.value is present"
        );
        explain_execution(&row.execution, p.source_bundle().unwrap()).unwrap();
        assert!(
            replay_case(&capture_scenario(&p, &row.name, Default::default()).unwrap())
                .unwrap()
                .verified
        );
    }
}
