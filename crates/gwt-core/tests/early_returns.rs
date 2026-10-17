use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, capture_scenario, compare_case, compile_bundle,
    compile_program, explain_execution, replay_case, scenario_from_case, validate_bundle,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_early_returns/rules.gwt");
const BOX: &str = "RECORD Box\n  value: optional<integer>\n";
const CONTACT: &str = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\n  pickup:\n    number: text\n  scan:\n    reference: text\n";
fn bundle(source: &str) -> SourceBundle {
    SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    }
}
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&bundle(source)).unwrap()
}
fn boxes(body: &str) -> String {
    format!(
        "{BOX}WHEN choose <selected> with <alias> and <replacement> if <flag>\n  GIVEN selected is Box\n  AND alias is Box\n  AND replacement is Box\n  AND flag is boolean\n  THEN returns integer\n{body}REQUEST choose\n  GIVEN box is Box\n  GIVEN replacement is Box\n  GIVEN flag is boolean\n  WHEN LET answer be choose box with box and replacement if flag\n  OUTPUT box is Box\n  OUTPUT answer is integer\n"
    )
}
fn input(value: Json, replacement: Json) -> Json {
    json!({"box":{"value":value},"replacement":replacement,"flag":true})
}

#[test]
fn exchange_policy_matches_independent_precedence_and_window_boundaries() {
    let p = program(SOURCE);
    assert!(validate_bundle(&bundle(SOURCE), Default::default()).ok);
    assert_eq!(p.scenario_names().len(), 8);
    let mut proofs = vec![Json::Null, json!({"kind":"gift","reference":"G"})];
    for age in [-1, 0, 30, 31] {
        for verified in [false, true] {
            proofs.push(json!({"kind":"receipt","age_days":age,"verified":verified}));
        }
    }
    let candidate = program(&SOURCE.replace("age_days > 30", "age_days >= 30"));
    let mut changed = 0;
    for allowed in [false, true] {
        for proof in &proofs {
            let expected = if !allowed {
                "disabled"
            } else if proof.is_null() {
                "missing_proof"
            } else if proof["kind"] == "gift" {
                "gift_route"
            } else if proof["verified"] == false {
                "unverified"
            } else if proof["age_days"].as_i64().unwrap() < 0 {
                "invalid_age"
            } else if proof["age_days"].as_i64().unwrap() > 30 {
                "outside_window"
            } else {
                "eligible"
            };
            let input = json!({"facts":{"allow_exchanges":allowed,"proof":proof}});
            let case = capture_request(&p, "assess exchange", &input, Default::default()).unwrap();
            assert_eq!(case.observed()["ok"], true);
            assert_eq!(case.observed()["result"], json!({"decision":expected}));
            assert!(replay_case(&case).unwrap().verified);
            let change = compare_case(&case, &candidate)
                .unwrap()
                .changes
                .unwrap()
                .outcome;
            assert_eq!(
                change,
                allowed
                    && proof["kind"] == "receipt"
                    && proof["verified"] == true
                    && proof["age_days"] == 30
            );
            changed += usize::from(change);
            let generated = scenario_from_case(&case, "reviewed exchange").unwrap();
            assert!(
                compile_bundle(generated.source_bundle())
                    .unwrap()
                    .test_scenarios(Default::default())
                    .iter()
                    .all(|s| s.execution.ok)
            );
        }
    }
    assert_eq!(changed, 1);
    for name in p.scenario_names() {
        let case = capture_scenario(&p, name, Default::default()).unwrap();
        assert_eq!(case.observed()["ok"], true);
        assert!(replay_case(&case).unwrap().verified);
    }
}

