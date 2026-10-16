use gwt_core::{SourceBundle, capture_request, compare_case, compile_bundle, replay_case};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/input_normalization/rules.gwt");
const REQUEST: &str = "normalize contact profile";

fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

fn input(state: &str, middle: Option<Json>) -> Json {
    let mut value =
        json!({"raw":{"name":"Ada","email":"ada@example.com","middle_name_state":state}});
    if let Some(middle) = middle {
        value["raw"]["middle_name"] = middle;
    }
    value
}

#[test]
fn typed_input_keeps_absence_distinct_from_domain_state_and_empty_text() {
    let program = program(SOURCE);
    assert_eq!(program.test_scenarios(Default::default()).len(), 6);
    assert!(
        program
            .test_scenarios(Default::default())
            .iter()
            .all(|s| s.execution.ok)
    );
    for (state, status, name_state, errors) in [
        ("provided", "normalized", "provided", vec![]),
        ("missing", "normalized", "missing", vec![]),
        ("not_applicable", "normalized", "not_applicable", vec![]),
        (
            "unrecognized",
            "invalid",
            "missing",
            vec!["invalid_middle_name_state"],
        ),
    ] {
        for middle in [
            None,
            Some(Json::Null),
            Some(json!("")),
            Some(json!("Lovelace")),
        ] {
            let facts = input(state, middle.clone());
            let run = program.run_request(REQUEST, &facts, Default::default());
            if state == "provided" && matches!(middle, None | Some(Json::Null)) {
                assert!(!run.ok);
                assert_eq!(run.diagnostic.unwrap().code, "assertion_failed");
                assert_eq!(run.state["profile"]["name"], "Ada");
                assert_eq!(run.state["profile"]["middle_name_status"], "missing");
                assert!(run.result.is_none());
            } else {
                assert!(run.ok, "{:?}", run.diagnostic);
                assert_eq!(
                    run.result.unwrap(),
                    json!({"profile":{
                        "name":"Ada","email":"ada@example.com","middle_name_status":name_state,
                        "middle_name":if state == "provided" { middle.unwrap() } else {json!("")},
                        "errors":errors,"error_count":errors.len().to_string(),"status":status
                    }})
                );
            }
            assert!(
                replay_case(
                    &capture_request(&program, REQUEST, &facts, Default::default()).unwrap()
                )
                .unwrap()
                .verified
            );
        }
    }
}

#[test]
fn malformed_fields_are_rejected_before_any_setup_even_when_unused() {
    let program = program(SOURCE);
    let mut malformed = Vec::new();
    for field in ["name", "email", "middle_name_state", "middle_name"] {
        for value in [json!(true), json!(0), json!([]), json!({})] {
            let mut facts = input("missing", None);
            facts["raw"][field] = value;
            malformed.push(facts);
        }
    }
    let mut extra = input("missing", None);
    extra["raw"]["extra"] = json!({});
    malformed.push(extra);
    let mut extra_root = input("missing", None);
    extra_root["extra"] = json!({});
    malformed.push(extra_root);
    malformed.push(json!({}));
    malformed.push(json!({"raw":null}));
    for facts in malformed {
        let run = program.run_request(REQUEST, &facts, Default::default());
        assert!(!run.ok, "{facts}");
        assert!(run.result.is_none());
        assert!(run.events.is_empty());
        assert_eq!(run.state, json!({}));
        let saved = capture_request(&program, REQUEST, &facts, Default::default()).unwrap();
        assert!(replay_case(&saved).unwrap().verified);
    }
}

#[test]
fn retained_cases_reveal_truthiness_and_domain_state_regressions() {
    let baseline = program(SOURCE);
    for (from, to, facts) in [
        (
            "IF raw.middle_name is present",
            "IF raw.middle_name is present and raw.middle_name != \"\"",
            input("provided", Some(json!(""))),
        ),
        (
            "IF raw.middle_name_state == \"not_applicable\"",
            "IF raw.middle_name_state == \"missing\"",
            input("not_applicable", None),
        ),
        (
            "append \"invalid_middle_name_state\" to profile.errors",
            "PASS",
            input("unrecognized", None),
        ),
    ] {
        assert_eq!(SOURCE.matches(from).count(), 1);
        let candidate = program(&SOURCE.replace(from, to));
        let case = capture_request(&baseline, REQUEST, &facts, Default::default()).unwrap();
        assert!(
            compare_case(&case, &candidate)
                .unwrap()
                .changes
                .unwrap()
                .outcome
        );
    }
}
