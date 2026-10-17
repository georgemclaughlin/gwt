use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, compare_case, compile_bundle, compile_program,
    explain_execution, replay_case, scenario_from_case, validate_bundle,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_kind_conditions/rules.gwt");
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
        "{CONTACT}REQUEST change\n  GIVEN contact is Contact\n  GIVEN replacement is Contact\n  WHEN act contact with contact and replacement\n  OUTPUT contact is Contact\nWHEN act <selected> with <alias> and <replacement>\n  GIVEN selected is Contact\n  AND alias is Contact\n  AND replacement is Contact\n{body}{helpers}"
    )
}
fn contact(kind: &str, text: &str) -> Json {
    if kind == "email" {
        json!({"kind":kind,"address":text})
    } else {
        json!({"kind":kind,"number":text})
    }
}

#[test]
fn contact_policy_matches_independent_expectations_and_detects_consent_reversal() {
    let p = program(SOURCE);
    let validation = validate_bundle(&bundle(SOURCE), Default::default());
    assert!(validation.ok);
    assert_eq!(p.scenario_names().len(), 7);
    let example: Json = serde_json::from_str(include_str!(
        "../../../examples/native_kind_conditions/request.json"
    ))
    .unwrap();
    assert_eq!(
        p.run_request("review contact", &example, Default::default())
            .result,
        Some(
            json!({"decision":{"status":"ready","channel":"email","destination":"orders@example.test"}})
        )
    );
    let candidate = program(&SOURCE.replace(
        "and facts.contact.opted_in",
        "and not facts.contact.opted_in",
    ));
    let mut changes = 0;
    let mut probes = 0;
    for allow in [false, true] {
        let mut cases = vec![(Json::Null, "review", "none", "")];
        for text in ["", "delivery"] {
            cases.extend([
                (
                    json!({"kind":"email","address":text,"confirmed":true}),
                    "ready",
                    "email",
                    text,
                ),
                (
                    json!({"kind":"email","address":text,"confirmed":false}),
                    "review",
                    "email",
                    "",
                ),
                (
                    json!({"kind":"sms","number":text,"opted_in":true}),
                    "ready",
                    "sms",
                    text,
                ),
                (
                    json!({"kind":"sms","number":text,"opted_in":false}),
                    "blocked",
                    "sms",
                    "",
                ),
                (
                    json!({"kind":"pickup","location":text}),
                    if allow { "ready" } else { "blocked" },
                    "pickup",
                    if allow { text } else { "" },
                ),
            ]);
        }
        for (contact, status, channel, destination) in cases {
            let input = json!({"facts":{"allow_pickup":allow,"contact":contact}});
            let case = capture_request(&p, "review contact", &input, Default::default()).unwrap();
            assert_eq!(
                case.observed()["result"],
                json!({"decision":{"status":status,"channel":channel,"destination":destination}}),
                "{input}"
            );
            assert!(replay_case(&case).unwrap().verified);
            let comparison = compare_case(&case, &candidate).unwrap();
            assert_eq!(comparison.changes.unwrap().outcome, channel == "sms");
            changes += usize::from(channel == "sms");
            probes += 1;
            let generated = scenario_from_case(&case, "observed contact").unwrap();
            assert!(
                compile_bundle(generated.source_bundle())
                    .unwrap()
                    .run_scenario("observed contact", Default::default())
                    .ok
            );
            let run = p.run_request("review contact", &input, Default::default());
            explain_execution(&run, p.source_bundle().unwrap()).unwrap();
            if contact.is_null() {
                assert!(
                    !run.events
                        .iter()
                        .any(|e| e.operation.starts_with("read facts.contact."))
                );
            }
        }
    }
    assert_eq!((probes, changes), (22, 8));
    assert_eq!(
        p.run_request(
            "review contact",
            &json!({"facts":{"allow_pickup":false}}),
            Default::default()
        )
        .result,
        Some(json!({"decision":{"status":"review","channel":"none","destination":""}}))
    );
}

