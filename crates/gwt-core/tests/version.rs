use gwt_core::{SourceBundle, capture_scenario, compile_bundle, version_info};
use serde_json::{Value, json};
use std::process::{Command, Stdio};

#[test]
fn executable_and_library_identity_match_the_engine_that_captures_cases() {
    let expected = serde_json::to_value(version_info()).unwrap();
    assert_eq!(expected["kind"], "gwt.native-version");
    assert_eq!(expected["schemaVersion"], 1);
    assert_eq!(expected["packageName"], "gwt-core");
    assert_eq!(expected["packageVersion"], env!("CARGO_PKG_VERSION"));
    assert_eq!(expected["languageProfile"], "gwt-native-experimental");
    assert_eq!(expected["languageVersion"], Value::Null);
    assert_eq!(expected["status"], "experimental");
    let program = compile_bundle(&SourceBundle {
        entry: "identity.gwt".into(),
        modules: [(
            "identity.gwt".into(),
            "GIVEN answer is 42\nTHEN answer == 42\n".into(),
        )]
        .into(),
    })
    .unwrap();
    let case = capture_scenario(&program, "Main", Default::default()).unwrap();
    assert_eq!(expected["engine"], json!(case.engine()));

    for args in [
        vec!["version"],
        vec!["version", "--json"],
        vec!["--version"],
        vec!["-V"],
    ] {
        // No source checkout, environment configuration, or stdin is needed.
        let output = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
            .args(args)
            .current_dir(std::env::temp_dir())
            .env_clear()
            .stdin(Stdio::null())
            .output()
            .unwrap();
        assert!(output.status.success(), "{:?}", output);
        assert!(output.stderr.is_empty());
        assert_eq!(
            serde_json::from_slice::<Value>(&output.stdout).unwrap(),
            expected
        );
    }
}

#[test]
fn version_refuses_extra_arguments_instead_of_reading_source_or_stdin() {
    for args in [
        vec!["version", "missing.gwt"],
        vec!["version", "--json", "--json"],
        vec!["--version", "--json"],
        vec!["-V", "--request", "anything"],
    ] {
        let output = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
            .args(args)
            .stdin(Stdio::null())
            .output()
            .unwrap();
        assert!(!output.status.success());
        assert!(output.stdout.is_empty());
        assert!(
            String::from_utf8(output.stderr)
                .unwrap()
                .contains("usage: gwt-native version")
        );
    }
}
