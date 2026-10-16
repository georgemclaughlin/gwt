use gwt_core::{
    CompiledProgram, MAX_PROFILE_BYTES, ProgramLimits, SourceBundle, compile_bundle,
    compile_program,
};
use serde_json::{Value as Json, json};
use std::{
    collections::BTreeMap,
    fs,
    process::Command,
    sync::atomic::{AtomicUsize, Ordering},
};

fn program(source: &str) -> CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
const SOURCE: &str = "# café 😀\nRECORD Result\n  values: list<text>\nREQUEST collect\n  GIVEN values is list<text>\n  GIVEN result is Result\n    values: []\n  WHEN collect values into result\n  OUTPUT result is Result\nWHEN collect <values> into <result>\n  GIVEN values is list<text>\n  AND result is Result\n  FOR value in values\n    append value to result.values\n";

#[test]
fn evidence_totals_and_both_groupings_match_independent_serialized_event_accounting() {
    let p = program(SOURCE);
    let input = json!({"values":["TOP_SECRET café 😀\n\"quoted\"","second"]});
    let run = p.run_request("collect", &input, Default::default());
    let report = p
        .profile_request("collect", &input, Default::default())
        .unwrap();
    assert!(report.ok);
    let bytes: usize = run
        .events
        .iter()
        .map(|event| serde_json::to_vec(event).unwrap().len())
        .sum();
    let values: usize = run
        .events
        .iter()
        .map(|event| serde_json::to_vec(&event.value).unwrap().len())
        .sum();
    assert_eq!(report.evidence.bytes, bytes);
    assert_eq!(report.evidence.value_bytes, values);
    assert_eq!(report.evidence.metadata_bytes, bytes - values);
    assert_eq!(report.evidence.events, run.events.len());
    assert_eq!(report.steps, run.steps);
    let mut operations = BTreeMap::<String, (usize, usize, usize)>::new();
    for event in &run.events {
        let row = operations.entry(event.operation.clone()).or_default();
        row.0 += 1;
        row.1 += serde_json::to_vec(event).unwrap().len();
        row.2 += serde_json::to_vec(&event.value).unwrap().len();
    }
    assert_eq!(report.by_operation.len(), operations.len());
    for row in &report.by_operation {
        assert_eq!(
            (row.usage.events, row.usage.bytes, row.usage.value_bytes),
            operations[&row.operation]
        );
    }
    assert_eq!(
        report
            .by_location
            .iter()
            .map(|row| row.usage.bytes)
            .sum::<usize>(),
        bytes
    );
    assert_eq!(
        report
            .by_location
            .iter()
            .map(|row| row.usage.events)
            .sum::<usize>(),
        run.events.len()
    );
    for row in &report.by_location {
        let matching: Vec<_> = run
            .events
            .iter()
            .filter(|event| event.span == row.span)
            .collect();
        assert_eq!(row.usage.events, matching.len());
        assert_eq!(
            row.usage.bytes,
            matching
                .iter()
                .map(|event| serde_json::to_vec(event).unwrap().len())
                .sum::<usize>()
        );
    }
    let payload = report.to_json().unwrap();
    assert!(!payload.to_string().contains("TOP_SECRET"));
    for field in ["state", "result", "output", "events"] {
        assert!(payload.get(field).is_none());
    }
    assert_eq!(payload["programIdentity"], json!(p.identity()));
}

#[test]
fn ordering_is_deterministic_and_uses_source_positions_for_equal_byte_counts() {
    let p = program(SOURCE);
    let input = json!({"values":["a","b","c"]});
    let report = p
        .profile_request("collect", &input, Default::default())
        .unwrap();
    assert_eq!(
        report.to_json().unwrap(),
        p.profile_request("collect", &input, Default::default())
            .unwrap()
            .to_json()
            .unwrap()
    );
    for pair in report.by_operation.windows(2) {
        assert!(pair[0].usage.bytes >= pair[1].usage.bytes);
        if pair[0].usage.bytes == pair[1].usage.bytes {
            assert!(pair[0].operation < pair[1].operation);
        }
    }
    for pair in report.by_location.windows(2) {
        assert!(pair[0].usage.bytes >= pair[1].usage.bytes);
        if pair[0].usage.bytes == pair[1].usage.bytes {
            let a = &pair[0].span;
            let b = &pair[1].span;
            assert!(
                (&a.file, a.start, a.end, a.line, a.column)
                    < (&b.file, b.start, b.end, b.line, b.column)
            );
        }
    }
}

#[test]
fn refusals_keep_actual_limits_and_count_only_retained_events() {
    let p = program(SOURCE);
    let input = json!({"values":["a"]});
    for (steps, evidence) in [(0, 1_048_576), (100_000, 0), (100_000, 400), (100_000, 800)] {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        limits.execution.evidence_bytes = evidence;
        limits.call_depth = 100;
        let run = p.run_request("collect", &input, limits);
        let report = p.profile_request("collect", &input, limits).unwrap();
        assert!(!report.ok);
        assert_eq!(report.diagnostic, run.diagnostic);
        assert_eq!(report.steps, run.steps);
        assert_eq!(report.limits.execution.steps, steps);
        assert_eq!(report.limits.execution.evidence_bytes, evidence);
        assert_eq!(report.effective_call_depth_limit, 64);
        assert_eq!(
            report.evidence.bytes,
            run.events
                .iter()
                .map(|e| serde_json::to_vec(e).unwrap().len())
                .sum::<usize>()
        );
        assert!(report.evidence.bytes <= evidence);
    }
    let invalid = p
        .profile_request("collect", &json!({"values":true}), Default::default())
        .unwrap();
    assert!(!invalid.ok);
    assert_eq!(invalid.steps, 0);
    assert_eq!(invalid.evidence.events, 0);
    assert!(invalid.by_location.is_empty() && invalid.by_operation.is_empty());
    let unknown = p
        .profile_request("missing", &json!({}), Default::default())
        .unwrap();
    assert!(!unknown.ok);
    assert_eq!(unknown.diagnostic.unwrap().code, "unknown_request");
}