#[test]
fn if_guard_clauses_refine_both_surviving_sides_and_nested_returns() {
    for branch in [
        "  IF selected.value is absent\n    RETURN -1\n",
        "  IF selected.value is absent\n    RETURN -1\n  ELSE\n    PASS\n",
        "  IF selected.value is present\n    PASS\n  ELSE\n    RETURN -1\n",
        "  IF selected.value is absent\n    IF flag\n      RETURN -1\n    ELSE\n      RETURN -1\n",
    ] {
        let p = program(&boxes(&format!(
            "{branch}  add 1 to selected.value\n  RETURN selected.value\n"
        )));
        for value in [Json::Null, json!(0), json!(4)] {
            let run = p.run_request(
                "choose",
                &input(value.clone(), json!({})),
                Default::default(),
            );
            assert!(run.ok, "{branch}: {:?}", run.diagnostic);
            assert_eq!(
                run.result.as_ref().unwrap()["answer"],
                value.as_i64().map(|n| n + 1).unwrap_or(-1)
            );
            assert_eq!(
                run.events
                    .iter()
                    .filter(|e| e.operation == "return")
                    .count(),
                1
            );
        }
    }
    let nested = "RECORD Inner\n  value: optional<integer>\nRECORD Outer\n  inner: optional<Inner>\nWHEN choose <outer>\n  GIVEN outer is Outer\n  THEN returns integer\n  IF outer.inner is absent or outer.inner.value is absent\n    RETURN -1\n  RETURN outer.inner.value\nREQUEST choose\n  GIVEN outer is Outer\n  WHEN LET answer be choose outer\n  OUTPUT answer is integer\n";
    for (outer, expected) in [
        (json!({}), -1),
        (json!({"inner":{}}), -1),
        (json!({"inner":{"value":0}}), 0),
    ] {
        assert_eq!(
            program(nested)
                .run_request("choose", &json!({"outer":outer}), Default::default())
                .result,
            Some(json!({"answer":expected}))
        );
    }
}

#[test]
fn decision_continuations_keep_only_common_presence_on_surviving_paths() {
    let branch = "  DECIDE\n    WHEN selected.value is absent\n      RETURN -1\n    WHEN flag\n      PASS\n    ELSE\n      PASS\n";
    let p = program(&boxes(&format!(
        "{branch}  set alias to replacement\n  RETURN selected.value\n"
    )));
    for flag in [false, true] {
        let mut data = input(json!(2), json!({"value":7}));
        data["flag"] = json!(flag);
        assert_eq!(
            p.run_request("choose", &data, Default::default()).result,
            Some(json!({"box":{"value":7},"answer":7}))
        );
        data["replacement"] = json!({});
        let run = p.run_request("choose", &data, Default::default());
        assert_eq!(run.diagnostic.unwrap().code, "presence_mutation");
        assert_eq!(run.state["box"]["value"], 2);
        assert!(!run.events.iter().any(|e| e.operation == "set"));
    }
    for body in [
        "  DECIDE\n    WHEN selected.value is present\n      PASS\n    WHEN flag\n      PASS\n    ELSE\n      RETURN -1\n  RETURN selected.value\n",
        "  IF selected.value is absent\n    REQUIRE not true\n  RETURN selected.value\n",
        "  IF flag\n    RETURN 1\n  ELSE\n    RETURN 2\n  RETURN selected.value\n",
    ] {
        assert!(compile_program(&boxes(body), "bad.gwt").is_err(), "{body}");
    }
    let loop_guard = "WHEN choose <value> using <items>\n  GIVEN value is optional<integer>\n  AND items is list<integer>\n  THEN returns integer\n  IF value is absent\n    FOR item in items\n      RETURN -1\n  RETURN value\n";
    let error = compile_program(loop_guard, "bad.gwt").unwrap_err();
    assert_eq!(error.code, "assignment_type");
}

#[test]
fn decisions_and_kind_dispatch_join_surviving_kind_sets_with_mutation_guards() {
    for branch in [
        "  DECIDE\n    WHEN selected.kind == \"email\"\n      RETURN \"email\"\n    WHEN selected.kind == \"phone\"\n      PASS\n    WHEN selected.kind == \"pickup\"\n      PASS\n    ELSE\n      RETURN \"scan\"\n",
        "  DEPENDING ON selected\n    WHEN the kind is email\n      RETURN \"email\"\n    WHEN the kind is phone\n      PASS\n    WHEN the kind is pickup\n      PASS\n    ELSE\n      RETURN \"scan\"\n",
    ] {
        let source = format!(
            "{CONTACT}WHEN choose <selected> with <alias> and <replacement>\n  GIVEN selected is Contact\n  AND alias is Contact\n  AND replacement is Contact\n  THEN returns text\n{branch}  set alias to replacement\n  RETURN selected.number\nREQUEST choose\n  GIVEN contact is Contact\n  GIVEN replacement is Contact\n  WHEN LET answer be choose contact with contact and replacement\n  OUTPUT contact is Contact\n  OUTPUT answer is text\n"
        );
        let p = program(&source);
        for initial in ["phone", "pickup"] {
            for kind in ["phone", "pickup", "email"] {
                let replacement = if kind == "email" {
                    json!({"kind":kind,"address":"new"})
                } else {
                    json!({"kind":kind,"number":"new"})
                };
                let run = p.run_request(
                    "choose",
                    &json!({"contact":{"kind":initial,"number":"old"},"replacement":replacement}),
                    Default::default(),
                );
                if kind == "email" {
                    assert_eq!(run.diagnostic.unwrap().code, "kind_mutation");
                    assert_eq!(run.state["contact"]["number"], "old");
                } else {
                    assert_eq!(
                        run.result,
                        Some(json!({"contact":replacement,"answer":"new"}))
                    );
                }
            }
        }
    }
    // Sequential exclusions intersect inside one path before alternatives union.
    let source = format!(
        "{CONTACT}WHEN choose <contact>\n  GIVEN contact is Contact\n  THEN returns text\n  IF contact.kind == \"email\"\n    RETURN \"email\"\n  IF contact.kind == \"scan\"\n    RETURN \"scan\"\n  IF contact.kind == \"pickup\"\n    RETURN \"pickup\"\n  RETURN contact.number\nREQUEST choose\n  GIVEN contact is Contact\n  WHEN LET answer be choose contact\n  OUTPUT answer is text\n"
    );
    assert_eq!(
        program(&source)
            .run_request(
                "choose",
                &json!({"contact":{"kind":"phone","number":"P"}}),
                Default::default()
            )
            .result,
        Some(json!({"answer":"P"}))
    );
}

