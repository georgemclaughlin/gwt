use gwt_core::{ProgramLimits, capture_request, compile_file};
use serde_json::{Value, json};
use std::{
    fs,
    path::PathBuf,
    process::{Command, Output},
    sync::atomic::{AtomicUsize, Ordering},
};

struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        static NEXT: AtomicUsize = AtomicUsize::new(0);
        let path = std::env::temp_dir().join(format!(
            "gwt-cli-limits-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        fs::write(
            path.join("invoice.gwt"),
            include_str!("fixtures/invoice.gwt"),
        )
        .unwrap();
        fs::write(
            path.join("input.json"),
            include_str!("fixtures/invoice-input.json"),
        )
        .unwrap();
        Self(path)
    }
    fn limits(&self, value: ProgramLimits) {
        fs::write(
            self.0.join("limits.json"),
            serde_json::to_vec(&value).unwrap(),
        )
        .unwrap();
    }
    fn command(&self, args: &[&str]) -> Output {
        Command::new(env!("CARGO_BIN_EXE_gwt-native"))
            .current_dir(&self.0)
            .args(args)
            .output()
            .unwrap()
    }
    fn payload(&self, args: &[&str], success: bool) -> Value {
        let output = self.command(args);
        assert_eq!(
            output.status.success(),
            success,
            "{args:?}: {} {}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        serde_json::from_slice(&output.stdout).unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn cli_request_limits_match_library_execution_profile_capture_and_replay() {
    let f = Fixture::new();
    let p = compile_file(&f.0.join("invoice.gwt"), None).unwrap();
    let input = serde_json::from_str(include_str!("fixtures/invoice-input.json")).unwrap();
    let defaults = ProgramLimits::default();
    let mut variations = vec![defaults; 5];
    variations[1].execution.steps = 0;
    variations[2].execution.evidence_bytes = 0;
    variations[3].execution.text_bytes = 1;
    variations[4].call_depth = 0;
    for (index, limits) in variations.into_iter().enumerate() {
        f.limits(limits);
        let expected = p.run_request("price invoice", &input, limits);
        // textBytes bounds concatenation, not every pre-existing string value.
        assert_eq!(expected.ok, index == 0 || index == 3);
        let mut args = vec![
            "run",
            "invoice.gwt",
            "--request",
            "price invoice",
            "--input",
            "input.json",
            "--limits",
            "limits.json",
        ];
        assert_eq!(f.payload(&args, expected.ok), json!(expected));
        args[0] = "profile";
        assert_eq!(
            f.payload(&args, expected.ok),
            p.profile_request("price invoice", &input, limits)
                .unwrap()
                .to_json()
                .unwrap()
        );
        args[0] = "capture";
        let case = f.payload(&args, true);
        assert_eq!(
            case,
            json!(capture_request(&p, "price invoice", &input, limits).unwrap())
        );
        fs::write(f.0.join("case.json"), serde_json::to_vec(&case).unwrap()).unwrap();
        assert_eq!(f.payload(&["replay", "case.json"], true)["verified"], true);
        let comparison = f.payload(
            &["compare", "case.json", "--candidate", "invoice.gwt"],
            true,
        );
        assert_eq!(comparison["status"], "compared");
        assert_eq!(comparison["changes"]["outcome"], false);
    }
}

#[test]
fn scenario_testing_and_validation_share_limits_with_fresh_budget_per_scenario() {
    let f = Fixture::new();
    fs::write(
        f.0.join("single.gwt"),
        "SCENARIO one\nGIVEN value is 7\nWHEN print value\nTHEN prints [7]\n",
    )
    .unwrap();
    let p = compile_file(&f.0.join("single.gwt"), None).unwrap();
    let mut limits = ProgramLimits::default();
    for steps in [100_000, 0] {
        limits.execution.steps = steps;
        f.limits(limits);
        let run = p.run_scenario("one", limits);
        assert_eq!(
            f.payload(&["run", "single.gwt", "--limits", "limits.json"], run.ok),
            json!(run)
        );
        for command in ["run", "profile", "capture"] {
            let success = command == "capture" || run.ok;
            assert_eq!(
                f.payload(&[command, "single.gwt", "--limits", "limits.json"], success),
                f.payload(
                    &[
                        command,
                        "single.gwt",
                        "--scenario",
                        "one",
                        "--limits",
                        "limits.json"
                    ],
                    success
                )
            );
        }
        let tested = f.payload(
            &["test", "invoice.gwt", "--limits", "limits.json"],
            steps != 0,
        );
        assert_eq!(tested["limits"], json!(limits));
        assert_eq!(tested["scenarioCount"], 2);
        let validated = f.payload(
            &["validate", "invoice.gwt", "--limits", "limits.json"],
            steps != 0,
        );
        assert_eq!(validated["limits"], json!(limits));
        assert_eq!(validated["results"].as_array().unwrap().len(), 2);
        for row in validated["results"].as_array().unwrap() {
            assert_eq!(row["ok"], steps != 0);
            if steps == 0 {
                assert_eq!(row["diagnostic"]["code"], "execution_limit");
            }
        }
    }
    let html = f.payload(
        &[
            "validate",
            "invoice.gwt",
            "--html",
            "report.html",
            "--limits",
            "limits.json",
        ],
        false,
    );
    assert_eq!(html["limits"], json!(limits));
    assert!(
        fs::read_to_string(f.0.join("report.html"))
            .unwrap()
            .contains("execution_limit")
    );
}

#[test]
fn malformed_or_ambiguous_limits_fail_before_loading_source_or_creating_reports() {
    let f = Fixture::new();
    let valid = serde_json::to_string(&ProgramLimits::default()).unwrap();
    let variants = vec![
        "{}".into(),
        "[]".into(),
        "null".into(),
        "{\"execution\":{}}".into(),
        valid.replace("100000", "-1"),
        valid.replace("100000", "1.5"),
        valid.replace("100000", "true"),
        valid.replace("100000", "18446744073709551616"),
        valid.replace("\"steps\":", "\"typo\":"),
        valid.replace("\"steps\":", "\"steps\":1,\"steps\":"),
        valid.replace("\"execution\":", "\"callDepth\":1,\"execution\":"),
        format!("{valid} null"),
        format!("{valid}{}", " ".repeat(4096)),
    ];
    for raw in variants {
        fs::write(f.0.join("limits.json"), raw).unwrap();
        for args in [
            vec!["run", "absent.gwt", "--limits", "limits.json"],
            vec!["test", "absent.gwt", "--limits", "limits.json"],
            vec![
                "validate",
                "absent.gwt",
                "--limits",
                "limits.json",
                "--html",
                "report.html",
            ],
        ] {
            let output = f.command(&args);
            assert!(!output.status.success());
            assert!(
                output.stdout.is_empty(),
                "must reject settings before source loading"
            );
            assert!(!output.stderr.is_empty());
            assert!(!f.0.join("report.html").exists());
        }
    }
    f.limits(ProgramLimits::default());
    for command in ["run", "profile", "capture", "test", "validate"] {
        for suffix in [
            vec!["--limits"],
            vec!["--limits", "--import-root"],
            vec!["--limits", "limits.json", "--limits", "limits.json"],
        ] {
            let mut args = vec![command, "invoice.gwt"];
            args.extend(suffix);
            let output = f.command(&args);
            assert!(
                !output.status.success() && output.stdout.is_empty(),
                "{args:?}"
            );
        }
    }
    for command in ["check", "inspect", "replay"] {
        assert!(
            !f.command(&[command, "invoice.gwt", "--limits", "limits.json"])
                .status
                .success()
        );
    }
}

#[test]
fn larger_execution_budgets_do_not_weaken_capture_or_hard_depth_bounds() {
    let f = Fixture::new();
    let mut limits = ProgramLimits::default();
    limits.execution.steps += 1;
    limits.call_depth = 65;
    f.limits(limits);
    let mut args = vec![
        "run",
        "invoice.gwt",
        "--request",
        "price invoice",
        "--input",
        "input.json",
        "--limits",
        "limits.json",
    ];
    let run = f.payload(&args, true);
    assert_eq!(run["result"]["decision"]["total"], "47.88");
    args[0] = "profile";
    let profile = f.payload(&args, true);
    assert_eq!(profile["limits"], json!(limits));
    assert_eq!(profile["effectiveCallDepthLimit"], 64);
    args[0] = "capture";
    let refused = f.payload(&args, false);
    assert_eq!(refused["phase"], "capture");
    assert_eq!(refused["diagnostic"]["code"], "case_limits");
}

#[test]
fn explicit_defaults_and_trailing_import_root_orders_preserve_existing_observations() {
    let f = Fixture::new();
    f.limits(ProgramLimits::default());
    let base = [
        "run",
        "invoice.gwt",
        "--request",
        "price invoice",
        "--input",
        "input.json",
    ];
    let expected = f.payload(&base, true);
    for suffix in [
        vec!["--limits", "limits.json", "--import-root", "."],
        vec!["--import-root", ".", "--limits", "limits.json"],
    ] {
        let mut args = base.to_vec();
        args.extend(suffix);
        assert_eq!(f.payload(&args, true), expected);
    }
    let help = f.payload(&["--help"], true).to_string();
    assert!(help.contains("--limits FILE.json"));
}

#[test]
fn text_budget_counts_utf8_concatenation_without_redefining_input_limits() {
    let f = Fixture::new();
    fs::write(f.0.join("text.gwt"), "SCENARIO text\nGIVEN message is \"café\"\nWHEN print message + \"!\"\nTHEN prints [\"café!\"]\n").unwrap();
    let p = compile_file(&f.0.join("text.gwt"), None).unwrap();
    let mut limits = ProgramLimits::default();
    for bytes in [5, 6] {
        limits.execution.text_bytes = bytes;
        f.limits(limits);
        let expected = p.run_scenario("text", limits);
        assert_eq!(expected.ok, bytes == 6);
        assert_eq!(
            f.payload(&["run", "text.gwt", "--limits", "limits.json"], bytes == 6),
            json!(expected)
        );
        let profile = f.payload(
            &["profile", "text.gwt", "--limits", "limits.json"],
            bytes == 6,
        );
        assert_eq!(profile["limits"]["execution"]["textBytes"], bytes);
        assert_eq!(profile["diagnostic"], json!(expected.diagnostic));
    }
}
