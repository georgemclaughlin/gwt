use gwt_core::{EditorQuery, complete_editor};
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
        let p = std::env::temp_dir().join(format!(
            "gwt-completion-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&p).unwrap();
        Self(p)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
const TYPES: &str = "RECORD RequestFacts\n  amount: decimal\nTYPE DecisionLabel is \"yes\" | \"no\"\nWHEN review <facts> into <decision>\n  GIVEN facts is RequestFacts\n  AND decision is DecisionLabel\n  PASS\nWHEN review score for <facts>\n  GIVEN facts is RequestFacts\n  THEN returns decimal\n  RETURN facts.amount\nREQUEST review account\n  WHEN REQUIRE false\n";
fn query(root: &Directory, source: &str, types: &str) -> gwt_core::EditorCompletion {
    let at = source.find('|').unwrap();
    let source = source.replacen('|', "", 1);
    complete_editor(
        &root.0.join("main.gwt"),
        Some(&root.0),
        &BTreeMap::from([
            ("main.gwt".into(), source),
            ("types.gwt".into(), types.into()),
        ]),
        &EditorQuery {
            path: "main.gwt".into(),
            byte_offset: at,
        },
    )
}
fn labels(report: &gwt_core::EditorCompletion) -> Vec<&str> {
    report.items.iter().map(|i| i.label.as_str()).collect()
}

#[test]
fn incomplete_calls_use_current_imports_and_expose_contracts_without_execution() {
    let root = Directory::new();
    fs::write(root.0.join("types.gwt"), "TYPE SavedOnly is integer\n").unwrap();
    let report = query(
        &root,
        "USE \"types.gwt\"\nSCENARIO edit\nWHEN rev|\n",
        TYPES,
    );
    assert!(report.ok, "{:?}", report.diagnostic);
    assert_eq!(
        labels(&report),
        ["review <facts> into <decision>", "review score for <facts>"]
    );
    assert_eq!(report.basis, "declarations");
    assert!(
        report.items[0]
            .detail
            .contains("GIVEN facts is RequestFacts")
    );
    assert!(
        report.items[0]
            .detail
            .contains("AND decision is DecisionLabel")
    );
    assert_eq!(
        report.items[0].definition.as_ref().unwrap().file,
        "types.gwt"
    );
    assert_eq!(report.checked_sources.len(), 2);
    assert_eq!(
        fs::read_to_string(root.0.join("types.gwt")).unwrap(),
        "TYPE SavedOnly is integer\n"
    );
    assert!(!root.0.join("main.gwt").exists());
    let fresh = query(
        &root,
        "USE \"types.gwt\"\nSCENARIO edit\nWHEN rev|\n",
        &TYPES.replace("review", "assess"),
    );
    assert!(fresh.ok);
    assert!(fresh.items.is_empty());
    let returned = query(
        &root,
        "USE \"types.gwt\"\nSCENARIO edit\nWHEN LET score be rev|\n",
        TYPES,
    );
    assert_eq!(labels(&returned), ["review score for <facts>"]);
    let body = query(&root, "USE \"types.gwt\"\nWHEN caller\n  rev|\n", TYPES);
    assert_eq!(labels(&body), labels(&report));
    let request = query(
        &root,
        "USE \"types.gwt\"\nSCENARIO edit\nREQUEST rev|\n",
        TYPES,
    );
    assert_eq!(labels(&request), ["review account"]);
    let domain_words = "WHEN check-in <facts> and résumé\n  GIVEN facts is RequestFacts\n  PASS\n";
    let report = query(&root, "USE \"types.gwt\"\nWHEN check-|\n", domain_words);
    assert_eq!(labels(&report), ["check-in <facts> and résumé"]);
}

#[test]
fn type_positions_replace_only_current_name_with_unicode_crlf_and_nested_containers() {
    let root = Directory::new();
    for text in [
        "# 😀 café\r\nUSE \"types.gwt\"\r\nSCENARIO edit\r\nGIVEN facts is list<optional<Req|uestX>>\r\n",
        "USE \"types.gwt\"\nRECORD Wrapper\n  facts: Req|uestX\n",
        "USE \"types.gwt\"\nTYPE Alias is Req|uestX\n",
        "USE \"types.gwt\"\nWHEN inspect\n  THEN returns Req|uestX\n  PASS\n",
    ] {
        let report = query(&root, text, TYPES);
        assert!(report.ok, "{:?}", report.diagnostic);
        assert_eq!(labels(&report), ["RequestFacts"]);
        let span = report.replacement.unwrap();
        let source = text.replacen('|', "", 1);
        assert_eq!(&source[span.start..span.end], "RequestX");
        assert_eq!(
            span.line,
            source[..span.start].bytes().filter(|b| *b == b'\n').count() + 1
        );
    }
    let builtins = query(&root, "SCENARIO edit\nGIVEN count is int|\n", TYPES);
    assert_eq!(labels(&builtins), ["integer"]);
    assert_eq!(builtins.checked_sources.len(), 1);
}

#[test]
fn expressions_comments_strings_indentation_and_declaration_headers_do_not_get_call_suggestions() {
    let root = Directory::new();
    for tail in [
        "WHEN \"rev|\"",
        "# WHEN rev|",
        "THEN rev|",
        "WHEN print \"escaped \\\" rev|\"",
        "WHEN rev| existing_argument",
        "GIVEN facts is Contact of kind rev|",
        "WHEN rev|iew <facts>\n  GIVEN facts is RequestFacts\n  PASS",
        "WHEN caller\n  DECIDE\n    WHEN rev|\n      PASS\n    ELSE\n      PASS",
        "WHEN caller\n | PASS",
        "WHEN caller\n  set value to rev|",
    ] {
        let source = format!("USE \"types.gwt\"\n{tail}\n");
        let report = query(&root, &source, TYPES);
        assert!(report.ok, "{tail}: {:?}", report.diagnostic);
        assert!(report.items.is_empty(), "{tail}: {:?}", labels(&report));
    }
}

#[test]
fn duplicate_declarations_are_omitted_and_responses_are_bounded() {
    let root = Directory::new();
    let duplicate = format!("{TYPES}\nWHEN review <input> into <output>\n  PASS\n");
    let report = query(&root, "USE \"types.gwt\"\nWHEN rev|\n", &duplicate);
    assert_eq!(labels(&report), ["review score for <facts>"]);
    let mut many = String::new();
    for index in 0..140 {
        use std::fmt::Write;
        writeln!(many, "WHEN action_{index:03}\n  PASS").unwrap();
    }
    let report = query(&root, "USE \"types.gwt\"\nWHEN action|\n", &many);
    assert!(report.ok);
    assert!(report.truncated);
    assert_eq!(report.items.len(), 128);
    assert_eq!(report.items[0].label, "action_000");
}

#[test]
fn bad_closures_and_queries_fail_without_stale_items_and_cli_requires_query() {
    let root = Directory::new();
    let report = query(
        &root,
        "USE \"types.gwt\"\nWHEN rev|\n",
        "USE \"missing.gwt\"\n",
    );
    assert!(!report.ok);
    assert!(report.items.is_empty());
    assert_eq!(report.checked_sources.len(), 2);
    let overlays = BTreeMap::from([("main.gwt".into(), "# 😀\nWHEN review\n  PASS\n".into())]);
    for (path, offset) in [("main.gwt", 3), ("main.gwt", 999), ("unread.gwt", 0)] {
        let r = complete_editor(
            &root.0.join("main.gwt"),
            Some(&root.0),
            &overlays,
            &EditorQuery {
                path: path.into(),
                byte_offset: offset,
            },
        );
        assert!(!r.ok);
        assert_eq!(r.diagnostic.unwrap().code, "editor_query");
        assert!(r.items.is_empty());
    }
    let mut child = std::process::Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("complete-editor")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    use std::io::Write;
    child
        .stdin
        .take()
        .unwrap()
        .write_all(br#"{"entry":"main.gwt","documents":[]}"#)
        .unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(!out.status.success());
    assert!(
        String::from_utf8(out.stderr)
            .unwrap()
            .contains("completion requires a query")
    );
}

#[test]
fn case_distinct_domain_completions_keep_spelling_and_exclude_reserved_heads() {
    let root = Directory::new();
    let declarations = "WHEN SET <target> to <value>\n  GIVEN target is integer\n  AND value is integer\n  PASS\nWHEN set invalid\n  PASS\nWHEN Find domain\n  PASS\nWHEN find invalid\n  PASS\nRECORD parcel\n  WHEN: integer\n";
    let report = query(&root, "USE \"types.gwt\"\nWHEN S|\n", declarations);
    assert!(report.ok);
    assert_eq!(labels(&report), ["SET <target> to <value>"]);
    let report = query(&root, "USE \"types.gwt\"\nWHEN s|\n", declarations);
    assert!(report.ok);
    assert!(report.items.is_empty());
    let report = query(&root, "USE \"types.gwt\"\nWHEN F|\n", declarations);
    assert_eq!(labels(&report), ["Find domain"]);
    let report = query(
        &root,
        "USE \"types.gwt\"\nGIVEN value is p|\n",
        declarations,
    );
    assert_eq!(labels(&report), ["parcel"]);
}
