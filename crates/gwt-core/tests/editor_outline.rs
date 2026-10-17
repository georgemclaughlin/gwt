use gwt_core::outline_source;
use serde_json::{Value, json};
use std::{
    io::Write,
    process::{Command, Stdio},
};

#[test]
fn outlines_declarations_fields_and_flat_scenario_sections_with_exact_ranges() {
    let source = "# 😀\r\nPROGRAM café\r\nRECORD Facts\r\n  amount: integer # comment\r\n  WHEN: text\r\nTYPE Status is \"yes\" | \"no\"\r\nWHEN review <facts> into <decision>\r\n  GIVEN facts is Facts\r\n  AND decision is Status\r\n  set decision to \"yes\"\r\nREQUEST review\r\n  GIVEN facts is Facts\r\n  WHEN print facts\r\nBACKGROUND\r\nGIVEN amount is 1\r\nSCENARIO café # comment\r\nWHEN print amount\r\nTHEN prints [1]\r\nEXAMPLES\r\n  | name |\r\n  | \"😀\" |\r\nSCENARIO second\r\nTHEN true\r\n";
    let symbols = outline_source(source, "unsaved.gwt").unwrap();
    let names: Vec<_> = symbols.iter().map(|s| (s.name.as_str(), s.kind)).collect();
    assert_eq!(
        names,
        vec![
            ("café", "program"),
            ("Facts", "record"),
            ("Status", "type"),
            ("review <facts> into <decision>", "behavior"),
            ("review", "request"),
            ("BACKGROUND", "background"),
            ("café", "scenario"),
            ("second", "scenario")
        ]
    );
    assert_eq!(
        symbols[1]
            .children
            .iter()
            .map(|s| s.name.as_str())
            .collect::<Vec<_>>(),
        vec!["amount", "WHEN"]
    );
    assert_eq!(symbols[6].children[0].kind, "examples");
    assert_eq!(
        &source[symbols[6].range.start..symbols[6].range.end],
        "SCENARIO café # comment\r\nWHEN print amount\r\nTHEN prints [1]\r\nEXAMPLES\r\n  | name |\r\n  | \"😀\" |"
    );
    fn verify(source: &str, symbols: &[gwt_core::OutlineSymbol]) {
        for symbol in symbols {
            assert_eq!(
                &source[symbol.selection_range.start..symbol.selection_range.end],
                symbol.name
            );
            assert!(
                symbol.range.start <= symbol.selection_range.start
                    && symbol.range.end >= symbol.selection_range.end
            );
            for child in &symbol.children {
                assert!(
                    child.range.start >= symbol.range.start && child.range.end <= symbol.range.end
                );
            }
            verify(source, &symbol.children);
        }
        for pair in symbols.windows(2) {
            assert!(pair[0].range.end <= pair[1].range.start);
        }
    }
    verify(source, &symbols);
}

#[test]
fn declarations_between_scenario_steps_do_not_create_overlapping_ranges() {
    let source = "SCENARIO first\nTHEN true\nTYPE Count is integer\nWHEN print 1\nREQUEST existing\nSCENARIO second\nTHEN true\n";
    let symbols = outline_source(source, "test.gwt").unwrap();
    assert_eq!(symbols.len(), 3);
    assert_eq!(
        &source[symbols[0].range.start..symbols[0].range.end],
        "SCENARIO first\nTHEN true"
    );
    assert_eq!(symbols[1].name, "Count");
    assert_eq!(symbols[2].name, "second");
}

#[test]
fn local_outline_survives_missing_imports_type_and_expression_errors_without_execution() {
    let source = "USE \"/unavailable.gwt\"\nRECORD Facts\n  value: Unknown\nWHEN broken <value>\n  GIVEN value is Unknown\n  print (\nSCENARIO unresolved\nWHEN broken missing\nTHEN false\n";
    let symbols = outline_source(source, "untitled:1").unwrap();
    assert_eq!(symbols.len(), 3);
    assert_eq!(symbols[0].children[0].name, "value");
    assert_eq!(symbols[1].kind, "behavior");
    assert_eq!(symbols[2].name, "unresolved");
    assert!(
        outline_source("# only a comment\n\n", "empty")
            .unwrap()
            .is_empty()
    );
    assert!(outline_source("", "empty").unwrap().is_empty());
    // A quoted keyword or a step call cannot become a declaration.
    assert!(
        outline_source(
            "WHEN print \"RECORD Fake # literal\"\nREQUEST run\n",
            "steps"
        )
        .unwrap()
        .is_empty()
    );
}

#[test]
fn layout_and_resource_errors_return_no_guessed_structure() {
    for source in [
        "RECORD Facts\n field: integer\n",
        "SCENARIO x\n\tTHEN true\n",
        "RECORD Facts\n    field: integer\n",
    ] {
        assert_eq!(
            outline_source(source, "bad").unwrap_err().code,
            "indentation"
        );
    }
    assert_eq!(
        outline_source(&"#".repeat(1_048_577), "big")
            .unwrap_err()
            .code,
        "source_limit"
    );
    assert_eq!(
        outline_source(&"THEN true\n".repeat(16_385), "many")
            .unwrap_err()
            .code,
        "source_limit"
    );
}

fn cli(input: Value) -> std::process::Output {
    let mut child = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("outline-editor")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all(input.to_string().as_bytes())
        .unwrap();
    child.wait_with_output().unwrap()
}

#[test]
fn cli_binds_outline_to_snapshot_and_rejects_unsupported_requests() {
    use sha2::{Digest, Sha256};
    let source = "SCENARIO unsaved\nTHEN false\n";
    let output = cli(json!({"file":"/does/not/exist.gwt","text":source}));
    assert!(output.status.success());
    let report: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["kind"], "gwt.native-outline");
    assert_eq!(
        report["sourceDigest"],
        format!("sha256:{:x}", Sha256::digest(source.as_bytes()))
    );
    assert_eq!(report["symbols"][0]["name"], "unsaved");
    assert_eq!(report["diagnostic"], Value::Null);
    let output = cli(json!({"file":"bad","text":" THEN false\n"}));
    assert!(!output.status.success());
    let report: Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["symbols"], json!([]));
    assert_eq!(report["diagnostic"]["code"], "indentation");
    assert!(
        !cli(json!({"file":"bad","text":"", "execute":true}))
            .status
            .success()
    );
    assert!(
        !cli(json!({"file":"x".repeat(4097),"text":""}))
            .status
            .success()
    );
}
