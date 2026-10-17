use gwt_core::{ProgramLimits, compile_program, format_source};
use serde_json::json;
use std::{
    fs,
    io::Write,
    process::{Command, Stdio},
    sync::atomic::{AtomicUsize, Ordering},
};

#[test]
fn canonical_layout_preserves_quoted_table_delimiters_comments_and_values() {
    let source = "\n\n#café\nSCENARIO   rows\n\n\nGIVEN  message is <message>  #value\nWHEN  print  message\nTHEN  prints [<message>]\nEXAMPLES\n  |message|\n  |\"a | #\"|\n  #row comment\n  |\"😀\"|\n\n";
    let expected = "# café\nSCENARIO rows\n\nGIVEN message is <message>  # value\nWHEN print message\nTHEN prints [<message>]\nEXAMPLES\n  | message |\n  | \"a | #\" |\n  # row comment\n  | \"😀\"     |\n";
    let formatted = format_source(source, "rules.gwt").unwrap();
    assert_eq!(formatted.text, expected);
    assert!(formatted.changed);
    assert!(!format_source(&formatted.text, "rules.gwt").unwrap().changed);
    let runs = compile_program(&formatted.text, "rules.gwt")
        .unwrap()
        .test_scenarios(ProgramLimits::default());
    assert_eq!(runs.len(), 2);
    assert!(runs.iter().all(|run| run.execution.ok));
    assert_eq!(runs[0].execution.output, vec![json!("a | #")]);
    assert_eq!(runs[1].execution.output, vec![json!("😀")]);
}

#[test]
fn exact_literals_grouped_arguments_and_failure_order_survive() {
    let source = "WHEN bump <amount>\n  GIVEN amount is integer\n  add  1 to amount\nSCENARIO exact\nGIVEN  amount is 9007199254740993\nGIVEN fraction is 0.1000000000000000000000\nWHEN bump (amount)\nWHEN  print  amount\nTHEN  prints [9007199254740993]\nWHEN print fraction / 0\nTHEN  fails with \"division_by_zero\"\nAND amount == 9007199254740993\n";
    let formatted = format_source(source, "rules.gwt").unwrap();
    assert!(formatted.text.contains("bump (amount)"));
    assert!(formatted.text.contains("0.1000000000000000000000"));
    assert!(
        formatted
            .text
            .contains("WHEN print fraction / 0\nTHEN fails with")
    );
    for candidate in [source, &formatted.text] {
        let run = compile_program(candidate, "rules.gwt")
            .unwrap()
            .test_scenarios(ProgramLimits::default())
            .remove(0)
            .execution;
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(run.state["amount"], json!(9007199254740993_u64));
        assert_eq!(run.state["fraction"], "0.1");
        assert_eq!(run.output, vec![json!(9007199254740993_u64)]);
    }
}

#[test]
fn layout_formatting_does_not_load_imports_or_resolve_request_dtos() {
    let imported_scenario = "USE  \"unavailable.gwt\"\nSCENARIO  local\nTHEN true\n";
    assert_eq!(
        format_source(imported_scenario, "main.gwt").unwrap().text,
        "USE \"unavailable.gwt\"\nSCENARIO local\nTHEN true\n"
    );
    let source = "USE \"unavailable.gwt\"\nGIVEN  request is ExternalDto\n  WHEN :  \"# | (literal)\"\n  values:   [1, 2]\n";
    let formatted = format_source(source, "request.gwt").unwrap();
    assert_eq!(
        formatted.text,
        "USE \"unavailable.gwt\"\nGIVEN request is ExternalDto\n  WHEN: \"# | (literal)\"\n  values: [1, 2]\n"
    );
    assert!(compile_program(&formatted.text, "request.gwt").is_err());
    // Expressions are intentionally not type-checked or repaired by formatting.
    let invalid = format_source("THEN  unknown +\n", "unfinished.gwt").unwrap();
    assert_eq!(invalid.text, "THEN unknown +\n");
    assert!(compile_program(&invalid.text, "unfinished.gwt").is_err());
}

#[test]
fn newline_style_and_original_error_offsets_are_preserved() {
    let source = "# 😀\r\nSCENARIO  kept\r\nTHEN  true\r\n";
    let result = format_source(source, "rules.gwt").unwrap();
    assert_eq!(result.text, "# 😀\r\nSCENARIO kept\r\nTHEN true\r\n");
    assert!(!format_source(&result.text, "rules.gwt").unwrap().changed);
    let broken = "# 😀\r\nSCENARIO bad\r\n THEN true\r\n";
    let error = format_source(broken, "rules.gwt").unwrap_err();
    assert_eq!(error.code, "indentation");
    assert_eq!(error.span.start, broken.find("THEN").unwrap());
    assert_eq!(error.span.line, 3);
    assert_eq!(
        format_source("THEN true\rTHEN true", "bad.gwt")
            .unwrap_err()
            .code,
        "format_newline"
    );
    assert_eq!(
        format_source("# x\r\nTHEN  true\n", "mixed.gwt")
            .unwrap()
            .text,
        "# x\nTHEN true\n"
    );
    assert_eq!(format_source("\n\n", "empty.gwt").unwrap().text, "");
    assert_eq!(
        format_source(" #odd comment\n", "comments.gwt")
            .unwrap()
            .text,
        " # odd comment\n"
    );
}

