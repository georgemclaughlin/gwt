use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, compare_case, compile_bundle, compile_program,
    explain_execution, replay_case, scenario_from_case,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const PRICING: &str = include_str!("../../../examples/native_return_values/rules.gwt");

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

fn state_program(body: &str, helpers: &str) -> String {
    format!(
        "RECORD State\n  number: integer\n  values: list<integer>\nREQUEST run\n  GIVEN state is State\n  WHEN act state\n  OUTPUT state is State\nWHEN act <state>\n  GIVEN state is State\n{body}{helpers}"
    )
}

#[test]
fn returned_pricing_matches_independent_exact_arithmetic_and_revision_probes() {
    let baseline = program(PRICING);
    let candidate = program(&PRICING.replace("RETURN 0.1", "RETURN 0.2"));
    let mut probes = 0;
    for cents in [0, 1, 10, 1995] {
        for quantity in [1, 2, 3, 10] {
            for member in [false, true] {
                let price = format!("{}.{:02}", cents / 100, cents % 100);
                let input =
                    json!({"order":{"unit_price":price,"quantity":quantity,"member":member}});
                let expected = |discount_tenths| {
                    let thousandths = cents * quantity * (10 - discount_tenths);
                    let mut value = format!("{}.{:03}", thousandths / 1000, thousandths % 1000);
                    while value.ends_with('0') {
                        value.pop();
                    }
                    if value.ends_with('.') {
                        value.pop();
                    }
                    json!({"quote":{"total":value}})
                };
                let case =
                    capture_request(&baseline, "quote order", &input, ProgramLimits::default())
                        .unwrap();
                assert_eq!(case.observed()["result"], expected(i32::from(member)));
                assert!(replay_case(&case).unwrap().verified);
                let comparison = compare_case(&case, &candidate).unwrap();
                assert_eq!(
                    comparison.candidate.as_ref().unwrap().result,
                    Some(expected(if member { 2 } else { 0 }))
                );
                assert_eq!(comparison.changes.unwrap().outcome, member && cents != 0);
                explain_execution(
                    comparison.candidate.as_ref().unwrap(),
                    candidate.source_bundle().unwrap(),
                )
                .unwrap();
                let generated = scenario_from_case(&case, "recorded total").unwrap();
                let mut changed = generated.source_bundle().clone();
                changed.modules.insert(
                    "rules.gwt".into(),
                    PRICING.replace("RETURN 0.1", "RETURN 0.2"),
                );
                let runs = compile_bundle(&changed)
                    .unwrap()
                    .test_scenarios(ProgramLimits::default());
                assert_eq!(runs[0].execution.ok, !(member && cents != 0));
                probes += 1;
            }
        }
    }
    assert_eq!(probes, 32);
    assert!(
        baseline
            .test_scenarios(ProgramLimits::default())
            .iter()
            .all(|row| row.execution.ok)
    );
}

#[test]
fn return_contracts_normalize_values_and_provide_empty_list_context() {
    for (ty, input, expression, expected) in [
        ("decimal", json!("0"), "1", json!("1")),
        (
            "integer",
            json!(0),
            "9007199254740993",
            json!(9007199254740993_u64),
        ),
        ("list<integer>", json!([1, 2]), "[]", json!([])),
        ("optional<text>", Json::Null, "value", Json::Null),
        (
            "\"open\" | \"closed\"",
            json!("open"),
            "\"closed\"",
            json!("closed"),
        ),
    ] {
        let source = format!(
            "TYPE Contract is {ty}\nREQUEST run\n  GIVEN value is Contract\n  WHEN replace value\n  OUTPUT value is Contract\nWHEN replace <value>\n  GIVEN value is Contract\n  LET result be calculate value\n  set value to result\nWHEN calculate <value>\n  GIVEN value is Contract\n  THEN returns Contract\n  RETURN {expression}\n"
        );
        let program = program(&source);
        let run = program.run_request("run", &json!({"value":input}), ProgramLimits::default());
        assert!(run.ok, "{ty}: {:?}", run.diagnostic);
        assert_eq!(run.result.unwrap(), json!({"value":expected}));
        let returned = run
            .events
            .iter()
            .find(|event| event.operation == "return")
            .unwrap();
        assert_eq!(returned.value, expected);
    }
}

