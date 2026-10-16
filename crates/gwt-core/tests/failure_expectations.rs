use std::collections::BTreeMap;

use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, capture_scenario, compare_case, compile_bundle,
    compile_program, explain_execution, replay_case, scenario_from_case,
};
use serde_json::{Value as Json, json};

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

#[test]
fn independent_stock_boundaries_generate_tests_for_success_and_failure() {
    let source = include_str!("../../../examples/native_expected_failures/rules.gwt");
    let original = program(source);
    let candidate = source.replace("  REQUIRE stock.available >= order.quantity", "  PASS");
    for available in [-1, 0, 1, 2, 10] {
        for quantity in [-1, 0, 1, 2, 3] {
            let accepted = quantity > 0 && available >= quantity;
            let facts = json!({"stock":{"available":available},"order":{"quantity":quantity}});
            let case =
                capture_request(&original, "reserve stock", &facts, ProgramLimits::default())
                    .unwrap();
            assert_eq!(case.observed()["ok"], accepted);
            assert_eq!(
                case.observed()["state"]["stock"]["available"],
                if accepted {
                    available - quantity
                } else {
                    available
                }
            );
            let prints = if quantity <= 0 {
                json!([])
            } else if accepted {
                json!(["checking stock", "reserved"])
            } else {
                json!(["checking stock"])
            };
            assert_eq!(case.observed()["output"], prints);
            let generated = scenario_from_case(&case, "stock boundary").unwrap();
            let metadata = json!(generated);
            assert_eq!(metadata["schemaVersion"], 3);
            if accepted {
                assert_eq!(
                    metadata["assertionScope"],
                    "declared_outputs_and_printed_sequence"
                );
                assert!(metadata.get("capturedFailure").is_none());
            } else {
                assert_eq!(
                    metadata["assertionScope"],
                    "failure_code_inputs_and_printed_sequence"
                );
                assert_eq!(metadata["capturedFailure"], case.observed()["diagnostic"]);
            }
            let checked = compile_bundle(generated.source_bundle()).unwrap();
            let scenario =
                capture_scenario(&checked, "stock boundary", ProgramLimits::default()).unwrap();
            assert_eq!(scenario.observed()["ok"], true);
            assert!(replay_case(&scenario).unwrap().verified);
            let mut changed = generated.source_bundle().clone();
            changed
                .modules
                .insert("rules.gwt".into(), candidate.clone());
            let compared = compare_case(&scenario, &compile_bundle(&changed).unwrap()).unwrap();
            let run = compared.candidate.unwrap();
            assert_eq!(run.ok, !(quantity > 0 && available < quantity));
            explain_execution(&run, &changed).unwrap();
        }
    }
    let scenarios = original.test_scenarios(ProgramLimits::default());
    assert_eq!(scenarios.len(), 4);
    assert!(scenarios.iter().all(|row| row.execution.ok));
}

#[test]
fn expected_failure_retains_original_diagnostic_and_source_evidence() {
    let source = "WHEN print 1 / 0\nTHEN fails with \"division_by_zero\"\nAND prints []\nWHEN print \"continued\"\n";
    let program = program(source);
    let run = program.run_scenario("Main", ProgramLimits::default());
    assert!(run.ok);
    assert!(run.diagnostic.is_none());
    assert_eq!(run.output, vec![json!("continued")]);
    let event = run
        .events
        .iter()
        .find(|event| event.operation == "assert failure")
        .unwrap();
    assert_eq!(event.value["matched"], true);
    assert_eq!(event.value["expectedCode"], "division_by_zero");
    assert_eq!(event.value["actual"]["code"], "division_by_zero");
    assert_eq!(
        &source[event.span.start..event.span.end],
        "THEN fails with \"division_by_zero\""
    );
    assert!(!event.inputs.is_empty());
    let explanation = explain_execution(&run, program.source_bundle().unwrap()).unwrap();
    let step = explanation
        .steps
        .iter()
        .find(|step| step.operation == "assert failure")
        .unwrap();
    assert_eq!(step.observed_failure.as_ref().unwrap().text, "1 / 0");
    assert!(step.summary.contains("scenario can continue"));
}

#[test]
fn unexpected_success_and_wrong_behavior_error_fail_the_expectation() {
    for (action, actual) in [
        ("print 1", Json::Null),
        ("print 1 / 3", json!("nonterminating_decimal")),
    ] {
        let source = format!(
            "WHEN {action}\nTHEN fails with \"division_by_zero\"\nWHEN print \"unreachable\"\n"
        );
        let run = program(&source).run_scenario("Main", ProgramLimits::default());
        assert_eq!(run.diagnostic.unwrap().code, "failure_assertion_failed");
        let event = run.events.last().unwrap();
        assert_eq!(event.operation, "assert failure");
        assert_eq!(event.value["matched"], false);
        assert_eq!(event.value["actual"]["code"], actual);
        assert!(!run.output.contains(&json!("unreachable")));
    }
}

