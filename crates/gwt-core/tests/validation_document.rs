use gwt_core::{
    SourceBundle, ValidationDocument, ValidationOptions, render_validation_html,
    validate_file_document,
};
use serde_json::Value;
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicUsize, Ordering},
};

fn bundle(text: &str) -> SourceBundle {
    SourceBundle {
        entry: "main.gwt".into(),
        modules: BTreeMap::from([("main.gwt".into(), text.into())]),
    }
}
fn data(html: &str, id: &str) -> Value {
    let begin = format!("<script type=application/json id={id}>");
    serde_json::from_str(
        html.split_once(&begin)
            .unwrap()
            .1
            .split_once("</script>")
            .unwrap()
            .0,
    )
    .unwrap()
}
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let path = std::env::temp_dir().join(format!(
            "gwt-validation-document-{}-{}",
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

#[test]
fn report_and_source_are_frozen_together_and_render_without_reopening_files() {
    let directory = Directory::new();
    let file = directory.0.join("main.gwt");
    let source = "SCENARIO original\nWHEN print 9007199254740993\nTHEN prints [9007199254740993]\n";
    fs::write(&file, source).unwrap();
    let document = validate_file_document(&file, None, ValidationOptions::default());
    assert!(document.report().ok);
    fs::write(&file, "SCENARIO changed\nTHEN false\n").unwrap();
    let html = render_validation_html(&document).unwrap();
    fs::remove_file(&file).unwrap();
    assert_eq!(render_validation_html(&document).unwrap(), html);
    assert_eq!(data(&html, "source-data")["modules"]["main.gwt"], source);
    assert_eq!(
        data(&html, "validation-data"),
        serde_json::to_value(document.report()).unwrap()
    );
    assert_eq!(
        data(&html, "validation-data")["results"][0]["expectations"][0]["outcome"],
        "passed"
    );
    assert!(document.into_report().ok);
}

#[test]
fn source_and_names_cannot_close_the_embedded_json_or_create_markup() {
    let source = "# </script><img src=x onerror=alert(1)> & 😀\nSCENARIO </script><script>alert(2)</script>\nTHEN true\n";
    let document = ValidationDocument::from_bundle(bundle(source), ValidationOptions::default());
    assert!(document.report().ok);
    let html = render_validation_html(&document).unwrap();
    assert!(!html.contains("<img src=x"));
    assert!(!html.contains("<script>alert(2)"));
    assert!(html.contains("\\u003c/script\\u003e"));
    assert_eq!(html.matches("<script").count(), 4);
    assert_eq!(data(&html, "source-data")["modules"]["main.gwt"], source);
    assert_eq!(
        data(&html, "validation-data")["results"][0]["name"],
        "</script><script>alert(2)</script>"
    );
    assert!(html.contains("connect-src 'none'"));
    assert!(!html.contains("innerHTML"));
}

#[test]
fn failures_and_no_scenarios_remain_explicit_and_do_not_invent_source() {
    let directory = Directory::new();
    let missing = validate_file_document(
        &directory.0.join("absent.gwt"),
        None,
        ValidationOptions::default(),
    );
    let html = render_validation_html(&missing).unwrap();
    assert!(data(&html, "source-data").is_null());
    assert_eq!(data(&html, "validation-data")["load"]["status"], "failed");
    assert_eq!(
        data(&html, "validation-data")["scenarios"]["status"],
        "skipped"
    );
    let invalid = "SCENARIO bad\nTHEN missing == 1\n";
    let document = ValidationDocument::from_bundle(bundle(invalid), ValidationOptions::default());
    let html = render_validation_html(&document).unwrap();
    assert_eq!(data(&html, "validation-data")["check"]["status"], "failed");
    assert_eq!(data(&html, "source-data")["modules"]["main.gwt"], invalid);
    let document = ValidationDocument::from_bundle(
        bundle("TYPE Amount is integer\n"),
        ValidationOptions {
            allow_no_scenarios: true,
            ..Default::default()
        },
    );
    let html = render_validation_html(&document).unwrap();
    assert_eq!(data(&html, "validation-data")["ok"], true);
    assert_eq!(
        data(&html, "validation-data")["scenarios"]["status"],
        "notExercised"
    );
    assert!(
        data(&html, "validation-data")["results"]
            .as_array()
            .unwrap()
            .is_empty()
    );
}

#[test]
fn refused_source_bounds_do_not_retain_unbounded_presentation_snapshots() {
    let source = bundle(&"#".repeat(1_048_577));
    let document = ValidationDocument::from_bundle(source, ValidationOptions::default());
    assert!(!document.report().ok);
    assert!(document.source().is_none());
    let html = render_validation_html(&document).unwrap();
    assert!(data(&html, "source-data").is_null());
    assert!(html.len() < 100_000);
}

#[test]
fn exact_limits_and_evidence_gaps_survive_rendering() {
    let mut options = ValidationOptions::default();
    options.limits.execution.steps = usize::MAX;
    let document = ValidationDocument::from_bundle(
        bundle(
            "WHEN unused <amount>\n  GIVEN amount is integer\n  PASS\nSCENARIO actions\nWHEN print 1\n",
        ),
        options,
    );
    assert!(document.report().ok);
    let html = render_validation_html(&document).unwrap();
    assert_eq!(
        data(&html, "validation-data")["limits"]["execution"]["steps"].to_string(),
        usize::MAX.to_string()
    );
    assert!(
        data(&html, "metadata-data")["limitsText"]
            .as_str()
            .unwrap()
            .contains(&usize::MAX.to_string())
    );
    let report = data(&html, "validation-data");
    let warnings = report["warnings"].as_array().unwrap();
    assert_eq!(warnings.len(), 2);
    assert_eq!(warnings[0]["code"], "scenarios_without_expectations");
    assert_eq!(warnings[1]["code"], "unobserved_callables");
}

#[test]
fn cli_writes_failure_reports_without_overwriting_sources_or_existing_artifacts() {
    let directory = Directory::new();
    let file = directory.0.join("main.gwt");
    let output = directory.0.join("review.html");
    let source = "SCENARIO bad\nTHEN false\n";
    fs::write(&file, source).unwrap();
    let invoke = |args: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .arg("validate")
            .arg(&file)
            .args(args)
            .output()
            .unwrap()
    };
    let result = invoke(&["--html", output.to_str().unwrap()]);
    assert_eq!(result.status.code(), Some(1));
    let report: Value = serde_json::from_slice(&result.stdout).unwrap();
    let html = fs::read_to_string(&output).unwrap();
    assert_eq!(data(&html, "validation-data"), report);
    assert_eq!(report["results"][0]["expectations"][0]["outcome"], "failed");
    let refusal = invoke(&["--html", output.to_str().unwrap()]);
    assert!(!refusal.status.success());
    assert!(refusal.stdout.is_empty());
    assert_eq!(fs::read_to_string(&output).unwrap(), html);
    assert!(!invoke(&["--html", file.to_str().unwrap()]).status.success());
    assert_eq!(fs::read_to_string(&file).unwrap(), source);
    for args in [
        vec!["--html"],
        vec!["--html", "--allow-no-scenarios"],
        vec!["--html", "one.html", "--html", "two.html"],
    ] {
        let result = invoke(&args);
        assert!(!result.status.success());
        assert!(result.stdout.is_empty());
    }
    let success = directory.0.join("passed.html");
    fs::write(&file, "TYPE Amount is integer\n").unwrap();
    let result = invoke(&[
        "--allow-no-scenarios",
        "--html",
        success.to_str().unwrap(),
        "--import-root",
        directory.0.to_str().unwrap(),
    ]);
    assert!(result.status.success());
    assert_eq!(
        data(&fs::read_to_string(success).unwrap(), "validation-data")["scenarios"]["status"],
        "notExercised"
    );
}
