use serde_json::Value;
use std::process::Command;

#[test]
fn native_command_emits_result_and_reports_check_failures() {
    let fixture = |name: &str| format!("{}/tests/fixtures/{name}", env!("CARGO_MANIFEST_DIR"));
    let run = |source: &str| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .args([
                "expression",
                source,
                &fixture("refund-types.json"),
                &fixture("refund-input.json"),
            ])
            .output()
            .unwrap()
    };
    let success = run("facts.days <= 30 or (facts.member and facts.days <= 45)");
    assert!(success.status.success());
    let payload: Value = serde_json::from_slice(&success.stdout).unwrap();
    assert_eq!(payload["kind"], "gwt.native-expression");
    assert_eq!(payload["result"], true);
    assert!(!payload["events"].as_array().unwrap().is_empty());
    let failure = run("facts.days and facts.member");
    assert!(!failure.status.success());
    let payload: Value = serde_json::from_slice(&failure.stdout).unwrap();
    assert_eq!(payload["phase"], "check");
    assert_eq!(payload["diagnostic"]["code"], "type_mismatch");
}

#[test]
fn native_program_commands_check_test_and_run_source_files() {
    let fixture = |name: &str| format!("{}/tests/fixtures/{name}", env!("CARGO_MANIFEST_DIR"));
    for command in ["check", "test"] {
        let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
            .args([command, &fixture("invoice.gwt")])
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stdout)
        );
        let payload: Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(payload["ok"], true);
        if command == "test" {
            assert_eq!(payload["scenarioCount"], 2);
        }
    }
    let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .args([
            "run",
            &fixture("invoice.gwt"),
            "--request",
            "price invoice",
            "--input",
            &fixture("invoice-input.json"),
        ])
        .output()
        .unwrap();
    assert!(output.status.success());
    let payload: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["result"]["decision"]["total"], "47.88");
    let failed = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .args([
            "run",
            &fixture("invoice.gwt"),
            "--request",
            "unknown",
            "--input",
            &fixture("invoice-input.json"),
        ])
        .output()
        .unwrap();
    assert!(!failed.status.success());
    let payload: Value = serde_json::from_slice(&failed.stdout).unwrap();
    assert_eq!(payload["diagnostic"]["code"], "unknown_request");
}
