use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, compile_bundle, compile_program,
    explain_execution, format_source, replay_case, scenario_from_case,
};
use serde_json::json;
use std::collections::BTreeMap;

fn bundled(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

const BOX: &str = "RECORD Box\n  amount: decimal\n  note: optional<text>\n";

#[test]
fn typed_locals_construct_aliases_nested_optional_records_and_selected_kinds() {
    let source = "RECORD Note\n  text: optional<text>\nRECORD Route is one of\n  pickup:\n    code: text\n  courier:\n    tracking: text\nTYPE Pickup is Route of kind pickup\nRECORD Result\n  route: Pickup\n  backup: optional<Note>\n  amounts: list<decimal>\n  omitted: optional<text>\nWHEN build\n  THEN returns Result\n  LET empty be Note:\n  LET result be Result:\n    route:\n      kind: \"pickup\"\n      code: \"café 😀\"\n    backup: empty\n    amounts: [0.1, 0.2]\n  RETURN result\nREQUEST build\n  WHEN LET result be build\n  OUTPUT result is Result\n";
    let result = bundled(source).run_request("build", &json!({}), ProgramLimits::default());
    assert!(result.ok, "{:?}", result.diagnostic);
    assert_eq!(
        result.result,
        Some(
            json!({"result":{"route":{"kind":"pickup","code":"café 😀"},"backup":{"text":null},"amounts":["0.1","0.2"],"omitted":null}})
        )
    );
}

#[test]
fn construction_is_explicit_and_does_not_change_expression_or_behavior_resolution() {
    let source = format!(
        "{BOX}WHEN Box\n  THEN returns integer\n  RETURN 7\nWHEN build <Box>\n  GIVEN Box is integer\n  THEN returns decimal\n  LET copied be Box\n  LET constructed be Box:\n    amount: copied\n  RETURN constructed.amount\nREQUEST build\n  WHEN LET called be Box\n  AND LET result be build called\n  OUTPUT result is decimal\n"
    );
    let result = bundled(&source).run_request("build", &json!({}), Default::default());
    assert!(result.ok, "{:?}", result.diagnostic);
    assert_eq!(result.result, Some(json!({"result":"7"})));
}

#[test]
fn constructors_reject_incomplete_extra_duplicate_incompatible_and_self_referential_fields() {
    for (body, code) in [
        ("  LET result be Box:\n", "missing_field"),
        (
            "  LET result be Missing:\n    amount: 0.0\n",
            "unknown_type",
        ),
        (
            "  LET result be integer:\n    amount: 0\n",
            "initializer_type",
        ),
        (
            "  LET result be Box:\n    amount: true\n",
            "assignment_type",
        ),
        (
            "  LET result be Box:\n    amount: 0.0\n    amount: 1.0\n",
            "duplicate_field",
        ),
        (
            "  LET result be Box:\n    amount: 0.0\n    extra: 1\n",
            "unknown_field",
        ),
        (
            "  LET result be Box:\n    amount: result.amount\n",
            "unknown_name",
        ),
        (
            "  LET result be Box:\n    amount: 0.0\n    note: amount\n",
            "unknown_name",
        ),
        (
            "  LET result be Box:\n    amount: 0.0\n  LET result be Box:\n    amount: 1.0\n",
            "duplicate_binding",
        ),
    ] {
        let source = format!("{BOX}WHEN build\n{body}");
        assert_eq!(
            compile_program(&source, "rules.gwt").unwrap_err().code,
            code,
            "{body}"
        );
    }
}

#[test]
fn constructor_reads_copy_values_and_branch_locals_do_not_escape() {
    let source = "RECORD Inner\n  value: integer\nRECORD Outer\n  inner: Inner\nWHEN build <original>\n  GIVEN original is Inner\n  THEN returns Outer\n  LET result be Outer:\n    inner: original\n  set result.inner.value to 99\n  REQUIRE original.value == 1\n  RETURN result\nREQUEST build\n  GIVEN original is Inner\n  WHEN LET result be build original\n  OUTPUT original is Inner\n  OUTPUT result is Outer\n";
    let result = bundled(source).run_request(
        "build",
        &json!({"original":{"value":1}}),
        Default::default(),
    );
    assert_eq!(
        result.result,
        Some(json!({"original":{"value":1},"result":{"inner":{"value":99}}}))
    );
    let escaping = format!(
        "{BOX}WHEN build\n  IF true\n    LET local be Box:\n      amount: 0.0\n  print local.amount\n"
    );
    assert_eq!(
        compile_program(&escaping, "rules.gwt").unwrap_err().code,
        "unknown_name"
    );
    let looped = format!(
        "{BOX}WHEN build <values>\n  GIVEN values is list<integer>\n  FOR value in values\n    LET local be Box:\n      amount: value\n    print local.amount\nREQUEST build\n  GIVEN values is list<integer>\n  WHEN build values\n"
    );
    let result =
        bundled(&looped).run_request("build", &json!({"values":[1,2]}), Default::default());
    assert!(result.ok, "{:?}", result.diagnostic);
    let initialized: Vec<_> = result
        .events
        .iter()
        .filter(|e| e.operation == "initialize")
        .map(|e| e.value["after"]["amount"].clone())
        .collect();
    assert_eq!(initialized, vec![json!("1"), json!("2")]);
}

#[test]
fn request_construction_is_atomic_on_operand_and_execution_budget_failures() {
    let source = "RECORD Pair\n  first: decimal\n  second: decimal\nREQUEST build\n  GIVEN divisor is integer\n  WHEN LET pair be Pair:\n    first: 7.0\n    second: 1.0 / divisor\n  OUTPUT pair is Pair\n";
    let program = bundled(source);
    let failed = program.run_request("build", &json!({"divisor":0}), Default::default());
    assert_eq!(failed.diagnostic.unwrap().code, "division_by_zero");
    assert!(failed.state.get("pair").is_none());
    assert!(!failed.events.iter().any(|e| e.operation == "initialize"));
    assert!(
        failed
            .events
            .iter()
            .any(|e| e.operation == "literal" && e.value == "7")
    );
    let successful = program.run_request("build", &json!({"divisor":2}), Default::default());
    assert!(successful.ok);
    for steps in 0..=successful.steps {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let result = program.run_request("build", &json!({"divisor":2}), limits);
        if let Some(pair) = result.state.get("pair") {
            assert_eq!(pair, &json!({"first":"7","second":"0.5"}));
            assert!(result.events.iter().any(|e| e.operation == "initialize"));
        }
    }
    for bytes in [0, 100, 500, 1000, 2000] {
        let mut limits = ProgramLimits::default();
        limits.execution.evidence_bytes = bytes;
        let result = program.run_request("build", &json!({"divisor":2}), limits);
        if let Some(pair) = result.state.get("pair") {
            assert_eq!(pair, &json!({"first":"7","second":"0.5"}));
            assert!(result.events.iter().any(|e| e.operation == "initialize"));
        }
    }
}

#[test]
fn source_mapping_explanation_capture_and_generated_scenarios_keep_constructor_fields() {
    let source = format!("# café 😀\n{BOX}REQUEST build\n  GIVEN amount is decimal\n  WHEN LET result be Box:\n    amount: amount\n  OUTPUT result is Box\nSCENARIO constructed\nWHEN LET result be Box:\n  amount: <amount>\nTHEN result.amount == <amount>\nEXAMPLES\n  | amount |\n  | 0.1 |\n  | 0.2 |\n").replace('\n',"\r\n");
    let program = bundled(&source);
    let outline = gwt_core::outline_source(&source, "rules.gwt").unwrap();
    assert_eq!(
        outline
            .iter()
            .filter(|item| item.kind == "behavior")
            .count(),
        0
    );
    assert!(
        outline
            .iter()
            .any(|item| item.name == "constructed" && item.kind == "scenario")
    );
    let scenarios = program.test_scenarios(Default::default());
    assert_eq!(scenarios.len(), 2);
    assert!(scenarios.iter().all(|s| s.execution.ok));
    for scenario in scenarios {
        let event = scenario
            .execution
            .events
            .iter()
            .find(|e| e.operation == "initialize")
            .unwrap();
        assert!(source[event.span.start..event.span.end].contains("LET result be Box:"));
    }
    let input = json!({"amount":"0.25"});
    let case = capture_request(&program, "build", &input, Default::default()).unwrap();
    assert!(replay_case(&case).unwrap().verified);
    let generated = scenario_from_case(&case, "constructed case").unwrap();
    assert!(
        compile_bundle(generated.source_bundle())
            .unwrap()
            .run_scenario(generated.name(), Default::default())
            .ok
    );
    let run = program.run_request("build", &input, Default::default());
    let explanation = explain_execution(&run, program.source_bundle().unwrap()).unwrap();
    assert!(
        explanation
            .steps
            .iter()
            .any(|s| s.operation == "initialize" && s.source.text.contains("LET result be Box:"))
    );
    let formatted = format_source(&source, "rules.gwt").unwrap();
    assert_eq!(
        bundled(&formatted.text)
            .run_request("build", &input, Default::default())
            .result,
        run.result
    );
}
