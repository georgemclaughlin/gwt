use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, compile_bundle, compile_program,
    explain_execution, format_source, replay_case,
};
use serde_json::json;
use std::collections::BTreeMap;
use std::fmt::Write;

fn bundled(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
const ITEM: &str =
    "RECORD Item\n  name: text\n  quantity: integer\n  note: optional<text>\nTYPE Row is Item\n";

#[test]
fn record_tables_use_ordered_exact_expressions_and_absent_optional_columns() {
    let source = format!(
        "{ITEM}GIVEN base is 9007199254740993\nGIVEN note is \"we are ready\"\nGIVEN items are Row\n  | quantity | name |\n  | base + 1 | \"café | #\" |\n  | 2 | note |\nWHEN print items\n"
    );
    let program = bundled(&source);
    let run = program.run_scenario("Main", ProgramLimits::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    let expected = json!([{"name":"café | #", "quantity":9007199254740994_u64,"note":null},{"name":"we are ready","quantity":2,"note":null}]);
    assert_eq!(run.state["items"], expected);
    assert_eq!(run.output, [expected]);
    let rows: Vec<_> = run
        .events
        .iter()
        .filter(|event| event.operation == "table row")
        .collect();
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].value["quantity"], json!(9007199254740994_u64));
    assert!(
        rows.iter()
            .all(|row| row.inputs.iter().all(|input| *input < row.sequence))
    );
    let explanation = explain_execution(&run, program.source_bundle().unwrap()).unwrap();
    assert!(
        explanation
            .steps
            .iter()
            .any(|step| step.operation == "table row" && step.source.text.contains("base + 1"))
    );
}

