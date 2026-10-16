use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, capture_scenario, compare_case, compile_bundle,
    compile_program, explain_execution, format_source, replay_case, scenario_from_case,
};
use serde_json::json;
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_value_dispatch/rules.gwt");

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

fn dispatch(ty: &str, subject: &str, branches: &str) -> String {
    format!(
        "TYPE Input is {ty}\nREQUEST classify\n  GIVEN value is Input\n  GIVEN result is \"initial\"\n  WHEN classify value into result\n  OUTPUT result is text\nWHEN classify <value> into <result>\n  GIVEN value is Input\n  AND result is text\n  DEPENDING ON {subject}\n{branches}"
    )
}

#[test]
fn delivery_policy_matches_independent_inputs_scenarios_replay_and_revision() {
    let p = program(SOURCE);
    let example_input = serde_json::from_str(include_str!(
        "../../../examples/native_value_dispatch/request.json"
    ))
    .unwrap();
    assert_eq!(
        p.run_request("review delivery", &example_input, Default::default())
            .result,
        Some(json!({"decision":{"action":"retry","delay":15,"notice":"retry"}}))
    );
    let candidate =
        program(&SOURCE.replace("set decision.delay to 15", "set decision.delay to 25"));
    for status in ["sent", "retry", "failed"] {
        for attempt in [1, 2, 3, 4, 9999] {
            for notify in [false, true] {
                let input = json!({"facts":{"status":status,"attempt":attempt,"notify":notify}});
                let (action, delay) = match (status, attempt) {
                    ("sent", _) => ("done", 0),
                    ("retry", 1) => ("retry", 5),
                    ("retry", 2) => ("retry", 15),
                    _ => ("manual", 0),
                };
                let expected = json!({"decision":{"action":action,"delay":delay,"notice":if notify {action} else {"silent"}}});
                let case =
                    capture_request(&p, "review delivery", &input, Default::default()).unwrap();
                assert_eq!(case.observed()["result"], expected);
                assert!(replay_case(&case).unwrap().verified);
                let comparison = compare_case(&case, &candidate).unwrap();
                assert_eq!(
                    comparison.changes.unwrap().outcome,
                    status == "retry" && attempt == 2
                );
                let generated = scenario_from_case(&case, "reviewed delivery").unwrap();
                let generated_program = compile_bundle(generated.source_bundle()).unwrap();
                assert!(
                    generated_program
                        .test_scenarios(Default::default())
                        .iter()
                        .all(|s| s.execution.ok)
                );
            }
        }
    }
    for attempt in [-1, 0] {
        let run = p.run_request(
            "review delivery",
            &json!({"facts":{"status":"sent","attempt":attempt,"notify":true}}),
            Default::default(),
        );
        assert_eq!(run.diagnostic.unwrap().code, "assertion_failed");
        assert!(!run.events.iter().any(|e| e.operation == "value branch"));
    }
    let scenarios = p.test_scenarios(Default::default());
    assert_eq!(scenarios.len(), 6);
    assert!(scenarios.iter().all(|s| s.execution.ok));
    assert_eq!(
        scenarios
            .iter()
            .flat_map(|s| &s.execution.events)
            .filter(|e| e.operation == "assert")
            .count(),
        24
    );
    assert!(!format_source(SOURCE, "rules.gwt").unwrap().changed);
}

