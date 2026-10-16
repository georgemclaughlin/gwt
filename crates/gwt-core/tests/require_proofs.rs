use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, capture_scenario, compare_case, compile_bundle,
    compile_program, explain_execution, replay_case, scenario_from_case, validate_bundle,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_require/rules.gwt");
const BOX: &str = "RECORD Box\n  value: optional<integer>\n";
const CONTACT: &str = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\n  pickup:\n    number: text\n";

fn bundle(source: &str) -> SourceBundle {
    SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    }
}
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&bundle(source)).unwrap()
}
fn aliased(body: &str, helpers: &str) -> String {
    format!(
        "{BOX}REQUEST examine\n  GIVEN box is Box\n  GIVEN replacement is Box\n  WHEN examine box with box and replacement\n  OUTPUT box is Box\nWHEN examine <box> with <alias> and <replacement>\n  GIVEN box is Box\n  AND alias is Box\n  AND replacement is Box\n{body}{helpers}"
    )
}

#[test]
fn transfer_policy_matches_independent_boundaries_and_detects_removed_verification() {
    let p = program(SOURCE);
    let validation = validate_bundle(&bundle(SOURCE), Default::default());
    assert!(validation.ok, "{validation:?}");
    assert_eq!(p.scenario_names().len(), 7);
    let example: Json = serde_json::from_str(include_str!(
        "../../../examples/native_require/request.json"
    ))
    .unwrap();
    assert_eq!(
        p.run_request("prepare transfer", &example, Default::default())
            .result,
        Some(json!({"transfer":{"account":"bank-reference-1","amount":100}}))
    );
    let candidate = program(&SOURCE.replace("REQUIRE facts.method.verified", "REQUIRE true"));
    let methods = [
        Json::Null,
        json!({"kind":"cash","desk":"North"}),
        json!({"kind":"bank","account":"","verified":false}),
        json!({"kind":"bank","account":"","verified":true}),
        json!({"kind":"bank","account":"A","verified":false}),
        json!({"kind":"bank","account":"A","verified":true}),
    ];
    let mut changes = 0;
    for amount in [-1, 0, 1, 100] {
        for method in &methods {
            let input = json!({"facts":{"amount":amount,"method":method}});
            let accepted = amount > 0
                && method["kind"] == "bank"
                && method["verified"] == true
                && method["account"] == "A";
            let case = capture_request(&p, "prepare transfer", &input, Default::default()).unwrap();
            assert_eq!(case.observed()["ok"], accepted, "{input}");
            if accepted {
                assert_eq!(
                    case.observed()["result"],
                    json!({"transfer":{"account":"A","amount":amount}})
                );
            } else {
                assert_eq!(
                    case.observed()["diagnostic"]["code"],
                    "assertion_failed",
                    "{input}"
                );
                assert_eq!(
                    case.observed()["state"]["transfer"],
                    json!({"account":"","amount":0})
                );
            }
            assert!(replay_case(&case).unwrap().verified);
            let generated = scenario_from_case(&case, "reviewed transfer").unwrap();
            assert!(
                compile_bundle(generated.source_bundle())
                    .unwrap()
                    .test_scenarios(Default::default())
                    .iter()
                    .all(|s| s.execution.ok)
            );
            let change = compare_case(&case, &candidate)
                .unwrap()
                .changes
                .unwrap()
                .outcome;
            assert_eq!(
                change,
                amount > 0
                    && method["kind"] == "bank"
                    && method["verified"] == false
                    && method["account"] == "A"
            );
            changes += usize::from(change);
        }
    }
    assert_eq!(changes, 2);
    for scenario in p.scenario_names() {
        let case = capture_scenario(&p, scenario, Default::default()).unwrap();
        assert_eq!(case.observed()["ok"], true);
        assert!(replay_case(&case).unwrap().verified);
    }
}