#[test]
fn branches_return_from_only_the_callee_and_statement_calls_discard_values() {
    let source = state_program(
        "  LET selected be choose state\n  set state.number to selected\n  choose state\n  add 1 to state.number\n  print state.number\n",
        "WHEN choose <state>\n  GIVEN state is State\n  THEN returns integer\n  IF state.number > 0\n    RETURN 11\n  ELSE\n    RETURN 22\n  print 999\n",
    );
    let program = program(&source);
    for (number, expected) in [(-1, 23), (0, 23), (1, 12)] {
        let run = program.run_request(
            "run",
            &json!({"state":{"number":number,"values":[]}}),
            ProgramLimits::default(),
        );
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(run.result.as_ref().unwrap()["state"]["number"], expected);
        assert_eq!(run.output, vec![json!(expected)]);
        assert_eq!(
            run.events
                .iter()
                .filter(|event| event.operation == "return")
                .count(),
            2
        );
        explain_execution(&run, program.source_bundle().unwrap()).unwrap();
    }
}

#[test]
fn return_through_loops_and_find_releases_only_its_own_traversal_guards() {
    let for_helper = "WHEN first positive in <state>\n  GIVEN state is State\n  THEN returns integer\n  FOR item in state.values\n    IF item > 0\n      RETURN item\n  RETURN 0\n";
    let find_helper = "WHEN first positive in <state>\n  GIVEN state is State\n  THEN returns integer\n  FIND item in state.values WHERE item > 0\n    RETURN item\n  ELSE\n    RETURN 0\n";
    for helper in [for_helper, find_helper] {
        let source = state_program(
            "  LET found be first positive in state\n  set state.number to found\n  append 7 to state.values\n",
            helper,
        );
        let program = program(&source);
        for (values, expected) in [(json!([]), 0), (json!([-1, 0]), 0), (json!([-1, 2, 3]), 2)] {
            let mut updated = values.clone();
            updated.as_array_mut().unwrap().push(json!(7));
            let run = program.run_request(
                "run",
                &json!({"state":{"number":99,"values":values}}),
                ProgramLimits::default(),
            );
            assert!(run.ok, "{:?}", run.diagnostic);
            assert_eq!(
                run.result.as_ref().unwrap(),
                &json!({"state":{"number":expected,"values":updated}})
            );
            if expected == 2 {
                assert!(
                    run.events
                        .iter()
                        .any(|event| event.operation == "leave collection"
                            && event.value["exit"] == "return")
                );
            }
            explain_execution(&run, program.source_bundle().unwrap()).unwrap();
        }
        let outer = state_program(
            "  FOR item in state.values\n    LET found be first positive in state\n    append found to state.values\n",
            helper,
        );
        let run = compile_program(&outer, "outer.gwt").unwrap().run_request(
            "run",
            &json!({"state":{"number":0,"values":[1,2]}}),
            ProgramLimits::default(),
        );
        assert_eq!(run.diagnostic.unwrap().code, "collection_mutation");
    }
}

#[test]
fn returned_collection_is_a_value_snapshot_while_arguments_keep_aliasing() {
    let source = state_program(
        "  LET copy be snapshot state\n  append 9 to state.values\n  append 5 to copy\n  set state.values to copy\n",
        "WHEN snapshot <state>\n  GIVEN state is State\n  THEN returns list<integer>\n  set state.number to 7\n  RETURN state.values\n",
    );
    let run = program(&source).run_request(
        "run",
        &json!({"state":{"number":0,"values":[1,2]}}),
        ProgramLimits::default(),
    );
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(
        run.result.unwrap(),
        json!({"state":{"number":7,"values":[1,2,5]}})
    );
}

