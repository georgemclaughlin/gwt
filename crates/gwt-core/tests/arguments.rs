use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, compare_case, compile_bundle, compile_program,
    explain_execution, replay_case, scenario_from_case,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

fn source(body: &str, helpers: &str) -> String {
    format!(
        "RECORD State\n  amount: integer\n  values: list<integer>\n  note: text\nREQUEST run\n  GIVEN state is State\n  WHEN act state\n  OUTPUT state is State\nWHEN act <state>\n  GIVEN state is State\n{body}{helpers}"
    )
}

fn input() -> Json {
    json!({"state":{"amount":7,"values":[1,2],"note":"original"}})
}

fn decimal(numerator: i32, scale: i32) -> String {
    let places = if scale == 100 { 2 } else { 3 };
    let mut value = format!(
        "{}.{:0width$}",
        numerator / scale,
        numerator % scale,
        width = places
    );
    while value.ends_with('0') {
        value.pop();
    }
    if value.ends_with('.') {
        value.pop();
    }
    value
}

#[test]
fn independent_quotes_keep_input_values_and_compare_generated_regressions() {
    let source = include_str!("../../../examples/native_value_arguments/rules.gwt");
    let baseline = program(source);
    let revised = source.replace("at 0.1", "at 0.2");
    let candidate = program(&revised);
    for cents in [0, 1, 10, 1995] {
        for quantity in [1, 2, 3, 10] {
            for member in [false, true] {
                let price = decimal(cents, 100);
                let facts =
                    json!({"basket":{"unit_price":price,"quantity":quantity,"member":member}});
                let expected = |rate| json!({"quote":{"total":decimal(cents*quantity*(10-rate),1000),"note":if member {"member # discount"}else{"standard"}}});
                let case =
                    capture_request(&baseline, "quote basket", &facts, ProgramLimits::default())
                        .unwrap();
                assert_eq!(case.observed()["result"], expected(i32::from(member)));
                assert_eq!(case.observed()["state"]["basket"], facts["basket"]);
                assert!(replay_case(&case).unwrap().verified);
                let compared = compare_case(&case, &candidate).unwrap();
                assert_eq!(
                    compared.candidate.as_ref().unwrap().result,
                    Some(expected(if member { 2 } else { 0 }))
                );
                assert_eq!(compared.changes.unwrap().outcome, member && cents != 0);
                explain_execution(
                    compared.candidate.as_ref().unwrap(),
                    candidate.source_bundle().unwrap(),
                )
                .unwrap();
                let generated = scenario_from_case(&case, "recorded quote").unwrap();
                let mut bundle = generated.source_bundle().clone();
                bundle.modules.insert("rules.gwt".into(), revised.clone());
                let run = compile_bundle(&bundle)
                    .unwrap()
                    .test_scenarios(ProgramLimits::default());
                assert_eq!(run[0].execution.ok, !(member && cents != 0));
            }
        }
    }
    let scenarios = baseline.test_scenarios(ProgramLimits::default());
    assert_eq!(scenarios.len(), 5);
    assert!(scenarios.iter().all(|row| row.execution.ok));
}

#[test]
fn parenthesized_records_are_deep_copies_and_paths_remain_shared() {
    let helper = "WHEN alter <state>\n  GIVEN state is State\n  set state.amount to 99\n  append 3 to state.values\n";
    for (argument, copied) in [("state", false), ("(state)", true)] {
        let text = source(&format!("  alter {argument}\n"), helper);
        let program = program(&text);
        let run = program.run_request("run", &input(), ProgramLimits::default());
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(
            run.result.as_ref().unwrap()["state"],
            if copied {
                input()["state"].clone()
            } else {
                json!({"amount":99,"values":[1,2,3],"note":"original"})
            }
        );
        let change = run
            .events
            .iter()
            .find(|event| event.operation == "append item")
            .unwrap();
        assert_eq!(
            change.value["path"],
            if copied {
                "state (value).values"
            } else {
                "state.values"
            }
        );
        let entered = run
            .events
            .iter()
            .find(|event| {
                event.operation == "enter behavior" && event.value["signature"] == "alter <state>"
            })
            .unwrap();
        assert_eq!(entered.value.get("valueArguments").is_some(), copied);
        explain_execution(&run, program.source_bundle().unwrap()).unwrap();
    }
}