#[test]
fn numeric_dispatch_uses_exact_equality_and_subject_expressions() {
    for (ty, subject, literal, input, matched) in [
        ("integer", "value", "1.00", json!(1), true),
        ("decimal", "value", "1", json!("1.000"), true),
        ("number", "value", "-1.25", json!("-1.250"), true),
        (
            "integer",
            "value",
            "-9007199254740993",
            json!(-9007199254740993_i64),
            true,
        ),
        (
            "integer",
            "value",
            "9007199254740993",
            json!(9007199254740992_u64),
            false,
        ),
        ("integer", "value / 8", "0.125", json!(1), true),
        (
            "decimal",
            "value",
            "0.100000000000000000000000000001",
            json!("0.100000000000000000000000000002"),
            false,
        ),
        ("decimal", "value", "-0.0", json!("0.00"), true),
    ] {
        let source = dispatch(
            ty,
            subject,
            &format!(
                "    WHEN the value is {literal}\n      set result to \"match\"\n    ELSE\n      set result to \"other\"\n"
            ),
        );
        let run =
            program(&source).run_request("classify", &json!({"value":input}), Default::default());
        assert!(run.ok, "{source}: {:?}", run.diagnostic);
        assert_eq!(
            run.result,
            Some(json!({"result":if matched {"match"} else {"other"}}))
        );
        let branch = run
            .events
            .iter()
            .find(|e| e.operation == "value branch")
            .unwrap();
        assert_eq!(branch.value["selected"], matched);
        assert_eq!(branch.inputs.len(), 1);
    }
    let source = dispatch(
        "integer",
        "value / 3",
        "    WHEN the value is 0\n      PASS\n    ELSE\n      PASS\n",
    );
    let run = program(&source).run_request("classify", &json!({"value":1}), Default::default());
    assert_eq!(run.diagnostic.unwrap().code, "nonterminating_decimal");
    assert!(!run.events.iter().any(|e| e.operation == "value branch"));
}

#[test]
fn literal_cases_exhaust_boolean_and_text_unions_without_refining_mutable_types() {
    for (ty, branches, inputs) in [
        (
            "boolean",
            "    WHEN the value is true\n      set result to \"yes\"\n    WHEN the value is false\n      set result to \"no\"\n",
            vec![(json!(true), "yes"), (json!(false), "no")],
        ),
        (
            "\"a\" | \"b\"",
            "    WHEN the value is \"a\"\n      set result to \"yes\"\n    ELSE\n      set result to \"no\"\n",
            vec![(json!("a"), "yes"), (json!("b"), "no")],
        ),
        (
            "text",
            "    WHEN the value is \"a\"\n      set result to \"yes\"\n    ELSE\n      set result to \"no\"\n",
            vec![(json!("a"), "yes"), (json!("😀"), "no")],
        ),
    ] {
        let p = program(&dispatch(ty, "value", branches));
        for (input, wanted) in inputs {
            let run = p.run_request("classify", &json!({"value":input}), Default::default());
            assert_eq!(run.result, Some(json!({"result":wanted})));
        }
    }
    let source = dispatch(
        "\"a\" | \"b\"",
        "value",
        "    WHEN the value is \"a\"\n      set value to \"b\"\n      set result to value\n    WHEN the value is \"b\"\n      set result to \"second\"\n",
    );
    let run = program(&source).run_request("classify", &json!({"value":"a"}), Default::default());
    assert_eq!(run.result, Some(json!({"result":"b"})));
    assert_eq!(run.state["value"], "b");
    assert_eq!(
        run.events
            .iter()
            .filter(|e| e.operation == "read value")
            .count(),
        2
    );
    let branches: Vec<_> = run
        .events
        .iter()
        .filter(|e| e.operation == "value branch")
        .collect();
    assert_eq!(branches.len(), 2);
    assert!(branches.iter().all(|e| e.value["actual"] == "a"));
    assert_eq!(
        branches
            .iter()
            .filter(|e| e.value["selected"] == true)
            .count(),
        1
    );
}