#[test]
fn sequential_and_compound_assertions_refine_only_proven_paths() {
    for proof in [
        "box.value is present",
        "not (box.value is absent)",
        "box.value is present and box.value >= 0",
        "not (box.value is absent or box.value < 0)",
    ] {
        let source = aliased(&format!("  REQUIRE {proof}\n  add 1 to box.value\n"), "");
        let p = program(&source);
        for value in [0, 4] {
            let run = p.run_request(
                "examine",
                &json!({"box":{"value":value},"replacement":{}}),
                Default::default(),
            );
            assert_eq!(run.result, Some(json!({"box":{"value":value+1}})));
            assert_eq!(
                run.events
                    .iter()
                    .filter(|e| e.operation == "assert")
                    .count(),
                1
            );
        }
        let run = p.run_request(
            "examine",
            &json!({"box":{},"replacement":{}}),
            Default::default(),
        );
        assert_eq!(run.diagnostic.unwrap().code, "assertion_failed");
        assert!(!run.events.iter().any(|e| e.operation == "add"));
    }
    for body in [
        "  REQUIRE box.value is present or true\n  add 1 to box.value\n",
        "  REQUIRE box.value is absent\n  add 1 to box.value\n",
        "  REQUIRE box.value is present\n  add 1 to alias.value\n",
        "  IF true\n    REQUIRE box.value is present\n  add 1 to box.value\n",
        "  REQUIRE box.value is present\n  set box.value to replacement.value\n",
    ] {
        assert!(
            compile_program(&aliased(body, ""), "bad.gwt").is_err(),
            "{body}"
        );
    }
    let nested = "RECORD Inner\n  flag: optional<boolean>\nRECORD Outer\n  inner: optional<Inner>\nWHEN inspect <outer>\n  GIVEN outer is Outer\n  REQUIRE outer.inner is present\n  REQUIRE outer.inner.flag is present\n  REQUIRE not outer.inner.flag\nREQUEST inspect\n  GIVEN outer is Outer\n  WHEN inspect outer\n  OUTPUT outer is Outer\n";
    assert!(
        program(nested)
            .run_request(
                "inspect",
                &json!({"outer":{"inner":{"flag":false}}}),
                Default::default()
            )
            .ok
    );
}

#[test]
fn alias_and_ancestor_mutations_preserve_presence_until_scope_exit() {
    for mutation in [
        "set alias.value to replacement.value",
        "set alias to replacement",
        "replace alias with replacement",
    ] {
        let p = program(&aliased(
            &format!("  REQUIRE box.value is present\n  {mutation}\n  add 1 to box.value\n"),
            "WHEN replace <target> with <replacement>\n  GIVEN target is Box\n  AND replacement is Box\n  set target to replacement\n",
        ));
        let run = p.run_request(
            "examine",
            &json!({"box":{"value":4},"replacement":{}}),
            Default::default(),
        );
        assert_eq!(run.diagnostic.unwrap().code, "presence_mutation");
        assert_eq!(run.state["box"]["value"], 4);
        assert!(!run.events.iter().any(|e| e.operation == "set"));
        let run = p.run_request(
            "examine",
            &json!({"box":{"value":4},"replacement":{"value":10}}),
            Default::default(),
        );
        assert_eq!(run.result, Some(json!({"box":{"value":11}})));
    }
    let nested = "RECORD Inner\n  value: optional<integer>\nRECORD Outer\n  inner: optional<Inner>\nWHEN inspect <outer> with <alias> and <replacement>\n  GIVEN outer is Outer\n  AND alias is Outer\n  AND replacement is Outer\n  REQUIRE outer.inner is present and outer.inner.value is present\n  set alias to replacement\n  add 1 to outer.inner.value\nREQUEST inspect\n  GIVEN outer is Outer\n  GIVEN replacement is Outer\n  WHEN inspect outer with outer and replacement\n  OUTPUT outer is Outer\n";
    for replacement in [json!({}), json!({"inner":{}})] {
        let run = program(nested).run_request(
            "inspect",
            &json!({"outer":{"inner":{"value":3}},"replacement":replacement}),
            Default::default(),
        );
        assert_eq!(run.diagnostic.unwrap().code, "presence_mutation");
        assert_eq!(run.state["outer"]["inner"]["value"], 3);
    }
}

#[test]
fn kind_assertions_protect_allowed_sets_and_compose_with_nested_guards() {
    let source = format!(
        "{CONTACT}WHEN inspect <selected> with <alias> and <replacement>\n  GIVEN selected is Contact\n  AND alias is Contact\n  AND replacement is Contact\n  REQUIRE selected.kind != \"email\"\n  set alias to replacement\n  print selected.number\nREQUEST inspect\n  GIVEN contact is Contact\n  GIVEN replacement is Contact\n  WHEN inspect contact with contact and replacement\n  OUTPUT contact is Contact\n"
    );
    let p = program(&source);
    for kind in ["phone", "pickup"] {
        let replacement = json!({"kind":kind,"number":"new"});
        let run = p.run_request(
            "inspect",
            &json!({"contact":{"kind":"phone","number":"old"},"replacement":replacement}),
            Default::default(),
        );
        assert_eq!(run.result, Some(json!({"contact":replacement})));
        assert_eq!(run.output, vec![json!("new")]);
    }
    let input = json!({"contact":{"kind":"phone","number":"old"},"replacement":{"kind":"email","address":"new"}});
    let run = p.run_request("inspect", &input, Default::default());
    assert_eq!(run.diagnostic.unwrap().code, "kind_mutation");
    assert_eq!(run.state["contact"], input["contact"]);
    assert!(!run.events.iter().any(|e| e.operation == "set"));
    let narrowed = source.replace(
        "  set alias to replacement",
        "  REQUIRE selected.kind == \"phone\"\n  set alias to replacement",
    );
    let input = json!({"contact":{"kind":"phone","number":"old"},"replacement":{"kind":"pickup","number":"new"}});
    assert_eq!(
        program(&narrowed)
            .run_request("inspect", &input, Default::default())
            .diagnostic
            .unwrap()
            .code,
        "kind_mutation"
    );
    let literal_left = source.replace("selected.kind != \"email\"", "\"email\" != selected.kind");
    assert!(
        program(&literal_left)
            .run_request("inspect", &input, Default::default())
            .ok
    );
}

