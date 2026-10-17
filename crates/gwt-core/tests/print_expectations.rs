use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, capture_scenario, compare_case, compile_bundle,
    compile_program, explain_execution, replay_case, scenario_from_case,
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

#[test]
fn exact_heterogeneous_output_has_source_and_print_dependencies() {
    let source = include_str!("../../../examples/native_print_expectations/rules.gwt");
    let program = program(source);
    let rows = program.test_scenarios(ProgramLimits::default());
    assert_eq!(rows.len(), 2);
    assert!(rows.iter().all(|row| row.execution.ok));
    let run = &rows[0].execution;
    assert_eq!(
        run.output,
        vec![
            json!("Packing receipt"),
            json!({"label":"fragile # café", "quantity":9007199254740993_u64}),
            json!(9007199254740993_u64)
        ]
    );
    let event = run
        .events
        .iter()
        .find(|event| event.operation == "assert prints")
        .unwrap();
    assert_eq!(
        event.value,
        json!({"matched":true,"expected":run.output,"actual":run.output})
    );
    assert_eq!(
        event.inputs,
        run.events
            .iter()
            .filter(|event| event.operation == "print")
            .map(|event| event.sequence)
            .collect::<Vec<_>>()
    );
    let explained = explain_execution(run, program.source_bundle().unwrap()).unwrap();
    assert!(
        json!(explained)
            .to_string()
            .contains("Captured output matched")
    );
    assert!(source[event.span.start..event.span.end].starts_with("THEN prints"));
    let empty = rows[1].execution.events.last().unwrap();
    assert!(empty.inputs.is_empty());
    assert_eq!(empty.value["expected"], json!([]));
}

#[test]
fn missing_extra_reordered_and_changed_output_fail_without_erasing_it() {
    for expected in [
        r#"["first"]"#,
        r#"["first", 2, 3]"#,
        r#"[2, "first"]"#,
        r#"["first", "2"]"#,
        "[]",
    ] {
        let source = format!(
            "WHEN print \"first\"\nWHEN print 2\nTHEN prints {expected}\nWHEN print \"unreachable\"\n"
        );
        let run = program(&source).run_scenario("Main", ProgramLimits::default());
        assert!(!run.ok);
        assert_eq!(run.diagnostic.unwrap().code, "print_assertion_failed");
        assert_eq!(run.output, vec![json!("first"), json!(2)]);
        assert_eq!(run.events.last().unwrap().value["matched"], false);
    }
}

#[test]
fn assertions_observe_output_so_far_including_background_and_repeated_checks() {
    let source = "BACKGROUND\nWHEN print \"background\"\nSCENARIO first\nTHEN prints [\"background\"]\nWHEN print true\nTHEN prints [\"background\", true]\nAND prints [\"background\", true]\nSCENARIO second\nTHEN prints [\"background\"]\n";
    let rows = program(source).test_scenarios(ProgramLimits::default());
    assert!(rows.iter().all(|row| row.execution.ok));
    assert_eq!(rows[1].execution.output, vec![json!("background")]);
    let run = program("GIVEN prints is true\nTHEN prints == true\nAND prints []\n")
        .run_scenario("Main", ProgramLimits::default());
    assert!(run.ok);
}