#[test]
fn duplicate_impossible_mixed_dynamic_and_incomplete_cases_are_rejected() {
    for (ty, branches, code) in [
        (
            "integer",
            "    WHEN the value is 1\n      PASS\n",
            "incomplete_depending",
        ),
        ("text", "    ELSE\n      PASS\n", "incomplete_depending"),
        (
            "boolean",
            "    WHEN the value is true\n      PASS\n",
            "incomplete_depending",
        ),
        (
            "integer",
            "    WHEN the value is 1\n      PASS\n    WHEN the value is 1.000\n      PASS\n    ELSE\n      PASS\n",
            "duplicate_value",
        ),
        (
            "decimal",
            "    WHEN the value is -0.0\n      PASS\n    WHEN the value is 0\n      PASS\n    ELSE\n      PASS\n",
            "duplicate_value",
        ),
        (
            "integer",
            "    WHEN the value is 1.5\n      PASS\n    ELSE\n      PASS\n",
            "unreachable_value",
        ),
        (
            "integer",
            "    WHEN the value is true\n      PASS\n    ELSE\n      PASS\n",
            "depending_value_type",
        ),
        (
            "integer",
            "    WHEN the value is \"1\"\n      PASS\n    ELSE\n      PASS\n",
            "depending_value_type",
        ),
        (
            "\"a\" | \"b\"",
            "    WHEN the value is \"c\"\n      PASS\n    ELSE\n      PASS\n",
            "unreachable_value",
        ),
        (
            "boolean",
            "    WHEN the value is true\n      PASS\n    WHEN the value is false\n      PASS\n    ELSE\n      PASS\n",
            "unreachable_else",
        ),
        (
            "integer",
            "    WHEN the kind is a\n      PASS\n    ELSE\n      PASS\n",
            "depending_branch",
        ),
        (
            "integer",
            "    WHEN the value is 1 + 0\n      PASS\n    ELSE\n      PASS\n",
            "depending_literal",
        ),
        (
            "integer",
            "    WHEN the value is value\n      PASS\n    ELSE\n      PASS\n",
            "unknown_name",
        ),
        (
            "boolean",
            "    WHEN the value is not false\n      PASS\n    ELSE\n      PASS\n",
            "depending_literal",
        ),
        (
            "integer",
            "    ELSE\n      PASS\n    WHEN the value is 1\n      PASS\n",
            "depending_order",
        ),
        (
            "optional<integer>",
            "    WHEN the value is 1\n      PASS\n    ELSE\n      PASS\n",
            "depending_type",
        ),
        (
            "list<integer>",
            "    WHEN the value is 1\n      PASS\n    ELSE\n      PASS\n",
            "depending_type",
        ),
        (
            "integer",
            "    WHEN the value is 1\n    ELSE\n      PASS\n",
            "empty_block",
        ),
    ] {
        let source = dispatch(ty, "value", branches);
        assert_eq!(
            compile_program(&source, "bad.gwt").unwrap_err().code,
            code,
            "{source}"
        );
    }
    let source = "RECORD Item is one of\n  a:\n    value: integer\nWHEN inspect <item>\n  GIVEN item is Item\n  DEPENDING ON item\n    WHEN the value is \"a\"\n      PASS\n";
    assert_eq!(
        compile_program(source, "bad.gwt").unwrap_err().code,
        "depending_branch"
    );
}

#[test]
fn branch_scope_return_analysis_and_skipped_body_failures_are_sound() {
    let source = "WHEN choose <flag>\n  GIVEN flag is boolean\n  THEN returns integer\n  DEPENDING ON flag\n    WHEN the value is true\n      RETURN 11\n    WHEN the value is false\n      RETURN 22\nGIVEN flag is false\nWHEN LET result be choose flag\nTHEN result == 22\n";
    assert!(program(source).run_scenario("Main", Default::default()).ok);
    assert!(compile_program(&source.replace("RETURN 22", "PASS"), "bad.gwt").is_err());
    let source = dispatch(
        "integer",
        "value",
        "    WHEN the value is 1\n      LET local be 10\n      set result to \"safe\"\n    ELSE\n      LET failure be 1 / 0\n  print local\n",
    );
    assert_eq!(
        compile_program(&source, "bad.gwt").unwrap_err().code,
        "unknown_name"
    );
    let source = source.replace("  print local\n", "");
    let p = program(&source);
    assert!(
        p.run_request("classify", &json!({"value":1}), Default::default())
            .ok
    );
    let failed = p.run_request("classify", &json!({"value":2}), Default::default());
    assert_eq!(failed.diagnostic.unwrap().code, "division_by_zero");
    assert!(compile_program(&source.replace("1 / 0", "undeclared"), "bad.gwt").is_err());
}