#[test]
fn header_only_is_an_explicit_empty_record_list_and_cells_copy_nested_values() {
    let source = "RECORD Meta\n  code: text\nRECORD Item\n  meta: Meta\n  values: list<integer>\nGIVEN meta is Meta\n  code: \"original\"\nGIVEN items are Item\n  | meta | values |\n  | meta | [] |\n  | meta | [1, 2] |\nGIVEN empty are Item\n  | meta | values |\nWHEN set meta.code to \"changed\"\nWHEN print items\nWHEN print empty\n";
    let run = bundled(source).run_scenario("Main", Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(
        run.output,
        [
            json!([{"meta":{"code":"original"},"values":[]},{"meta":{"code":"original"},"values":[1,2]}]),
            json!([])
        ]
    );
}

fn request(rows: &str) -> String {
    format!(
        "RECORD Item\n  quantity: integer\nRECORD Box\n  items: list<Item>\nREQUEST replace\n  GIVEN box is Box\n  GIVEN box.items are Item\n    | quantity |\n{rows}  WHEN accept box\n  OUTPUT box is Box\nWHEN accept <box>\n  GIVEN box is Box\n  PASS\n"
    )
}
#[test]
fn nested_collection_replacement_is_atomic_across_row_failures_and_budgets() {
    let input = json!({"box":{"items":[{"quantity":99}]}});
    let program = bundled(&request("    | 1 |\n    | 2 |\n"));
    let expected = json!({"items":[{"quantity":1},{"quantity":2}]});
    let run = program.run_request("replace", &input, Default::default());
    assert!(run.ok);
    assert_eq!(run.result.as_ref().unwrap()["box"], expected);
    assert_eq!(input, json!({"box":{"items":[{"quantity":99}]}}));
    for steps in 0..=run.steps {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let result = program.run_request("replace", &input, limits);
        assert!(result.state["box"] == input["box"] || result.state["box"] == expected);
    }
    for bytes in [0, 64, 256, 512, 1024, 4096] {
        let mut limits = ProgramLimits::default();
        limits.execution.evidence_bytes = bytes;
        let result = program.run_request("replace", &input, limits);
        assert!(result.state["box"] == input["box"] || result.state["box"] == expected);
    }
}

#[test]
fn row_evaluation_failure_keeps_prior_field_and_original_cell_diagnostic() {
    let source =
        request("    | 1.0 |\n    | 1 / 0 |\n").replace("quantity: integer", "quantity: decimal");
    let input = json!({"box":{"items":[{"quantity":"99"}]}});
    let program = bundled(&source);
    let run = program.run_request("replace", &input, Default::default());
    assert!(!run.ok);
    assert_eq!(run.state["box"], input["box"]);
    let error = run.diagnostic.as_ref().unwrap();
    assert_eq!(error.code, "division_by_zero");
    assert_eq!(&source[error.span.start..error.span.end], "1 / 0");
    assert_eq!(
        run.events
            .iter()
            .filter(|event| event.operation == "table row")
            .count(),
        1
    );
    assert_eq!(
        run.events
            .iter()
            .find(|event| event.operation == "table row")
            .unwrap()
            .value["quantity"],
        "1"
    );
    assert!(
        !run.events
            .iter()
            .any(|event| event.operation == "initialize field")
    );
    explain_execution(&run, program.source_bundle().unwrap()).unwrap();
}

#[test]
fn header_shape_cell_types_and_targets_are_checked_before_execution() {
    for (suffix, code) in [
        ("GIVEN items are Item\n", "table_header"),
        (
            "GIVEN items are Item\n  | name |\n  | \"x\" |\n",
            "table_header",
        ),
        (
            "GIVEN items are Item\n  | name | quantity | extra |\n  | \"x\" | 1 | 2 |\n",
            "table_header",
        ),
        (
            "GIVEN items are Item\n  | name | quantity | name |\n  | \"x\" | 1 | \"y\" |\n",
            "table_header",
        ),
        (
            "GIVEN items are Item\n  | name | quantity |\n  | \"x\" |\n",
            "table_columns",
        ),
        (
            "GIVEN items are Item\n  | name | quantity |\n  | \"x\" | true |\n",
            "assignment_type",
        ),
        (
            "GIVEN items are Item\n  | name | quantity |\n  | | 1 |\n",
            "table_cell",
        ),
        (
            "GIVEN items are integer\n  | value |\n  | 1 |\n",
            "table_type",
        ),
        (
            "GIVEN items is 1\nGIVEN items are Item\n  | name | quantity |\n",
            "duplicate_binding",
        ),
        (
            "GIVEN missing.items are Item\n  | name | quantity |\n",
            "unknown_name",
        ),
    ] {
        let error = compile_program(&format!("{ITEM}{suffix}"), "bad.gwt").unwrap_err();
        assert_eq!(error.code, code, "{suffix}: {error}");
    }
    let wrong = "RECORD Wrong\n  items: list<integer>\nGIVEN wrong is Wrong\n  items: []\nGIVEN wrong.items are Item\n  | name | quantity |\n";
    assert_eq!(
        compile_program(&format!("{ITEM}{wrong}"), "bad.gwt")
            .unwrap_err()
            .code,
        "table_target_type"
    );
}

#[test]
fn table_rows_in_example_templates_keep_cell_sources_after_unicode_and_crlf() {
    let source = "# 😀\nRECORD Item\n  quantity: integer\nSCENARIO rows\nGIVEN items are Item\n  | quantity |\n  | <quantity> |\nWHEN print items\nTHEN prints [[{\"quantity\": <quantity>}]]\nEXAMPLES\n  | quantity |\n  | 9007199254740993 |\n  | 2 |\n".replace('\n', "\r\n");
    let formatted = format_source(&source, "rules.gwt").unwrap();
    assert!(!format_source(&formatted.text, "rules.gwt").unwrap().changed);
    let program = bundled(&formatted.text);
    let runs = program.test_scenarios(Default::default());
    assert_eq!(runs.len(), 2);
    assert!(runs.iter().all(|run| run.execution.ok));
    assert_eq!(
        runs[0].execution.output[0],
        json!([{"quantity":9007199254740993_u64}])
    );
    assert_eq!(runs[1].execution.output[0], json!([{"quantity":2}]));
    for run in &runs {
        explain_execution(&run.execution, program.source_bundle().unwrap()).unwrap();
    }
    let literal = runs[0]
        .execution
        .events
        .iter()
        .find(|event| event.operation == "literal" && event.value == json!(9007199254740993_u64))
        .unwrap();
    assert_eq!(literal.span.line, 12);
    assert_eq!(
        &formatted.text[literal.span.start..literal.span.end],
        "9007199254740993"
    );
}

#[test]
fn table_row_column_and_cell_limits_are_explicit() {
    let source = format!(
        "RECORD Item\n  value: integer\nGIVEN items are Item\n  | value |\n{}",
        "  | 1 |\n".repeat(1024)
    );
    assert!(compile_program(&source, "limit.gwt").is_ok());
    assert_eq!(
        compile_program(&(source + "  | 1 |\n"), "limit.gwt")
            .unwrap_err()
            .code,
        "table_limit"
    );
    let mut fields = String::new();
    for index in 0..257 {
        writeln!(&mut fields, "  f{index}: integer").unwrap();
    }
    let header = (0..257)
        .map(|index| format!("f{index}"))
        .collect::<Vec<_>>()
        .join(" | ");
    let source = format!("RECORD Wide\n{fields}GIVEN values are Wide\n  | {header} |\n");
    assert_eq!(
        compile_program(&source, "limit.gwt").unwrap_err().code,
        "table_limit"
    );
    let mut fields = String::new();
    for index in 0..17 {
        writeln!(&mut fields, "  f{index}: integer").unwrap();
    }
    let header = (0..17)
        .map(|index| format!("f{index}"))
        .collect::<Vec<_>>()
        .join(" | ");
    let row = format!("  | {} |\n", vec!["1"; 17].join(" | "));
    let source = format!(
        "RECORD Wide\n{fields}GIVEN values are Wide\n  | {header} |\n{}",
        row.repeat(1024)
    );
    assert_eq!(
        compile_program(&source, "limit.gwt").unwrap_err().code,
        "table_limit"
    );
}

#[test]
fn receiving_example_has_independent_totals_and_isolates_a_changed_row() {
    let source = include_str!("../../../examples/native_setup_tables/rules.gwt");
    let program = bundled(source);
    let runs = program.test_scenarios(Default::default());
    assert_eq!(runs.len(), 3);
    for (run, total) in runs.iter().zip([6, 4, 0]) {
        assert!(run.execution.ok, "{:?}", run.execution.diagnostic);
        assert_eq!(run.execution.state["receipt"]["total"], total);
        let case = gwt_core::capture_scenario(&program, &run.name, Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
        let candidate_source = source.replacen("| 2", "| 3", 1);
        assert_ne!(candidate_source, source);
        let comparison = gwt_core::compare_case(&case, &bundled(&candidate_source)).unwrap();
        assert_eq!(comparison.changes.as_ref().unwrap().outcome, total == 6);
        if total == 6 {
            let candidate = comparison.candidate.as_ref().unwrap();
            assert!(!candidate.ok);
            assert_eq!(candidate.state["receipt"]["total"], 7);
        }
    }
}

#[test]
fn request_table_evidence_survives_case_capture_replay_and_comparison() {
    let source = request("    | 1 |\n    | 2 |\n");
    let program = bundled(&source);
    let case = capture_request(
        &program,
        "replace",
        &json!({"box":{"items":[]}}),
        Default::default(),
    )
    .unwrap();
    let replay = replay_case(&case).unwrap();
    assert!(replay.verified);
    assert_eq!(
        replay.actual.result.as_ref().unwrap()["box"]["items"],
        json!([{"quantity":1},{"quantity":2}])
    );
    let candidate = bundled(&source.replace("| 2 |", "| 3 |"));
    let comparison = gwt_core::compare_case(&case, &candidate).unwrap();
    assert!(comparison.changes.as_ref().unwrap().outcome);
    assert_eq!(
        comparison
            .candidate
            .as_ref()
            .unwrap()
            .result
            .as_ref()
            .unwrap()["box"]["items"],
        json!([{"quantity":1},{"quantity":3}])
    );
}
