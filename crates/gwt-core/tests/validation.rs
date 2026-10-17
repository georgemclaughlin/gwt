use gwt_core::{
    SourceBundle, ValidationOptions, ValidationStatus as Status, load_bundle, validate_bundle,
    validate_file,
};
use serde_json::Value;
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicUsize, Ordering},
};

fn bundle(source: &str) -> SourceBundle {
    SourceBundle {
        entry: "main.gwt".into(),
        modules: BTreeMap::from([("main.gwt".into(), source.into())]),
    }
}

struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let path = std::env::temp_dir().join(format!(
            "gwt-validation-{}-{}",
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
fn valid_report_identifies_exact_source_and_serializes_explicit_gates() {
    let source = bundle(
        "SCENARIO exact\nGIVEN amount is 9007199254740993\nWHEN print amount\nTHEN prints [9007199254740993]\n",
    );
    let report = validate_bundle(&source, ValidationOptions::default());
    assert!(report.ok, "{report:?}");
    assert_eq!(report.results.len(), 1);
    assert_eq!(report.results[0].name, "exact");
    assert!(report.results[0].steps > 0);
    let json = serde_json::to_value(&report).unwrap();
    assert_eq!(json["kind"], "gwt.native-validation");
    assert_eq!(json["schemaVersion"], 1);
    for phase in ["load", "check", "format", "scenarios"] {
        assert_eq!(json[phase]["status"], "passed");
    }
    assert_eq!(json["modules"][0]["changed"], false);
    assert_eq!(
        report.program_identity,
        gwt_core::compile_bundle(&source)
            .unwrap()
            .identity()
            .cloned()
    );
    // Compact validation must not accumulate every scenario's execution evidence.
    assert!(json["results"][0].get("events").is_none());
    assert!(json["results"][0].get("state").is_none());
}

#[test]
fn no_scenarios_requires_explicit_permission_and_never_claims_exercise() {
    let source = bundle("TYPE Amount is integer\n");
    let strict = validate_bundle(&source, ValidationOptions::default());
    assert!(!strict.ok);
    assert_eq!(strict.check.status, Status::Passed);
    assert_eq!(strict.format.status, Status::Passed);
    assert_eq!(strict.scenarios.status, Status::NotExercised);
    let permitted = validate_bundle(
        &source,
        ValidationOptions {
            allow_no_scenarios: true,
            ..Default::default()
        },
    );
    assert!(permitted.ok);
    assert_eq!(permitted.scenarios.status, Status::NotExercised);
    assert!(permitted.results.is_empty());
    let empty = validate_bundle(
        &bundle(""),
        ValidationOptions {
            allow_no_scenarios: true,
            ..Default::default()
        },
    );
    assert!(!empty.ok);
    assert_eq!(empty.check.status, Status::Failed);
}

#[test]
fn formatting_and_scenario_failures_are_independent_and_all_scenarios_run() {
    let mut source =
        bundle("USE \"types.gwt\"\nSCENARIO fails\nTHEN  false\nSCENARIO passes\nTHEN true\n");
    source
        .modules
        .insert("types.gwt".into(), "TYPE Amount is integer\n\n".into());
    let original = source.clone();
    let report = validate_bundle(&source, ValidationOptions::default());
    assert!(!report.ok);
    assert_eq!(report.check.status, Status::Passed, "{report:?}");
    assert_eq!(report.format.status, Status::Failed);
    assert!(report.modules.iter().all(|item| item.changed == Some(true)));
    assert_eq!(report.scenarios.status, Status::Failed);
    assert_eq!(report.results.len(), 2);
    assert!(!report.results[0].ok);
    let error = report.results[0].diagnostic.as_ref().unwrap();
    assert_eq!(error.code, "assertion_failed");
    assert_eq!(error.span.file, "main.gwt");
    assert_eq!(error.span.line, 3);
    assert!(report.results[1].ok);
    assert_eq!(source, original);
    let formatting_only = validate_bundle(
        &bundle("SCENARIO  passes\nTHEN true\n"),
        ValidationOptions::default(),
    );
    assert!(!formatting_only.ok);
    assert_eq!(formatting_only.scenarios.status, Status::Passed);
}

#[test]
fn load_and_compile_failures_explicitly_skip_dependent_gates() {
    let directory = Directory::new();
    let report = validate_file(
        &directory.0.join("absent.gwt"),
        None,
        ValidationOptions::default(),
    );
    assert!(!report.ok);
    assert_eq!(report.load.status, Status::Failed);
    assert!(report.load.diagnostic.is_some());
    assert_eq!(report.check.status, Status::Skipped);
    assert_eq!(report.format.status, Status::Skipped);
    assert_eq!(report.scenarios.status, Status::Skipped);
    let report = validate_bundle(
        &bundle("SCENARIO bad\nTHEN unknown == 1\n"),
        ValidationOptions::default(),
    );
    assert_eq!(report.load.status, Status::Passed);
    assert_eq!(report.check.status, Status::Failed);
    assert!(report.check.diagnostic.is_some());
    assert_eq!(report.scenarios.status, Status::Skipped);
    assert!(report.program_identity.is_none());
    assert!(report.results.is_empty());
}

#[test]
fn frozen_closure_formats_imports_but_executes_only_entry_scenarios() {
    let directory = Directory::new();
    let entry = directory.0.join("main.gwt");
    let imported = directory.0.join("types.gwt");
    fs::write(
        &entry,
        "USE \"types.gwt\"\nSCENARIO entry\nGIVEN amount is 4\nTHEN amount == 4\n",
    )
    .unwrap();
    fs::write(
        &imported,
        "TYPE Amount is integer\nSCENARIO ignored\nTHEN false\n",
    )
    .unwrap();
    let captured = load_bundle(&entry, None).unwrap();
    fs::write(&imported, "BROKEN after capture\n").unwrap();
    fs::remove_file(&entry).unwrap();
    let report = validate_bundle(&captured, ValidationOptions::default());
    assert!(report.ok, "{report:?}");
    assert_eq!(report.modules.len(), 2);
    assert_eq!(report.results.len(), 1);
    assert_eq!(report.results[0].name, "entry");
    assert_eq!(
        fs::read_to_string(imported).unwrap(),
        "BROKEN after capture\n"
    );
}

#[test]
fn caller_budgets_fail_execution_without_being_bypassed_by_permission() {
    let mut options = ValidationOptions {
        allow_no_scenarios: true,
        ..Default::default()
    };
    options.limits.execution.steps = 0;
    let report = validate_bundle(&bundle("SCENARIO bounded\nTHEN true\n"), options);
    assert!(!report.ok);
    assert_eq!(report.check.status, Status::Passed, "{report:?}");
    assert_eq!(report.format.status, Status::Passed);
    assert_eq!(report.scenarios.status, Status::Failed);
    assert!(
        report.results[0]
            .diagnostic
            .as_ref()
            .unwrap()
            .code
            .contains("limit")
    );
    assert_eq!(report.limits.execution.steps, 0);
}

#[test]
fn cli_reports_gates_exit_statuses_and_refuses_ambiguous_flags_without_writing() {
    let directory = Directory::new();
    let file = directory.0.join("main.gwt");
    let invoke = |args: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .arg("validate")
            .arg(&file)
            .args(args)
            .output()
            .unwrap()
    };
    fs::write(&file, "TYPE Amount is integer\n").unwrap();
    let strict = invoke(&[]);
    assert_eq!(strict.status.code(), Some(1));
    let parsed: Value = serde_json::from_slice(&strict.stdout).unwrap();
    assert_eq!(parsed["scenarios"]["status"], "notExercised");
    for args in [
        vec![
            "--allow-no-scenarios",
            "--import-root",
            directory.0.to_str().unwrap(),
        ],
        vec![
            "--import-root",
            directory.0.to_str().unwrap(),
            "--allow-no-scenarios",
        ],
    ] {
        let result = invoke(&args);
        assert!(result.status.success(), "{:?}", result);
        assert_eq!(
            serde_json::from_slice::<Value>(&result.stdout).unwrap()["allowNoScenarios"],
            true
        );
    }
    for args in [
        vec!["--allow-no-scenarios", "--allow-no-scenarios"],
        vec!["--import-root"],
        vec!["--import-root", "--allow-no-scenarios"],
        vec!["--unknown"],
        vec!["--import-root", ".", "--import-root", "."],
    ] {
        let result = invoke(&args);
        assert!(!result.status.success());
        assert!(result.stdout.is_empty());
    }
    let source = "SCENARIO  dirty\nTHEN true\n";
    fs::write(&file, source).unwrap();
    let result = invoke(&[]);
    assert!(!result.status.success());
    let parsed: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(parsed["format"]["status"], "failed");
    assert_eq!(parsed["scenarios"]["status"], "passed");
    assert_eq!(fs::read_to_string(file).unwrap(), source);
}