#[test]
fn subject_snapshots_and_guards_survive_nested_calls_and_collection_iteration() {
    let source = "RECORD State\n  values: list<integer>\n  total: integer\nWHEN adjust <state>\n  GIVEN state is State\n  FOR item in state.values\n    DEPENDING ON item\n      WHEN the value is 1\n        replace item\n        add item to state.total\n      ELSE\n        add item to state.total\nWHEN replace <value>\n  GIVEN value is integer\n  set value to 10\nGIVEN state is State\n  values: [1, 2, 1]\n  total: 0\nWHEN adjust state\nTHEN state.values == [10, 2, 10]\nAND state.total == 22\n";
    let p = program(source);
    let case = capture_scenario(&p, "Main", Default::default()).unwrap();
    assert!(replay_case(&case).unwrap().verified);
    assert_eq!(case.observed()["state"]["state"]["total"], 22);
    let invalid = source.replace("replace item", "append 0 to state.values");
    let run = program(&invalid).run_scenario("Main", Default::default());
    assert_eq!(run.diagnostic.unwrap().code, "collection_mutation");
}

#[test]
fn scalar_comparisons_are_metered_and_evidence_precedes_branch_mutation() {
    let source = dispatch(
        "integer",
        "value",
        "    WHEN the value is 1\n      set result to \"one\"\n    WHEN the value is 2\n      set result to \"two\"\n    ELSE\n      set result to \"other\"\n",
    );
    let p = program(&source);
    let run = p.run_request("classify", &json!({"value":1}), Default::default());
    assert!(run.ok);
    let mut during_dispatch = false;
    for steps in 0..run.steps {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let failed = p.run_request("classify", &json!({"value":1}), limits);
        assert!(!failed.ok);
        assert_eq!(failed.diagnostic.unwrap().code, "execution_limit");
        if failed
            .events
            .iter()
            .filter(|e| e.operation == "value branch")
            .count()
            == 1
        {
            during_dispatch = true;
            assert_eq!(failed.state["result"], "initial");
            assert!(!failed.events.iter().any(|e| e.operation == "set"));
        }
    }
    assert!(during_dispatch);
    let branches: Vec<_> = run
        .events
        .iter()
        .filter(|e| e.operation == "value branch")
        .collect();
    assert!(branches.iter().all(|e| e.inputs == branches[0].inputs));
    assert_eq!(
        run.events[branches[0].inputs[0] - 1].operation,
        "read value"
    );
    let explanation = explain_execution(&run, p.source_bundle().unwrap()).unwrap();
    let encoded = serde_json::to_string(&explanation).unwrap();
    assert!(encoded.contains("Scalar value matched; branch selected."));
    assert!(encoded.contains("Scalar value did not match; branch not selected."));
}

#[test]
fn expanded_dispatch_maps_unicode_and_crlf_evidence_to_original_source() {
    let source = "# café 😀\nWHEN describe <value>\n  GIVEN value is text\n  DEPENDING ON value\n    WHEN the value is \"café\"\n      print \"coffee\"\n    ELSE\n      print value\nSCENARIO label <value>\nGIVEN value is <value>\nWHEN describe value\nTHEN prints [<expected>]\nEXAMPLES\n  | value | expected |\n  | \"café\" | \"coffee\" |\n  | \"😀\" | \"😀\" |\n".replace('\n', "\r\n");
    let p = program(&source);
    for row in p.test_scenarios(Default::default()) {
        assert!(row.execution.ok, "{:?}", row.execution.diagnostic);
        let branch = row
            .execution
            .events
            .iter()
            .find(|e| e.operation == "value branch")
            .unwrap();
        assert_eq!(
            &source[branch.span.start..branch.span.end],
            "WHEN the value is \"café\""
        );
        explain_execution(&row.execution, p.source_bundle().unwrap()).unwrap();
        let case = capture_scenario(&p, &row.name, Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
    }
}