#[test]
fn first_match_returns_prove_only_surviving_outer_paths() {
    let branch =
        "  FIND item in [1, 2] WHERE selected.value is present\n    PASS\n  ELSE\n    RETURN -1\n";
    let p = program(&boxes(&format!(
        "{branch}  set alias to replacement\n  RETURN selected.value\n"
    )));
    assert_eq!(
        p.run_request("choose", &input(Json::Null, json!({})), Default::default())
            .result
            .unwrap()["answer"],
        -1
    );
    assert_eq!(
        p.run_request(
            "choose",
            &input(json!(1), json!({"value":4})),
            Default::default()
        )
        .result
        .unwrap()["answer"],
        4
    );
    assert_eq!(
        p.run_request("choose", &input(json!(1), json!({})), Default::default())
            .diagnostic
            .unwrap()
            .code,
        "presence_mutation"
    );
    for body in [
        "  FIND item in [1, 2] WHERE selected.value is present\n    PASS\n  ELSE\n    RETURN -1\n  RETURN item\n",
        "  FIND item in [1, 2] WHERE selected.value is absent\n    RETURN -1\n  ELSE\n    PASS\n  RETURN selected.value\n",
        "  FOR item in [1, 2] WHERE selected.value is present\n    PASS\n  RETURN selected.value\n",
    ] {
        assert!(compile_program(&boxes(body), "bad.gwt").is_err(), "{body}");
    }
    // A returning FIND on both paths makes its containing IF a return guard.
    let p = program(&boxes(
        "  IF selected.value is absent\n    FIND item in [1] WHERE true\n      RETURN -1\n    ELSE\n      RETURN -1\n  RETURN selected.value\n",
    ));
    assert_eq!(
        p.run_request("choose", &input(json!(0), json!({})), Default::default())
            .result
            .unwrap()["answer"],
        0
    );
}

#[test]
fn continuation_guards_release_on_return_failure_and_loop_body_exit() {
    let common = "RECORD Box\n  label: text\n  value: optional<integer>\nWHEN replace <box> with <empty>\n  GIVEN box is Box\n  AND empty is Box\n  set box to empty\n";
    for tail in [
        "  RETURN box.value\n",
        "  REQUIRE false\n  RETURN box.value\n",
    ] {
        let expectation = if tail.contains("REQUIRE") {
            "THEN fails with \"assertion_failed\"\n"
        } else {
            ""
        };
        let source = format!(
            "{common}WHEN choose <box>\n  GIVEN box is Box\n  THEN returns integer\n  IF box.value is absent\n    RETURN -1\n  add 1 to box.value\n{tail}GIVEN box is Box\n  label: \"box\"\n  value: 1\nGIVEN empty is Box\n  label: \"empty\"\nWHEN choose box\n{expectation}THEN box.value is present and box.value == 2\nWHEN replace box with empty\nTHEN box.value is absent\n"
        );
        let run = program(&source).run_scenario("Main", Default::default());
        assert!(run.ok, "{:?}", run.diagnostic);
    }
    let body = "  IF selected.value is absent\n    RETURN -1\n  FOR item in [1, 2]\n    IF replacement.value is absent\n      RETURN -2\n    add item to replacement.value\n  set alias to replacement\n  RETURN selected.value\n";
    let run = program(&boxes(body)).run_request(
        "choose",
        &input(json!(1), json!({"value":0})),
        Default::default(),
    );
    assert_eq!(run.result, Some(json!({"box":{"value":3},"answer":3})));
    let source = boxes(
        "  REQUIRE selected.value is present\n  helper (selected)\n  set alias to replacement\n  RETURN selected.value\n",
    ) + "WHEN helper <box>\n  GIVEN box is Box\n  THEN returns integer\n  IF box.value is absent\n    RETURN -1\n  RETURN box.value\n";
    assert_eq!(
        program(&source)
            .run_request("choose", &input(json!(1), json!({})), Default::default())
            .diagnostic
            .unwrap()
            .code,
        "presence_mutation"
    );
}