#[test]
fn comparisons_negation_and_short_circuit_proofs_are_scoped_and_conservative() {
    for condition in [
        "selected.kind == \"email\"",
        "\"email\" == selected.kind",
        "not (selected.kind != \"email\")",
        "selected.kind == \"email\" and selected.address != \"\"",
    ] {
        let source = aliased(
            &format!("  IF {condition}\n    print selected.address\n  ELSE\n    PASS\n"),
            "",
        );
        let p = program(&source);
        for kind in ["email", "phone", "pickup"] {
            let run = p.run_request(
                "change",
                &json!({"contact":contact(kind,"before"),"replacement":contact(kind,"after")}),
                Default::default(),
            );
            assert!(run.ok, "{condition}: {:?}", run.diagnostic);
            assert_eq!(
                serde_json::to_value(run.output).unwrap(),
                if kind == "email" {
                    json!(["before"])
                } else {
                    json!([])
                }
            );
        }
    }
    for body in [
        "  IF selected.kind == \"email\" or true\n    print selected.address\n",
        "  IF selected.kind != \"email\" and false\n    PASS\n  ELSE\n    print selected.address\n",
        "  IF selected.kind == \"email\"\n    PASS\n  print selected.address\n",
        "  IF selected.kind == \"email\"\n    print alias.address\n",
        "  LET wanted be \"email\"\n  IF selected.kind == wanted\n    print selected.address\n",
        "  IF selected.kind == \"unknown\"\n    print selected.address\n",
    ] {
        let error = compile_program(&aliased(body, ""), "rules.gwt").unwrap_err();
        assert_eq!(error.code, "one_of_field", "{body}: {error:?}");
    }
    for condition in [
        "selected.kind != \"email\"",
        "not (\"email\" == selected.kind)",
        "selected.kind != \"email\" or selected.address == \"x\"",
    ] {
        let source = aliased(
            &format!("  IF {condition}\n    PASS\n  ELSE\n    print selected.address\n"),
            "",
        );
        assert!(program(&source).run_request("change",&json!({"contact":contact("email","before"),"replacement":contact("phone","after")}),Default::default()).ok);
    }
    let ordinary = "RECORD Item\n  kind: text\n  amount: integer\nWHEN inspect <item>\n  GIVEN item is Item\n  IF item.kind == \"email\"\n    print item.amount\n";
    assert!(compile_program(ordinary, "rules.gwt").is_ok());
}

#[test]
fn aliases_preserve_allowed_kind_sets_including_multikind_replacements() {
    let helper = "WHEN replace <target> with <value>\n  GIVEN target is Contact\n  AND value is Contact\n  set target to value\n";
    for (condition, initial, allowed) in [
        ("selected.kind == \"email\"", "email", vec!["email"]),
        (
            "selected.kind != \"email\"",
            "phone",
            vec!["phone", "pickup"],
        ),
    ] {
        let field = if initial == "email" {
            "address"
        } else {
            "number"
        };
        let source = aliased(
            &format!(
                "  IF {condition}\n    replace alias with replacement\n    REQUIRE selected.{field} == \"after\"\n"
            ),
            helper,
        );
        let p = program(&source);
        for kind in ["email", "phone", "pickup"] {
            let input =
                json!({"contact":contact(initial,"before"),"replacement":contact(kind,"after")});
            let run = p.run_request("change", &input, Default::default());
            assert_eq!(
                run.ok,
                allowed.contains(&kind),
                "{condition}/{kind}: {:?}",
                run.diagnostic
            );
            if !run.ok {
                assert_eq!(run.diagnostic.unwrap().code, "kind_mutation");
                assert_eq!(run.state["contact"], input["contact"]);
                assert!(!run.events.iter().any(|e| e.operation == "set"));
                let case = capture_request(&p, "change", &input, Default::default()).unwrap();
                assert!(replay_case(&case).unwrap().verified);
            }
        }
    }
}