#[test]
fn malformed_layout_delimiters_tables_and_expanding_output_are_refused() {
    for source in [
        "  THEN true\n",
        "WHEN act\n    PASS\n",
        "THEN \"unfinished\n",
        "THEN (true]\n",
        "EXAMPLES\n  | a |\n  | 1 |\n",
        "SCENARIO bad\nTHEN true\nEXAMPLES\n  | a | b |\n  | 1 |\n",
    ] {
        assert!(format_source(source, "bad.gwt").is_err(), "{source}");
    }
    assert!(format_source(&"#".repeat(1_048_577), "large.gwt").is_err());
    assert!(format_source(&"\n".repeat(16385), "lines.gwt").is_err());
    let columns = format!("|{}|\n", vec!["x"; 257].join("|"));
    assert_eq!(
        format_source(&columns, "wide.gwt").unwrap_err().code,
        "format_limit"
    );
    let mut expanding = format!(
        "SCENARIO wide\nTHEN true\nEXAMPLES\n  | value |\n  | \"{}\" |\n",
        "x".repeat(2000)
    );
    for _ in 0..600 {
        expanding.push_str("  | \"\" |\n");
    }
    assert!(expanding.len() < 10_000);
    assert_eq!(
        format_source(&expanding, "wide.gwt").unwrap_err().code,
        "format_limit"
    );
}

#[test]
fn native_example_shapes_remain_idempotent_and_execute_the_same_outcomes() {
    for source in [
        include_str!("../../../examples/native_delivery/rules.gwt"),
        include_str!("../../../examples/native_return_values/rules.gwt"),
        include_str!("../../../examples/native_value_arguments/rules.gwt"),
        include_str!("../../../examples/native_print_expectations/rules.gwt"),
        include_str!("../../../examples/native_expected_failures/rules.gwt"),
    ] {
        let formatted = format_source(source, "rules.gwt").unwrap();
        assert!(!format_source(&formatted.text, "rules.gwt").unwrap().changed);
        let before = compile_program(source, "rules.gwt")
            .unwrap()
            .test_scenarios(ProgramLimits::default());
        let after = compile_program(&formatted.text, "rules.gwt")
            .unwrap()
            .test_scenarios(ProgramLimits::default());
        assert_eq!(before.len(), after.len());
        assert!(!before.is_empty());
        for (old, new) in before.iter().zip(&after) {
            assert_eq!(old.name, new.name);
            assert!(old.execution.ok && new.execution.ok);
            assert_eq!(old.execution.state, new.execution.state);
            assert_eq!(old.execution.output, new.execution.output);
            assert_eq!(
                old.execution
                    .events
                    .iter()
                    .map(|event| &event.operation)
                    .collect::<Vec<_>>(),
                new.execution
                    .events
                    .iter()
                    .map(|event| &event.operation)
                    .collect::<Vec<_>>()
            );
        }
    }
}

static NEXT: AtomicUsize = AtomicUsize::new(0);
#[test]
fn cli_preview_check_write_and_snapshot_modes_have_explicit_effects() {
    let root = std::env::temp_dir().join(format!(
        "gwt-format-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir(&root).unwrap();
    let path = root.join("rules.gwt");
    fs::write(&path, "THEN  true  #yes\n").unwrap();
    let invoke = |mode: Option<&str>| {
        let mut command = Command::new(env!("CARGO_BIN_EXE_gwt"));
        command.arg("format").arg(&path);
        if let Some(mode) = mode {
            command.arg(mode);
        }
        command.output().unwrap()
    };
    assert!(invoke(None).status.success());
    assert_eq!(fs::read_to_string(&path).unwrap(), "THEN  true  #yes\n");
    assert!(!invoke(Some("--check")).status.success());
    assert!(invoke(Some("--write")).status.success());
    assert_eq!(fs::read_to_string(&path).unwrap(), "THEN true  # yes\n");
    assert!(invoke(Some("--check")).status.success());
    fs::write(&path, " THEN true\n").unwrap();
    assert!(!invoke(Some("--write")).status.success());
    assert_eq!(fs::read_to_string(&path).unwrap(), " THEN true\n");
    assert_eq!(fs::read_dir(&root).unwrap().count(), 1);
    let mut child = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("format-editor")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(
            json!({"file":"unsaved.gwt","text":"WHEN  print  9007199254740993\n"})
                .to_string()
                .as_bytes(),
        )
        .unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["kind"], "gwt.native-format");
    assert_eq!(report["text"], "WHEN print 9007199254740993\n");
    assert!(
        report["sourceDigest"]
            .as_str()
            .unwrap()
            .starts_with("sha256:")
    );
    fs::remove_dir_all(root).unwrap();
}

#[test]
#[cfg(unix)]
fn file_formatting_refuses_symlinks_and_read_only_files_and_preserves_permissions() {
    use std::os::unix::fs::{PermissionsExt, symlink};
    let root = std::env::temp_dir().join(format!(
        "gwt-format-permissions-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir(&root).unwrap();
    let path = root.join("rules.gwt");
    let link = root.join("link.gwt");
    fs::write(&path, "THEN  true\n").unwrap();
    symlink(&path, &link).unwrap();
    let write = |path: &std::path::Path| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .arg("format")
            .arg(path)
            .arg("--write")
            .output()
            .unwrap()
    };
    assert!(!write(&link).status.success());
    fs::set_permissions(&path, fs::Permissions::from_mode(0o444)).unwrap();
    assert!(!write(&path).status.success());
    assert_eq!(fs::read_to_string(&path).unwrap(), "THEN  true\n");
    fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
    assert!(write(&path).status.success());
    assert_eq!(
        fs::metadata(&path).unwrap().permissions().mode() & 0o777,
        0o640
    );
    assert_eq!(fs::read_to_string(&path).unwrap(), "THEN true\n");
    assert_eq!(fs::read_dir(&root).unwrap().count(), 2);
    fs::remove_dir_all(root).unwrap();
}
