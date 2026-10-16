use gwt_core::{SourceBundle, capture_request, compare_case, compile_bundle, replay_case};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/pressure_tests/subscription_entitlements.gwt");
const REQUEST: &str = "decide entitlement";

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

fn input(statuses: &[&str], overrides: Json, users: i64) -> Json {
    json!({"account": {
        "account_id":"test", "plan":"pro", "requested_feature":"automations",
        "active_users":users,"seat_limit":1,
        "invoices":statuses.iter().enumerate().map(|(i,status)| json!({
            "invoice_id":format!("invoice-{i}"),"status":status,
            "days_overdue":if *status == "past_due" {0} else {9}
        })).collect::<Vec<_>>(),
        "overrides":overrides
    }})
}

fn decision(due: bool) -> Json {
    json!({"allowed":!due,"matched_override":false,"has_past_due_invoice":due,
        "seat_limit_exceeded":false,"plan_rank":"2","required_plan_rank":"2",
        "status":if due {"blocked"} else {"allowed"},
        "reason":if due {"past_due_invoice"} else {"feature_in_plan"},
        "reasons":if due {vec!["invoice_must_be_paid"]} else {vec![]}})
}

#[test]
fn named_boolean_search_handles_empty_missing_and_later_matches() {
    let compiled = program(SOURCE);
    let mut cases = vec![(vec![], false)];
    for (first, first_due) in [("paid", false), ("past_due", true), ("void", false)] {
        cases.push((vec![first], first_due));
        for (second, second_due) in [("paid", false), ("past_due", true), ("void", false)] {
            cases.push((vec![first, second], first_due || second_due));
        }
    }
    assert_eq!(cases.len(), 13);
    for (statuses, due) in cases {
        let facts = input(&statuses, json!([]), 1);
        let execution = compiled.run_request(REQUEST, &facts, Default::default());
        assert!(execution.ok, "{:?}", execution.diagnostic);
        assert_eq!(execution.result.unwrap(), json!({"decision":decision(due)}));
        assert!(
            execution
                .events
                .iter()
                .any(|event| event.operation == "return" && event.value == due)
        );
        let captured = capture_request(&compiled, REQUEST, &facts, Default::default()).unwrap();
        assert!(replay_case(&captured).unwrap().verified);
    }
}

#[test]
fn scenario_policy_and_reuse_checks_detect_real_regressions() {
    let compiled = program(SOURCE);
    let scenarios = compiled.test_scenarios(Default::default());
    assert_eq!(scenarios.len(), 13);
    assert!(scenarios.iter().all(|s| s.execution.ok));
    let stale = program(&SOURCE.replace("  set decision.seat_limit_exceeded to false\n", ""));
    let reused = stale.run_scenario(
        "decision reuse clears earlier invoice and seat blockers",
        Default::default(),
    );
    assert!(!reused.ok);
    assert_eq!(reused.state["decision"]["seat_limit_exceeded"], true);
    assert_eq!(reused.diagnostic.unwrap().code, "assertion_failed");
}

#[test]
fn captured_witnesses_expose_search_order_status_and_seat_faults() {
    let compiled = program(SOURCE);
    let duplicate = json!([
        {"feature":"automations","active":false,"reason":"first"},
        {"feature":"automations","active":true,"reason":"second"}
    ]);
    let changes = [
        (
            "    RETURN false\n",
            "    RETURN true\n",
            input(&[], json!([]), 1),
        ),
        (
            "WHERE invoice.status == \"past_due\"",
            "WHERE invoice.days_overdue > 0",
            input(&["past_due"], json!([]), 1),
        ),
        (
            "WHERE override.feature == account.requested_feature",
            "WHERE override.feature == account.requested_feature and override.active",
            input(&["past_due"], duplicate, 2),
        ),
        (
            "account.active_users > account.seat_limit",
            "account.active_users >= account.seat_limit",
            input(&[], json!([]), 1),
        ),
    ];
    for (from, to, facts) in changes {
        assert_eq!(SOURCE.matches(from).count(), 1);
        let candidate = program(&SOURCE.replace(from, to));
        let case = capture_request(&compiled, REQUEST, &facts, Default::default()).unwrap();
        let comparison = compare_case(&case, &candidate).unwrap();
        assert!(comparison.changes.unwrap().outcome, "{from}");
    }
}