#[test]
fn argument_values_are_snapshots_before_any_callee_mutation() {
    let helper = "WHEN touch <left> beside <right>\n  GIVEN left is State\n  AND right is State\n  set left.amount to 99\n  print right.amount\n";
    for (call, expected) in [
        ("touch state beside (state)", 99),
        ("touch (state) beside state", 7),
    ] {
        let run = program(&source(&format!("  {call}\n"), helper)).run_request(
            "run",
            &input(),
            ProgramLimits::default(),
        );
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(run.output, vec![json!(7)]);
        assert_eq!(run.result.unwrap()["state"]["amount"], expected);
    }
}

#[test]
fn value_contracts_widen_without_weakening_mutable_path_contracts() {
    let helper = "WHEN adjust <amount>\n  GIVEN amount is decimal\n  THEN returns decimal\n  set amount to 1.5\n  RETURN amount\n";
    let shared = source(
        "  LET result be adjust state.amount\n  print result\n",
        helper,
    );
    assert_eq!(
        compile_program(&shared, "shared.gwt").unwrap_err().code,
        "argument_type"
    );
    for value in ["(state.amount)", "7", "-7"] {
        let run = program(&source(
            &format!("  LET result be adjust {value}\n  print result\n"),
            helper,
        ))
        .run_request("run", &input(), ProgramLimits::default());
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(run.output, vec![json!("1.5")]);
        assert_eq!(run.result.unwrap(), input());
    }
    for (ty, literal, expected) in [
        ("list<decimal>", "[]", json!([])),
        ("list<decimal>", "[1, (2 + 3)]", json!(["1", "5"])),
        ("boolean", "true", json!(true)),
        ("optional<integer>", "7", json!(7)),
        ("\"open\" | \"closed\"", "\"closed\"", json!("closed")),
    ] {
        let helper = format!("WHEN show <value>\n  GIVEN value is {ty}\n  print value\n");
        let run = program(&source(&format!("  show {literal}\n"), &helper)).run_request(
            "run",
            &input(),
            ProgramLimits::default(),
        );
        assert!(run.ok, "{ty}: {:?}", run.diagnostic);
        assert_eq!(run.output, vec![expected]);
    }
}

#[test]
fn quoted_text_is_never_resolved_as_a_path_and_keeps_utf8_source_spans() {
    let helper = "WHEN éclair <text>\n  GIVEN text is text\n  print text\n";
    for value in [
        "state.note",
        "text # with spaces and (groups) [lists] café",
        "quote: \" and slash: \\",
    ] {
        let literal = json!(value).to_string();
        let text = source(&format!("  éclair {literal}\n"), helper).replace('\n', "\r\n");
        let program = program(&text);
        let run = program.run_request("run", &input(), ProgramLimits::default());
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(run.output, vec![json!(value)]);
        let argument = run
            .events
            .iter()
            .find(|event| event.operation == "argument value")
            .unwrap();
        assert_eq!(&text[argument.span.start..argument.span.end], literal);
        let prefix = &text[..argument.span.start];
        assert_eq!(
            argument.span.column,
            prefix.rsplit('\n').next().unwrap().chars().count() + 1
        );
        explain_execution(&run, program.source_bundle().unwrap()).unwrap();
    }
}

#[test]
fn failed_arguments_and_evidence_limits_do_not_enter_the_callee() {
    let helper = "WHEN combine <first> with <second> using <state>\n  GIVEN first is decimal\n  AND second is decimal\n  AND state is State\n  set state.amount to 99\n";
    let failed = program(&source(
        "  combine (state.amount + 1) with (1 / 0) using state\n",
        helper,
    ));
    let run = failed.run_request("run", &input(), ProgramLimits::default());
    assert_eq!(run.diagnostic.unwrap().code, "division_by_zero");
    assert_eq!(run.state, input());
    assert!(
        !run.events
            .iter()
            .any(|event| event.operation == "enter behavior"
                && event.value["signature"] == "combine <first> with <second> using <state>")
    );
    let argument = run
        .events
        .iter()
        .find(|event| event.operation == "argument value")
        .unwrap();
    assert_eq!(argument.value, json!({"parameter":"first","value":"8"}));
    let working = program(&source(
        "  combine (state.amount + 1) with (state.amount + 2) using state\n",
        helper,
    ));
    let run = working.run_request("run", &input(), ProgramLimits::default());
    assert!(run.ok);
    let values: Vec<_> = run
        .events
        .iter()
        .filter(|event| event.operation == "argument value")
        .map(|event| event.value["value"].clone())
        .collect();
    assert_eq!(values, vec![json!("8"), json!("9")]);
    for operation in ["argument value", "enter behavior"] {
        let index = run
            .events
            .iter()
            .position(|event| {
                event.operation == operation
                    && (operation != "enter behavior"
                        || event.value["signature"]
                            == "combine <first> with <second> using <state>")
            })
            .unwrap();
        let mut limits = ProgramLimits::default();
        limits.execution.evidence_bytes = run.events[..index]
            .iter()
            .map(|event| serde_json::to_vec(event).unwrap().len())
            .sum();
        let failed = working.run_request("run", &input(), limits);
        assert_eq!(failed.diagnostic.unwrap().code, "evidence_limit");
        assert_eq!(failed.state, input());
        assert_eq!(failed.events.len(), index);
    }
}