#[test]
fn nested_optional_ancestor_replacements_cannot_break_kind_or_presence_proofs() {
    let source = format!(
        "{CONTACT}RECORD Envelope\n  contact: optional<Contact>\nREQUEST change\n  GIVEN box is Envelope\n  GIVEN replacement is Envelope\n  WHEN replace box with box and replacement\n  OUTPUT box is Envelope\nWHEN replace <selected> with <alias> and <replacement>\n  GIVEN selected is Envelope\n  AND alias is Envelope\n  AND replacement is Envelope\n  IF selected.contact is present and selected.contact.kind == \"email\"\n    set alias to replacement\n    REQUIRE selected.contact.address == \"after\"\n"
    );
    let p = program(&source);
    for (replacement, code) in [
        (json!({"contact":contact("email","after")}), None),
        (
            json!({"contact":contact("phone","after")}),
            Some("kind_mutation"),
        ),
        (json!({}), Some("presence_mutation")),
    ] {
        let input = json!({"box":{"contact":contact("email","before")},"replacement":replacement});
        let run = p.run_request("change", &input, Default::default());
        assert_eq!(run.diagnostic.as_ref().map(|d| d.code.as_str()), code);
        if code.is_some() {
            assert_eq!(run.state["box"], input["box"]);
        }
    }
}

