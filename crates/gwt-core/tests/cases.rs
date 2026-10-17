use gwt_core::{
    ExecutionCase, ProgramLimits, SourceBundle, capture_request, compare_case, compile_bundle,
    compile_program, engine_identity, replay_case,
};
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
};

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
fn invoice() -> gwt_core::CompiledProgram {
    program(include_str!("fixtures/invoice.gwt"))
}
fn input(quantity: i64) -> Json {
    json!({"invoice":{"unit_price":"19.95","quantity":quantity}})
}
fn capture() -> ExecutionCase {
    capture_request(
        &invoice(),
        "price invoice",
        &input(2),
        ProgramLimits::default(),
    )
    .unwrap()
}
fn payload(case: &ExecutionCase) -> Json {
    serde_json::from_str(&case.to_json()).unwrap()
}

// Independent encoding route: serde_json's default BTreeMap order, rather than
// the library's custom canonical writer. Used to exercise coherent tampering.
fn resign(mut value: Json) -> String {
    value.as_object_mut().unwrap().remove("integrity");
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-case-sha256-v1\0");
    hash.update(serde_json::to_vec(&value).unwrap());
    value["integrity"] = json!(format!("sha256:{:x}", hash.finalize()));
    serde_json::to_string(&value).unwrap()
}

#[test]
fn captured_cases_round_trip_with_exact_execution_and_inputs() {
    let program = invoice();
    let input = input(2);
    let case =
        capture_request(&program, "price invoice", &input, ProgramLimits::default()).unwrap();
    assert_eq!(case.request(), Some("price invoice"));
    assert_eq!(case.input(), &input);
    assert_eq!(case.observed()["result"]["decision"]["total"], "47.88");
    assert_eq!(payload(&case)["record"]["engine"], json!(engine_identity()));
    assert_eq!(capture().to_json(), case.to_json());
    // Whitespace and object property order do not determine artifact integrity.
    let reserialized = resign(payload(&case));
    let restored = ExecutionCase::from_json(&reserialized).unwrap();
    let replay = replay_case(&restored).unwrap();
    assert!(replay.verified);
    assert!(replay.actual.ok);
    assert!(replay.differences.is_empty());
    assert_eq!(json!(replay.actual), *case.observed());
}

#[test]
fn recorded_failures_and_small_budgets_replay_without_claiming_execution_success() {
    let program = invoice();
    for (input, limits, expected) in [
        (input(0), ProgramLimits::default(), "assertion_failed"),
        (json!({}), ProgramLimits::default(), "missing_input"),
        (
            input(2),
            ProgramLimits {
                execution: gwt_core::Limits {
                    steps: 0,
                    ..ProgramLimits::default().execution
                },
                ..ProgramLimits::default()
            },
            "execution_limit",
        ),
        (
            input(2),
            ProgramLimits {
                execution: gwt_core::Limits {
                    evidence_bytes: 1,
                    ..ProgramLimits::default().execution
                },
                ..ProgramLimits::default()
            },
            "evidence_limit",
        ),
    ] {
        let case = capture_request(&program, "price invoice", &input, limits).unwrap();
        let replay = replay_case(&ExecutionCase::from_json(&case.to_json()).unwrap()).unwrap();
        assert!(replay.verified);
        assert!(!replay.actual.ok);
        assert_eq!(replay.actual.diagnostic.unwrap().code, expected);
        assert_eq!(case.observed()["result"], Json::Null);
    }
}

#[test]
fn corrupted_cases_and_unsupported_versions_are_rejected() {
    let original = payload(&capture());
    for pointer in [
        "/record/input/invoice/quantity",
        "/record/observed/result/decision/total",
        "/record/limits/execution/steps",
        "/record/source/modules/rules.gwt",
    ] {
        let mut changed = original.clone();
        let field = changed.pointer_mut(pointer).unwrap();
        *field = if field.is_number() {
            json!(1)
        } else {
            json!("changed")
        };
        assert_eq!(
            ExecutionCase::from_json(&changed.to_string())
                .unwrap_err()
                .code,
            "case_integrity"
        );
    }
    let mut changed = original.clone();
    changed["schemaVersion"] = json!(99);
    assert_eq!(
        ExecutionCase::from_json(&resign(changed)).unwrap_err().code,
        "case_version"
    );
    let mut changed = original.clone();
    changed["unexpected"] = json!(true);
    assert_eq!(
        ExecutionCase::from_json(&resign(changed)).unwrap_err().code,
        "case_format"
    );
    let mut changed = original;
    changed["record"]["limits"]["callDepth"] = json!(65);
    assert_eq!(
        ExecutionCase::from_json(&resign(changed)).unwrap_err().code,
        "case_limits"
    );
}