#[test]
fn imported_scenarios_and_expanded_rows_keep_original_source_locations() {
    let source = "# café 😀\r\nUSE \"helper.gwt\"\r\nSCENARIO values\r\nGIVEN value is <amount>\r\nWHEN echo value\r\nTHEN prints [<amount>]\r\nEXAMPLES\r\n  | amount |\r\n  | 1 |\r\n  | 2 |\r\n";
    let helper = "WHEN echo <value>\n  GIVEN value is integer\n  print value\n";
    let p = compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([
            ("rules.gwt".into(), source.into()),
            ("helper.gwt".into(), helper.into()),
        ]),
    })
    .unwrap();
    for name in p.scenario_names() {
        let run = p.run_scenario(name, Default::default());
        let report = p.profile_scenario(name, Default::default()).unwrap();
        assert!(report.ok);
        assert_eq!(report.scenario.as_deref(), Some(name));
        assert_eq!(report.steps, run.steps);
        assert!(
            report
                .by_location
                .iter()
                .any(|row| row.span.file == "helper.gwt")
        );
        for row in report.by_location {
            let text = if row.span.file == "helper.gwt" {
                helper
            } else {
                source
            };
            assert!(text.get(row.span.start..row.span.end).is_some());
            assert_eq!(
                text[..row.span.start]
                    .bytes()
                    .filter(|b| *b == b'\n')
                    .count()
                    + 1,
                row.span.line
            );
        }
    }
    let expected =
        program("SCENARIO expected\nWHEN print 1 / 0\nTHEN fails with \"division_by_zero\"\n");
    assert!(
        expected
            .profile_scenario("expected", Default::default())
            .unwrap()
            .ok
    );
}

#[test]
fn oversized_profile_input_and_output_are_refused_without_truncated_groups() {
    let p = program(
        "REQUEST repeat\n  GIVEN rows is list<integer>\n  GIVEN text is text\n  WHEN repeat rows with text\nWHEN repeat <rows> with <text>\n  GIVEN rows is list<integer>\n  AND text is text\n  FOR row in rows\n    LET copied be text\n",
    );
    let input = json!({"rows":vec![1;1200],"text":"x".repeat(4000)});
    let mut limits = ProgramLimits::default();
    limits.execution.evidence_bytes = 16 * 1_048_576;
    assert!(p.run_request("repeat", &input, limits).ok);
    assert_eq!(
        p.profile_request("repeat", &input, limits)
            .unwrap_err()
            .code,
        "profile_limit"
    );
    let mut report = p
        .profile_request(
            "repeat",
            &json!({"rows":[1],"text":"x"}),
            Default::default(),
        )
        .unwrap();
    report.by_operation[0].operation = "x".repeat(MAX_PROFILE_BYTES);
    assert_eq!(report.to_json().unwrap_err().code, "profile_limit");
}

static NEXT: AtomicUsize = AtomicUsize::new(0);
#[test]
fn cli_profiles_requests_scenarios_and_failures_with_the_same_selection_rules_as_run() {
    let root = std::env::temp_dir().join(format!(
        "gwt-profile-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir(&root).unwrap();
    let source = root.join("rules.gwt");
    let input = root.join("input.json");
    fs::write(&source, SOURCE).unwrap();
    fs::write(&input, r#"{"values":["a","b"]}"#).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .args([
            "profile",
            source.to_str().unwrap(),
            "--request",
            "collect",
            "--input",
            input.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let payload: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["kind"], "gwt.native-profile");
    assert_eq!(payload["ok"], true);
    fs::write(&input, r#"{"values":false}"#).unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .args([
            "profile",
            source.to_str().unwrap(),
            "--request",
            "collect",
            "--input",
            input.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(!output.status.success());
    let payload: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["evidence"]["events"], 0);
    fs::write(&source, "SCENARIO one\nWHEN print 1\nTHEN prints [1]\n").unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .args(["profile", source.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(output.status.success());
    let payload: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["scenario"], "one");
    fs::write(
        &source,
        "SCENARIO one\nTHEN true\nSCENARIO two\nTHEN true\n",
    )
    .unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_gwt-native"))
        .args(["profile", source.to_str().unwrap()])
        .output()
        .unwrap();
    assert!(!output.status.success());
    let payload: Json = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(payload["phase"], "selection");
    fs::remove_dir_all(root).unwrap();
    let unbundled = compile_program("REQUEST run\n  WHEN PASS\n", "direct.gwt").unwrap();
    assert!(
        unbundled
            .profile_request("run", &json!({}), Default::default())
            .unwrap()
            .program_identity
            .is_none()
    );
}
