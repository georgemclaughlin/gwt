use gwt_core::{ProgramLimits, SourceBundle, compile_bundle, compile_program, explain_execution};
use serde_json::json;
use std::collections::BTreeMap;

fn bundled(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

#[test]
fn backgrounds_run_in_fresh_state_before_each_scenario() {
    let source = "WHEN increment <count>\n  GIVEN count is integer\n  add 1 to count\nBACKGROUND\nGIVEN count is 0\nWHEN increment count\nTHEN count == 1\nSCENARIO first\nWHEN increment count\nTHEN count == 2\nSCENARIO second\nTHEN count == 1\n";
    let program = bundled(source);
    let runs = program.test_scenarios(ProgramLimits::default());
    assert_eq!(runs.len(), 2);
    assert!(runs.iter().all(|run| run.execution.ok));
    assert_eq!(runs[0].execution.state["count"], 2);
    assert_eq!(runs[1].execution.state["count"], 1);
    for run in &runs {
        let explanation =
            explain_execution(&run.execution, program.source_bundle().unwrap()).unwrap();
        assert!(
            explanation.steps.iter().any(
                |step| step.operation == "initialize" && step.source.text == "GIVEN count is 0"
            )
        );
    }
    let again = program.test_scenarios(ProgramLimits::default());
    assert_eq!(json!(runs), json!(again));
}

#[test]
fn examples_expand_source_values_with_calls_lists_and_exact_decimals() {
    let source = "WHEN increase <target> by <amount>\n  GIVEN target is integer\n  GIVEN amount is integer\n  add amount to target\nBACKGROUND\nGIVEN total is 1\nSCENARIO table\nGIVEN delta is <amount>\nGIVEN values is [<amount>, <amount> + 1]\nWHEN increase <destination> by delta\nTHEN total == <expected>\nAND values == [delta, delta + 1]\nEXAMPLES\n  | amount | destination | expected |\n  | 2 | total | 3 |\n  | 4 | total | 5 |\n";
    let program = bundled(source);
    assert_eq!(
        program.scenario_names(),
        ["table example 1", "table example 2"]
    );
    for (index, run) in program
        .test_scenarios(ProgramLimits::default())
        .iter()
        .enumerate()
    {
        assert!(run.execution.ok, "{:?}", run.execution.diagnostic);
        assert_eq!(run.execution.state["total"], [3, 5][index]);
        assert_eq!(run.execution.events[0].operation, "example row");
        assert_eq!(run.execution.events[0].value["row"], index + 1);
        explain_execution(&run.execution, program.source_bundle().unwrap()).unwrap();
    }
    let program = bundled(
        "SCENARIO decimals\nGIVEN amount is <value>\nTHEN amount == <expected>\nEXAMPLES\n  | value | expected |\n  | 0.1 + 0.2 | 0.3 |\n  | 9007199254740993 | 9007199254740993 |\n",
    );
    let runs = program.test_scenarios(ProgramLimits::default());
    assert!(runs.iter().all(|run| run.execution.ok));
    assert_eq!(runs[0].execution.state["amount"], "0.3");
    assert_eq!(
        runs[1].execution.state["amount"],
        json!(9007199254740993_u64)
    );
}

#[test]
fn quoted_pipes_hashes_unicode_and_crlf_keep_exact_source_locations() {
    let source = "# café\nSCENARIO messages\nGIVEN message is <value>\nTHEN message == <value>\nAND true or (1 / 0 > 0)\nEXAMPLES\n  | value |\n  | \"café | # \\\"quoted\\\"\" | # outside comment\n  | \"\" |\n".replace('\n', "\r\n");
    let program = bundled(&source);
    let runs = program.test_scenarios(ProgramLimits::default());
    assert!(runs.iter().all(|run| run.execution.ok));
    assert_eq!(runs[0].execution.state["message"], "café | # \"quoted\"");
    assert_eq!(runs[1].execution.state["message"], "");
    let explanation =
        explain_execution(&runs[0].execution, program.source_bundle().unwrap()).unwrap();
    let literal = explanation
        .steps
        .iter()
        .find(|step| step.operation == "literal" && step.value == "café | # \"quoted\"")
        .unwrap();
    assert_eq!(literal.source.text, "\"café | # \\\"quoted\\\"\"");
    assert_eq!(literal.source.span.line, 8);
    assert_eq!(literal.source.span.column, 5);
    assert!(explanation.steps.iter().any(|step| step.skipped.is_some()));
}

#[test]
fn expanded_compound_expressions_point_to_template_and_cells() {
    let source = "SCENARIO calculation\nGIVEN total is <left> + <right>\nTHEN total == 30\nEXAMPLES\n  | left | right |\n  | 10 | 20 |\n";
    let program = bundled(source);
    let runs = program.test_scenarios(ProgramLimits::default());
    assert!(runs[0].execution.ok);
    let explanation =
        explain_execution(&runs[0].execution, program.source_bundle().unwrap()).unwrap();
    let sum = explanation
        .steps
        .iter()
        .find(|step| step.operation == "+")
        .unwrap();
    assert_eq!(sum.source.text, "GIVEN total is <left> + <right>");
    let operands: Vec<_> = sum
        .operands
        .iter()
        .map(|id| &explanation.steps[id - 1].source.text)
        .collect();
    assert_eq!(operands, [&"10".to_string(), &"20".to_string()]);
}

#[test]
fn every_row_is_checked_and_diagnostics_identify_the_actual_cell() {
    let source = "SCENARIO checking\nGIVEN amount is <value>\nTHEN amount > 0\nEXAMPLES\n  | value |\n  | 1 |\n  | missing |\n";
    let error = compile_program(source, "checking.gwt").unwrap_err();
    assert_eq!(error.code, "unknown_name");
    assert!(error.message.contains("checking example 2"));
    assert_eq!(&source[error.span.start..error.span.end], "missing");
    assert_eq!(error.span.line, 7);
    let missing = source.replace("| value |", "| other |");
    let error = compile_program(&missing, "checking.gwt").unwrap_err();
    assert_eq!(error.code, "example_placeholder");
    assert_eq!(&missing[error.span.start..error.span.end], "<value>");
}

#[test]
fn failing_rows_and_backgrounds_keep_evidence_and_do_not_stop_other_runs() {
    let program = bundled(
        "BACKGROUND\nGIVEN seed is 10\nSCENARIO divide\nGIVEN divisor is <value>\nTHEN seed / divisor > 0\nEXAMPLES\n  | value |\n  | 2 |\n  | 0 |\n  | 5 |\n",
    );
    let runs = program.test_scenarios(ProgramLimits::default());
    assert_eq!(
        runs.iter().map(|run| run.execution.ok).collect::<Vec<_>>(),
        [true, false, true]
    );
    assert_eq!(
        runs[1].execution.diagnostic.as_ref().unwrap().code,
        "division_by_zero"
    );
    for run in &runs {
        explain_execution(&run.execution, program.source_bundle().unwrap()).unwrap();
    }
    let program = bundled(
        "BACKGROUND\nGIVEN seed is 1\nTHEN false\nSCENARIO first\nWHEN print seed\nSCENARIO second\nWHEN print seed\n",
    );
    for run in program.test_scenarios(ProgramLimits::default()) {
        assert_eq!(run.execution.diagnostic.unwrap().code, "assertion_failed");
        assert_eq!(run.execution.state, json!({"seed":1}));
        assert!(run.execution.output.is_empty());
    }
}

#[test]
fn malformed_tables_and_ambiguous_scenario_structure_are_rejected() {
    for source in [
        "BACKGROUND\nGIVEN count is 0\n",
        "BACKGROUND\nSCENARIO empty\nTHEN true\n",
        "BACKGROUND\nGIVEN count is 0\nBACKGROUND\nGIVEN other is 1\nSCENARIO bad\nTHEN true\n",
        "SCENARIO bad\nTHEN true\nBACKGROUND\nGIVEN count is 0\n",
        "BACKGROUND\nWHEN define <count>\n  GIVEN count is integer\n  PASS\nSCENARIO bad\nTHEN true\n",
        "EXAMPLES\n  | value |\n  | 1 |\n",
        "SCENARIO empty\nEXAMPLES\n  | value |\n  | 1 |\n",
        "SCENARIO bad\nTHEN true\nEXAMPLES\n  | value |\n",
        "SCENARIO bad\nTHEN true\nEXAMPLES\n  | value | value |\n  | 1 | 2 |\n",
        "SCENARIO bad\nTHEN true\nEXAMPLES\n  | value |\n  | 1 | 2 |\n",
        "SCENARIO bad\nTHEN true\nEXAMPLES\n  | value |\n  | |\n",
        "SCENARIO bad\nTHEN true\nEXAMPLES\n  | value |\n  | \"open |\n",
        "SCENARIO bad\nTHEN true\nEXAMPLES\n  | bad-name |\n  | 1 |\n",
        "SCENARIO bad\nTHEN true\nEXAMPLES\n  | value |\n  | 1 |\nTHEN true\n",
        "SCENARIO bad\nTHEN true\nEXAMPLES\n  | value |\n  | 1 |\nEXAMPLES\n  | value |\n  | 2 |\n",
        "SCENARIO same\nTHEN true\nEXAMPLES\n  | value |\n  | 1 |\nSCENARIO same example 1\nTHEN true\n",
    ] {
        assert!(compile_program(source, "bad.gwt").is_err(), "{source}");
    }
}

#[test]
fn imported_backgrounds_and_tables_stay_outside_entry_state_and_scenarios() {
    let module = "RECORD Item\n  count: integer\nBACKGROUND\nGIVEN ignored is missing\nSCENARIO ignored example\nTHEN missing == <value>\nEXAMPLES\n  | value |\n  | 1 |\n";
    let program = compile_bundle(&SourceBundle {
        entry: "entry.gwt".into(),
        modules: BTreeMap::from([
            (
                "entry.gwt".into(),
                "USE \"module.gwt\"\nGIVEN item is Item\n  count: 3\nTHEN item.count == 3\n".into(),
            ),
            ("module.gwt".into(), module.into()),
        ]),
    })
    .unwrap();
    assert_eq!(program.scenario_names(), ["Main"]);
    let runs = program.test_scenarios(ProgramLimits::default());
    assert!(runs[0].execution.ok);
    assert_eq!(runs[0].execution.state, json!({"item":{"count":3}}));
    assert!(compile_program(module, "module.gwt").is_err());
}

#[test]
fn example_expansion_has_total_row_and_byte_limits() {
    let source = format!(
        "SCENARIO {}\nTHEN true\nEXAMPLES\n  | value |\n{}",
        "n".repeat(50000),
        "  | 1 |\n".repeat(100)
    );
    assert_eq!(
        compile_program(&source, "names.gwt").unwrap_err().code,
        "scenario_limit"
    );
    let source = format!(
        "SCENARIO pieces\nGIVEN value is {}\nEXAMPLES\n  | item |\n  | 1 |\n",
        "<".repeat(10000)
    );
    assert_eq!(
        compile_program(&source, "pieces.gwt").unwrap_err().code,
        "scenario_limit"
    );
    let source = format!(
        "SCENARIO nodes\n{}EXAMPLES\n  | item |\n{}",
        "THEN true\n".repeat(1000),
        "  | 1 |\n".repeat(66)
    );
    assert_eq!(
        compile_program(&source, "nodes.gwt").unwrap_err().code,
        "scenario_limit"
    );
    // Header names are shared internally; repeated metadata still has a total budget.
    let source = format!(
        "SCENARIO headers\nTHEN true\nEXAMPLES\n  | {} |\n{}",
        "h".repeat(50000),
        "  | 1 |\n".repeat(100)
    );
    assert_eq!(
        compile_program(&source, "headers.gwt").unwrap_err().code,
        "scenario_limit"
    );
    let source = format!(
        "SCENARIO boundary\nTHEN true\nEXAMPLES\n  | value |\n{}",
        "  | 1 |\n".repeat(1024)
    );
    let program = compile_program(&source, "limit.gwt").unwrap();
    assert_eq!(program.scenario_names().len(), 1024);
    assert_eq!(
        compile_program(&(source + "SCENARIO extra\nTHEN true\n"), "limit.gwt")
            .unwrap_err()
            .code,
        "scenario_limit"
    );
    let source = format!(
        "SCENARIO growth\nGIVEN value is [<item>, <item>, <item>, <item>, <item>]\nTHEN true\nEXAMPLES\n  | item |\n{}",
        format!("  | \"{}\" |\n", "x".repeat(1000)).repeat(900)
    );
    assert_eq!(
        compile_program(&source, "growth.gwt").unwrap_err().code,
        "scenario_limit"
    );
}

#[test]
fn delivery_tables_and_host_requests_match_independent_boundary_expectations() {
    let source = include_str!("../../../examples/native_delivery/rules.gwt");
    let program = bundled(source);
    let rows = program.test_scenarios(ProgramLimits::default());
    assert_eq!(rows.len(), 10);
    assert!(rows.iter().all(|row| row.execution.ok));
    for row in &rows {
        explain_execution(&row.execution, program.source_bundle().unwrap()).unwrap();
    }
    for (weight, normal_fee, status) in [
        (1, 5, "standard"),
        (999, 5, "standard"),
        (1000, 5, "standard"),
        (1001, 9, "standard"),
        (4999, 9, "standard"),
        (5000, 9, "standard"),
        (5001, 0, "manual"),
        (9000, 0, "manual"),
    ] {
        for member in [false, true] {
            let result = program.run_request(
                "quote delivery",
                &json!({"parcel":{"weight_grams":weight,"member":member}}),
                ProgramLimits::default(),
            );
            assert!(result.ok);
            assert_eq!(
                result.result.unwrap(),
                json!({"quote":{"status":status,"fee":if member {0} else {normal_fee}}})
            );
            assert!(
                !result
                    .events
                    .iter()
                    .any(|event| event.operation == "example row")
            );
        }
    }
    for weight in [0, -1] {
        let result = program.run_request(
            "quote delivery",
            &json!({"parcel":{"weight_grams":weight,"member":true}}),
            ProgramLimits::default(),
        );
        assert_eq!(result.diagnostic.unwrap().code, "assertion_failed");
    }
}

#[test]
fn cli_counts_expanded_rows_and_reports_each_failure() {
    use std::process::Command;
    let fixture = format!(
        "{}/../../examples/native_delivery/rules.gwt",
        env!("CARGO_MANIFEST_DIR")
    );
    let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .args(["test", &fixture])
        .output()
        .unwrap();
    assert!(output.status.success());
    let payload: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["scenarioCount"], 10);
    let temporary =
        std::env::temp_dir().join(format!("gwt-scenario-failure-{}.gwt", std::process::id()));
    std::fs::write(&temporary, "SCENARIO assertion\nTHEN <value>\nEXAMPLES\n  | value |\n  | true |\n  | false |\n  | true |\n").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("test")
        .arg(&temporary)
        .output()
        .unwrap();
    std::fs::remove_file(&temporary).unwrap();
    assert!(!output.status.success());
    let payload: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["scenarioCount"], 3);
    let rows = payload["scenarios"].as_array().unwrap();
    assert_eq!(
        rows.iter()
            .map(|row| row["execution"]["ok"].as_bool().unwrap())
            .collect::<Vec<_>>(),
        [true, false, true]
    );
}