#[test]
fn failures_and_evidence_limits_prevent_binding_a_returned_value() {
    let source = state_program(
        "  LET answer be calculate state\n  set state.number to 9\n",
        "WHEN calculate <state>\n  GIVEN state is State\n  THEN returns decimal\n  set state.number to 7\n  RETURN 1 / 0\n",
    );
    let input = json!({"state":{"number":0,"values":[]}});
    let run = program(&source).run_request("run", &input, ProgramLimits::default());
    assert_eq!(run.diagnostic.unwrap().code, "division_by_zero");
    assert_eq!(run.state["state"]["number"], 7);
    assert!(
        !run.events
            .iter()
            .any(|event| event.operation == "initialize" && event.value["path"] == "answer")
    );
    let working = program(&source.replace("RETURN 1 / 0", "RETURN 1"));
    let run = working.run_request("run", &input, ProgramLimits::default());
    assert!(run.ok);
    let position = run
        .events
        .iter()
        .position(|event| event.operation == "initialize" && event.value["path"] == "answer")
        .unwrap();
    let mut limits = ProgramLimits::default();
    limits.execution.evidence_bytes = run.events[..position]
        .iter()
        .map(|event| serde_json::to_vec(event).unwrap().len())
        .sum();
    let failed = working.run_request("run", &input, limits);
    assert_eq!(failed.diagnostic.as_ref().unwrap().code, "evidence_limit");
    assert_eq!(failed.events.len(), position);
    assert_eq!(failed.state["state"]["number"], 7);
    assert!(failed.result.is_none());
    explain_execution(&failed, working.source_bundle().unwrap()).unwrap();
}

#[test]
fn return_and_caller_binding_evidence_form_an_exact_source_linked_chain() {
    let source = state_program(
        "  LET answer be constant value\n  set state.number to answer\n",
        "WHEN constant value\n  THEN returns integer\n  RETURN 42\n",
    )
    .replace('\n', "\r\n");
    let program = program(&source);
    let run = program.run_request(
        "run",
        &json!({"state":{"number":0,"values":[]}}),
        ProgramLimits::default(),
    );
    assert!(run.ok);
    let returned = run
        .events
        .iter()
        .find(|event| event.operation == "return")
        .unwrap();
    assert_eq!(&source[returned.span.start..returned.span.end], "RETURN 42");
    assert_eq!(returned.value, 42);
    assert_eq!(run.events[returned.inputs[0] - 1].operation, "literal");
    let bound = run
        .events
        .iter()
        .find(|event| event.operation == "initialize" && event.value["path"] == "answer")
        .unwrap();
    let leave = &run.events[bound.inputs[0] - 1];
    assert_eq!(leave.operation, "leave behavior");
    assert_eq!(leave.inputs, vec![returned.sequence]);
    assert_eq!(leave.value["returned"], 42);
    explain_execution(&run, program.source_bundle().unwrap()).unwrap();
}

