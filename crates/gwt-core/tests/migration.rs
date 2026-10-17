//! Protocol fixtures are synthetic. The dated migration qualification runs two real engines.
use gwt_core::{
    ExecutionCase, ProgramLimits, SourceBundle, capture_request, capture_scenario, compile_bundle,
    engine_identity, prepare_migration, replay_case,
};
use serde_json::{Value as Json, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

const SOURCE: &str = "REQUEST echo\n  GIVEN amount is integer\n  WHEN print amount\n  OUTPUT amount is integer\nSCENARIO exact\nGIVEN amount is 9007199254740993\nREQUEST echo\nTHEN amount == 9007199254740993\n";
fn digest(c: char) -> String {
    format!("sha256:{}", c.to_string().repeat(64))
}
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
fn resign(mut value: Json) -> ExecutionCase {
    value.as_object_mut().unwrap().remove("integrity");
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-case-sha256-v1\0");
    hash.update(serde_json::to_vec(&value).unwrap());
    value["integrity"] = json!(format!("sha256:{:x}", hash.finalize()));
    ExecutionCase::from_json(&value.to_string()).unwrap()
}
fn previous(mut value: Json) -> ExecutionCase {
    value["record"]["engine"]["sourceDigest"] = json!(digest('a'));
    resign(value)
}
fn report(case: &ExecutionCase) -> String {
    json!({"kind":"gwt.native-replay","schemaVersion":1,"verified":true,"differences":[],"differencesTruncated":false,"actual":case.observed()}).to_string()
}
fn fixture() -> ExecutionCase {
    previous(json!(
        capture_request(
            &program(SOURCE),
            "echo",
            &json!({"amount":9007199254740993_u64}),
            ProgramLimits::default()
        )
        .unwrap()
    ))
}

#[test]
fn request_transition_preserves_original_settings_and_exact_observation() {
    let case = fixture();
    let original = case.to_json();
    assert_eq!(replay_case(&case).unwrap_err().code, "case_engine");
    let proposal = prepare_migration(&case, &report(&case), &digest('b')).unwrap();
    let candidate = proposal.candidate().unwrap();
    assert_eq!(case.to_json(), original);
    assert_eq!(proposal.original().to_json(), original);
    assert_eq!(candidate.source(), case.source());
    assert_eq!(candidate.input(), case.input());
    assert_eq!(json!(candidate.limits()), json!(case.limits()));
    assert_eq!(candidate.request(), case.request());
    assert_eq!(candidate.scenario(), None);
    assert_eq!(candidate.engine(), &engine_identity());
    assert_eq!(candidate.observed(), case.observed());
    assert_eq!(
        candidate.migration().unwrap().parent_case_integrity,
        case.integrity()
    );
    assert_eq!(
        candidate.migration().unwrap().previous_executable_sha256,
        digest('b')
    );
    let loaded = ExecutionCase::from_json(&candidate.to_json()).unwrap();
    assert!(replay_case(&loaded).unwrap().verified);
    let payload = json!(proposal);
    assert_eq!(payload["status"], "observation_preserved");
    assert_eq!(payload["approved"], false);
    assert_eq!(payload["candidate"]["schemaVersion"], 3);
    assert_eq!(
        payload["changes"],
        json!({"source":false,"outcome":false,"state":false,"evidence":false})
    );
}

#[test]
fn scenarios_failed_requests_and_reduced_budgets_remain_distinct_targets() {
    let program = program(SOURCE);
    let mut limits = ProgramLimits::default();
    limits.execution.steps = 0;
    let cases = [
        capture_scenario(&program, "exact", ProgramLimits::default()).unwrap(),
        capture_scenario(&program, "exact", limits).unwrap(),
        capture_request(&program, "echo", &json!({}), ProgramLimits::default()).unwrap(),
        capture_request(&program, "echo", &json!({"amount":9}), limits).unwrap(),
    ];
    for case in cases {
        let old = previous(json!(case));
        let proposal = prepare_migration(&old, &report(&old), &digest('b')).unwrap();
        let new = proposal.candidate().unwrap();
        assert_eq!(new.scenario(), old.scenario());
        assert_eq!(new.request(), old.request());
        assert_eq!(new.observed(), old.observed());
        assert_eq!(json!(new.limits()), json!(old.limits()));
        assert!(replay_case(new).unwrap().verified);
    }
}

#[test]
fn changed_outcome_state_and_evidence_are_reported_without_approval() {
    let old = fixture();
    let mut payload = json!(old);
    payload["record"]["observed"]["result"]["amount"] = json!(1);
    payload["record"]["observed"]["state"]["amount"] = json!(2);
    payload["record"]["observed"]["steps"] = json!(999);
    let old = resign(payload);
    let proposal = prepare_migration(&old, &report(&old), &digest('b')).unwrap();
    let payload = json!(proposal);
    assert_eq!(payload["status"], "observation_changed");
    assert_eq!(payload["approved"], false);
    assert_eq!(
        payload["changes"],
        json!({"source":false,"outcome":true,"state":true,"evidence":true})
    );
    assert!(
        payload["observationDifferences"]
            .as_array()
            .unwrap()
            .iter()
            .any(|d| d["path"] == "/state/amount")
    );
    assert_eq!(
        proposal.candidate().unwrap().observed()["result"]["amount"],
        9007199254740993_u64
    );
}

#[test]
fn baseline_mismatch_wrong_transcript_and_limits_stop_before_recapture() {
    let old = fixture();
    let verified: Json = serde_json::from_str(&report(&old)).unwrap();
    for (path, value) in [
        ("verified", json!(false)),
        ("differencesTruncated", json!(true)),
        ("differences", json!([{}])),
        ("kind", json!("wrong")),
        ("schemaVersion", json!(2)),
        ("actual", json!({})),
        ("extra", json!(true)),
    ] {
        let mut changed = verified.clone();
        changed[path] = value;
        assert_eq!(
            prepare_migration(&old, &changed.to_string(), &digest('b'))
                .unwrap_err()
                .code,
            "migration_baseline"
        );
    }
    assert_eq!(
        prepare_migration(&old, "invalid", &digest('b'))
            .unwrap_err()
            .code,
        "migration_baseline"
    );
    assert_eq!(
        prepare_migration(
            &old,
            &" ".repeat(gwt_core::MAX_BASELINE_REPLAY_BYTES + 1),
            &digest('b')
        )
        .unwrap_err()
        .code,
        "migration_limit"
    );
    assert_eq!(
        prepare_migration(&old, &report(&old), "not-a-digest")
            .unwrap_err()
            .code,
        "migration_executable"
    );
    let current = capture_request(
        &program(SOURCE),
        "echo",
        &json!({"amount":9}),
        ProgramLimits::default(),
    )
    .unwrap();
    assert_eq!(
        prepare_migration(&current, &report(&current), &digest('b'))
            .unwrap_err()
            .code,
        "migration_same_engine"
    );
}

#[test]
fn incompatible_source_retains_a_proposal_without_a_candidate() {
    let old = fixture();
    let mut payload = json!(old);
    payload["record"]["source"]["modules"]["rules.gwt"] =
        json!(format!("{SOURCE}\nUNKNOWN old syntax\n"));
    let old = resign(payload);
    let proposal = prepare_migration(&old, &report(&old), &digest('b')).unwrap();
    assert!(proposal.candidate().is_none());
    assert_eq!(proposal.original().to_json(), old.to_json());
    let payload = json!(proposal);
    assert_eq!(payload["status"], "candidate_unavailable");
    assert!(payload["candidateDiagnostic"].is_object());
    assert!(payload["changes"].is_null());
    let mut bad: Json = serde_json::from_str(&report(&old)).unwrap();
    bad["verified"] = json!(false);
    assert_eq!(
        prepare_migration(&old, &bad.to_string(), &digest('b'))
            .unwrap_err()
            .code,
        "migration_baseline"
    );
}

#[test]
fn provenance_is_versioned_and_chained_and_integrity_covers_the_entire_proposal() {
    let old = fixture();
    let first = prepare_migration(&old, &report(&old), &digest('b')).unwrap();
    let mut payload = json!(first);
    let expected = payload
        .as_object_mut()
        .unwrap()
        .remove("integrity")
        .unwrap();
    let mut hash = Sha256::new();
    hash.update(b"gwt-native-case-migration-sha256-v1\0");
    hash.update(serde_json::to_vec(&payload).unwrap());
    assert_eq!(expected, json!(format!("sha256:{:x}", hash.finalize())));
    let mut intermediate = json!(first.candidate().unwrap());
    intermediate["record"]["engine"]["sourceDigest"] = json!(digest('c'));
    let intermediate = resign(intermediate);
    let next = prepare_migration(&intermediate, &report(&intermediate), &digest('d')).unwrap();
    assert_eq!(
        next.original().migration().unwrap().parent_case_integrity,
        old.integrity()
    );
    assert_eq!(
        next.candidate()
            .unwrap()
            .migration()
            .unwrap()
            .parent_case_integrity,
        intermediate.integrity()
    );
    assert!(replay_case(next.candidate().unwrap()).unwrap().verified);
    for (version, origin) in [
        (1, json!(first.candidate().unwrap().migration().unwrap())),
        (3, Json::Null),
    ] {
        let mut invalid = json!(first.candidate().unwrap());
        invalid["schemaVersion"] = json!(version);
        invalid["record"]["migration"] = origin;
        assert!(ExecutionCase::from_json(&invalid.to_string()).is_err());
    }
    let mut invalid = json!(first.candidate().unwrap());
    invalid["record"]["migration"]["parentCaseIntegrity"] = json!(digest('e'));
    assert_eq!(
        ExecutionCase::from_json(&invalid.to_string())
            .unwrap_err()
            .code,
        "case_integrity"
    );
}

#[test]
fn full_difference_counts_do_not_turn_truncation_into_preservation() {
    let mut payload = json!(fixture());
    payload["record"]["observed"]["output"] = json!((0..200).collect::<Vec<_>>());
    let old = resign(payload);
    let proposal = prepare_migration(&old, &report(&old), &digest('b')).unwrap();
    let payload = json!(proposal);
    assert_eq!(payload["status"], "observation_changed");
    assert_eq!(
        payload["observationDifferences"].as_array().unwrap().len(),
        128
    );
    assert_eq!(payload["observationDifferencesTruncated"], true);
    assert_eq!(payload["outcomeDifferencesTruncated"], true);
}

#[test]
#[cfg(unix)]
fn cli_executes_the_selected_verifier_with_limits_and_preserves_the_original_file() {
    use std::{fs, os::unix::fs::PermissionsExt, process::Command};
    let root = std::env::temp_dir().join(format!("gwt-migration-test-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let old = fixture();
    let path = root.join("case.json");
    fs::write(&path, old.to_json()).unwrap();
    let executable = root.join("trusted-test-verifier");
    let write_script = |body: &str| {
        fs::write(&executable, format!("#!/bin/sh\n{body}\n")).unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o700)).unwrap();
    };
    let run = |timeout: &str| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .arg("migrate")
            .arg(&path)
            .arg("--previous-engine")
            .arg(&executable)
            .arg("--timeout-ms")
            .arg(timeout)
            .output()
            .unwrap()
    };
    // Synthetic trusted-verifier response exercises the CLI protocol, not old-engine correctness.
    write_script(&format!(
        "printf '%s' '{}'",
        report(&old).replace('\'', "'\\''")
    ));
    let result = run("1000");
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stdout)
    );
    let payload: Json = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(payload["approved"], false);
    let candidate = ExecutionCase::from_json(&payload["candidate"].to_string()).unwrap();
    assert!(replay_case(&candidate).unwrap().verified);
    let expected = format!(
        "sha256:{:x}",
        Sha256::digest(fs::read(&executable).unwrap())
    );
    assert_eq!(payload["previousExecutableSha256"], expected);
    for body in [
        "exit 7",
        "exec sleep 5",
        "exec head -c 33554433 /dev/zero",
        "exec head -c 65537 /dev/zero >&2",
    ] {
        write_script(body);
        let result = run(if body.contains("sleep") { "20" } else { "3000" });
        assert!(!result.status.success());
        let payload: Json = serde_json::from_slice(&result.stdout).unwrap();
        assert_eq!(payload["phase"], "previous-engine-replay");
        assert!(payload.get("candidate").is_none());
    }
    write_script("printf '%s' '{}' ");
    let result = run("1000");
    assert!(!result.status.success());
    assert_eq!(
        serde_json::from_slice::<Json>(&result.stdout).unwrap()["phase"],
        "migration"
    );
    // A real, wrong engine must refuse the old fingerprint before any candidate is proposed.
    let result = Command::new(env!("CARGO_BIN_EXE_gwt"))
        .arg("migrate")
        .arg(&path)
        .arg("--previous-engine")
        .arg(env!("CARGO_BIN_EXE_gwt"))
        .output()
        .unwrap();
    assert!(!result.status.success());
    assert_eq!(
        serde_json::from_slice::<Json>(&result.stdout).unwrap()["phase"],
        "previous-engine-replay"
    );
    assert_eq!(fs::read_to_string(&path).unwrap(), old.to_json());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn migration_decisions_require_explicit_review_and_bind_the_exact_transition() {
    use gwt_core::{MigrationDecision, assess_migration};
    let old = fixture();
    let proposal = prepare_migration(&old, &report(&old), &digest('b')).unwrap();
    let pending = MigrationDecision::pending(&proposal);
    assert!(!assess_migration(&proposal, &pending).unwrap().accepted);
    let mut value = json!(pending);
    value["status"] = json!("accept");
    assert_eq!(
        MigrationDecision::from_json(&value.to_string())
            .unwrap_err()
            .code,
        "migration_decision_required"
    );
    value["reviewer"] = json!("Synthetic test reviewer");
    value["note"] = json!("Verified test fixture only.");
    let accepted = MigrationDecision::from_json(&value.to_string()).unwrap();
    let assessment = assess_migration(&proposal, &accepted).unwrap();
    assert!(assessment.accepted);
    assert_eq!(assessment.original_case_integrity, old.integrity());
    assert_eq!(
        assessment.candidate_case_integrity.as_deref(),
        Some(proposal.candidate().unwrap().integrity())
    );
    for status in ["reject", "needs_information", "pending"] {
        value["status"] = json!(status);
        let decision = MigrationDecision::from_json(&value.to_string()).unwrap();
        let other = assess_migration(&proposal, &decision).unwrap();
        assert!(!other.accepted);
        assert_ne!(other.decision_integrity, assessment.decision_integrity);
    }
    // Even an equivalent executable's different bytes require a new decision.
    let other = prepare_migration(&old, &report(&old), &digest('c')).unwrap();
    assert_eq!(
        assess_migration(&other, &accepted).unwrap_err().code,
        "migration_decision_stale"
    );
    let mut changed = json!(old);
    changed["record"]["observed"]["steps"] = json!(999);
    let changed = resign(changed);
    let other = prepare_migration(&changed, &report(&changed), &digest('b')).unwrap();
    assert_eq!(
        assess_migration(&other, &accepted).unwrap_err().code,
        "migration_decision_stale"
    );
}

