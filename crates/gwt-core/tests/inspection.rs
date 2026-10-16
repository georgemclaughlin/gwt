use gwt_core::{ProgramLimits, SourceBundle, Type, compile_bundle, compile_file, compile_program};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs,
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
};

#[test]
fn request_metadata_matches_the_host_boundary_and_excludes_local_initialization() {
    let source = include_str!("fixtures/invoice.gwt");
    let program = compile_program(source, "invoice.gwt").unwrap();
    let report = program.inspect();
    assert_eq!(report.program, Some("invoice pricing"));
    assert!(report.program_identity.is_none());
    let request = &report.requests[0];
    assert_eq!(request.name, "price invoice");
    assert_eq!(request.required_inputs, vec!["invoice"]);
    assert_eq!(request.inputs.len(), 1);
    assert_eq!(request.outputs.len(), 1);
    assert_eq!(request.outputs[0].name, "decision");
    assert_eq!(
        &source[request.outputs[0].span.start..request.outputs[0].span.end],
        "OUTPUT decision is InvoiceDecision"
    );
    let payload = report.to_json().unwrap();
    assert_eq!(
        payload["requests"][0]["inputs"][0]["type"],
        json!({"kind":"record","value":{"quantity":{"kind":"integer"},"unit_price":{"kind":"decimal"}}})
    );
    assert_eq!(
        payload["behaviors"][0]["signature"],
        "price <invoice> into <decision>"
    );
    assert_eq!(payload["scenarios"].as_array().unwrap().len(), 2);
    assert_eq!(payload["scenarios"][0]["declaredExpectations"], 2);
    let run = program.run_request(
        request.name,
        &json!({"invoice":{"unit_price":"0.1","quantity":3}}),
        ProgramLimits::default(),
    );
    assert!(run.ok);
    assert_eq!(
        run.result,
        Some(json!({"decision":{"status":"priced","total":"0.36"}}))
    );
}

#[test]
fn optional_inputs_and_declared_outputs_do_not_turn_into_refined_or_sample_types() {
    let source = "REQUEST echo\n  GIVEN note is optional<text>\n  WHEN print note\n  OUTPUT note is optional<text>\nWHEN choose <note>\n  GIVEN note is optional<text>\n  THEN returns text\n  IF note is absent\n    RETURN \"missing\"\n  RETURN note\n";
    let program = compile_program(source, "optional.gwt").unwrap();
    let report = program.inspect();
    assert!(report.requests[0].required_inputs.is_empty());
    assert_eq!(
        report.requests[0].inputs[0].ty,
        &Type::Optional(Box::new(Type::Text))
    );
    assert_eq!(
        report.requests[0].outputs[0].ty,
        report.requests[0].inputs[0].ty
    );
    assert_eq!(report.behaviors[0].returns, Some(&Type::Text));
    assert_eq!(
        report.behaviors[0].parameters[0].ty,
        report.requests[0].inputs[0].ty
    );
    let span = report.behaviors[0].return_span.unwrap();
    assert!(source[span.start..span.end].contains("returns text"));
    let result = program.run_request("echo", &json!({}), ProgramLimits::default());
    assert!(result.ok);
    assert_eq!(result.result, Some(json!({"note":null})));
}

#[test]
fn imported_aliases_kind_contracts_and_source_identity_are_resolved_without_running() {
    let mut bundle=SourceBundle {entry:"main.gwt".into(),modules:BTreeMap::from([
        ("types.gwt".into(),"# café 😀\r\nRECORD Contact is one of\r\n  email:\r\n    address: text\r\n  phone:\r\n    number: text\r\nTYPE Email is Contact of kind email\r\nTYPE Contacts is list<optional<Contact>>\r\nSCENARIO imported failure\r\nTHEN false\r\n".into()),
        ("main.gwt".into(),"USE \"types.gwt\"\nREQUEST deliver\n  GIVEN email is Email\n  GIVEN contacts is Contacts\n  WHEN print 1 / 0\n  OUTPUT email is Email\nSCENARIO entry failure\nTHEN false\n".into()),
    ])};
    let program = compile_bundle(&bundle).unwrap();
    let before = program.inspect().to_json().unwrap();
    assert_eq!(before["programIdentity"], json!(program.identity()));
    assert_eq!(
        before["programIdentity"]["modules"]
            .as_array()
            .unwrap()
            .len(),
        2
    );
    assert_eq!(before["scenarios"].as_array().unwrap().len(), 1);
    assert_eq!(before["scenarios"][0]["name"], "entry failure");
    let email = before["types"]
        .as_array()
        .unwrap()
        .iter()
        .find(|t| t["name"] == "Email")
        .unwrap();
    assert_eq!(
        email["type"],
        json!({"kind":"one_of","value":{"email":{"address":{"kind":"text"}}}})
    );
    assert_eq!(email["span"]["file"], "types.gwt");
    let start = email["span"]["start"].as_u64().unwrap() as usize;
    let end = email["span"]["end"].as_u64().unwrap() as usize;
    assert_eq!(
        &bundle.modules["types.gwt"][start..end],
        "TYPE Email is Contact of kind email"
    );
    bundle
        .modules
        .insert("types.gwt".into(), "invalid replacement".into());
    assert_eq!(program.inspect().to_json().unwrap(), before);
    assert!(
        !program.test_scenarios(ProgramLimits::default())[0]
            .execution
            .ok
    );
}