#[test]
fn valid_checksums_do_not_prove_observations_or_source_identity() {
    let case = capture();
    for (pointer, replacement) in [
        ("/record/observed/result/decision/total", json!("999")),
        ("/record/observed/state/decision/status", json!("new")),
        ("/record/observed/steps", json!(0)),
        ("/record/observed/events/0/value", json!("invented event")),
    ] {
        let mut changed = payload(&case);
        *changed.pointer_mut(pointer).unwrap() = replacement;
        let changed = ExecutionCase::from_json(&resign(changed)).unwrap();
        let replay = replay_case(&changed).unwrap();
        assert!(!replay.verified);
        assert!(!replay.differences.is_empty());
        let comparison = compare_case(&changed, &invoice()).unwrap();
        assert_eq!(comparison.status, "baseline_mismatch");
        assert!(comparison.candidate.is_none());
        assert!(comparison.changes.is_none());
    }
    let mut changed = payload(&case);
    let source = changed["record"]["source"]["modules"]["rules.gwt"]
        .as_str()
        .unwrap()
        .to_owned();
    changed["record"]["source"]["modules"]["rules.gwt"] = json!(format!("# edited\n{source}"));
    let changed = ExecutionCase::from_json(&resign(changed)).unwrap();
    assert_eq!(replay_case(&changed).unwrap_err().code, "case_source");
    let mut changed = payload(&case);
    changed["record"]["engine"]["sourceDigest"] = json!("sha256:old-engine");
    let changed = ExecutionCase::from_json(&resign(changed)).unwrap();
    assert_eq!(replay_case(&changed).unwrap_err().code, "case_engine");
}

#[test]
fn comparison_separates_outcomes_state_and_evidence() {
    let before_source = include_str!("../../../examples/refund_review/stage0.gwt");
    let before = program(before_source);
    let after = program(include_str!("../../../examples/refund_review/stage1.gwt"));
    let input = json!({"facts":{"days":46,"damaged":true,"receipt":false,"clearance":false,"member":false}});
    let case = capture_request(&before, "assess refund", &input, ProgramLimits::default()).unwrap();
    let comparison = compare_case(&case, &after).unwrap();
    assert_eq!(comparison.status, "compared");
    assert!(comparison.baseline.verified);
    assert!(comparison.changes.as_ref().unwrap().outcome);
    assert!(comparison.changes.as_ref().unwrap().state);
    assert_eq!(
        comparison.candidate.unwrap().result.unwrap()["decision"],
        json!({"status":"approved","reason":"damaged"})
    );
    assert_eq!(comparison.outcome_differences.len(), 2);
    assert!(
        comparison
            .outcome_differences
            .iter()
            .any(|difference| difference.path == "/result/decision/status")
    );
    let identical = compare_case(&case, &before).unwrap();
    let changes = identical.changes.unwrap();
    assert!(!changes.source && !changes.outcome && !changes.state && !changes.evidence);
    let moved = program(&format!("# moved source positions\n{before_source}"));
    let moved = compare_case(&case, &moved).unwrap();
    let changes = moved.changes.unwrap();
    assert!(!changes.outcome && !changes.state);
    assert!(changes.evidence);
    assert!(changes.source);
    assert!(moved.outcome_differences.is_empty());
}

#[test]
fn candidate_failures_are_observed_comparisons_not_baseline_failures() {
    let case = capture();
    let rejecting = program(&include_str!("fixtures/invoice.gwt").replace(
        "REQUIRE invoice.quantity > 0",
        "REQUIRE invoice.quantity > 100",
    ));
    let comparison = compare_case(&case, &rejecting).unwrap();
    assert_eq!(comparison.status, "compared");
    assert!(comparison.changes.unwrap().outcome);
    assert!(!comparison.candidate.as_ref().unwrap().ok);
    assert!(
        comparison
            .outcome_differences
            .iter()
            .any(|difference| difference.path == "/diagnostic")
    );
    let missing = compare_case(&case, &program("TYPE Unrelated is text\n")).unwrap();
    assert_eq!(
        missing.candidate.unwrap().diagnostic.unwrap().code,
        "unknown_request"
    );
}