#[test]
fn checker_requires_explicit_types_and_complete_return_paths() {
    for (source, code) in [
        ("WHEN result\n  RETURN 1\n", "return_contract"),
        (
            "WHEN result\n  THEN returns integer\n  PASS\n",
            "missing_return",
        ),
        (
            "WHEN result\n  THEN returns integer\n  IF true\n    RETURN 1\n",
            "missing_return",
        ),
        (
            "WHEN result\n  THEN returns integer\n  FOR item in [1]\n    RETURN item\n",
            "missing_return",
        ),
        (
            "WHEN result\n  THEN returns integer\n  RETURN \"wrong\"\n",
            "assignment_type",
        ),
        (
            "WHEN result\n  THEN returns integer\n  RETURN\n",
            "missing_operand",
        ),
        (
            "WHEN result\n  THEN returns integer\n  THEN returns integer\n  RETURN 1\n",
            "duplicate_return_contract",
        ),
        (
            "WHEN result <x>\n  THEN returns integer\n  GIVEN x is integer\n  RETURN x\n",
            "contract_order",
        ),
        (
            "WHEN result\n  THEN returns Unknown\n  RETURN 1\n",
            "unknown_type",
        ),
        (
            "WHEN do nothing\n  PASS\nWHEN caller\n  LET x be do nothing\n",
            "void_call",
        ),
        ("WHEN RETURN 1\n", "return_contract"),
        (
            "WHEN result\n  THEN returns integer\n  RETURN 1\n  RETURN \"wrong\"\n",
            "assignment_type",
        ),
    ] {
        assert_eq!(
            compile_program(source, "invalid.gwt").unwrap_err().code,
            code,
            "{source}"
        );
    }
}

#[test]
fn returning_recursion_obeys_the_shared_hard_depth_limit() {
    let source = state_program(
        "  LET number be recurse state\n  set state.number to number\n",
        "WHEN recurse <state>\n  GIVEN state is State\n  THEN returns integer\n  LET again be recurse state\n  RETURN again\n",
    );
    let program = program(&source);
    for depth in [0, 1, 4, usize::MAX] {
        let run = program.run_request(
            "run",
            &json!({"state":{"number":0,"values":[]}}),
            ProgramLimits {
                call_depth: depth,
                ..ProgramLimits::default()
            },
        );
        assert_eq!(run.diagnostic.unwrap().code, "call_depth");
    }
}

#[test]
fn recursive_results_and_returned_records_have_independent_local_values() {
    let source = state_program(
        "  LET copy be snapshot state\n  set copy.number to 99\n  REQUIRE state.number == 5\n  LET product be factorial state.number\n  set state.number to product\n  print copy.number\n",
        "WHEN snapshot <state>\n  GIVEN state is State\n  THEN returns State\n  RETURN state\nWHEN factorial <number>\n  GIVEN number is integer\n  THEN returns integer\n  REQUIRE number >= 0\n  IF number <= 1\n    RETURN 1\n  LET previous be number - 1\n  LET product be factorial previous\n  RETURN number * product\n",
    );
    let run = program(&source).run_request(
        "run",
        &json!({"state":{"number":5,"values":[]}}),
        ProgramLimits::default(),
    );
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.result.unwrap()["state"]["number"], 120);
    assert_eq!(run.output, vec![json!(99)]);

    // A deep successful call chain still has room to evaluate a nested return
    // expression; this runs on the ordinary Rust test thread stack.
    let helper = format!(
        "WHEN descend <remaining>\n  GIVEN remaining is integer\n  THEN returns integer\n  IF remaining == 0\n    RETURN {}1\n  LET previous be remaining - 1\n  LET result be descend previous\n  RETURN result\n",
        "-".repeat(40)
    );
    let source = state_program(
        "  LET value be descend state.number\n  set state.number to value\n",
        &helper,
    );
    let run = program(&source).run_request(
        "run",
        &json!({"state":{"number":55,"values":[]}}),
        ProgramLimits::default(),
    );
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.result.unwrap()["state"]["number"], 1);
}

#[test]
fn expression_bindings_keep_precedence_over_zero_argument_behavior_names() {
    let source = state_program(
        "  LET rate be 3\n  LET answer be rate\n  set state.number to answer\n",
        "WHEN rate\n  THEN returns integer\n  RETURN 99\n",
    );
    let run = program(&source).run_request(
        "run",
        &json!({"state":{"number":0,"values":[]}}),
        ProgramLimits::default(),
    );
    assert!(run.ok);
    assert_eq!(run.result.unwrap()["state"]["number"], 3);
    assert!(!run.events.iter().any(|event| event.operation == "return"));
}