#[test]
fn copied_lists_can_change_during_a_shared_source_traversal() {
    let text = source(
        "  FOR item in state.values\n    extend (state.values)\n",
        "WHEN extend <values>\n  GIVEN values is list<integer>\n  append 9 to values\n  print values\n",
    );
    let run = program(&text).run_request("run", &input(), ProgramLimits::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.result.unwrap(), input());
    assert_eq!(run.output, vec![json!([1, 2, 9]), json!([1, 2, 9])]);
    let shared = text.replace("extend (state.values)", "extend state.values");
    let run = program(&shared).run_request("run", &input(), ProgramLimits::default());
    assert_eq!(run.diagnostic.unwrap().code, "collection_mutation");
}

#[test]
fn malformed_ungrouped_and_unknown_arguments_fail_checking() {
    let helper = "WHEN consume <value>\n  GIVEN value is integer\n  PASS\n";
    for (argument, code) in [
        ("(1]", "argument_syntax"),
        ("(1", "argument_syntax"),
        ("\"unterminated", "argument_syntax"),
        ("state.amount+1", "argument_group"),
        ("missing", "unknown_name"),
        ("\"text\"", "assignment_type"),
        ("true", "assignment_type"),
        ("[1, 2]", "assignment_type"),
    ] {
        let text = source(&format!("  consume {argument}\n"), helper);
        assert_eq!(
            compile_program(&text, "bad.gwt").unwrap_err().code,
            code,
            "{argument}"
        );
    }
    let deep = format!("{}1{}", "(".repeat(65), ")".repeat(65));
    assert_eq!(
        compile_program(&source(&format!("  consume {deep}\n"), helper), "deep.gwt")
            .unwrap_err()
            .code,
        "expression_limit"
    );
    assert_eq!(
        compile_program(
            "WHEN bad( <value>\n  GIVEN value is integer\n  PASS\n",
            "signature.gwt"
        )
        .unwrap_err()
        .code,
        "signature"
    );
}

#[test]
fn example_arguments_keep_original_cells_and_template_spans() {
    let text = "WHEN show <text> with <number>\n  GIVEN text is text\n  AND number is integer\n  print text\n  print number\nSCENARIO values\nWHEN show <message> with (<quantity> + 1)\nTHEN true\nEXAMPLES\n  | message | quantity |\n  | \"café # text\" | 2 |\n";
    let program = program(text);
    let rows = program.test_scenarios(ProgramLimits::default());
    assert!(rows[0].execution.ok);
    assert_eq!(
        rows[0].execution.output,
        vec![json!("café # text"), json!(3)]
    );
    let argument = rows[0]
        .execution
        .events
        .iter()
        .find(|event| event.operation == "argument value" && event.value["parameter"] == "text")
        .unwrap();
    assert_eq!(
        &text[argument.span.start..argument.span.end],
        "\"café # text\""
    );
    explain_execution(&rows[0].execution, program.source_bundle().unwrap()).unwrap();
}

#[test]
fn recursive_value_calls_respect_depth_budgets_and_do_not_modify_the_input() {
    let helper = "WHEN descend <remaining>\n  GIVEN remaining is integer\n  THEN returns integer\n  IF remaining == 0\n    RETURN 1\n  LET result be descend (remaining - 1)\n  RETURN result\n";
    let program = program(&source(
        "  LET value be descend (state.amount)\n  print value\n",
        helper,
    ));
    let facts = json!({"state":{"amount":55,"values":[],"note":"unchanged"}});
    let run = program.run_request("run", &facts, ProgramLimits::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.result.unwrap(), facts);
    assert_eq!(run.output, vec![json!(1)]);
    let run = program.run_request(
        "run",
        &facts,
        ProgramLimits {
            call_depth: 4,
            ..ProgramLimits::default()
        },
    );
    assert_eq!(run.diagnostic.unwrap().code, "call_depth");
}