#[test]
fn preceding_setup_and_actions_cannot_satisfy_later_expectations() {
    for prefix in ["GIVEN amount is 1 / 0\n", "WHEN print 1 / 0\n"] {
        let source = format!("{prefix}WHEN PASS\nTHEN fails with \"division_by_zero\"\n");
        let run = program(&source).run_scenario("Main", ProgramLimits::default());
        assert_eq!(run.diagnostic.unwrap().code, "division_by_zero");
        assert!(
            !run.events
                .iter()
                .any(|event| event.operation == "assert failure")
        );
    }
    assert!(compile_program("BACKGROUND\nWHEN print 1 / 0\nSCENARIO separate\nTHEN fails with \"division_by_zero\"\n","scope.gwt").is_err());
}

#[test]
fn failed_actions_cannot_establish_new_bindings() {
    let source =
        "WHEN LET created be 1 / 0\nTHEN fails with \"division_by_zero\"\nTHEN created == 1\n";
    assert_eq!(
        compile_program(source, "scope.gwt").unwrap_err().code,
        "unknown_name"
    );
    let source = "REQUEST failed\n  GIVEN result is 1\n  WHEN REQUIRE false\n  OUTPUT result is integer\nREQUEST failed\nTHEN fails with \"assertion_failed\"\nTHEN result == 1\n";
    assert_eq!(
        compile_program(source, "scope.gwt").unwrap_err().code,
        "unknown_name"
    );
    let replaced = source.replace("THEN result == 1", "GIVEN result is 2\nTHEN result == 2");
    let run = program(&replaced).run_scenario("Main", ProgramLimits::default());
    assert!(run.ok);
    assert_eq!(run.state["result"], 2);
}