#[test]
fn capture_requires_frozen_sources_and_enforces_resource_profile() {
    let source = include_str!("fixtures/invoice.gwt");
    let loose = compile_program(source, "invoice.gwt").unwrap();
    assert_eq!(
        capture_request(&loose, "price invoice", &input(2), ProgramLimits::default())
            .unwrap_err()
            .code,
        "case_source"
    );
    let excessive = ProgramLimits {
        execution: gwt_core::Limits {
            steps: 100_001,
            ..ProgramLimits::default().execution
        },
        ..ProgramLimits::default()
    };
    assert_eq!(
        capture_request(&invoice(), "price invoice", &input(2), excessive)
            .unwrap_err()
            .code,
        "case_limits"
    );
    assert_eq!(
        ExecutionCase::from_json(&" ".repeat(gwt_core::MAX_CASE_BYTES + 1))
            .unwrap_err()
            .code,
        "case_limit"
    );
    let mut nested = json!(null);
    for _ in 0..66 {
        nested = json!([nested]);
    }
    assert_eq!(
        capture_request(
            &invoice(),
            "price invoice",
            &nested,
            ProgramLimits::default()
        )
        .unwrap_err()
        .code,
        "input_limit"
    );
}

#[test]
fn replay_differences_are_bounded_and_preserve_missing_versus_null() {
    let mut changed = payload(&capture());
    changed["record"]["observed"]["extra/field~"] = Json::Null;
    let report = replay_case(&ExecutionCase::from_json(&resign(changed)).unwrap()).unwrap();
    let value = json!(report);
    assert_eq!(value["differences"][0]["path"], "/extra~1field~0");
    assert_eq!(
        value["differences"][0]["before"],
        json!({"presence":"present","value":null})
    );
    assert_eq!(
        value["differences"][0]["after"],
        json!({"presence":"missing"})
    );
    let mut changed = payload(&capture());
    for index in 0..200 {
        changed["record"]["observed"][format!("extra{index}")] = json!(index);
    }
    let report = replay_case(&ExecutionCase::from_json(&resign(changed)).unwrap()).unwrap();
    assert!(!report.verified);
    assert_eq!(report.differences.len(), 128);
    assert!(report.differences_truncated);
}

struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let path = std::env::temp_dir().join(format!(
            "gwt-cases-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

#[test]
fn cli_captures_imports_and_replays_after_original_sources_are_removed() {
    let directory = Directory::new();
    let source = include_str!("fixtures/invoice.gwt");
    let start = source.find("WHEN price <").unwrap();
    let end = source.find("SCENARIO ").unwrap();
    let entry = directory.0.join("main.gwt");
    let dependency = directory.0.join("pricing.gwt");
    fs::write(
        &entry,
        format!(
            "USE \"pricing.gwt\"\n{}{}",
            &source[..start],
            &source[end..]
        ),
    )
    .unwrap();
    fs::write(&dependency, &source[start..end]).unwrap();
    let input_file = directory.0.join("input.json");
    fs::write(&input_file, input(2).to_string()).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("capture")
        .arg(&entry)
        .args(["--request", "price invoice", "--input"])
        .arg(&input_file)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let case = ExecutionCase::from_json(std::str::from_utf8(&output.stdout).unwrap()).unwrap();
    assert_eq!(case.source().modules.len(), 2);
    let case_file = directory.0.join("case.json");
    fs::write(&case_file, output.stdout).unwrap();
    fs::remove_file(entry).unwrap();
    fs::remove_file(dependency).unwrap();
    fs::remove_file(input_file).unwrap();
    let replay = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("replay")
        .arg(&case_file)
        .output()
        .unwrap();
    assert!(replay.status.success());
    let result: Json = serde_json::from_slice(&replay.stdout).unwrap();
    assert_eq!(result["verified"], true);
    assert_eq!(result["actual"]["result"]["decision"]["total"], "47.88");
    let candidate = directory.0.join("candidate.gwt");
    fs::write(
        &candidate,
        source.replace("subtotal * 0.2", "subtotal * 0.1"),
    )
    .unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("compare")
        .arg(&case_file)
        .arg("--candidate")
        .arg(candidate)
        .output()
        .unwrap();
    assert!(output.status.success());
    let result: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["changes"]["outcome"], true);
    assert_eq!(result["candidate"]["result"]["decision"]["total"], "43.89");
    let mut changed = payload(&case);
    changed["record"]["observed"]["steps"] = json!(0);
    fs::write(&case_file, resign(changed)).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("replay")
        .arg(case_file)
        .output()
        .unwrap();
    assert!(!output.status.success());
    let result: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["verified"], false);
}

