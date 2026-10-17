use gwt_core::{
    SourceBundle, Type, capture_request, compare_case, compile_bundle, compile_expression,
    compile_program, explain_execution, format_source, replay_case, scenario_from_case,
};
use serde_json::{Value, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_finite_codes/rules.gwt");
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
fn bad(source: &str, code: &str) {
    let error = compile_program(source, "bad.gwt").expect_err("must reject");
    assert_eq!(error.code, code, "{source}: {error:?}");
}
fn dispatch(ty: &str, branches: &str) -> String {
    format!(
        "TYPE Code is {ty}\nREQUEST classify\n  GIVEN code is Code\n  GIVEN answer is 0\n  WHEN classify code into answer\n  OUTPUT answer is integer\nWHEN classify <code> into <answer>\n  GIVEN code is Code\n  AND answer is integer\n  DEPENDING ON code\n{branches}"
    )
}

#[test]
fn closed_receipt_policy_matches_independent_inputs_and_rejects_before_execution() {
    let p = program(SOURCE);
    let mut accepted = 0;
    let mut rejected = 0;
    for code in [
        -1,
        0,
        9,
        10,
        11,
        19,
        20,
        21,
        29,
        30,
        31,
        9007199254740993_i64,
    ] {
        for (factor, multiplier) in [
            ("0", 0),
            ("0.5", 5),
            ("1", 10),
            ("1.000", 10),
            ("1.5", 15),
            ("2.0", 20),
        ] {
            for confirmed in [false, true] {
                let input =
                    json!({"receipt":{"code":code,"retry_factor":factor,"confirmed":confirmed}});
                let run = p.run_request("review receipt", &input, Default::default());
                let valid =
                    [10, 20, 30].contains(&code) && [5, 10, 20].contains(&multiplier) && confirmed;
                assert_eq!(run.ok, valid, "{input}: {:?}", run.diagnostic);
                if valid {
                    accepted += 1;
                    let (action, delay) = match code {
                        10 => ("complete", 0),
                        20 => ("retry", multiplier),
                        30 => ("manual", 0),
                        _ => unreachable!(),
                    };
                    assert_eq!(
                        run.result,
                        Some(
                            json!({"decision":{"action":action,"delay_minutes":delay.to_string()}})
                        )
                    );
                    assert_eq!(
                        run.events
                            .iter()
                            .filter(|e| e.operation == "value branch")
                            .count(),
                        3
                    );
                    explain_execution(&run, p.source_bundle().unwrap()).unwrap();
                } else {
                    rejected += 1;
                    assert_eq!(run.diagnostic.unwrap().code, "input_type");
                    assert!(run.result.is_none());
                    assert!(run.events.is_empty());
                }
            }
        }
    }
    assert_eq!((accepted, rejected), (12, 132));
    for (field, value) in [
        ("code", json!(true)),
        ("code", json!("20")),
        ("code", json!(20.0)),
        ("retry_factor", json!(0.5)),
        ("confirmed", json!(1)),
        ("confirmed", Value::Null),
    ] {
        let mut input = json!({"receipt":{"code":20,"retry_factor":"0.5","confirmed":true}});
        input["receipt"][field] = value;
        let run = p.run_request("review receipt", &input, Default::default());
        assert!(!run.ok, "{input}");
        assert!(run.events.is_empty());
    }
    assert_eq!(p.test_scenarios(Default::default()).len(), 5);
    assert!(
        p.test_scenarios(Default::default())
            .iter()
            .all(|s| s.execution.ok)
    );
}

#[test]
fn scalar_dispatch_is_exact_exhaustive_and_preserves_numeric_base() {
    for (ty, values) in [
        (
            "-1 | 9007199254740993",
            vec![json!(-1), serde_json::from_str("9007199254740993").unwrap()],
        ),
        (
            "0.1000000000000000000000000001 | 0.1000000000000000000000000002",
            vec![
                json!("0.1000000000000000000000000001"),
                json!("0.1000000000000000000000000002"),
            ],
        ),
        ("true", vec![json!(true)]),
        ("false", vec![json!(false)]),
        ("true | false", vec![json!(true), json!(false)]),
    ] {
        let parts = ty.split(" | ").collect::<Vec<_>>();
        let mut branches = String::new();
        for (i, value) in parts.iter().enumerate() {
            use std::fmt::Write;
            writeln!(
                branches,
                "    WHEN the value is {value}\n      set answer to {i}"
            )
            .unwrap();
        }
        let p = program(&dispatch(ty, &branches));
        for (i, value) in values.iter().enumerate() {
            let run = p.run_request("classify", &json!({"code":value}), Default::default());
            assert!(run.ok, "{ty}: {:?}", run.diagnostic);
            assert_eq!(run.result, Some(json!({"answer":i})));
        }
        bad(
            &dispatch(ty, &format!("{branches}    ELSE\n      PASS\n")),
            "unreachable_else",
        );
    }
    let p = program(&dispatch(
        "1 | 2.5",
        "    WHEN the value is 1.0\n      set answer to 1\n    WHEN the value is 2.50\n      set answer to 2\n",
    ));
    for value in [json!(1), json!("1.000"), json!("2.50")] {
        assert!(
            p.run_request("classify", &json!({"code":value}), Default::default())
                .ok
        );
    }
    bad(
        &dispatch("1 | 2", "    WHEN the value is 1\n      PASS\n"),
        "incomplete_depending",
    );
    bad(
        &dispatch(
            "1 | 2",
            "    WHEN the value is 3\n      PASS\n    ELSE\n      PASS\n",
        ),
        "unreachable_value",
    );
    bad(
        &dispatch(
            "1 | 2",
            "    WHEN the value is true\n      PASS\n    ELSE\n      PASS\n",
        ),
        "depending_value_type",
    );
}

#[test]
fn declarations_reject_mixed_computed_duplicate_and_noncanonical_public_types() {
    for ty in [
        "1 | 1.0",
        "0 | -0.00",
        "true | true",
        "\"a\" | \"a\"",
        "0.5 | 0.50",
    ] {
        bad(&format!("TYPE Code is {ty}\n"), "duplicate_literal");
    }
    for ty in [
        "1 | true",
        "\"1\" | 1",
        "1 + 1 | 2",
        "1 | text",
        "null | true",
        "1e2 | 2",
        "--1 | 2",
    ] {
        bad(&format!("TYPE Code is {ty}\n"), "unsupported_type");
    }
    for ty in [
        Type::IntegerUnion(vec![]),
        Type::IntegerUnion(vec!["1.0".into()]),
        Type::DecimalUnion(vec!["01".into()]),
        Type::DecimalUnion(vec!["0.5".into(), "0.5".into()]),
        Type::BooleanUnion(vec![true, false]),
    ] {
        let result = compile_expression(
            "value",
            "contract.gwt",
            BTreeMap::from([("value".into(), ty)]),
        );
        assert_eq!(result.err().unwrap().code, "invalid_type");
    }
}

#[test]
fn assignments_returns_lists_and_mutable_aliases_keep_finite_promises() {
    let source = "TYPE Code is -1 | 2\nRECORD State\n  code: Code\n  codes: list<Code>\nREQUEST change\n  GIVEN state is State\n  WHEN change state\n  OUTPUT state is State\nWHEN change <state>\n  GIVEN state is State\n  set state.code to -1\n  append 2 to state.codes\n  LET returned be chosen code\n  set state.code to returned\nWHEN chosen code\n  THEN returns Code\n  RETURN 2\n";
    let p = program(source);
    let run = p.run_request(
        "change",
        &json!({"state":{"code":2,"codes":[-1]}}),
        Default::default(),
    );
    assert_eq!(run.result, Some(json!({"state":{"code":2,"codes":[-1,2]}})));
    for candidate in [
        source.replace("set state.code to -1", "set state.code to 3"),
        source.replace("RETURN 2", "RETURN 1 + 1"),
        source.replace("append 2", "append 3"),
    ] {
        bad(&candidate, "assignment_type");
    }
    bad(
        &source.replace("set state.code to -1", "add 2 to state.code"),
        "mutation_type",
    );
    bad(
        &source.replace("set state.code to -1", "count state.codes into state.code"),
        "aggregate_type",
    );
    let copy = "TYPE Code is 1 | 2\nREQUEST inspect\n  GIVEN code is Code\n  WHEN inspect (code)\n  OUTPUT code is Code\nWHEN inspect <value>\n  GIVEN value is integer\n  set value to 3\n";
    assert!(
        program(copy)
            .run_request("inspect", &json!({"code":1}), Default::default())
            .ok
    );
    bad(
        &copy.replace("inspect (code)", "inspect code"),
        "argument_type",
    );
}

#[test]
fn finite_values_widen_for_arithmetic_boolean_conditions_and_containment() {
    let source = "TYPE Code is -2 | 2\nTYPE Yes is true\nREQUEST calculate\n  GIVEN code is Code\n  GIVEN yes is Yes\n  GIVEN answer is 0\n  WHEN calculate code with yes into answer\n  OUTPUT answer is integer\nWHEN calculate <code> with <yes> into <answer>\n  GIVEN code is Code\n  AND yes is Yes\n  AND answer is integer\n  IF yes and not false\n    set answer to -code + 1\n  REQUIRE yes == true\n";
    for (code, answer) in [(-2, 3), (2, -1)] {
        assert_eq!(
            program(source)
                .run_request(
                    "calculate",
                    &json!({"code":code,"yes":true}),
                    Default::default()
                )
                .result,
            Some(json!({"answer":answer}))
        );
    }
    let expression = compile_expression(
        "codes contains code and switches contains yes",
        "test.gwt",
        BTreeMap::from([
            (
                "codes".into(),
                Type::List(Box::new(Type::IntegerUnion(vec!["1".into(), "2".into()]))),
            ),
            ("code".into(), Type::Integer),
            (
                "switches".into(),
                Type::List(Box::new(Type::BooleanUnion(vec![true]))),
            ),
            ("yes".into(), Type::Boolean),
        ]),
    );
    assert!(expression.is_ok());
}

#[test]
fn capture_replay_revision_generation_and_formatting_retain_finite_contracts() {
    let formatted = format_source(SOURCE, "rules.gwt").unwrap();
    let p = program(&formatted.text);
    let candidate = program(
        &formatted
            .text
            .replace("10 * receipt.retry_factor", "12 * receipt.retry_factor"),
    );
    for code in [10, 20, 30] {
        let input = json!({"receipt":{"code":code,"retry_factor":"0.5","confirmed":true}});
        let case = capture_request(&p, "review receipt", &input, Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
        assert_eq!(
            compare_case(&case, &candidate)
                .unwrap()
                .changes
                .unwrap()
                .outcome,
            code == 20
        );
        let generated = scenario_from_case(&case, "captured finite receipt").unwrap();
        let rebuilt = compile_bundle(generated.source_bundle()).unwrap();
        assert!(
            rebuilt
                .test_scenarios(Default::default())
                .iter()
                .all(|s| s.execution.ok)
        );
    }
    let mut missing = json!({"receipt":{"code":20,"retry_factor":"0.5","confirmed":true}});
    missing["receipt"]
        .as_object_mut()
        .unwrap()
        .remove("confirmed");
    assert_eq!(
        p.run_request("review receipt", &missing, Default::default())
            .diagnostic
            .unwrap()
            .code,
        "missing_input"
    );
}

#[test]
fn inspection_editor_optional_and_nested_contracts_expose_exact_domains() {
    let p = program(SOURCE);
    let inspection = p.inspect().to_json().unwrap();
    let types = inspection["types"].as_array().unwrap();
    for (name, ty) in [
        (
            "ReceiptCode",
            json!({"kind":"integer_union","value":["10","20","30"]}),
        ),
        (
            "RetryFactor",
            json!({"kind":"decimal_union","value":["0.5","1","2"]}),
        ),
        ("Confirmed", json!({"kind":"boolean_union","value":[true]})),
    ] {
        assert_eq!(
            types.iter().find(|v| v["name"] == name).unwrap()["type"],
            ty
        );
    }
    let root = std::env::temp_dir().join(format!("gwt-finite-editor-{}", std::process::id()));
    std::fs::create_dir(&root).unwrap();
    let source = format!("# café 😀\r\n{}", SOURCE.replace('\n', "\r\n"));
    let report = gwt_core::check_editor_query(
        &root.join("rules.gwt"),
        Some(&root),
        &BTreeMap::from([("rules.gwt".into(), source.clone())]),
        Some(&gwt_core::EditorQuery {
            path: "rules.gwt".into(),
            byte_offset: source.find("receipt.retry_factor").unwrap() + 8,
        }),
    );
    std::fs::remove_dir(&root).unwrap();
    assert!(report.ok, "{:?}", report.diagnostic);
    let symbols = report.navigation.unwrap().symbols;
    assert!(
        symbols.iter().any(|s| s.label.contains("0.5 | 1.0 | 2.0")),
        "{symbols:?}"
    );
    assert!(symbols.iter().all(|s| s.definition.is_some()));
    let source = "TYPE Code is 1 | 2\nRECORD Facts\n  codes: list<Code>\n  preferred: optional<Code>\nREQUEST echo\n  GIVEN facts is Facts\n  WHEN PASS\n  OUTPUT facts is Facts\n";
    for input in [
        json!({"facts":{"codes":[]}}),
        json!({"facts":{"codes":[1,2],"preferred":2}}),
        json!({"facts":{"codes":[2],"preferred":null}}),
    ] {
        let p = program(source);
        let case = capture_request(&p, "echo", &input, Default::default()).unwrap();
        assert_eq!(case.observed()["ok"], true);
        let generated = scenario_from_case(&case, "nested finite").unwrap();
        assert!(
            compile_bundle(generated.source_bundle())
                .unwrap()
                .test_scenarios(Default::default())
                .iter()
                .all(|s| s.execution.ok)
        );
    }
    for input in [
        json!({"facts":{"codes":[3]}}),
        json!({"facts":{"codes":[1],"preferred":0}}),
    ] {
        let run = program(source).run_request("echo", &input, Default::default());
        assert!(!run.ok);
        assert!(run.events.is_empty());
    }
}

#[test]
fn negative_literals_and_subsets_copy_but_computed_values_do_not_claim_membership() {
    for (from, to, value, expected) in [
        ("1", "1 | 2", "1", json!(1)),
        ("1 | 2", "1.0 | 2.0", "2", json!("2")),
        ("true", "boolean", "true", json!(true)),
        ("-2.5", "decimal", "\"-2.5\"", json!("-2.5")),
    ] {
        let source = format!(
            "TYPE Narrow is {from}\nTYPE Wide is {to}\nREQUEST relay\n  GIVEN value is Narrow\n  WHEN LET result be relay (value)\n  OUTPUT result is Wide\nWHEN relay <value>\n  GIVEN value is Wide\n  THEN returns Wide\n  RETURN value\n"
        );
        let value: Value = serde_json::from_str(value).unwrap();
        let run =
            program(&source).run_request("relay", &json!({"value":value}), Default::default());
        assert!(run.ok, "{source}: {:?}", run.diagnostic);
        assert_eq!(run.result, Some(json!({"result":expected})));
    }
    let source = "TYPE Code is -2.5 | 1.0\nWHEN choose\n  THEN returns Code\n  RETURN -2.5\nGIVEN answer is 0\nWHEN LET result be choose\nTHEN result == -2.5\n";
    assert!(
        program(source).test_scenarios(Default::default())[0]
            .execution
            .ok
    );
    bad(
        &source.replace("RETURN -2.5", "RETURN -1.0"),
        "assignment_type",
    );
    let source = "TYPE Code is 1 | 2\nWHEN choose <code>\n  GIVEN code is integer\n  THEN returns Code\n  IF code == 1\n    RETURN code\n  ELSE\n    RETURN 2\n";
    bad(source, "assignment_type");
    // A domain equality check is not a finite-type refinement or alias lock.
    compile_program(&source.replace("RETURN code", "RETURN 1"), "fixed.gwt").unwrap();
}