#[test]
fn migration_decision_parser_refuses_ambiguous_or_unbounded_files() {
    use gwt_core::MigrationDecision;
    let old = fixture();
    let proposal = prepare_migration(&old, &report(&old), &digest('b')).unwrap();
    let template = MigrationDecision::pending(&proposal).to_json();
    let base: Json = serde_json::from_str(&template).unwrap();
    for (field, value) in [
        ("kind", json!("gwt.native-review-decisions")),
        ("schemaVersion", json!(2)),
        ("proposalIntegrity", json!("bad")),
        ("status", json!("approved")),
        ("reviewer", json!("a\nb")),
        ("reviewer", json!("é".repeat(129))),
        ("note", json!("x".repeat(4097))),
        ("extra", json!(true)),
    ] {
        let mut invalid = base.clone();
        invalid[field] = value;
        assert!(
            MigrationDecision::from_json(&invalid.to_string()).is_err(),
            "{field}"
        );
    }
    let duplicate = template.replacen('{', "{\"status\":\"accept\",", 1);
    assert!(MigrationDecision::from_json(&duplicate).is_err());
    let escaped_duplicate = template.replacen('{', "{\"st\\u0061tus\":\"accept\",", 1);
    assert!(MigrationDecision::from_json(&escaped_duplicate).is_err());
    assert!(MigrationDecision::from_json(&format!("{template}{{}}")).is_err());
    assert_eq!(
        MigrationDecision::from_json(&" ".repeat(32769))
            .unwrap_err()
            .code,
        "migration_decision_limit"
    );
}

