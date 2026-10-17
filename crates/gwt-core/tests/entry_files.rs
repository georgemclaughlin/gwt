use gwt_core::{
    ExecutionCase, ProgramLimits, SourceBundle, capture_scenario, compare_case, compile_bundle,
    compile_file, compile_program, explain_execution, replay_case, validate_bundle,
};
use serde_json::{Value as Json, json};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
};

const RULES: &str = "USE \"types.gwt\"\nREQUEST deposit savings\n  GIVEN savings is Account\n  WHEN credit savings\n  OUTPUT savings is Account\nREQUEST charge fee\n  GIVEN savings is Account\n  WHEN debit savings\n  OUTPUT savings is Account\nWHEN credit <account>\n  GIVEN account is Account\n  add 3 to account.balance\nWHEN debit <account>\n  GIVEN account is Account\n  subtract 1 from account.balance\nSCENARIO library example is not the entry\nTHEN false\n";
const INPUT: &str = "# 😀 café\r\nUSE \"lib/rules.gwt\"\r\nGIVEN savings is Account\r\n  balance: 5\r\nREQUEST deposit savings\r\nTHEN savings.balance == 8\r\nREQUEST charge fee\r\nTHEN savings.balance == 7\r\n";

fn bundle() -> SourceBundle {
    SourceBundle {
        entry: "request.gwt".into(),
        modules: BTreeMap::from([
            ("request.gwt".into(), INPUT.into()),
            ("lib/rules.gwt".into(), RULES.into()),
            (
                "lib/types.gwt".into(),
                "RECORD Account\n  balance: integer\n".into(),
            ),
        ]),
    }
}

struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        static ID: AtomicU64 = AtomicU64::new(0);
        let path = std::env::temp_dir().join(format!(
            "gwt-entry-{}-{}",
            std::process::id(),
            ID.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
    fn write(&self, bundle: &SourceBundle) {
        for (name, text) in &bundle.modules {
            let path = self.0.join(name);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, text).unwrap();
        }
    }
    fn cli(&self, args: &[&str], ok: bool) -> Json {
        let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
            .current_dir(&self.0)
            .args(args)
            .output()
            .unwrap();
        assert_eq!(output.status.success(), ok, "{output:?}");
        assert!(output.stderr.is_empty(), "{output:?}");
        serde_json::from_slice(&output.stdout).unwrap()
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

#[test]
fn readable_entry_calls_public_requests_in_order_with_exact_source_evidence() {
    let source = bundle();
    let program = compile_bundle(&source).unwrap();
    assert_eq!(program.single_scenario().unwrap(), "Main");
    assert_eq!(program.scenario_names(), ["Main"]);
    let run = program.run_scenario(program.single_scenario().unwrap(), Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.state, json!({"savings":{"balance":7}}));
    assert_eq!(run.result.as_ref().unwrap(), &run.state);
    assert_eq!(run.request, None); // Entry execution may call more than one request.
    let entries: Vec<_> = run
        .events
        .iter()
        .filter(|event| event.operation == "enter request")
        .collect();
    assert_eq!(entries.len(), 2);
    let explanation = explain_execution(&run, &source).unwrap();
    assert!(
        explanation
            .steps
            .iter()
            .any(|step| step.operation == "add" && step.source.span.file == "lib/rules.gwt")
    );
    assert!(
        explanation
            .steps
            .iter()
            .any(|step| step.operation == "assert"
                && step.source.span.file == "request.gwt"
                && step.source.span.line == 6)
    );
    let report = validate_bundle(&source, Default::default());
    assert!(report.ok, "{report:?}");
    assert_eq!(report.results.len(), 1);
    assert_eq!(
        report
            .evidence
            .as_ref()
            .unwrap()
            .scenario_expectations
            .passed,
        2
    );
    assert!(report.warnings.is_empty());
    // Every execution gets fresh state and one shared budget across both calls.
    for steps in 0..run.steps {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let limited = program.run_scenario("Main", limits);
        assert!(!limited.ok);
        assert!(limited.steps <= steps);
    }
    assert_eq!(
        json!(program.run_scenario("Main", Default::default())),
        json!(run)
    );
}

#[test]
fn default_cli_execution_and_capture_match_explicit_selection_and_survive_relocation() {
    let dir = Directory::new();
    dir.write(&bundle());
    let default = dir.cli(&["run", "request.gwt"], true);
    assert_eq!(default["state"]["savings"]["balance"], 7);
    assert_eq!(
        default,
        dir.cli(&["run", "request.gwt", "--scenario", "Main"], true)
    );
    let captured = dir.cli(&["capture", "request.gwt"], true);
    let case = ExecutionCase::from_json(&captured.to_string()).unwrap();
    assert_eq!(case.scenario(), Some("Main"));
    assert_eq!(case.source(), &bundle());
    let relocated = Directory::new();
    fs::write(relocated.0.join("case.json"), captured.to_string()).unwrap();
    fs::remove_file(dir.0.join("request.gwt")).unwrap();
    fs::remove_file(dir.0.join("lib/rules.gwt")).unwrap();
    let replay = relocated.cli(&["replay", "case.json"], true);
    assert_eq!(replay["verified"], true);
    assert_eq!(replay["actual"], default);
}

#[test]
fn sole_named_scenario_or_example_can_run_but_ambiguous_entries_do_not_execute() {
    let dir = Directory::new();
    for source in [
        "SCENARIO only\nWHEN print 7\nTHEN prints [7]\n",
        "SCENARIO row\nWHEN print <n>\nTHEN prints [7]\nEXAMPLES\n  | n |\n  | 7 |\n",
    ] {
        fs::write(dir.0.join("entry.gwt"), source).unwrap();
        let result = dir.cli(&["run", "entry.gwt"], true);
        assert_eq!(result["output"], json!([7]));
        let case = dir.cli(&["capture", "entry.gwt"], true);
        assert_eq!(case["record"]["observed"], result);
    }
    for (source, count) in [
        ("TYPE Amount is integer\n", 0),
        (
            "SCENARIO first\nTHEN false\nSCENARIO second\nTHEN false\n",
            2,
        ),
        (
            "SCENARIO row\nTHEN <n> == 0\nEXAMPLES\n  | n |\n  | 1 |\n  | 2 |\n",
            2,
        ),
    ] {
        fs::write(dir.0.join("entry.gwt"), source).unwrap();
        for command in ["run", "capture"] {
            let result = dir.cli(&[command, "entry.gwt"], false);
            assert_eq!(result["phase"], "selection");
            assert_eq!(result["diagnostic"]["code"], "scenario_selection");
            assert_eq!(result["scenarios"].as_array().unwrap().len(), count);
            assert!(result.get("events").is_none());
        }
    }
    fs::write(dir.0.join("entry.gwt"), "THEN false\n").unwrap();
    let failed = dir.cli(&["run", "entry.gwt"], false);
    assert_eq!(failed["diagnostic"]["code"], "assertion_failed");
    // Capturing a failed run succeeds as an evidence operation.
    let captured = dir.cli(&["capture", "entry.gwt"], true);
    assert_eq!(captured["record"]["observed"]["ok"], false);
}

#[test]
fn revision_review_preserves_entry_inputs_and_distinguishes_changed_rules() {
    let source = bundle();
    let program = compile_bundle(&source).unwrap();
    let case = capture_scenario(
        &program,
        program.single_scenario().unwrap(),
        Default::default(),
    )
    .unwrap();
    assert!(replay_case(&case).unwrap().verified);
    let mut changed = source.clone();
    changed
        .modules
        .insert("lib/rules.gwt".into(), RULES.replace("add 3", "add 4"));
    let candidate = compile_bundle(&changed).unwrap();
    let review = compare_case(&case, &candidate).unwrap();
    assert!(review.baseline.verified);
    assert!(review.changes.as_ref().unwrap().outcome);
    assert!(review.changes.as_ref().unwrap().source);
    let run = review.candidate.unwrap();
    assert!(!run.ok);
    assert_eq!(run.state["savings"]["balance"], 9);
    let error = run.diagnostic.as_ref().unwrap();
    assert_eq!(error.span.file, "request.gwt");
    assert_eq!(error.span.line, 6);
    assert_eq!(
        source.modules["request.gwt"],
        changed.modules["request.gwt"]
    );
    assert_eq!(
        run.events
            .iter()
            .filter(|event| event.operation == "enter request")
            .count(),
        1
    );
    explain_execution(&run, &changed).unwrap();
}

#[test]
fn request_entries_keep_contract_and_import_root_errors_at_their_sources() {
    let dir = Directory::new();
    let mut source = bundle();
    source.modules.insert(
        "requests/request.gwt".into(),
        INPUT.replace("lib/rules.gwt", "../lib/rules.gwt"),
    );
    source.modules.remove("request.gwt");
    source.entry = "requests/request.gwt".into();
    dir.write(&source);
    let denied = dir.cli(&["run", "requests/request.gwt"], false);
    assert_eq!(denied["diagnostic"]["code"], "import_path");
    let run = dir.cli(&["run", "requests/request.gwt", "--import-root", "."], true);
    assert_eq!(run["state"]["savings"]["balance"], 7);
    for (input, code, text) in [
        (
            INPUT.replace("balance: 5", "balance: true"),
            "assignment_type",
            "true",
        ),
        (
            INPUT.replace("GIVEN savings is Account\r\n  balance: 5\r\n", ""),
            "missing_request_input",
            "REQUEST deposit savings",
        ),
        (
            INPUT.replace("REQUEST charge fee", "REQUEST unknown"),
            "unknown_request",
            "REQUEST unknown",
        ),
    ] {
        let mut source = bundle();
        source.modules.insert("request.gwt".into(), input.clone());
        let error = compile_bundle(&source).unwrap_err();
        assert_eq!(error.code, code);
        assert_eq!(error.span.file, "request.gwt");
        assert_eq!(&input[error.span.start..error.span.end], text);
    }
    let declarations = compile_program("TYPE Amount is integer\n", "types.gwt").unwrap();
    assert_eq!(
        declarations.single_scenario().unwrap_err().code,
        "scenario_selection"
    );
}

#[test]
fn order_fulfillment_entry_has_independent_outcomes_and_matches_public_json_request() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../examples/order_fulfillment");
    let program = compile_file(&root.join("native_request.gwt"), None).unwrap();
    assert_eq!(program.scenario_names(), ["Main"]);
    let run = program.run_scenario(program.single_scenario().unwrap(), Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    let fulfillment = &run.state["fulfillment"];
    assert_eq!(fulfillment["status"], "partial");
    assert_eq!(fulfillment["reason"], "partial_inventory");
    assert_eq!(fulfillment["requested_units"], "4");
    assert_eq!(fulfillment["reserved_units"], "3");
    assert_eq!(fulfillment["backordered_units"], "1");
    assert_eq!(fulfillment["shipping_fee"], "19.5");
    assert_eq!(run.state["inventory"]["widget_available"], "4");
    assert_eq!(run.state["inventory"]["gadget_available"], "0");
    assert_eq!(run.state["inventory"]["cable_available"], "4");
    let rules = compile_file(&root.join("rules.gwt"), None).unwrap();
    let input =
        serde_json::from_str(&fs::read_to_string(root.join("request.json")).unwrap()).unwrap();
    let host = rules.run_request("fulfill order", &input, Default::default());
    assert!(host.ok);
    assert_eq!(host.result.as_ref().unwrap()["fulfillment"], *fulfillment);
    assert_eq!(
        host.result.as_ref().unwrap()["inventory"],
        run.state["inventory"]
    );
    assert!(run.result.as_ref().unwrap().get("order").is_some());
    assert!(host.result.as_ref().unwrap().get("order").is_none());
    let report = validate_bundle(program.source_bundle().unwrap(), Default::default());
    assert!(report.ok);
    assert_eq!(
        report
            .evidence
            .as_ref()
            .unwrap()
            .scenario_expectations
            .passed,
        10
    );
    assert!(report.warnings.is_empty());
}
