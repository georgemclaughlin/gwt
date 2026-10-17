use gwt_core::{
    EditorQuery, ProgramLimits, SourceBundle, capture_request, check_editor_query, compare_case,
    compile_bundle, compile_program, explain_execution, replay_case, scenario_from_case,
    validate_bundle,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_branch_proofs/rules.gwt");
const BOX: &str = "RECORD Box\n  value: optional<integer>\n";
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
fn input(flag: bool, value: Json, replacement: Json) -> Json {
    json!({"box":{"value":value},"replacement":replacement,"flag":flag})
}

#[test]
fn collection_authorization_matches_independent_policy_and_fault_boundaries() {
    let p = program(SOURCE);
    assert!(validate_bundle(&bundle(SOURCE), Default::default()).ok);
    assert_eq!(p.scenario_names().len(), 7);
    let candidate = program(&SOURCE.replace("REQUIRE facts.locker_checked", "REQUIRE true"));
    let mut changes = 0;
    for mode in ["counter", "locker"] {
        for staff in [false, true] {
            for locker in [false, true] {
                for proof in [
                    Json::Null,
                    json!({"kind":"gift","message":"G"}),
                    json!({"kind":"receipt","reference":""}),
                    json!({"kind":"receipt","reference":"R"}),
                ] {
                    let accepted = (if mode == "counter" { staff } else { locker })
                        && proof["kind"] == "receipt"
                        && proof["reference"] == "R";
                    let input = json!({"facts":{"mode":mode,"staff_checked":staff,"locker_checked":locker,"proof":proof}});
                    let case =
                        capture_request(&p, "authorize collection", &input, Default::default())
                            .unwrap();
                    assert_eq!(case.observed()["ok"], accepted);
                    if accepted {
                        assert_eq!(case.observed()["result"], json!({"reference":"R"}));
                    } else {
                        assert_eq!(case.observed()["diagnostic"]["code"], "assertion_failed");
                    }
                    assert!(replay_case(&case).unwrap().verified);
                    let generated = scenario_from_case(&case, "reviewed collection").unwrap();
                    assert!(
                        compile_bundle(generated.source_bundle())
                            .unwrap()
                            .test_scenarios(Default::default())
                            .iter()
                            .all(|row| row.execution.ok)
                    );
                    let changed = compare_case(&case, &candidate)
                        .unwrap()
                        .changes
                        .unwrap()
                        .outcome;
                    assert_eq!(
                        changed,
                        mode == "locker"
                            && !locker
                            && proof["kind"] == "receipt"
                            && proof["reference"] == "R"
                    );
                    changes += usize::from(changed);
                }
            }
        }
    }
    assert_eq!(changes, 2);
}

#[test]
fn if_decide_and_nested_guards_promote_common_body_exit_proofs() {
    for branch in [
        "  IF flag\n    REQUIRE selected.value is present\n  ELSE\n    REQUIRE selected.value is present\n",
        "  IF flag\n    REQUIRE selected.value is present\n  ELSE\n    RETURN -1\n",
        "  IF flag\n    IF selected.value is absent\n      RETURN -1\n  ELSE\n    REQUIRE selected.value is present\n",
        "  DECIDE\n    WHEN flag\n      REQUIRE selected.value is present\n    ELSE\n      IF selected.value is absent\n        RETURN -1\n",
        "  DEPENDING ON flag\n    WHEN the value is true\n      REQUIRE selected.value is present\n    WHEN the value is false\n      REQUIRE selected.value is present\n",
        "  DEPENDING ON 1\n    WHEN the value is 1\n      REQUIRE selected.value is present\n    ELSE\n      REQUIRE selected.value is present\n",
    ] {
        let p = program(&boxes(&format!(
            "{branch}  set alias to replacement\n  RETURN selected.value\n"
        )));
        for flag in [false, true] {
            let run = p.run_request(
                "choose",
                &input(flag, json!(2), json!({"value":7})),
                Default::default(),
            );
            assert!(run.ok, "{branch}: {:?}", run.diagnostic);
            assert_eq!(
                run.result.as_ref().unwrap()["answer"],
                if !flag && branch.contains("ELSE\n    RETURN -1") {
                    -1
                } else {
                    7
                }
            );
            let run = p.run_request(
                "choose",
                &input(flag, json!(2), json!({})),
                Default::default(),
            );
            if !flag && branch.contains("ELSE\n    RETURN -1") {
                assert!(run.ok);
            } else {
                assert_eq!(run.diagnostic.unwrap().code, "presence_mutation");
                assert_eq!(run.state["box"]["value"], 2);
                assert!(!run.events.iter().any(|event| event.operation == "set"));
            }
        }
    }
}

#[test]
fn find_joins_both_exits_but_never_promotes_item_locals_or_zero_iteration_proofs() {
    for values in [json!([]), json!([1])] {
        for (index, branch) in [
            "  FIND item in items WHERE true\n    REQUIRE selected.value is present\n  ELSE\n    REQUIRE selected.value is present\n",
            "  FIND item in items WHERE true\n    RETURN -1\n  ELSE\n    REQUIRE selected.value is present\n",
            "  FIND item in items WHERE true\n    REQUIRE selected.value is present\n  ELSE\n    RETURN -1\n",
        ].iter().enumerate() {
            let source = boxes(&format!("{branch}  RETURN selected.value\n"))
                .replace("if <flag>", "if <flag> from <items>")
                .replace("  AND flag is boolean\n", "  AND flag is boolean\n  AND items is list<integer>\n")
                .replace("  GIVEN flag is boolean\n", "  GIVEN flag is boolean\n  GIVEN items is list<integer>\n")
                .replace("replacement if flag\n", "replacement if flag from items\n");
            let p = program(&source);
            let mut data = input(true, json!(3), json!({}));
            data["items"] = values.clone();
            let run = p.run_request("choose", &data, Default::default());
            assert!(run.ok, "{source}: {:?}", run.diagnostic);
            let empty = values.as_array().unwrap().is_empty();
            assert_eq!(run.result.unwrap()["answer"], if index == 1 && !empty || index == 2 && empty { -1 } else { 3 });
        }
    }
    for branch in [
        "  IF flag\n    REQUIRE selected.value is present\n",
        "  IF flag\n    REQUIRE selected.value is present\n  ELSE\n    PASS\n",
        "  FOR item in [1, 2]\n    REQUIRE selected.value is present\n",
        "  FIND item in [1] WHERE true\n    REQUIRE selected.value is present\n  ELSE\n    PASS\n",
        "  IF flag\n    LET copy be selected\n    REQUIRE copy.value is present\n  ELSE\n    LET copy be selected\n    REQUIRE copy.value is present\n",
        "  IF flag\n    REQUIRE not true\n  ELSE\n    REQUIRE selected.value is present\n",
    ] {
        assert!(
            compile_program(
                &boxes(&format!("{branch}  RETURN selected.value\n")),
                "bad.gwt"
            )
            .is_err(),
            "{branch}"
        );
    }
}

#[test]
fn kind_sets_intersect_within_branches_and_union_across_continuations() {
    let declarations = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\n  pickup:\n    number: text\nRECORD Envelope\n  contact: optional<Contact>\n";
    let source = format!(
        "{declarations}WHEN choose <selected> with <alias> and <replacement> if <flag>\n  GIVEN selected is Envelope\n  AND alias is Envelope\n  AND replacement is Envelope\n  AND flag is boolean\n  THEN returns text\n  IF flag\n    REQUIRE selected.contact is present\n    REQUIRE selected.contact.kind != \"pickup\"\n    REQUIRE selected.contact.kind != \"email\"\n  ELSE\n    REQUIRE selected.contact is present\n    REQUIRE selected.contact.kind != \"email\"\n  set alias to replacement\n  RETURN selected.contact.number\nREQUEST choose\n  GIVEN envelope is Envelope\n  GIVEN replacement is Envelope\n  GIVEN flag is boolean\n  WHEN LET answer be choose envelope with envelope and replacement if flag\n  OUTPUT envelope is Envelope\n  OUTPUT answer is text\n"
    );
    let p = program(&source);
    for flag in [false, true] {
        for replacement in [
            json!({"kind":"phone","number":"P"}),
            json!({"kind":"pickup","number":"D"}),
            json!({"kind":"email","address":"E"}),
            Json::Null,
        ] {
            let data = json!({"envelope":{"contact":{"kind":"phone","number":"old"}},"replacement":{"contact":replacement},"flag":flag});
            let case = capture_request(&p, "choose", &data, Default::default()).unwrap();
            let accepted = replacement["kind"] == "phone" || replacement["kind"] == "pickup";
            assert_eq!(case.observed()["ok"], accepted);
            if accepted {
                assert_eq!(case.observed()["result"]["answer"], replacement["number"]);
            } else {
                assert_eq!(
                    case.observed()["diagnostic"]["code"],
                    if replacement.is_null() {
                        "presence_mutation"
                    } else {
                        "kind_mutation"
                    }
                );
            }
            assert!(replay_case(&case).unwrap().verified);
        }
    }
}

#[test]
fn kind_dispatch_promotes_outer_body_facts_and_inner_guards_release_at_return() {
    let source = format!(
        "RECORD Mode is one of\n  a:\n    id: integer\n  b:\n    id: integer\n{BOX}WHEN inspect <box> using <mode>\n  GIVEN box is Box\n  AND mode is Mode\n  DEPENDING ON mode\n    WHEN the kind is a\n      REQUIRE box.value is present\n    ELSE\n      REQUIRE box.value is present\n  add 1 to box.value\nWHEN clear <box> with <empty>\n  GIVEN box is Box\n  AND empty is Box\n  set box to empty\nREQUEST inspect\n  GIVEN box is Box\n  GIVEN empty is Box\n  GIVEN mode is Mode\n  WHEN inspect box using mode\n  WHEN clear box with empty\n  OUTPUT box is Box\n"
    );
    let p = program(&source);
    for kind in ["a", "b"] {
        let run = p.run_request(
            "inspect",
            &json!({"box":{"value":3},"empty":{},"mode":{"kind":kind,"id":0}}),
            Default::default(),
        );
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(run.result, Some(json!({"box":{"value":null}})));
    }
}

#[test]
fn source_evidence_limits_and_editor_navigation_follow_joined_paths() {
    let source = SOURCE
        .replace('\n', "\r\n")
        .replace("collection authorization", "collection authorization café");
    let p = program(&source);
    let data: Json = serde_json::from_str(include_str!(
        "../../../examples/native_branch_proofs/request.json"
    ))
    .unwrap();
    let run = p.run_request("authorize collection", &data, Default::default());
    assert!(run.ok);
    explain_execution(&run, p.source_bundle().unwrap()).unwrap();
    for event in &run.events {
        assert!(source.get(event.span.start..event.span.end).is_some());
    }
    for steps in 0..=run.steps {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let case = capture_request(&p, "authorize collection", &data, limits).unwrap();
        assert_eq!(case.observed()["ok"], steps == run.steps);
        assert!(replay_case(&case).unwrap().verified);
    }
    let root = std::env::current_dir().unwrap();
    let entry = root.join("joined-navigation.gwt");
    let query = EditorQuery {
        path: "joined-navigation.gwt".into(),
        byte_offset: source.find("RETURN facts.proof.reference").unwrap()
            + "RETURN facts.proof.".len(),
    };
    let checked = check_editor_query(
        &entry,
        Some(&root),
        &BTreeMap::from([("joined-navigation.gwt".into(), source.clone())]),
        Some(&query),
    );
    assert!(checked.ok, "{:?}", checked.diagnostic);
    let navigation = checked.navigation.unwrap();
    assert_eq!(navigation.symbols.len(), 1);
    let definition = navigation.symbols[0].definition.as_ref().unwrap();
    assert_eq!(&source[definition.start..definition.end], "reference");
}