#[test]
fn migration_html_retains_exact_values_and_source_without_executing_markup() {
    use gwt_core::render_migration_html;
    let source = SOURCE.replace(
        "WHEN print amount",
        "WHEN print amount\n  AND print \"</script><img src=x onerror=alert(1)>\"",
    );
    let old = previous(json!(
        capture_request(
            &program(&source),
            "echo",
            &json!({"amount":9007199254740993_u64}),
            ProgramLimits::default()
        )
        .unwrap()
    ));
    let proposal = prepare_migration(&old, &report(&old), &digest('b')).unwrap();
    let html = render_migration_html(&proposal).unwrap();
    assert!(html.contains("9007199254740993"));
    assert!(!html.contains("<img src=x"));
    assert!(html.contains("&lt;/script&gt;&lt;img"));
    assert!(html.contains("href=\"#before-event-"));
    assert!(html.contains("href=\"#after-event-"));
    assert!(html.contains("<summary>#1 <strong>"));
    let raw = html
        .split("<script type=application/json id=proposal-data>")
        .nth(1)
        .unwrap()
        .split("</script>")
        .next()
        .unwrap();
    let embedded: Json = serde_json::from_str(raw).unwrap();
    assert_eq!(embedded, json!(proposal));
    assert_eq!(
        embedded["original"]["record"]["observed"]["result"]["amount"],
        9007199254740993_u64
    );
}

