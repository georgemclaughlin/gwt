use gwt_core::{SourceBundle, capture_request, compare_case, compile_bundle, replay_case};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/pressure_tests/feature_flag_rollout.gwt");
const REQUEST: &str = "evaluate flag";

fn bundle(source: &str) -> SourceBundle {
    SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    }
}

fn facts(bucket: i64, account: bool, kill: bool, overrides: Json, rules: Json) -> Json {
    json!({"request":{"account_id":"acct","flag_key":"dashboard","segment":"beta",
        "bucket":bucket,"account_enabled":account,"kill_switch_active":kill,
        "overrides":overrides,"rollout_rules":rules}})
}

fn rule(segment: &str, percent: i64, enabled: bool) -> Json {
    json!({"segment":segment,"percent":percent,"enabled":enabled})
}

fn decision(reason: &str, prefix: &[&str]) -> Json {
    let enabled = matches!(reason, "override_enabled" | "rollout_rule_enabled");
    let mut reasons = prefix.to_vec();
    reasons.push(reason);
    json!({"enabled":enabled,"matched_override":reason.starts_with("override_"),
        "matched_rule":reason.starts_with("rollout_rule_"),"blocked_by_kill_switch":reason=="kill_switch",
        "status":if reason=="invalid_bucket" {"needs_review"} else if enabled {"enabled"} else {"disabled"},
        "reason":reason,"reasons":reasons})
}

#[test]
fn independent_flag_boundaries_and_precedence_capture_and_replay() {
    let p = compile_bundle(&bundle(SOURCE)).unwrap();
    let override_on =
        json!({"account_id":"acct","flag_key":"dashboard","enabled":true,"reason":"first"});
    let override_off =
        json!({"account_id":"acct","flag_key":"dashboard","enabled":false,"reason":"first"});
    let mut later = override_on.clone();
    later["reason"] = json!("later");
    let cases = [
        (
            facts(-1, false, true, json!([override_on]), json!([])),
            "invalid_bucket",
            vec![],
        ),
        (
            facts(101, true, false, json!([]), json!([rule("all", 100, true)])),
            "invalid_bucket",
            vec![],
        ),
        (
            facts(50, false, true, json!([override_on]), json!([])),
            "account_disabled",
            vec![],
        ),
        (
            facts(50, true, true, json!([override_on]), json!([])),
            "kill_switch",
            vec![],
        ),
        (
            facts(
                50,
                true,
                false,
                json!([override_off, later]),
                json!([rule("all", 100, true)]),
            ),
            "override_disabled",
            vec!["first"],
        ),
        (
            facts(
                50,
                true,
                false,
                json!([override_on, override_off]),
                json!([]),
            ),
            "override_enabled",
            vec!["first"],
        ),
        (
            facts(
                50,
                true,
                false,
                json!([]),
                json!([rule("all", 100, false), rule("beta", 50, true)]),
            ),
            "rollout_rule_enabled",
            vec![],
        ),
        (
            facts(
                51,
                true,
                false,
                json!([]),
                json!([rule("all", 100, false), rule("beta", 50, true)]),
            ),
            "rollout_rule_disabled",
            vec![],
        ),
        (
            facts(51, true, false, json!([]), json!([rule("beta", 50, true)])),
            "no_matching_rule",
            vec![],
        ),
        (
            facts(0, true, false, json!([]), json!([rule("all", 0, true)])),
            "rollout_rule_enabled",
            vec![],
        ),
        (
            facts(1, true, false, json!([]), json!([rule("all", 0, true)])),
            "no_matching_rule",
            vec![],
        ),
        (
            facts(100, true, false, json!([]), json!([rule("all", 100, true)])),
            "rollout_rule_enabled",
            vec![],
        ),
    ];
    for (input, reason, prefix) in cases {
        let case = capture_request(&p, REQUEST, &input, Default::default()).unwrap();
        assert_eq!(case.observed()["ok"], true);
        assert_eq!(
            case.observed()["result"],
            json!({"decision":decision(reason, &prefix)})
        );
        assert!(replay_case(&case).unwrap().verified);
    }
}

#[test]
fn scenario_reuse_and_captured_faults_expose_stale_flags_and_wrong_selection() {
    let p = compile_bundle(&bundle(SOURCE)).unwrap();
    let scenarios = p.test_scenarios(Default::default());
    assert_eq!(scenarios.len(), 10);
    assert!(scenarios.iter().all(|s| s.execution.ok));
    let stale = compile_bundle(&bundle(
        &SOURCE.replace("  set decision.blocked_by_kill_switch to false\n", ""),
    ))
    .unwrap();
    let failed = stale.run_scenario(
        "reusing a decision clears earlier kill switch state",
        Default::default(),
    );
    assert!(!failed.ok);
    assert_eq!(failed.state["decision"]["blocked_by_kill_switch"], true);
    for (before, after, input) in [
        (
            "request.bucket <= rule.percent",
            "request.bucket < rule.percent",
            facts(50, true, false, json!([]), json!([rule("beta", 50, true)])),
        ),
        (
            "override.account_id == request.account_id and override.flag_key == request.flag_key",
            "override.account_id == request.account_id or override.flag_key == request.flag_key",
            facts(
                50,
                true,
                false,
                json!([{"account_id":"other","flag_key":"dashboard","enabled":true,"reason":"unrelated"}]),
                json!([]),
            ),
        ),
        (
            "WHERE rule.enabled == true",
            "WHERE rule.enabled == false",
            facts(
                51,
                true,
                false,
                json!([]),
                json!([rule("all", 100, false), rule("beta", 50, true)]),
            ),
        ),
        (
            "request.bucket < 0",
            "request.bucket <= 0",
            facts(0, true, false, json!([]), json!([rule("all", 0, true)])),
        ),
    ] {
        assert!(SOURCE.contains(before));
        let faulty = compile_bundle(&bundle(&SOURCE.replace(before, after))).unwrap();
        let case = capture_request(&p, REQUEST, &input, Default::default()).unwrap();
        assert!(
            compare_case(&case, &faulty)
                .unwrap()
                .changes
                .unwrap()
                .outcome
        );
    }
}

#[test]
fn reason_helper_uses_the_declared_domain_and_explicit_literal_arguments() {
    let wrapper = "\nREQUEST direct helper\n  GIVEN decision is FlagDecision\n  WHEN enable flag with \"override_enabled\" into decision\n  OUTPUT decision is FlagDecision\n";
    let p = compile_bundle(&bundle(&(SOURCE.to_string() + wrapper))).unwrap();
    let input = json!({"decision":{"enabled":false,"matched_override":false,"matched_rule":false,
        "blocked_by_kill_switch":false,"reasons":[],"status":"new","reason":"new"}});
    let result = p.run_request("direct helper", &input, Default::default());
    assert!(result.ok);
    assert_eq!(
        result.result.unwrap()["decision"]["reason"],
        "override_enabled"
    );
    let invalid = SOURCE.to_string() + &wrapper.replace("\"override_enabled\"", "\"unrecognized\"");
    assert!(compile_bundle(&bundle(&invalid)).is_err());
    let bare = SOURCE.to_string() + &wrapper.replace("\"override_enabled\"", "override_enabled");
    assert_eq!(
        compile_bundle(&bundle(&bare)).unwrap_err().code,
        "unknown_name"
    );
}