#[test]
fn continuation_evidence_preserves_source_short_circuit_and_execution_budgets() {
    let source = SOURCE.replace('\n', "\r\n");
    let p = program(&source);
    for input in [
        json!({"facts":{"allow_exchanges":true}}),
        json!({"facts":{"allow_exchanges":true,"proof":{"kind":"gift","reference":"G"}}}),
        json!({"facts":{"allow_exchanges":true,"proof":{"kind":"receipt","age_days":30,"verified":true}}}),
    ] {
        let run = p.run_request("assess exchange", &input, Default::default());
        assert!(run.ok);
        assert_eq!(
            run.events
                .iter()
                .filter(|e| e.operation == "return")
                .count(),
            1
        );
        assert!(!run.events.iter().any(|e| e.operation == "assert"));
        if input["facts"]["proof"].is_null() {
            assert!(
                !run.events
                    .iter()
                    .any(|e| e.operation.starts_with("read facts.proof."))
            );
        }
        for event in &run.events {
            assert!(source.get(event.span.start..event.span.end).is_some());
        }
        explain_execution(&run, p.source_bundle().unwrap()).unwrap();
        for steps in 0..=run.steps {
            let mut limits = ProgramLimits::default();
            limits.execution.steps = steps;
            let case = capture_request(&p, "assess exchange", &input, limits).unwrap();
            assert_eq!(case.observed()["ok"], steps == run.steps);
            assert!(replay_case(&case).unwrap().verified);
        }
    }
}

#[test]
fn joined_optional_kind_paths_protect_ancestors_and_keep_allowed_replacements() {
    let source = format!(
        "{CONTACT}RECORD Envelope\n  contact: optional<Contact>\nWHEN choose <selected> with <alias> and <replacement>\n  GIVEN selected is Envelope\n  AND alias is Envelope\n  AND replacement is Envelope\n  THEN returns text\n  DECIDE\n    WHEN selected.contact is absent\n      RETURN \"missing\"\n    WHEN selected.contact.kind == \"email\"\n      RETURN \"email\"\n    WHEN selected.contact.kind == \"phone\"\n      PASS\n    WHEN selected.contact.kind == \"pickup\"\n      PASS\n    ELSE\n      RETURN \"scan\"\n  set alias to replacement\n  RETURN selected.contact.number\nREQUEST choose\n  GIVEN envelope is Envelope\n  GIVEN replacement is Envelope\n  WHEN LET answer be choose envelope with envelope and replacement\n  OUTPUT envelope is Envelope\n  OUTPUT answer is text\n"
    );
    let p = program(&source);
    for (replacement, error) in [
        (json!({}), Some("presence_mutation")),
        (
            json!({"contact":{"kind":"email","address":"new"}}),
            Some("kind_mutation"),
        ),
        (json!({"contact":{"kind":"pickup","number":"new"}}), None),
    ] {
        let original = json!({"contact":{"kind":"phone","number":"old"}});
        let run = p.run_request(
            "choose",
            &json!({"envelope":original,"replacement":replacement}),
            Default::default(),
        );
        if let Some(code) = error {
            assert_eq!(run.diagnostic.unwrap().code, code);
            assert_eq!(run.state["envelope"], original);
        } else {
            assert_eq!(
                run.result,
                Some(json!({"envelope":replacement,"answer":"new"}))
            );
        }
    }
    let helpers = "WHEN passthrough <value>\n  GIVEN value is integer\n  THEN returns integer\n  RETURN value\n";
    let wrong =
        boxes("  IF selected.value is absent\n    passthrough -1\n  RETURN selected.value\n")
            + helpers;
    assert!(compile_program(&wrong, "bad.gwt").is_err());
}
