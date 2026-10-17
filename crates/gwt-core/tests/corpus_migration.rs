//! Synthetic protocol responses exercise API invariants; dated qualification uses real engines.
use gwt_core::{
    Corpus, CorpusEntry, CorpusMigration, CorpusMigrationDecisions, ExecutionCase, ProgramLimits,
    SourceBundle, assess_corpus_migration, capture_request, capture_scenario, compile_bundle,
    corpus_integrity, prepare_corpus_migration, promote_corpus_migration,
    render_corpus_migration_html, replay_case,
};
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
const SOURCE: &str = "REQUEST echo\n  GIVEN amount is integer\n  WHEN print amount\n  OUTPUT amount is integer\nSCENARIO exact\nGIVEN amount is 9007199254740993\nREQUEST echo\nTHEN amount == 9007199254740993\n";
fn digest(c: char) -> String {
    format!("sha256:{}", c.to_string().repeat(64))
}
fn hash(domain: &[u8], value: &Json) -> String {
    let mut h = Sha256::new();
    h.update(domain);
    h.update(serde_json::to_vec(value).unwrap());
    format!("sha256:{:x}", h.finalize())
}
fn resign(mut value: Json) -> ExecutionCase {
    value.as_object_mut().unwrap().remove("integrity");
    value["integrity"] = json!(hash(b"gwt-native-case-sha256-v1\0", &value));
    ExecutionCase::from_json(&value.to_string()).unwrap()
}
fn current(scenario: bool) -> ExecutionCase {
    let program = compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), SOURCE.into())]),
    })
    .unwrap();
    if scenario {
        capture_scenario(&program, "exact", ProgramLimits::default()).unwrap()
    } else {
        capture_request(
            &program,
            "echo",
            &json!({"amount":9007199254740993_u64}),
            ProgramLimits::default(),
        )
        .unwrap()
    }
}
fn previous(case: &ExecutionCase, c: char) -> ExecutionCase {
    let mut value = json!(case);
    value["record"]["engine"]["sourceDigest"] = json!(digest(c));
    resign(value)
}
fn entry(id: &str, case: &ExecutionCase) -> CorpusEntry {
    CorpusEntry {
        id: id.into(),
        label: format!("Label for {id}"),
        case: json!(case),
    }
}
fn response(case: &ExecutionCase) -> String {
    json!({"kind":"gwt.native-replay","schemaVersion":1,"verified":true,"differences":[],"differencesTruncated":false,"actual":case.observed()}).to_string()
}
fn prepare(corpus: &Corpus) -> CorpusMigration {
    prepare_corpus_migration(corpus, |case| Ok((response(case), digest('e')))).unwrap()
}
fn accept(report: &CorpusMigration) -> CorpusMigrationDecisions {
    let mut decisions = json!(CorpusMigrationDecisions::pending(report));
    decisions["reviewer"] = json!("Synthetic test reviewer");
    for choice in decisions["decisions"].as_array_mut().unwrap() {
        choice["status"] = json!("accept");
        choice["note"] = json!("Qualification only.");
    }
    CorpusMigrationDecisions::from_json(&decisions.to_string()).unwrap()
}
#[test]
fn mixed_engines_and_current_cases_promote_only_after_complete_review() {
    let original = current(false);
    let old = previous(&original, 'a');
    let mut changed = json!(previous(&current(true), 'b'));
    changed["record"]["observed"]["steps"] = json!(999);
    let changed = resign(changed);
    let corpus = Corpus::new(vec![
        entry("current", &original),
        entry("old", &old),
        entry("different", &changed),
    ])
    .unwrap();
    let frozen = corpus.to_json();
    let mut calls = Vec::new();
    let report = prepare_corpus_migration(&corpus, |case| {
        calls.push(case.engine().source_digest.clone());
        Ok((response(case), digest('e')))
    })
    .unwrap();
    assert_eq!(calls, vec![digest('a'), digest('b')]);
    assert!(report.complete());
    assert_eq!(
        json!(report)["totals"],
        json!({"total":3,"ready":3,"retainedCurrent":1,"observationPreserved":1,"observationChanged":1,"unavailable":0})
    );
    assert!(
        !assess_corpus_migration(&report, &CorpusMigrationDecisions::pending(&report))
            .unwrap()
            .all_accepted
    );
    assert_eq!(
        promote_corpus_migration(&report, &CorpusMigrationDecisions::pending(&report))
            .unwrap_err()
            .code,
        "migration_not_accepted"
    );
    let (promoted, assessment) = promote_corpus_migration(&report, &accept(&report)).unwrap();
    assert!(assessment.all_accepted);
    assert_eq!(corpus.to_json(), frozen);
    for (index, row) in promoted.entries().iter().enumerate() {
        assert_eq!(row.id, corpus.entries()[index].id);
        assert_eq!(row.label, corpus.entries()[index].label);
        let case = ExecutionCase::from_json(&row.case.to_string()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
        if index == 0 {
            assert_eq!(row.case, json!(original));
        } else {
            assert_eq!(row.case["schemaVersion"], 3);
            assert_eq!(
                row.case["record"]["migration"]["parentCaseIntegrity"],
                corpus.entries()[index].case["integrity"]
            );
        }
    }
    assert_ne!(corpus_integrity(&promoted), corpus_integrity(&corpus));
}
#[test]
fn every_failed_entry_remains_visible_and_prevents_export() {
    let old = previous(&current(false), 'a');
    let mut mismatch = json!(current(false));
    mismatch["record"]["observed"]["steps"] = json!(999);
    let mismatch = resign(mismatch);
    let mut incompatible = json!(old);
    incompatible["record"]["source"]["modules"]["rules.gwt"] =
        json!(format!("{SOURCE}\nUNKNOWN old syntax\n"));
    let incompatible = resign(incompatible);
    let corpus = Corpus::new(vec![
        entry("valid", &current(false)),
        CorpusEntry {
            id: "corrupt".into(),
            label: String::new(),
            case: json!({}),
        },
        entry("wrong-current", &mismatch),
        entry("unsupported", &incompatible),
        entry("missing-engine", &previous(&current(false), 'b')),
    ])
    .unwrap();
    let report = prepare_corpus_migration(&corpus, |case| {
        if case.engine().source_digest == digest('b') {
            return Err(gwt_core::source::Diagnostic::new(
                "missing",
                "no selected engine",
                &gwt_core::source::Span {
                    file: "<test>".into(),
                    start: 0,
                    end: 0,
                    line: 1,
                    column: 1,
                },
            ));
        }
        Ok((response(case), digest('e')))
    })
    .unwrap();
    assert!(!report.complete());
    let payload = json!(report);
    assert_eq!(payload["totals"]["total"], 5);
    assert_eq!(payload["totals"]["ready"], 1);
    let statuses: Vec<_> = payload["cases"]
        .as_array()
        .unwrap()
        .iter()
        .map(|r| r["status"].as_str().unwrap())
        .collect();
    assert_eq!(
        statuses,
        vec![
            "current_verified",
            "unavailable",
            "baseline_mismatch",
            "candidate_unavailable",
            "unavailable"
        ]
    );
    let html = render_corpus_migration_html(&report).unwrap();
    assert_eq!(html.matches("value=accept disabled").count(), 4);
    assert!(html.contains("wrong-current"));
    assert!(html.contains("no selected engine"));
    for index in 1..5 {
        let mut choices = json!(CorpusMigrationDecisions::pending(&report));
        choices["reviewer"] = json!("Synthetic");
        choices["decisions"][index]["status"] = json!("accept");
        choices["decisions"][index]["note"] = json!("Must fail");
        assert_eq!(
            assess_corpus_migration(
                &report,
                &CorpusMigrationDecisions::from_json(&choices.to_string()).unwrap()
            )
            .unwrap_err()
            .code,
            "migration_decisions_unavailable"
        );
    }
}
#[test]
fn report_identity_binds_full_corpus_metadata_order_cases_and_engine_bytes() {
    let corpus = Corpus::new(vec![
        entry("one", &previous(&current(false), 'a')),
        entry("two", &current(true)),
    ])
    .unwrap();
    let report = prepare(&corpus);
    let decisions = accept(&report);
    let mut payload = json!(report);
    let expected = payload
        .as_object_mut()
        .unwrap()
        .remove("integrity")
        .unwrap();
    assert_eq!(
        expected,
        json!(hash(b"gwt-native-corpus-migration-sha256-v1\0", &payload))
    );
    assert_eq!(
        corpus_integrity(&corpus),
        hash(b"gwt-native-corpus-sha256-v1\0", &json!(corpus))
    );
    for change in 0..4 {
        let mut value = json!(corpus);
        match change {
            0 => value["cases"][0]["id"] = json!("renamed"),
            1 => value["cases"][0]["label"] = json!("Changed label"),
            2 => value["cases"].as_array_mut().unwrap().reverse(),
            _ => {
                value["cases"].as_array_mut().unwrap().pop();
            }
        }
        let other = prepare(&Corpus::from_json(&value.to_string()).unwrap());
        assert_eq!(
            assess_corpus_migration(&other, &decisions)
                .unwrap_err()
                .code,
            "migration_decisions_stale"
        );
    }
    let changed =
        prepare_corpus_migration(&corpus, |case| Ok((response(case), digest('f')))).unwrap();
    assert_eq!(
        assess_corpus_migration(&changed, &decisions)
            .unwrap_err()
            .code,
        "migration_decisions_stale"
    );
    let mut choice = json!(decisions);
    choice["decisions"].as_array_mut().unwrap().reverse();
    assert!(
        assess_corpus_migration(
            &report,
            &CorpusMigrationDecisions::from_json(&choice.to_string()).unwrap()
        )
        .unwrap()
        .all_accepted
    );
    choice["decisions"].as_array_mut().unwrap().pop();
    assert_eq!(
        assess_corpus_migration(
            &report,
            &CorpusMigrationDecisions::from_json(&choice.to_string()).unwrap()
        )
        .unwrap_err()
        .code,
        "migration_decisions_coverage"
    );
}
#[test]
fn decision_validation_and_every_non_accepting_status_block_promotion() {
    let report = prepare(&Corpus::new(vec![entry("one", &current(false))]).unwrap());
    let accepted = accept(&report);
    let baseline = json!(accepted);
    for status in ["pending", "reject", "needs_information"] {
        let mut value = baseline.clone();
        value["decisions"][0]["status"] = json!(status);
        let decisions = CorpusMigrationDecisions::from_json(&value.to_string()).unwrap();
        assert!(
            !assess_corpus_migration(&report, &decisions)
                .unwrap()
                .all_accepted
        );
        assert_eq!(
            promote_corpus_migration(&report, &decisions)
                .unwrap_err()
                .code,
            "migration_not_accepted"
        );
    }
    for field in [
        "reviewer",
        "note",
        "extra",
        "id",
        "duplicate",
        "unknown",
        "version",
        "digest",
    ] {
        let mut value = baseline.clone();
        match field {
            "reviewer" => value["reviewer"] = json!("\n"),
            "note" => value["decisions"][0]["note"] = json!(" "),
            "extra" => value["unexpected"] = json!(true),
            "id" => value["decisions"][0]["id"] = json!("x".repeat(129)),
            "duplicate" => {
                let row = value["decisions"][0].clone();
                value["decisions"].as_array_mut().unwrap().push(row);
            }
            "unknown" => value["decisions"][0]["status"] = json!("approved"),
            "version" => value["schemaVersion"] = json!(2),
            _ => value["reportIntegrity"] = json!("bad"),
        }
        assert!(
            CorpusMigrationDecisions::from_json(&value.to_string()).is_err(),
            "{field}"
        );
    }
    let duplicated = accepted.to_json().replacen('{', "{\"reviewer\":\"a\",", 1);
    assert!(CorpusMigrationDecisions::from_json(&duplicated).is_err());
    assert!(
        CorpusMigrationDecisions::from_json(&" ".repeat(gwt_core::MAX_DECISIONS_BYTES + 1))
            .is_err()
    );
}
#[test]
fn html_preserves_exact_report_values_and_unique_operand_targets() {
    let id = "</script><img src=x onerror=alert(1)>";
    let corpus = Corpus::new(vec![
        entry(id, &previous(&current(false), 'a')),
        entry("current", &current(true)),
    ])
    .unwrap();
    let report = prepare(&corpus);
    let html = render_corpus_migration_html(&report).unwrap();
    assert!(!html.contains("<img"));
    assert!(html.contains("&lt;img"));
    assert!(html.contains("#case-0-before-event-"));
    assert!(html.contains("#case-0-after-event-"));
    assert!(html.contains("#case-1-current-event-"));
    let raw = html
        .split("<script type=application/json id=report-data>")
        .nth(1)
        .unwrap()
        .split("</script>")
        .next()
        .unwrap();
    let embedded: Json = serde_json::from_str(raw).unwrap();
    assert_eq!(embedded, json!(report));
    assert!(raw.contains("9007199254740993"));
}
#[test]
#[cfg(unix)]
fn cli_mixed_corpus_replays_every_case_and_never_partially_promotes() {
    use std::{fs, os::unix::fs::PermissionsExt, process::Command};
    let root = std::env::temp_dir().join(format!("gwt-corpus-migration-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let original = current(false);
    let old = previous(&original, 'a');
    let corpus = Corpus::new(vec![
        entry("old-a", &old),
        entry("current", &original),
        entry("old-b", &previous(&original, 'b')),
    ])
    .unwrap();
    let path = root.join("corpus.json");
    let decisions = root.join("decisions.json");
    let output = root.join("new.json");
    let map = root.join("engines.json");
    let marker = root.join("calls");
    let html = root.join("review.html");
    fs::write(&path, corpus.to_json()).unwrap();
    let verifier = root.join("verifier");
    fs::write(
        &verifier,
        format!(
            "#!/bin/sh\nprintf x >> '{}'\nprintf '%s' '{}'\n",
            marker.display(),
            response(&old).replace('\'', "'\\''")
        ),
    )
    .unwrap();
    fs::set_permissions(&verifier, fs::Permissions::from_mode(0o700)).unwrap();
    let engines = json!({"kind":"gwt.native-migration-engines","schemaVersion":1,"engines":[{"sourceDigest":digest('a'),"executable":"verifier"},{"sourceDigest":digest('b'),"executable":"verifier"}]});
    fs::write(&map, engines.to_string()).unwrap();
    let run = |command: &str, extra: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .arg(command)
            .arg(&path)
            .arg("--engines")
            .arg(&map)
            .args(extra)
            .output()
            .unwrap()
    };
    let result = run(
        "migrate-corpus",
        &[
            "--html",
            html.to_str().unwrap(),
            "--decisions-template",
            decisions.to_str().unwrap(),
        ],
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    let report: Json = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(report["totals"]["ready"], 3);
    let export_args = [
        "--decisions",
        decisions.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ];
    assert!(
        !run("export-corpus-migration", &export_args)
            .status
            .success()
    );
    assert!(!output.exists());
    let mut choice: Json = serde_json::from_str(&fs::read_to_string(&decisions).unwrap()).unwrap();
    choice["reviewer"] = json!("Synthetic CLI reviewer");
    for item in choice["decisions"].as_array_mut().unwrap() {
        item["status"] = json!("accept");
        item["note"] = json!("Qualification only");
    }
    fs::write(&decisions, choice.to_string()).unwrap();
    assert!(
        run(
            "assess-corpus-migration",
            &["--decisions", decisions.to_str().unwrap()]
        )
        .status
        .success()
    );
    assert!(
        run("export-corpus-migration", &export_args)
            .status
            .success()
    );
    let exported = fs::read_to_string(&output).unwrap();
    let loaded = Corpus::from_json(&exported).unwrap();
    assert_eq!(loaded.entries().len(), 3);
    assert_eq!(loaded.entries()[1].case, json!(original));
    for entry in loaded.entries() {
        assert!(
            replay_case(&ExecutionCase::from_json(&entry.case.to_string()).unwrap())
                .unwrap()
                .verified
        );
    }
    assert!(
        !run("export-corpus-migration", &export_args)
            .status
            .success()
    );
    assert_eq!(fs::read_to_string(&output).unwrap(), exported);
    // Removing an explicitly selected engine retains that case as unavailable.
    let mut missing = engines.clone();
    missing["engines"].as_array_mut().unwrap().pop();
    fs::write(&map, missing.to_string()).unwrap();
    let result = run("migrate-corpus", &[]);
    assert!(!result.status.success());
    let payload: Json = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(
        payload["cases"][2]["diagnostic"]["code"],
        "migration_engine_missing"
    );
    assert_eq!(payload["totals"]["total"], 3);
    fs::remove_file(&output).unwrap();
    assert!(
        !run("export-corpus-migration", &export_args)
            .status
            .success()
    );
    assert!(!output.exists());
    assert_eq!(fs::read_to_string(&marker).unwrap().len(), 12);
    let mut duplicate = engines.clone();
    let row = duplicate["engines"][0].clone();
    duplicate["engines"].as_array_mut().unwrap().push(row);
    fs::write(&map, duplicate.to_string()).unwrap();
    assert!(!run("migrate-corpus", &[]).status.success());
    assert_eq!(fs::read_to_string(&path).unwrap(), corpus.to_json());
    fs::remove_dir_all(root).unwrap();
}