#[test]
fn continued_scenarios_keep_mutations_output_and_release_traversal_guards() {
    let source = "WHEN visit <items>\n  GIVEN items is list<integer>\n  FOR item in items\n    add 1 to item\n    print item\n    REQUIRE false\nGIVEN items is [1, 2]\nWHEN visit items\nTHEN fails with \"assertion_failed\"\nWHEN append 3 to items\nWHEN visit items\nTHEN fails with \"assertion_failed\"\nAND items == [3, 2, 3]\nAND prints [2, 3]\n";
    let run = program(source).run_scenario("Main", ProgramLimits::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(
        run.events
            .iter()
            .filter(|event| event.operation == "assert failure")
            .count(),
        2
    );
}

#[test]
fn limits_before_or_after_the_action_cannot_turn_into_passing_expectations() {
    let action = "GIVEN amount is 0\nWHEN change <amount>\n  GIVEN amount is integer\n  add 1 to amount\n  print amount\n  REQUIRE false\nWHEN change amount\n";
    let source = format!("{action}THEN fails with \"assertion_failed\"\n");
    let original = program(action).run_scenario("Main", ProgramLimits::default());
    let program = program(&source);
    let complete = program.run_scenario("Main", ProgramLimits::default());
    assert!(complete.ok);
    let assertion = complete.events.len() - 1;
    let mut limits = ProgramLimits::default();
    limits.execution.evidence_bytes = complete.events[..assertion]
        .iter()
        .map(|event| serde_json::to_vec(event).unwrap().len())
        .sum();
    let limited = program.run_scenario("Main", limits);
    assert_eq!(limited.diagnostic.unwrap().code, "evidence_limit");
    assert_eq!(limited.state["amount"], 1);
    assert_eq!(limited.output, vec![json!(1)]);
    assert_eq!(limited.events.len(), assertion);
    for steps in [0, original.steps] {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let run = program.run_scenario("Main", limits);
        assert_eq!(run.diagnostic.unwrap().code, "execution_limit");
        assert!(
            !run.events
                .iter()
                .any(|event| event.operation == "assert failure")
        );
    }
}

#[test]
fn malformed_unsupported_or_misplaced_expectations_fail_checking() {
    for code in [
        "execution_limit",
        "evidence_limit",
        "numeric_limit",
        "input_type",
        "collection_mutation",
        "uninitialized_state",
        "typo",
    ] {
        let source = format!("WHEN PASS\nTHEN fails with {code:?}\n");
        assert_eq!(
            compile_program(&source, "bad.gwt").unwrap_err().code,
            "failure_expectation_code"
        );
    }
    for text in ["assertion_failed", "42", "[\"assertion_failed\"]"] {
        assert_eq!(
            compile_program(&format!("WHEN PASS\nTHEN fails with {text}\n"), "bad.gwt")
                .unwrap_err()
                .code,
            "failure_expectation"
        );
    }
    for source in [
        "GIVEN value is 1\nTHEN fails with \"assertion_failed\"\n",
        "WHEN PASS\nTHEN true\nAND fails with \"assertion_failed\"\n",
        "WHEN REQUIRE false\nTHEN fails with \"assertion_failed\"\nTHEN fails with \"assertion_failed\"\n",
        "WHEN act\n  REQUIRE false\n  THEN fails with \"assertion_failed\"\n",
    ] {
        assert!(compile_program(source, "bad.gwt").is_err());
    }
}

#[test]
fn generated_failures_assert_partial_inputs_and_reject_resource_or_boundary_cases() {
    let source = include_str!("../../../examples/native_expected_failures/rules.gwt");
    let program = program(source);
    let facts = json!({"stock":{"available":2},"order":{"quantity":3}});
    let case =
        capture_request(&program, "reserve stock", &facts, ProgramLimits::default()).unwrap();
    let generated = scenario_from_case(&case, "partial state").unwrap();
    let mut candidate = generated.source_bundle().clone();
    candidate.modules.insert("rules.gwt".into(),source.replace("  REQUIRE stock.available >= order.quantity","  subtract order.quantity from stock.available\n  REQUIRE stock.available >= order.quantity"));
    let run = compile_bundle(&candidate)
        .unwrap()
        .run_scenario("partial state", ProgramLimits::default());
    assert_eq!(run.diagnostic.unwrap().code, "assertion_failed");
    assert!(
        run.events
            .iter()
            .any(|event| event.operation == "assert failure" && event.value["matched"] == true)
    );
    let mut limits = ProgramLimits::default();
    limits.execution.steps = 0;
    for case in [
        capture_request(&program, "reserve stock", &facts, limits).unwrap(),
        capture_request(
            &program,
            "reserve stock",
            &json!({}),
            ProgramLimits::default(),
        )
        .unwrap(),
    ] {
        assert_eq!(
            scenario_from_case(&case, "unsupported").unwrap_err().code,
            "scenario_failure_unsupported"
        );
    }
}

#[test]
fn generated_arithmetic_failures_preserve_the_exact_initial_diagnostic() {
    for (denominator, code) in [(0, "division_by_zero"), (3, "nonterminating_decimal")] {
        let source = format!("REQUEST calculate\n  WHEN print 1 / {denominator}\n");
        let original = program(&source);
        let case =
            capture_request(&original, "calculate", &json!({}), ProgramLimits::default()).unwrap();
        let generated = scenario_from_case(&case, "expected arithmetic failure").unwrap();
        assert_eq!(json!(generated)["capturedFailure"]["code"], code);
        let run = compile_bundle(generated.source_bundle())
            .unwrap()
            .run_scenario(generated.name(), ProgramLimits::default());
        assert!(run.ok);
        assert_eq!(
            run.events
                .iter()
                .find(|event| event.operation == "assert failure")
                .unwrap()
                .value["actual"],
            case.observed()["diagnostic"]
        );
    }
}

#[test]
fn recursion_and_example_rows_keep_failure_boundaries_and_original_sources() {
    let source = "WHEN descend <depth>\n  GIVEN depth is integer\n  REQUIRE depth > 0\n  descend (depth - 1)\nWHEN descend 55\nTHEN fails with \"assertion_failed\"\n";
    let original = program(source);
    assert!(original.run_scenario("Main", ProgramLimits::default()).ok);
    let limits = ProgramLimits {
        call_depth: 3,
        ..ProgramLimits::default()
    };
    let limited = original.run_scenario("Main", limits);
    assert_eq!(limited.diagnostic.unwrap().code, "call_depth");
    let source="SCENARIO arithmetic\nWHEN print 1 / <divisor>\nTHEN fails with <code>\nAND prints []\nEXAMPLES\n  | divisor | code |\n  | 0 | \"division_by_zero\" |\n  | 3 | \"nonterminating_decimal\" |\n".replace('\n',"\r\n");
    let original = program(&source);
    for row in original.test_scenarios(ProgramLimits::default()) {
        assert!(row.execution.ok);
        explain_execution(&row.execution, original.source_bundle().unwrap()).unwrap();
    }
}

#[test]
fn explanation_rejects_a_fabricated_observed_failure_location() {
    let program = program("WHEN REQUIRE false\nTHEN fails with \"assertion_failed\"\n");
    let mut run = program.run_scenario("Main", ProgramLimits::default());
    let event = run
        .events
        .iter_mut()
        .find(|event| event.operation == "assert failure")
        .unwrap();
    event.value["actual"]["span"]["file"] = json!("invented.gwt");
    assert_eq!(
        explain_execution(&run, program.source_bundle().unwrap())
            .unwrap_err()
            .code,
        "evidence_source"
    );
}
