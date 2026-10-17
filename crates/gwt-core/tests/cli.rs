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

#[test]
fn paired_options_reject_unknown_duplicate_and_unpaired_flags_before_loading_files() {
    let groups = [
        (
            "scenario-from-case",
            "--name",
            "unknown or duplicate scenario option",
        ),
        (
            "review",
            "--candidate",
            "unknown or duplicate review option",
        ),
        (
            "assess-review",
            "--decisions",
            "unknown or duplicate review option",
        ),
        (
            "migrate",
            "--previous-engine",
            "unknown or duplicate migration option",
        ),
        (
            "assess-migration",
            "--decision",
            "unknown or duplicate migration option",
        ),
        (
            "export-migration",
            "--output",
            "unknown or duplicate migration option",
        ),
        (
            "migrate-corpus",
            "--engines",
            "unknown or duplicate corpus migration option",
        ),
        (
            "assess-corpus-migration",
            "--decisions",
            "unknown or duplicate corpus migration option",
        ),
        (
            "export-corpus-migration",
            "--output",
            "unknown or duplicate corpus migration option",
        ),
        ("test-cases", "--candidate", "usage: gwt test-cases"),
    ];
    for (command, flag, error) in groups {
        for options in [
            vec![flag, "unused", "--unknown", "unused"],
            vec![flag, "unused", flag, "unused"],
        ] {
            let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
                .args([command, "missing-file.json"])
                .args(options)
                .output()
                .unwrap();
            assert!(!output.status.success(), "{command}");
            assert!(output.stdout.is_empty(), "{command}");
            assert!(
                String::from_utf8_lossy(&output.stderr).starts_with(error),
                "{command}"
            );
        }
        let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
            .args([command, "missing-file.json", flag])
            .output()
            .unwrap();
        assert!(!output.status.success(), "{command}");
        let message = String::from_utf8_lossy(&output.stderr);
        assert!(
            message.contains("usage:") || message.contains("paired options"),
            "{command}: {message}"
        );
    }
}