#[test]
fn unavailable_candidates_can_be_reviewed_but_never_accepted() {
    use gwt_core::{MigrationDecision, assess_migration, render_migration_html};
    let mut value = json!(fixture());
    value["record"]["source"]["modules"]["rules.gwt"] =
        json!(format!("{SOURCE}\nUNKNOWN old syntax\n"));
    let old = resign(value);
    let proposal = prepare_migration(&old, &report(&old), &digest('b')).unwrap();
    let html = render_migration_html(&proposal).unwrap();
    assert!(html.contains("Candidate unavailable"));
    assert!(html.contains("value=accept disabled"));
    let mut decision = json!(MigrationDecision::pending(&proposal));
    decision["reviewer"] = json!("Synthetic reviewer");
    decision["note"] = json!("No current candidate.");
    decision["status"] = json!("accept");
    assert_eq!(
        assess_migration(
            &proposal,
            &MigrationDecision::from_json(&decision.to_string()).unwrap()
        )
        .unwrap_err()
        .code,
        "migration_decision_unavailable"
    );
    decision["status"] = json!("needs_information");
    assert!(
        !assess_migration(
            &proposal,
            &MigrationDecision::from_json(&decision.to_string()).unwrap()
        )
        .unwrap()
        .accepted
    );
}

#[test]
#[cfg(unix)]
fn cli_review_assessment_and_export_reverify_and_never_overwrite() {
    use std::{fs, os::unix::fs::PermissionsExt, process::Command};
    let root =
        std::env::temp_dir().join(format!("gwt-migration-review-test-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let old = fixture();
    let path = root.join("original.json");
    let decision = root.join("decision.json");
    let output = root.join("exported.json");
    let html = root.join("review.html");
    let verifier = root.join("synthetic-verifier");
    let marker = root.join("replay-count");
    fs::write(&path, old.to_json()).unwrap();
    // Synthetic protocol fixture records each fresh invocation.
    let script = format!(
        "#!/bin/sh\nprintf x >> '{}'\nprintf '%s' '{}'\n",
        marker.display(),
        report(&old).replace('\'', "'\\''")
    );
    fs::write(&verifier, &script).unwrap();
    fs::set_permissions(&verifier, fs::Permissions::from_mode(0o700)).unwrap();
    let run = |command: &str, options: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .arg(command)
            .arg(&path)
            .arg("--previous-engine")
            .arg(&verifier)
            .args(options)
            .output()
            .unwrap()
    };
    let result = run(
        "migrate",
        &[
            "--html",
            html.to_str().unwrap(),
            "--decision-template",
            decision.to_str().unwrap(),
        ],
    );
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stderr)
    );
    assert!(
        fs::read_to_string(&html)
            .unwrap()
            .contains("Observation preserved")
    );
    let proposal: Json = serde_json::from_slice(&result.stdout).unwrap();
    let mut choice: Json = serde_json::from_str(&fs::read_to_string(&decision).unwrap()).unwrap();
    let assess_args = ["--decision", decision.to_str().unwrap()];
    let export_args = [
        "--decision",
        decision.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
    ];
    assert!(run("assess-migration", &assess_args).status.success());
    assert!(!run("export-migration", &export_args).status.success());
    assert!(!output.exists());
    for status in ["reject", "needs_information", "accept"] {
        choice["status"] = json!(status);
        choice["reviewer"] = json!("Synthetic CLI reviewer");
        choice["note"] = json!("Protocol qualification only.");
        fs::write(&decision, choice.to_string()).unwrap();
        let assessed = run("assess-migration", &assess_args);
        assert!(assessed.status.success());
        assert_eq!(
            serde_json::from_slice::<Json>(&assessed.stdout).unwrap()["accepted"],
            status == "accept"
        );
        let exported = run("export-migration", &export_args);
        assert_eq!(exported.status.success(), status == "accept");
        assert_eq!(output.exists(), status == "accept");
    }
    let captured = fs::read_to_string(&output).unwrap();
    assert_eq!(
        serde_json::from_str::<Json>(&captured).unwrap(),
        proposal["candidate"]
    );
    assert!(
        replay_case(&ExecutionCase::from_json(&captured).unwrap())
            .unwrap()
            .verified
    );
    assert!(!run("export-migration", &export_args).status.success());
    assert_eq!(fs::read_to_string(&output).unwrap(), captured);
    // Same transcript, different executable bytes: the earlier acceptance is stale.
    fs::write(&verifier, format!("{script}# changed executable\n")).unwrap();
    let stale = run("assess-migration", &assess_args);
    assert!(!stale.status.success());
    assert_eq!(
        serde_json::from_slice::<Json>(&stale.stdout).unwrap()["diagnostic"]["code"],
        "migration_decision_stale"
    );
    fs::remove_file(&output).unwrap();
    assert!(!run("export-migration", &export_args).status.success());
    assert!(!output.exists());
    assert_eq!(fs::read_to_string(&marker).unwrap().len(), 12);
    assert_eq!(fs::read_to_string(&path).unwrap(), old.to_json());
    assert!(
        !run(
            "migrate",
            &["--decision-template", decision.to_str().unwrap()]
        )
        .status
        .success()
    );
    assert_eq!(fs::read_to_string(&decision).unwrap(), choice.to_string());
    fs::remove_dir_all(root).unwrap();
}