#[test]
fn example_rows_have_original_locations_and_declared_counts_without_test_results() {
    let source = "BACKGROUND\nTHEN true\nSCENARIO row\nTHEN <value> == 1\nEXAMPLES\n  | value |\n  | 1 |\n  | 2 |\n";
    let program = compile_program(source, "rows.gwt").unwrap();
    let report = program.inspect();
    assert_eq!(report.scenarios.len(), 2);
    for (i, scenario) in report.scenarios.iter().enumerate() {
        assert_eq!(scenario.example_row, Some(i + 1));
        assert_eq!(scenario.declared_expectations, 2);
        let span = scenario.example_span.unwrap();
        assert_eq!(&source[span.start..span.end], format!("| {} |", i + 1));
    }
    assert!(report.to_json().unwrap().get("execution").is_none());
    let runs = program.test_scenarios(ProgramLimits::default());
    assert!(runs[0].execution.ok);
    assert!(!runs[1].execution.ok);
}

#[test]
fn deep_contracts_are_complete_and_oversized_reports_fail_without_truncation() {
    let ty = format!("{}integer{}", "list<".repeat(60), ">".repeat(60));
    let source =
        format!("REQUEST echo\n  GIVEN values is {ty}\n  WHEN PASS\n  OUTPUT values is {ty}\n");
    let program = compile_program(&source, "deep.gwt").unwrap();
    let value = program.inspect().to_json().unwrap();
    let mut contract = &value["requests"][0]["inputs"][0]["type"];
    for _ in 0..60 {
        assert_eq!(contract["kind"], "list");
        contract = &contract["value"];
    }
    assert_eq!(contract["kind"], "integer");
    let mut source = "RECORD Wide\n".to_string();
    for i in 0..512 {
        source.push_str(&format!("  field_{i:04}: integer\n"));
    }
    for i in 0..300 {
        source.push_str(&format!(
            "REQUEST echo {i}\n  GIVEN value is Wide\n  WHEN PASS\n  OUTPUT value is Wide\n"
        ));
    }
    let program = compile_program(&source, "wide.gwt").unwrap();
    let error = program.inspect().to_json().unwrap_err();
    assert_eq!(error.code, "inspection_limit");
}

#[test]
fn cli_supports_import_root_and_preserves_source_while_refusing_invalid_programs() {
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let root = std::env::temp_dir().join(format!(
        "gwt-inspect-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir(&root).unwrap();
    let source = "USE \"types.gwt\"\nREQUEST echo\n  GIVEN value is Count\n  WHEN print value\n  OUTPUT value is Count\nSCENARIO fail\nTHEN false\n";
    fs::write(root.join("main.gwt"), source).unwrap();
    fs::write(root.join("types.gwt"), "TYPE Count is integer\n").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .args(["inspect"])
        .arg(root.join("main.gwt"))
        .arg("--import-root")
        .arg(&root)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let value: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(value["kind"], "gwt.native-inspection");
    assert_eq!(value["schemaVersion"], 1);
    assert_eq!(value["ok"], true);
    assert_eq!(fs::read_to_string(root.join("main.gwt")).unwrap(), source);
    assert_eq!(
        value,
        compile_file(&root.join("main.gwt"), Some(&root))
            .unwrap()
            .inspect()
            .to_json()
            .unwrap()
    );
    fs::write(root.join("types.gwt"), "TYPE Count is Missing\n").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .arg("inspect")
        .arg(root.join("main.gwt"))
        .output()
        .unwrap();
    assert!(!output.status.success());
    let error: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(error["phase"], "check");
    assert!(error.get("requests").is_none());
    let bad = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .args(["inspect", "ignored", "--request", "echo"])
        .output()
        .unwrap();
    assert!(!bad.status.success());
    fs::remove_dir_all(root).unwrap();
}