#[test]
fn malformed_ambiguous_or_excessive_literals_fail_before_execution() {
    for (literal, code) in [
        ("[1,]".into(), "print_expectation"),
        ("[unknown]".into(), "print_expectation"),
        (r#"[{"a":1,"\u0061":2}]"#.into(), "print_expectation"),
        ("[0.1]".into(), "print_expectation_number"),
        ("[1e2]".into(), "print_expectation_number"),
        (format!("[{}]", "9".repeat(513)), "print_expectation_number"),
        (
            format!("{}0{}", "[".repeat(66), "]".repeat(66)),
            "print_expectation_limit",
        ),
        (
            format!("[{}]", vec!["0"; 16385].join(",")),
            "print_expectation_limit",
        ),
    ] {
        let error =
            compile_program(&format!("WHEN PASS\nTHEN prints {literal}\n"), "bad.gwt").unwrap_err();
        assert_eq!(error.code, code, "{}", &literal[..literal.len().min(40)]);
    }
    for source in [
        "WHEN action\n  THEN prints []\n",
        "REQUEST action\n  WHEN PASS\n  THEN prints []\n",
    ] {
        assert!(compile_program(source, "scope.gwt").is_err());
    }
    // Identical key names in different objects and punctuation inside strings are valid.
    program(
        r#"WHEN PASS
THEN prints [{"a":1},{"a":"}: [ \" #"}]
"#,
    );
}

#[test]
fn step_and_evidence_limits_cannot_claim_an_unrecorded_assertion() {
    let source = "WHEN print 7\nTHEN prints [7]\nWHEN print 8\n";
    let program = program(source);
    let complete = program.run_scenario("Main", ProgramLimits::default());
    let index = complete
        .events
        .iter()
        .position(|event| event.operation == "assert prints")
        .unwrap();
    let mut limits = ProgramLimits::default();
    limits.execution.evidence_bytes = complete.events[..index]
        .iter()
        .map(|event| serde_json::to_vec(event).unwrap().len())
        .sum();
    let limited = program.run_scenario("Main", limits);
    assert_eq!(limited.diagnostic.unwrap().code, "evidence_limit");
    assert_eq!(limited.events.len(), index);
    assert_eq!(limited.output, vec![json!(7)]);
    let before = compile_program("WHEN print 7\n", "before.gwt").unwrap();
    let steps = before.run_scenario("Main", ProgramLimits::default()).steps;
    let mut limits = ProgramLimits::default();
    limits.execution.steps = steps;
    let limited = program.run_scenario("Main", limits);
    assert_eq!(limited.diagnostic.unwrap().code, "execution_limit");
    assert_eq!(limited.output, vec![json!(7)]);
}

#[test]
fn generated_cases_preserve_json_output_even_without_declared_outputs() {
    let source = "RECORD Facts\n  amount: decimal\n  note: optional<text>\n  values: list<integer>\nREQUEST emit\n  GIVEN facts is Facts\n  WHEN describe facts\nWHEN describe <facts>\n  GIVEN facts is Facts\n  print facts\n  print facts.amount\n  print facts.note\n  print facts.values\n  print \"quote \\\" # café\"\n";
    let original = program(source);
    let case = capture_request(
        &original,
        "emit",
        &json!({"facts":{"amount":"0.10","values":[9007199254740993_u64]}}),
        ProgramLimits::default(),
    )
    .unwrap();
    let artifact = scenario_from_case(&case, "recorded receipt").unwrap();
    let generated = compile_bundle(artifact.source_bundle()).unwrap();
    let run = generated.run_scenario("recorded receipt", ProgramLimits::default());
    assert!(run.ok);
    assert_eq!(
        run.output,
        vec![
            json!({"amount":"0.1","note":null,"values":[9007199254740993_u64]}),
            json!("0.1"),
            Json::Null,
            json!([9007199254740993_u64]),
            json!("quote \" # café")
        ]
    );
    let scenario_case =
        capture_scenario(&generated, "recorded receipt", ProgramLimits::default()).unwrap();
    assert!(replay_case(&scenario_case).unwrap().verified);
    let mut candidate = artifact.source_bundle().clone();
    candidate.modules.insert(
        "rules.gwt".into(),
        source.replace("  print facts.amount\n", ""),
    );
    let compared = compare_case(&scenario_case, &compile_bundle(&candidate).unwrap()).unwrap();
    let run = compared.candidate.unwrap();
    assert_eq!(
        run.diagnostic.as_ref().unwrap().code,
        "print_assertion_failed"
    );
    explain_execution(&run, &candidate).unwrap();
}

#[test]
fn generation_also_locks_an_initially_empty_print_stream() {
    let source = "REQUEST quiet\n  WHEN PASS\n";
    let case = capture_request(
        &program(source),
        "quiet",
        &json!({}),
        ProgramLimits::default(),
    )
    .unwrap();
    let artifact = scenario_from_case(&case, "no incidental output").unwrap();
    let mut candidate = artifact.source_bundle().clone();
    candidate
        .modules
        .insert("rules.gwt".into(), source.replace("PASS", "print 1"));
    let run = compile_bundle(&candidate)
        .unwrap()
        .run_scenario(artifact.name(), ProgramLimits::default());
    assert_eq!(run.diagnostic.unwrap().code, "print_assertion_failed");
}

#[test]
fn example_rows_and_crlf_keep_original_assertion_sources() {
    let source = "SCENARIO messages\nWHEN print <message>\nTHEN prints [<message>]\nEXAMPLES\n  | message |\n  | \"first # café\" |\n  | \"second\" |\n".replace('\n',"\r\n");
    let program = program(&source);
    for row in program.test_scenarios(ProgramLimits::default()) {
        assert!(row.execution.ok);
        let event = row.execution.events.last().unwrap();
        assert_eq!(
            &source[event.span.start..event.span.end],
            "THEN prints [<message>]"
        );
        explain_execution(&row.execution, program.source_bundle().unwrap()).unwrap();
    }
}