#[test]
fn calls_returns_failures_branches_and_iterations_release_only_their_own_proofs() {
    let common = String::from(
        "RECORD Box\n  tag: text\n  value: optional<integer>\nWHEN replace <box> with <empty>\n  GIVEN box is Box\n  AND empty is Box\n  set box to empty\n",
    );
    for helper in [
        "WHEN inspect <box>\n  GIVEN box is Box\n  REQUIRE box.value is present\n  add 1 to box.value\n",
        "WHEN inspect <box>\n  GIVEN box is Box\n  THEN returns Box\n  REQUIRE box.value is present\n  add 1 to box.value\n  RETURN box\n",
        "WHEN inspect <box>\n  GIVEN box is Box\n  IF true\n    REQUIRE box.value is present\n    add 1 to box.value\n",
    ] {
        let source = format!(
            "{common}{helper}GIVEN box is Box\n  tag: \"box\"\n  value: 1\nGIVEN empty is Box\n  tag: \"empty\"\nWHEN inspect box\nTHEN box.value is present and box.value == 2\nWHEN replace box with empty\nTHEN box.value is absent\n"
        );
        assert!(program(&source).run_scenario("Main", Default::default()).ok);
    }
    let source = format!(
        "{common}WHEN refuse <box>\n  GIVEN box is Box\n  REQUIRE box.value is present\n  add 1 to box.value\n  REQUIRE false\nGIVEN box is Box\n  tag: \"box\"\n  value: 1\nGIVEN empty is Box\n  tag: \"empty\"\nWHEN refuse box\nTHEN fails with \"assertion_failed\"\nAND box.value is present and box.value == 2\nWHEN replace box with empty\nTHEN box.value is absent\n"
    );
    assert!(program(&source).run_scenario("Main", Default::default()).ok);
    let source = aliased(
        "  REQUIRE box.value is present\n  inspect (box)\n  set alias to replacement\n",
        "WHEN inspect <box>\n  GIVEN box is Box\n  REQUIRE box.value is present\n  PASS\n",
    );
    assert_eq!(
        program(&source)
            .run_request(
                "examine",
                &json!({"box":{"value":1},"replacement":{}}),
                Default::default()
            )
            .diagnostic
            .unwrap()
            .code,
        "presence_mutation"
    );
    let source = format!(
        "{BOX}WHEN inspect <boxes> with <empty>\n  GIVEN boxes is list<Box>\n  AND empty is Box\n  FOR box in boxes\n    REQUIRE box.value is present\n    add 1 to box.value\n  FOR box in boxes\n    set box to empty\nREQUEST inspect\n  GIVEN boxes is list<Box>\n  GIVEN empty is Box\n  WHEN inspect boxes with empty\n  OUTPUT boxes is list<Box>\n"
    );
    assert_eq!(
        program(&source)
            .run_request(
                "inspect",
                &json!({"boxes":[{"value":0},{"value":3}],"empty":{}}),
                Default::default()
            )
            .result,
        Some(json!({"boxes":[{"value":null},{"value":null}]}))
    );
}