#[test]
fn remaining_decision_guards_compose_and_release_on_return_or_failure() {
    let source = aliased(
        "  DECIDE\n    WHEN selected.kind == \"email\"\n      PASS\n    WHEN selected.kind == \"phone\"\n      PASS\n    ELSE\n      set alias to replacement\n      print selected.number\n",
        "",
    );
    let run = program(&source).run_request(
        "change",
        &json!({"contact":contact("pickup","before"),"replacement":contact("phone","after")}),
        Default::default(),
    );
    assert_eq!(run.diagnostic.unwrap().code, "kind_mutation");
    let source = format!(
        "{CONTACT}WHEN describe <value>\n  GIVEN value is Contact\n  THEN returns text\n  IF value.kind == \"email\"\n    RETURN value.address\n  ELSE\n    RETURN value.number\nWHEN fail <value>\n  GIVEN value is Contact\n  IF value.kind == \"email\"\n    set value.address to \"committed\"\n    REQUIRE false\nGIVEN item is Contact\n  kind: \"email\"\n  address: \"before\"\nGIVEN other is Contact\n  kind: \"phone\"\n  number: \"after\"\nWHEN LET description be describe item\nTHEN description == \"before\"\nWHEN fail item\nTHEN fails with \"assertion_failed\"\nTHEN item.address == \"committed\"\nWHEN set item to other\nTHEN item == other\n"
    );
    let source = source.replace(
        "THEN item.address == \"committed\"",
        "THEN item.kind == \"email\" and item.address == \"committed\"",
    );
    let p = program(&source);
    let run = p.run_scenario("Main", Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
}

#[test]
fn resource_failure_never_publishes_a_kind_invalidating_write() {
    let source = aliased(
        "  IF selected.kind == \"email\"\n    set alias to replacement\n    print selected.address\n",
        "",
    );
    let p = program(&source);
    let input = json!({"contact":contact("email","before"),"replacement":contact("phone","after")});
    for steps in 0..35 {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let run = p.run_request("change", &input, limits);
        assert!(!run.ok);
        assert!(matches!(
            run.diagnostic.as_ref().unwrap().code.as_str(),
            "execution_limit" | "kind_mutation"
        ));
        assert!(!run.events.iter().any(|e| e.operation == "set"));
        if run.state.get("contact").is_some() {
            assert_eq!(run.state["contact"], input["contact"]);
        }
    }
}

#[test]
fn optional_record_setup_is_present_and_preserves_closed_contract_errors() {
    let source = "RECORD Inner\n  value: integer\nRECORD Outer\n  nested: optional<Inner>\nGIVEN item is Outer\n  nested:\n    value: 4\nTHEN item.nested is present and item.nested.value == 4\n";
    assert!(program(source).run_scenario("Main", Default::default()).ok);
    for (bad, code) in [
        (source.replace("value: 4", "unknown: 4"), "unknown_field"),
        (
            source.replace("value: 4", "value: false"),
            "assignment_type",
        ),
        (
            source.replace("optional<Inner>", "optional<integer>"),
            "initializer_type",
        ),
    ] {
        assert_eq!(compile_program(&bad, "rules.gwt").unwrap_err().code, code);
    }
}

#[test]
fn selected_helpers_copies_and_collection_items_keep_their_contracts() {
    let source = format!(
        "{CONTACT}WHEN label <contact>\n  GIVEN contact is Contact of kind email\n  set contact.address to \"updated\"\nWHEN copy <contact>\n  GIVEN contact is Contact\n  THEN returns Contact\n  IF contact.kind == \"email\"\n    RETURN contact\n  ELSE\n    RETURN contact\nWHEN inspect <contacts>\n  GIVEN contacts is list<Contact>\n  FOR contact in contacts\n    IF contact.kind == \"email\"\n      label contact\n      LET saved be copy (contact)\n      REQUIRE saved.kind == \"email\" and saved.address == \"updated\"\nREQUEST inspect contacts\n  GIVEN contacts is list<Contact>\n  WHEN inspect contacts\n  OUTPUT contacts is list<Contact>\n"
    );
    let input = json!({"contacts":[contact("email","before"),contact("phone","555"),contact("email","other")]});
    let run = program(&source).run_request("inspect contacts", &input, Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(
        run.result,
        Some(
            json!({"contacts":[contact("email","updated"),contact("phone","555"),contact("email","updated")]})
        )
    );
    let bad = source.replace("copy (contact)", "copy contact");
    assert_eq!(
        compile_program(&bad, "rules.gwt").unwrap_err().code,
        "argument_type"
    );
    let outer = aliased(
        "  IF selected.kind == \"email\"\n    LET text be describe selected\n    set alias to replacement\n",
        "WHEN describe <contact>\n  GIVEN contact is Contact of kind email\n  THEN returns text\n  IF contact.address == \"before\"\n    RETURN contact.address\n  ELSE\n    RETURN \"other\"\n",
    );
    let run = program(&outer).run_request(
        "change",
        &json!({"contact":contact("email","before"),"replacement":contact("phone","after")}),
        Default::default(),
    );
    assert_eq!(run.diagnostic.unwrap().code, "kind_mutation");
}

#[test]
fn expanded_kind_conditions_retain_original_unicode_crlf_evidence() {
    let source=format!("# café 😀\n{CONTACT}WHEN describe <contact>\n  GIVEN contact is Contact\n  THEN returns text\n  IF contact.kind == \"email\"\n    RETURN contact.address\n  ELSE\n    RETURN contact.number\nSCENARIO describe <label>\nGIVEN item is Contact\n  kind: \"email\"\n  address: <address>\nWHEN LET text be describe item\nTHEN text == <address>\nEXAMPLES\n  | label | address |\n  | first | \"café 😀\" |\n  | second | \"other\" |\n").replace('\n',"\r\n");
    let p = program(&source);
    for name in p.scenario_names() {
        let case = gwt_core::capture_scenario(&p, name, Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
        let run = p.run_scenario(name, Default::default());
        assert!(run.ok);
        explain_execution(&run, p.source_bundle().unwrap()).unwrap();
        let branch = run.events.iter().find(|e| e.operation == "branch").unwrap();
        assert_eq!(
            &source[branch.span.start..branch.span.end],
            "contact.kind == \"email\""
        );
        assert!(
            run.events
                .iter()
                .all(|e| e.span.file == "rules.gwt"
                    && source.get(e.span.start..e.span.end).is_some())
        );
    }
    let bad = source.replace("RETURN contact.number", "PASS");
    assert_eq!(
        compile_program(&bad, "rules.gwt").unwrap_err().code,
        "missing_return"
    );
}
