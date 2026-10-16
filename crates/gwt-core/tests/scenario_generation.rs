use gwt_core::{
    ExecutionCase, ProgramLimits, SourceBundle, capture_request, compile_bundle, scenario_from_case,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

fn capture(source: &str, request: &str, input: Json) -> ExecutionCase {
    let program = compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap();
    capture_request(&program, request, &input, ProgramLimits::default()).unwrap()
}
fn generated_state(case: &ExecutionCase) -> Json {
    let generated = scenario_from_case(case, "saved decision").unwrap();
    let program = compile_bundle(generated.source_bundle()).unwrap();
    let rows = program.test_scenarios(ProgramLimits::default());
    assert_eq!(rows.len(), 1);
    assert!(rows[0].execution.ok);
    rows.into_iter().next().unwrap().execution.state
}

#[test]
fn generated_delivery_scenario_preserves_snapshot_and_detects_a_regression() {
    let source = include_str!("../../../examples/native_delivery/rules.gwt");
    let case = capture(
        source,
        "quote delivery",
        json!({"parcel":{"weight_grams":1001,"member":false}}),
    );
    let generated = scenario_from_case(&case, "nonmember medium parcel").unwrap();
    assert_eq!(generated.name(), "nonmember medium parcel");
    assert_eq!(generated.source_bundle().modules["rules.gwt"], source);
    let text = &generated.source_bundle().modules[&generated.source_bundle().entry];
    assert!(text.contains("GIVEN parcel is Parcel"));
    assert!(text.contains("THEN quote == expected_quote_"));
    let metadata = json!(generated);
    assert_eq!(
        metadata["expectationBasis"],
        "verified_observation_not_approval"
    );
    assert_eq!(metadata["schemaVersion"], 3);
    assert_eq!(
        metadata["assertionScope"],
        "declared_outputs_and_printed_sequence"
    );
    assert_eq!(metadata["caseIntegrity"], case.integrity());
    assert_eq!(
        generated_state(&case)["quote"],
        json!({"fee":9,"status":"standard"})
    );
    let mut changed = generated.source_bundle().clone();
    changed
        .modules
        .get_mut("rules.gwt")
        .unwrap()
        .push_str("\n# moved source, same behavior\n");
    assert!(
        compile_bundle(&changed)
            .unwrap()
            .test_scenarios(ProgramLimits::default())[0]
            .execution
            .ok
    );
    changed.modules.insert(
        "rules.gwt".into(),
        source.replace("set quote.fee to 9", "set quote.fee to 8"),
    );
    let run = compile_bundle(&changed)
        .unwrap()
        .test_scenarios(ProgramLimits::default());
    assert_eq!(
        run[0].execution.diagnostic.as_ref().unwrap().code,
        "assertion_failed"
    );
}

#[test]
fn generated_inventory_scenario_uses_preexecution_inputs_and_checks_mutated_outputs() {
    let case = capture(
        include_str!("../../../examples/native_reservation/rules.gwt"),
        "reserve order",
        json!({"order":{"lines":[{"sku":"widget","quantity":3}]},"inventory":{"items":[{"sku":"widget","available":5}]}}),
    );
    let state = generated_state(&case);
    assert_eq!(
        state["inventory"],
        json!({"items":[{"sku":"widget","available":2}]})
    );
    assert_eq!(
        state["decision"],
        json!({"line_count":1,"requested":3,"reserved":3,"remaining":2,"missing":[],"shortages":[]})
    );
    assert_eq!(case.input()["inventory"]["items"][0]["available"], 5);
}

#[test]
fn typed_values_preserve_optional_union_decimal_and_empty_list_contracts() {
    for (ty, value, expected) in [
        ("decimal", json!(5), json!("5")),
        (
            "integer",
            json!(9007199254740993_u64),
            json!(9007199254740993_u64),
        ),
        (
            "text",
            json!("\"quoted\" # | café\n<value>"),
            json!("\"quoted\" # | café\n<value>"),
        ),
        ("optional<text>", Json::Null, Json::Null),
        ("optional<text>", json!("present"), json!("present")),
        ("list<integer>", json!([]), json!([])),
        (
            "list<optional<decimal>>",
            json!([null, "0.10", 2]),
            json!([null, "0.1", "2"]),
        ),
        ("\"open\" | \"closed\"", json!("open"), json!("open")),
    ] {
        let source = format!(
            "TYPE Contract is {ty}\nREQUEST echo\n  GIVEN value is Contract\n  WHEN retain value\n  OUTPUT value is Contract\nWHEN retain <value>\n  GIVEN value is Contract\n  PASS\n"
        );
        let case = capture(&source, "echo", json!({"value":value}));
        assert_eq!(generated_state(&case)["value"], expected, "{ty}");
    }
    let source = "RECORD Detail\n  note: optional<text>\nRECORD Facts\n  detail: Detail\n  maybe: optional<Detail>\n  list: list<optional<Detail>>\nREQUEST echo\n  GIVEN value is Facts\n  WHEN retain value\n  OUTPUT value is Facts\nWHEN retain <value>\n  GIVEN value is Facts\n  PASS\n";
    let case = capture(
        source,
        "echo",
        json!({"value":{"detail":{},"maybe":{},"list":[null,{}, {"note":"yes"}]}}),
    );
    assert_eq!(
        generated_state(&case)["value"],
        json!({"detail":{"note":null},"maybe":{"note":null},"list":[null,{"note":null},{"note":"yes"}]})
    );
}

#[test]
fn generation_preserves_supported_failure_printed_and_empty_output() {
    let failed = capture(
        include_str!("../../../examples/native_delivery/rules.gwt"),
        "quote delivery",
        json!({"parcel":{"weight_grams":0,"member":false}}),
    );
    let generated = scenario_from_case(&failed, "bad").unwrap();
    let text = &generated.source_bundle().modules[&generated.source_bundle().entry];
    assert!(text.contains("THEN fails with \"assertion_failed\""));
    let source = "REQUEST echo\n  GIVEN value is integer\n  WHEN retain value\n  OUTPUT value is integer\nWHEN retain <value>\n  GIVEN value is integer\n  print value\n";
    let printed = capture(source, "echo", json!({"value":1}));
    let generated = scenario_from_case(&printed, "print").unwrap();
    let text = &generated.source_bundle().modules[&generated.source_bundle().entry];
    assert!(text.contains("THEN prints [1]"));
    let empty = capture(
        &source
            .replace("  OUTPUT value is integer\n", "")
            .replace("  print value", "  PASS"),
        "echo",
        json!({"value":1}),
    );
    let generated = scenario_from_case(&empty, "empty").unwrap();
    let text = &generated.source_bundle().modules[&generated.source_bundle().entry];
    assert!(text.contains("THEN prints []"));
    for name in ["", " whitespace", "two\nlines", "inline # comment"] {
        assert_eq!(
            scenario_from_case(&empty, name).unwrap_err().code,
            "scenario_name"
        );
    }
}

fn resign(mut value: Json) -> String {
    use sha2::{Digest, Sha256};
    value.as_object_mut().unwrap().remove("integrity");
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-case-sha256-v1\0");
    hash.update(serde_json::to_vec(&value).unwrap());
    value["integrity"] = json!(format!("sha256:{:x}", hash.finalize()));
    value.to_string()
}

#[test]
fn forged_observations_and_incompatible_engines_cannot_become_expectations() {
    let case = capture(
        include_str!("fixtures/invoice.gwt"),
        "price invoice",
        json!({"invoice":{"unit_price":"19.95","quantity":2}}),
    );
    let mut forged = json!(case);
    forged["record"]["observed"]["result"]["decision"]["total"] = json!("999");
    let forged = ExecutionCase::from_json(&resign(forged)).unwrap();
    assert_eq!(
        scenario_from_case(&forged, "forged").unwrap_err().code,
        "scenario_baseline_mismatch"
    );
    let mut incompatible = json!(case);
    incompatible["record"]["engine"]["profile"] = json!("different-engine");
    let incompatible = ExecutionCase::from_json(&resign(incompatible)).unwrap();
    assert_eq!(
        scenario_from_case(&incompatible, "old engine")
            .unwrap_err()
            .code,
        "case_engine"
    );
}

#[test]
fn generated_names_and_entry_paths_do_not_collide_with_frozen_modules() {
    let source = "RECORD CapturedRecord1\n  other: integer\nTYPE Contract is list<integer>\nREQUEST echo\n  GIVEN captured_holder_1 is Contract\n  WHEN retain captured_holder_1\n  OUTPUT captured_holder_1 is Contract\nWHEN retain <value>\n  GIVEN value is Contract\n  PASS\n";
    let program = compile_bundle(&SourceBundle {
        entry: "captured_scenario_1.gwt".into(),
        modules: BTreeMap::from([("captured_scenario_1.gwt".into(), source.into())]),
    })
    .unwrap();
    let case = capture_request(
        &program,
        "echo",
        &json!({"captured_holder_1":[]}),
        ProgramLimits::default(),
    )
    .unwrap();
    let generated = scenario_from_case(&case, "collision test").unwrap();
    assert_ne!(generated.source_bundle().entry, "captured_scenario_1.gwt");
    assert_eq!(generated_state(&case)["captured_holder_1"], json!([]));
}

#[test]
fn all_refund_scenarios_detect_exactly_the_independently_expected_revision_changes() {
    let root =
        std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../evaluations/maintenance");
    let manifest: Json =
        serde_json::from_str(&std::fs::read_to_string(root.join("manifest.json")).unwrap())
            .unwrap();
    let mut checked = 0;
    for task in manifest["cases"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| task["kind"] == "maintain")
    {
        let starter =
            std::fs::read_to_string(root.join(task["starter"]["gwt"].as_str().unwrap())).unwrap();
        let candidate =
            std::fs::read_to_string(root.join(task["gold"]["gwt"].as_str().unwrap())).unwrap();
        for probe in task["probes"].as_array().unwrap() {
            let case = capture(
                &starter,
                task["request"].as_str().unwrap(),
                probe["input"].clone(),
            );
            let generated = scenario_from_case(&case, "refund observation").unwrap();
            let mut revised = generated.source_bundle().clone();
            revised
                .modules
                .insert("rules.gwt".into(), candidate.clone());
            let rows = compile_bundle(&revised)
                .unwrap()
                .test_scenarios(ProgramLimits::default());
            assert_eq!(rows[0].execution.ok, probe["kind"] != "changed");
            assert_eq!(
                rows[0].execution.state["decision"],
                probe["expected"]["decision"]
            );
            checked += 1;
        }
    }
    assert_eq!(checked, 336);
}

#[test]
fn cli_exports_a_frozen_runnable_bundle_and_refuses_existing_destinations() {
    use std::{fs, process::Command};
    let root = std::env::temp_dir().join(format!("gwt-generated-scenario-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let case = capture(
        include_str!("fixtures/invoice.gwt"),
        "price invoice",
        json!({"invoice":{"unit_price":"19.95","quantity":2}}),
    );
    let case_path = root.join("case.json");
    fs::write(&case_path, case.to_json()).unwrap();
    let destination = root.join("generated");
    let output = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .arg("scenario-from-case")
        .arg(&case_path)
        .arg("--output")
        .arg(&destination)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{} {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let payload: Json = serde_json::from_slice(&output.stdout).unwrap();
    let entry = destination.join(payload["source"]["entry"].as_str().unwrap());
    let result = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .arg("test")
        .arg(entry)
        .arg("--import-root")
        .arg(&destination)
        .output()
        .unwrap();
    assert!(result.status.success());
    let again = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .arg("scenario-from-case")
        .arg(&case_path)
        .arg("--output")
        .arg(&destination)
        .output()
        .unwrap();
    assert!(!again.status.success());
    assert_eq!(
        fs::read_to_string(destination.join("rules.gwt")).unwrap(),
        case.source().modules["rules.gwt"]
    );
    let bad = capture(
        include_str!("fixtures/invoice.gwt"),
        "price invoice",
        json!({"invoice":{"unit_price":"19.95","quantity":0}}),
    );
    fs::write(&case_path, bad.to_json()).unwrap();
    let expected_failure = root.join("expected-failure");
    let result = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .arg("scenario-from-case")
        .arg(&case_path)
        .arg("--output")
        .arg(&expected_failure)
        .output()
        .unwrap();
    assert!(result.status.success());
    let generated: Json = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(generated["capturedFailure"]["code"], "assertion_failed");
    let result = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .arg("test")
        .arg(expected_failure.join(generated["source"]["entry"].as_str().unwrap()))
        .arg("--import-root")
        .arg(&expected_failure)
        .output()
        .unwrap();
    assert!(result.status.success());
    let unsupported = capture(
        include_str!("fixtures/invoice.gwt"),
        "price invoice",
        json!({}),
    );
    fs::write(&case_path, unsupported.to_json()).unwrap();
    let rejected = root.join("rejected");
    let result = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .arg("scenario-from-case")
        .arg(&case_path)
        .arg("--output")
        .arg(&rejected)
        .output()
        .unwrap();
    assert!(!result.status.success());
    assert!(!rejected.exists());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn output_only_requests_generate_tests_and_source_limits_fail_explicitly() {
    let source = "RECORD Answer\n  value: integer\nREQUEST answer\n  GIVEN answer is Answer\n    value: 42\n  WHEN retain answer\n  OUTPUT answer is Answer\nWHEN retain <answer>\n  GIVEN answer is Answer\n  PASS\n";
    let case = capture(source, "answer", json!({}));
    assert_eq!(generated_state(&case)["answer"]["value"], 42);
    // A short source can accept a large text value; source generation has its own bound.
    let source = "REQUEST echo\n  GIVEN value is text\n  WHEN retain value\n  OUTPUT value is text\nWHEN retain <value>\n  GIVEN value is text\n  PASS\n";
    // The verified value fits input/evidence limits, but duplicating it as source
    // input and expectation exceeds the generated-module limit.
    let case = capture(source, "echo", json!({"value":"x".repeat(600000)}));
    assert_eq!(
        scenario_from_case(&case, "large").unwrap_err().code,
        "scenario_generation_limit"
    );
    assert_eq!(
        scenario_from_case(&case, &"n".repeat(257))
            .unwrap_err()
            .code,
        "scenario_name"
    );
}

#[test]
fn transitive_imports_keep_original_bytes_and_generated_assertions_have_real_source_spans() {
    let bundle = SourceBundle {
        entry: "domain/entry.gwt".into(),
        modules: BTreeMap::from([
            ("domain/entry.gwt".into(), "USE \"types.gwt\"\nUSE \"behavior.gwt\"\nREQUEST bump\n  GIVEN counter is Counter\n  WHEN bump counter\n  OUTPUT counter is Counter\n".into()),
            ("domain/types.gwt".into(), "RECORD Counter\n  value: integer\n".into()),
            ("domain/behavior.gwt".into(), "USE \"types.gwt\"\nWHEN bump <counter>\n  GIVEN counter is Counter\n  add 1 to counter.value\n".into()),
        ]),
    };
    let program = compile_bundle(&bundle).unwrap();
    let case = capture_request(
        &program,
        "bump",
        &json!({"counter":{"value":4}}),
        ProgramLimits::default(),
    )
    .unwrap();
    let generated = scenario_from_case(&case, "frozen dependency").unwrap();
    for (path, content) in &bundle.modules {
        assert_eq!(&generated.source_bundle().modules[path], content);
    }
    let compiled = compile_bundle(generated.source_bundle()).unwrap();
    let rows = compiled.test_scenarios(ProgramLimits::default());
    assert_eq!(rows[0].execution.state["counter"]["value"], 5);
    let explanation =
        gwt_core::explain_execution(&rows[0].execution, generated.source_bundle()).unwrap();
    assert!(
        explanation
            .steps
            .iter()
            .any(|step| step.operation == "assert"
                && step.source.span.file == generated.source_bundle().entry)
    );
    assert!(
        explanation
            .steps
            .iter()
            .any(|step| step.operation == "add" && step.source.span.file == "domain/behavior.gwt")
    );
}