#[test]
fn all_refund_comparisons_match_independent_changed_and_preserved_expectations() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../evaluations/maintenance");
    let manifest: Json =
        serde_json::from_str(&fs::read_to_string(root.join("manifest.json")).unwrap()).unwrap();
    let mut count = 0;
    for task in manifest["cases"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|task| task["kind"] == "maintain")
    {
        let before = program(
            &fs::read_to_string(root.join(task["starter"]["gwt"].as_str().unwrap())).unwrap(),
        );
        let after =
            program(&fs::read_to_string(root.join(task["gold"]["gwt"].as_str().unwrap())).unwrap());
        for probe in task["probes"].as_array().unwrap() {
            let case = capture_request(
                &before,
                task["request"].as_str().unwrap(),
                &probe["input"],
                ProgramLimits::default(),
            )
            .unwrap();
            let saved = ExecutionCase::from_json(&case.to_json()).unwrap();
            let comparison = compare_case(&saved, &after).unwrap();
            assert!(comparison.baseline.verified);
            assert_eq!(
                comparison.changes.unwrap().outcome,
                probe["kind"] == "changed",
                "{}: {}",
                task["id"],
                probe["input"]
            );
            assert_eq!(
                comparison.candidate.unwrap().result.unwrap(),
                probe["expected"]
            );
            count += 1;
        }
    }
    assert_eq!(count, 336);
}

#[test]
fn cli_distinguishes_capturing_and_replaying_failure_from_invalid_case_files() {
    let directory = Directory::new();
    let source = directory.0.join("invoice.gwt");
    let input_file = directory.0.join("input.json");
    let case_file = directory.0.join("failure.case.json");
    fs::write(&source, include_str!("fixtures/invoice.gwt")).unwrap();
    fs::write(&input_file, input(0).to_string()).unwrap();
    let capture = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("capture")
        .arg(&source)
        .args(["--request", "price invoice", "--input"])
        .arg(input_file)
        .output()
        .unwrap();
    assert!(capture.status.success());
    let captured: Json = serde_json::from_slice(&capture.stdout).unwrap();
    assert_eq!(captured["record"]["observed"]["ok"], false);
    fs::write(&case_file, capture.stdout).unwrap();
    let replay = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("replay")
        .arg(&case_file)
        .output()
        .unwrap();
    assert!(replay.status.success());
    let report: Json = serde_json::from_slice(&replay.stdout).unwrap();
    assert_eq!(report["verified"], true);
    assert_eq!(report["actual"]["ok"], false);
    let comparison = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("compare")
        .arg(&case_file)
        .arg("--candidate")
        .arg(source)
        .output()
        .unwrap();
    assert!(comparison.status.success());
    let report: Json = serde_json::from_slice(&comparison.stdout).unwrap();
    assert_eq!(report["status"], "compared");
    assert_eq!(report["changes"]["outcome"], false);
    assert_eq!(report["candidate"]["ok"], false);
    let mut broken = captured;
    broken["record"]["input"]["invoice"]["quantity"] = json!(2);
    fs::write(&case_file, broken.to_string()).unwrap();
    let replay = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("replay")
        .arg(case_file)
        .output()
        .unwrap();
    assert!(!replay.status.success());
    let report: Json = serde_json::from_slice(&replay.stdout).unwrap();
    assert_eq!(report["phase"], "load-case");
    assert_eq!(report["diagnostic"]["code"], "case_integrity");
}
