use gwt_core::{EditorQuery, check_editor, check_editor_query, compile_file};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    sync::atomic::{AtomicUsize, Ordering},
};
static NEXT: AtomicUsize = AtomicUsize::new(0);
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let path = std::env::temp_dir().join(format!(
            "gwt-editor-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
const SOURCE: &str = "USE \"types.gwt\"\nREQUEST echo\n  GIVEN amount is Amount\n  WHEN print amount\n  OUTPUT amount is Amount\nSCENARIO example\nGIVEN amount is 2\nREQUEST echo\nTHEN prints [2]\n";
#[test]
fn unsaved_entry_and_imports_are_checked_without_writing_or_executing() {
    let root = Directory::new();
    let entry = root.0.join("main.gwt");
    fs::write(&entry, "BROKEN saved source\n").unwrap();
    fs::write(root.0.join("types.gwt"), "TYPE Amount is text\n").unwrap();
    let overlays = BTreeMap::from([
        ("main.gwt".into(), SOURCE.into()),
        ("types.gwt".into(), "TYPE Amount is integer\n".into()),
    ]);
    let report = check_editor(&entry, Some(&root.0), &overlays);
    assert!(report.ok, "{:?}", report.diagnostic);
    assert_eq!(report.requests, ["echo"]);
    assert_eq!(report.scenarios, ["example"]);
    assert_eq!(report.checked_sources.len(), 2);
    assert_eq!(fs::read_to_string(&entry).unwrap(), "BROKEN saved source\n");
    assert_eq!(
        fs::read_to_string(root.0.join("types.gwt")).unwrap(),
        "TYPE Amount is text\n"
    );
    let mut changed = overlays.clone();
    changed.insert(
        "main.gwt".into(),
        SOURCE.replace("THEN prints [2]", "THEN prints [999]"),
    );
    let checked = check_editor(&entry, Some(&root.0), &changed);
    assert!(checked.ok, "checks do not execute failing assertions");
    assert_ne!(report.program_identity, checked.program_identity);
}
#[test]
fn imported_parse_failures_retain_the_exact_unsaved_unicode_crlf_source() {
    let root = Directory::new();
    let entry = root.0.join("main.gwt");
    fs::write(&entry, SOURCE).unwrap();
    let broken = "# 😀 café\r\nRECORD Facts\r\n field: integer\r\n";
    let overlays = BTreeMap::from([("types.gwt".into(), broken.into())]);
    let report = check_editor(&entry, Some(&root.0), &overlays);
    assert!(!report.ok);
    assert_eq!(report.diagnostic_source.as_deref(), Some(broken));
    let diagnostic = report.diagnostic.unwrap();
    assert_eq!(diagnostic.span.file, "types.gwt");
    assert_eq!(diagnostic.span.line, 3);
    assert!(broken.is_char_boundary(diagnostic.span.start));
    assert!(broken.is_char_boundary(diagnostic.span.end));
    assert!(!root.0.join("types.gwt").exists());
}
#[test]
fn new_overlay_files_work_and_unreachable_valid_snapshots_do_not_change_identity() {
    let root = Directory::new();
    let entry = root.0.join("main.gwt");
    fs::write(&entry, SOURCE).unwrap();
    let mut overlays = BTreeMap::from([("types.gwt".into(), "TYPE Amount is integer\n".into())]);
    let report = check_editor(&entry, Some(&root.0), &overlays);
    assert!(report.ok);
    overlays.insert("unused.gwt".into(), "BROKEN unrelated buffer".into());
    assert_eq!(
        check_editor(&entry, Some(&root.0), &overlays).program_identity,
        report.program_identity
    );
    fs::write(root.0.join("types.gwt"), "TYPE Amount is integer\n").unwrap();
    assert_eq!(
        compile_file(&entry, Some(&root.0)).unwrap().identity(),
        report.program_identity.as_ref()
    );
}
#[test]
fn paths_and_overlay_limits_fail_before_any_source_can_escape_the_root() {
    let root = Directory::new();
    let entry = root.0.join("main.gwt");
    fs::write(&entry, "SCENARIO ok\nTHEN true\n").unwrap();
    for key in ["../outside.gwt", "/absolute.gwt", "a/../b.gwt", "a\\b.gwt"] {
        let report = check_editor(
            &entry,
            Some(&root.0),
            &BTreeMap::from([(key.into(), "SCENARIO ok\nTHEN true\n".into())]),
        );
        assert!(!report.ok);
        assert_eq!(report.diagnostic.unwrap().code, "import_path");
        assert!(report.checked_sources.is_empty());
    }
    let oversized = BTreeMap::from([("main.gwt".into(), "x".repeat(1_048_577))]);
    assert_eq!(
        check_editor(&entry, Some(&root.0), &oversized)
            .diagnostic
            .unwrap()
            .code,
        "source_limit"
    );
    let too_many = (0..257)
        .map(|i| (format!("{i}.gwt"), String::new()))
        .collect();
    assert_eq!(
        check_editor(&entry, Some(&root.0), &too_many)
            .diagnostic
            .unwrap()
            .code,
        "source_limit"
    );
}
#[test]
#[cfg(unix)]
fn overlays_do_not_bypass_existing_symlink_guards() {
    use std::os::unix::fs::symlink;
    let root = Directory::new();
    let entry = root.0.join("main.gwt");
    fs::write(&entry, SOURCE).unwrap();
    fs::write(root.0.join("real.gwt"), "TYPE Amount is integer\n").unwrap();
    symlink("real.gwt", root.0.join("types.gwt")).unwrap();
    let report = check_editor(
        &entry,
        Some(&root.0),
        &BTreeMap::from([("types.gwt".into(), "TYPE Amount is integer\n".into())]),
    );
    assert_eq!(report.diagnostic.unwrap().code, "source_symlink");
    assert!(!report.checked_sources.contains_key("types.gwt"));
}
#[test]
fn cli_uses_bounded_stdin_and_refuses_duplicate_documents() {
    use std::{
        io::Write,
        process::{Command, Stdio},
    };
    let root = Directory::new();
    let entry = root.0.join("main.gwt");
    let request = serde_json::json!({"entry":entry,"importRoot":root.0,"documents":[{"path":"main.gwt","text":"SCENARIO exact\nGIVEN note is \"😀\"\nTHEN prints []\n"}]});
    let invoke = |input: String| {
        let mut child = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
            .arg("check-editor")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .unwrap();
        child
            .stdin
            .take()
            .unwrap()
            .write_all(input.as_bytes())
            .unwrap();
        child.wait_with_output().unwrap()
    };
    let output = invoke(request.to_string());
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(report["kind"], "gwt.native-editor-check");
    assert_eq!(report["ok"], true);
    assert!(!entry.exists());
    let mut duplicate = request.clone();
    let first = duplicate["documents"][0].clone();
    duplicate["documents"].as_array_mut().unwrap().push(first);
    assert!(!invoke(duplicate.to_string()).status.success());
    assert!(!invoke("{".into()).status.success());
    assert!(!invoke(" ".repeat(8 * 1_048_576 + 1)).status.success());
}

fn query(source: &str, offset: usize) -> gwt_core::EditorCheck {
    let root = Directory::new();
    check_editor_query(
        &root.0.join("main.gwt"),
        Some(&root.0),
        &BTreeMap::from([("main.gwt".into(), source.into())]),
        Some(&EditorQuery {
            path: "main.gwt".into(),
            byte_offset: offset,
        }),
    )
}

#[test]
fn navigation_uses_resolved_imported_behaviors_and_scoped_binding_slots() {
    let root = Directory::new();
    let imported = "WHEN twice <amount>\n  GIVEN amount is integer\n  THEN returns integer\n  RETURN amount * 2\n";
    let source = "USE \"math.gwt\"\nWHEN first <amount>\n  GIVEN amount is integer\n  LET answer be twice amount\n  print answer\nWHEN second <amount>\n  GIVEN amount is integer\n  print amount\nSCENARIO run\nGIVEN amount is 4\nWHEN first amount\n";
    let overlays = BTreeMap::from([
        ("main.gwt".into(), source.into()),
        ("math.gwt".into(), imported.into()),
    ]);
    let check = |path: &str, offset| {
        check_editor_query(
            &root.0.join("main.gwt"),
            Some(&root.0),
            &overlays,
            Some(&EditorQuery {
                path: path.into(),
                byte_offset: offset,
            }),
        )
    };
    let call = check("main.gwt", source.find("twice amount").unwrap());
    assert!(call.ok, "{:?}", call.diagnostic);
    let symbol = &call.navigation.as_ref().unwrap().symbols[0];
    assert_eq!(symbol.kind, "behavior");
    assert!(symbol.label.contains("THEN returns integer"));
    assert_eq!(symbol.definition.as_ref().unwrap().file, "math.gwt");
    assert_eq!(symbol.definition.as_ref().unwrap().start, 0);
    let variable = check("main.gwt", source.find("print amount").unwrap() + 6);
    let symbol = &variable.navigation.as_ref().unwrap().symbols[0];
    assert_eq!(symbol.kind, "binding");
    assert_eq!(
        symbol.definition.as_ref().unwrap().start,
        source.rfind("GIVEN amount is integer").unwrap() + 6
    );
    assert_eq!(symbol.context, "WHEN second <amount>");
    let result = check("main.gwt", source.find("print answer").unwrap() + 6);
    assert_eq!(
        result.navigation.unwrap().symbols[0]
            .definition
            .as_ref()
            .unwrap()
            .start,
        source.find("LET answer").unwrap() + 4
    );
    let imported_read = check("math.gwt", imported.find("amount * 2").unwrap());
    assert_eq!(
        imported_read.navigation.unwrap().symbols[0]
            .definition
            .as_ref()
            .unwrap()
            .start,
        imported.find("GIVEN amount").unwrap() + 6
    );
}

#[test]
fn navigation_covers_loop_bindings_field_paths_and_request_outputs() {
    let source = "RECORD Item\n  price: integer\nREQUEST total\n  GIVEN items is list<Item>\n  GIVEN total is 0\n  WHEN compute items into total\n  OUTPUT total is integer\nWHEN compute <items> into <total>\n  GIVEN items is list<Item>\n  AND total is integer\n  FOR item in items\n    add item.price to total\n  sum row.price in items into total\nSCENARIO empty\nGIVEN items is []\n";
    // Check the reusable declarations without an untyped empty-list scenario.
    let source = source.split("SCENARIO empty").next().unwrap();
    let read = query(source, source.find("item.price").unwrap());
    assert!(read.ok, "{:?}", read.diagnostic);
    let symbol = &read.navigation.as_ref().unwrap().symbols[0];
    assert!(symbol.label.contains("item: record { price: integer }"));
    assert_eq!(
        symbol.definition.as_ref().unwrap().start,
        source.find("FOR item").unwrap() + 4
    );
    let field = query(source, source.find("item.price").unwrap() + 5);
    let field = &field.navigation.as_ref().unwrap().symbols[0];
    assert_eq!(field.kind, "field");
    assert_eq!(
        field.definition.as_ref().unwrap().start,
        source.find("price: integer").unwrap()
    );
    let projected = query(source, source.find("row.price").unwrap());
    assert_eq!(
        projected.navigation.unwrap().symbols[0]
            .definition
            .as_ref()
            .unwrap()
            .start,
        source.find("row.price").unwrap()
    );
    let output = query(source, source.find("OUTPUT total").unwrap() + 7);
    assert_eq!(
        output.navigation.unwrap().symbols[0]
            .definition
            .as_ref()
            .unwrap()
            .start,
        source.find("GIVEN total").unwrap() + 6
    );
    let record = query(source, 8);
    assert!(
        record.navigation.unwrap().symbols[0]
            .label
            .contains("price: integer")
    );
}

#[test]
fn navigation_does_not_guess_symbols_in_comments_or_invalid_programs() {
    let source = "# 😀 amount\r\nSCENARIO exact\r\nGIVEN amount is 2\r\nTHEN amount == 2\r\n";
    assert!(query(source, 8).navigation.unwrap().symbols.is_empty());
    let reference = query(source, source.rfind("amount").unwrap());
    let symbol = &reference.navigation.as_ref().unwrap().symbols[0];
    assert_eq!(symbol.span.start, source.rfind("amount").unwrap());
    assert_eq!(symbol.definition.as_ref().unwrap().line, 3);
    assert!(
        query(source, source.len())
            .navigation
            .unwrap()
            .symbols
            .is_empty()
    );
    for offset in [3, source.len() + 1] {
        let invalid = query(source, offset);
        assert!(!invalid.ok);
        assert_eq!(invalid.diagnostic.unwrap().code, "editor_query");
        assert!(invalid.navigation.is_none());
    }
    let invalid = query("SCENARIO bad\nTHEN missing == true\n", 18);
    assert!(!invalid.ok);
    assert!(invalid.navigation.is_none());
}

#[test]
fn navigation_keeps_branch_locals_and_expanded_example_contexts_distinct() {
    let source = "WHEN choose <value>\n  GIVEN value is integer\n  IF value > 0\n    LET chosen be 1\n    print chosen\n  ELSE\n    LET chosen be 2\n    print chosen\n";
    for (usage, declaration) in [
        (
            source.find("print chosen").unwrap(),
            source.find("LET chosen").unwrap(),
        ),
        (
            source.rfind("print chosen").unwrap(),
            source.rfind("LET chosen").unwrap(),
        ),
    ] {
        let result = query(source, usage + 6);
        assert!(result.ok, "{:?}", result.diagnostic);
        assert_eq!(
            result.navigation.unwrap().symbols[0]
                .definition
                .as_ref()
                .unwrap()
                .start,
            declaration + 4
        );
    }
    let mut source =
        "SCENARIO rows\nGIVEN value is <input>\nTHEN value == value\nEXAMPLES\n  | input |\n"
            .to_string();
    for i in 0..70 {
        source.push_str(&format!("  | {i} |\n"));
    }
    let result = query(&source, source.find("THEN value").unwrap() + 5);
    assert!(result.ok, "{:?}", result.diagnostic);
    let navigation = result.navigation.unwrap();
    assert_eq!(navigation.symbols.len(), 64);
    assert!(navigation.truncated);
    assert_eq!(navigation.symbols[0].context, "SCENARIO rows example 1");
    assert!(
        navigation
            .symbols
            .iter()
            .all(|symbol| symbol.definition.as_ref().unwrap().file == "main.gwt")
    );
}

#[test]
fn navigation_handles_expected_failures_and_implicit_request_output_bindings() {
    let source = "WHEN stop <amount>\n  GIVEN amount is integer\n  REQUIRE false\nREQUEST create\n  GIVEN result is 9\n  WHEN print result\n  OUTPUT result is integer\nSCENARIO handled\nGIVEN amount is 2\nWHEN stop amount\nTHEN fails with \"assertion_failed\"\nREQUEST create\nTHEN result == 9\n";
    let call = query(source, source.find("WHEN stop amount").unwrap() + 5);
    assert!(call.ok, "{:?}", call.diagnostic);
    assert_eq!(
        call.navigation.unwrap().symbols[0]
            .definition
            .as_ref()
            .unwrap()
            .start,
        0
    );
    let output = query(source, source.find("THEN result").unwrap() + 5);
    assert_eq!(
        output.navigation.unwrap().symbols[0]
            .definition
            .as_ref()
            .unwrap()
            .start,
        source.rfind("REQUEST create").unwrap()
    );
    let request = query(source, source.rfind("REQUEST create").unwrap() + 8);
    assert_eq!(
        request.navigation.unwrap().symbols[0]
            .definition
            .as_ref()
            .unwrap()
            .start,
        source.find("REQUEST create").unwrap()
    );
}

#[test]
fn navigation_marks_shortened_field_names_and_bounds_type_labels() {
    let name = "field".repeat(40);
    let source = format!("RECORD Facts\n  {name}: integer\n");
    let result = query(&source, 8);
    assert!(result.ok, "{:?}", result.diagnostic);
    let label = &result.navigation.as_ref().unwrap().symbols[0].label;
    assert!(label.contains(&format!("{}…: integer", &name[..128])));
    assert!(!label.contains(&name));
    let source = format!("TYPE Label is \"{}\"\n", "😀".repeat(600));
    let result = query(&source, 6);
    assert!(result.ok, "{:?}", result.diagnostic);
    let label = &result.navigation.as_ref().unwrap().symbols[0].label;
    assert!(label.ends_with('…'));
    assert!(label.len() < 1100);
}