#[test]
fn root_assertions_backgrounds_contracts_and_caught_failures_keep_scopes_aligned() {
    let source = format!(
        "{BOX}REQUEST inspect\n  GIVEN box is Box\n  WHEN REQUIRE box.value is present\n  AND add 1 to box.value\n  OUTPUT box is Box\n  THEN box.value > 0\nBACKGROUND\nGIVEN box is Box\n  value: 1\nWHEN REQUIRE box.value is present\nSCENARIO increment\nWHEN add 1 to box.value\nTHEN box.value == 2\n"
    );
    let p = program(&source);
    assert!(p.run_scenario("increment", Default::default()).ok);
    assert_eq!(
        p.run_request("inspect", &json!({"box":{"value":0}}), Default::default())
            .result,
        Some(json!({"box":{"value":1}}))
    );
    let source = String::from(
        "RECORD Box\n  tag: text\n  value: optional<integer>\nGIVEN box is Box\n  tag: \"box\"\nWHEN REQUIRE box.value is present\nTHEN fails with \"assertion_failed\"\nAND box.value is absent\n",
    );
    assert!(program(&source).run_scenario("Main", Default::default()).ok);
    let helpers = "WHEN optional <value>\n  GIVEN value is optional<integer>\n  PASS\n";
    assert!(
        compile_program(
            &aliased(
                "  REQUIRE box.value is present\n  optional box.value\n",
                helpers
            ),
            "bad.gwt"
        )
        .is_err()
    );
    assert!(
        program(&aliased(
            "  REQUIRE box.value is present\n  optional (box.value)\n",
            helpers
        ))
        .run_request(
            "examine",
            &json!({"box":{"value":0},"replacement":{}}),
            Default::default()
        )
        .ok
    );
}

#[test]
fn expanded_unicode_sources_and_budgets_preserve_real_assertion_evidence() {
    let source = format!("{BOX}SCENARIO guarded café 😀\nGIVEN box is Box\n  value: <amount>\nWHEN REQUIRE box.value is present\nWHEN add 1 to box.value\nTHEN box.value == <expected>\nEXAMPLES\n  | amount | expected |\n  | 0 | 1 |\n  | 4 | 5 |\n").replace('\n', "\r\n");
    let p = program(&source);
    for name in p.scenario_names() {
        let case = capture_scenario(&p, name, Default::default()).unwrap();
        assert_eq!(case.observed()["ok"], true);
        assert!(replay_case(&case).unwrap().verified);
        let run = p.run_scenario(name, Default::default());
        let asserts: Vec<_> = run
            .events
            .iter()
            .filter(|e| e.operation == "assert")
            .collect();
        assert_eq!(asserts.len(), 2);
        assert_eq!(
            &source[asserts[0].span.start..asserts[0].span.end],
            "REQUIRE box.value is present"
        );
        assert_eq!(
            run.state["box"]["value"],
            if name.ends_with('1') { 1 } else { 5 }
        );
        let explanation = explain_execution(&run, p.source_bundle().unwrap()).unwrap();
        assert!(!serde_json::to_string(&explanation).unwrap().is_empty());
    }
    let p = program(SOURCE);
    let input =
        json!({"facts":{"amount":1,"method":{"kind":"bank","account":"A","verified":true}}});
    let normal = p.run_request("prepare transfer", &input, Default::default());
    assert_eq!(
        normal
            .events
            .iter()
            .filter(|e| e.operation == "assert")
            .count(),
        5
    );
    let mut zero_steps = ProgramLimits::default();
    zero_steps.execution.steps = 0;
    let mut zero_evidence = ProgramLimits::default();
    zero_evidence.execution.evidence_bytes = 0;
    for limits in [zero_steps, zero_evidence] {
        let case = capture_request(&p, "prepare transfer", &input, limits).unwrap();
        assert_eq!(case.observed()["ok"], false);
        assert!(replay_case(&case).unwrap().verified);
    }
}

#[test]
fn kind_proofs_end_on_normal_return_and_caught_failure_without_escaping_to_callers() {
    for (tail, expectation) in [
        ("  print contact.number\n", ""),
        ("  RETURN contact\n", ""),
        (
            "  REQUIRE false\n",
            "THEN fails with \"assertion_failed\"\n",
        ),
    ] {
        let return_contract = if tail.contains("RETURN") {
            "  THEN returns Contact\n"
        } else {
            ""
        };
        let source = format!(
            "{CONTACT}WHEN inspect <contact>\n  GIVEN contact is Contact\n{return_contract}  REQUIRE contact.kind == \"phone\"\n{tail}WHEN replace <contact> with <replacement>\n  GIVEN contact is Contact\n  AND replacement is Contact\n  set contact to replacement\nGIVEN contact is Contact\n  kind: \"phone\"\n  number: \"old\"\nGIVEN replacement is Contact\n  kind: \"email\"\n  address: \"new\"\nWHEN inspect contact\n{expectation}WHEN replace contact with replacement\nTHEN contact.kind == \"email\"\n"
        );
        let run = program(&source).run_scenario("Main", Default::default());
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(
            run.state["contact"],
            json!({"kind":"email","address":"new"})
        );
    }
}
