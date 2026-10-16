use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, compile_bundle, compile_program,
    explain_execution, format_source, replay_case, validate_bundle,
};
use serde_json::json;
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_kind_dispatch/rules.gwt");
const CONTACT: &str =
    "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\n";
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
fn input(kind: &str) -> serde_json::Value {
    json!({"contact":{"kind":"email","address":"before"},"replacement":if kind == "email" { json!({"kind":"email","address":"after"}) } else {json!({"kind":"phone","number":"555"})}})
}

#[test]
fn exhaustive_routes_read_specific_fields_and_replay_with_explanations() {
    let p = program(SOURCE);
    let report = validate_bundle(&bundle(SOURCE), Default::default());
    assert!(report.ok);
    for (kind, field, value) in [
        ("email", "address", "a@example.test"),
        ("sms", "number", "555"),
        ("pickup", "location", "North desk"),
    ] {
        let input = json!({"destination":{"kind":kind,field:value}});
        let case = capture_request(&p, "route delivery", &input, Default::default()).unwrap();
        let replay = replay_case(&case).unwrap();
        assert!(replay.verified);
        let run = p.run_request("route delivery", &input, Default::default());
        assert_eq!(
            run.result,
            Some(json!({"route":{"channel":kind,"destination":value}}))
        );
        let branches: Vec<_> = run
            .events
            .iter()
            .filter(|e| e.operation == "kind branch")
            .collect();
        assert_eq!(branches.len(), 3);
        assert_eq!(
            branches
                .iter()
                .filter(|e| e.value["selected"] == true)
                .count(),
            1
        );
        assert!(branches.iter().all(|e| e.inputs == branches[0].inputs));
        explain_execution(&run, p.source_bundle().unwrap()).unwrap();
    }
    let formatted = format_source(SOURCE, "rules.gwt").unwrap();
    assert!(!formatted.changed);
}

#[test]
fn aliases_cannot_invalidate_narrowing_but_can_replace_with_the_same_kind() {
    let source = aliased(
        "  DEPENDING ON selected\n    WHEN the kind is email\n      replace alias with replacement\n      REQUIRE selected.address == \"after\"\n    WHEN the kind is phone\n      PASS\n",
        "WHEN replace <target> with <value>\n  GIVEN target is Contact\n  AND value is Contact\n  set target to value\n",
    );
    let p = program(&source);
    let good = p.run_request("change", &input("email"), Default::default());
    assert!(good.ok, "{:?}", good.diagnostic);
    let bad = p.run_request("change", &input("phone"), Default::default());
    assert_eq!(bad.diagnostic.unwrap().code, "kind_mutation");
    assert_eq!(bad.state["contact"], input("email")["contact"]);
    assert!(!bad.events.iter().any(|e| e.operation == "set"));
}

#[test]
fn nested_subject_is_guarded_against_ancestor_replacement() {
    let source = format!(
        "{CONTACT}RECORD Envelope\n  contact: Contact\nREQUEST change\n  GIVEN envelope is Envelope\n  GIVEN replacement is Envelope\n  WHEN act envelope with envelope and replacement\n  OUTPUT envelope is Envelope\nWHEN act <selected> with <alias> and <replacement>\n  GIVEN selected is Envelope\n  AND alias is Envelope\n  AND replacement is Envelope\n  DEPENDING ON selected.contact\n    WHEN the kind is email\n      set alias to replacement\n      REQUIRE selected.contact.address == \"after\"\n    ELSE\n      REQUIRE selected.contact.number != \"\"\n"
    );
    let p = program(&source);
    for kind in ["email", "phone"] {
        let values = input(kind);
        let run=p.run_request("change",&json!({"envelope":{"contact":values["contact"]},"replacement":{"contact":values["replacement"]}}),Default::default());
        assert_eq!(run.ok, kind == "email");
        if kind == "phone" {
            assert_eq!(run.diagnostic.unwrap().code, "kind_mutation");
        }
    }
}

#[test]
fn exhaustive_returns_and_remaining_kind_else_are_checked() {
    let source = format!(
        "{CONTACT}WHEN describe <contact>\n  GIVEN contact is Contact\n  THEN returns text\n  DEPENDING ON contact\n    WHEN the kind is email\n      RETURN contact.address\n    ELSE\n      RETURN contact.number\nGIVEN contact is Contact\n  kind: \"phone\"\n  number: \"555\"\nWHEN LET result be describe contact\nTHEN result == \"555\"\n"
    );
    assert!(program(&source).run_scenario("Main", Default::default()).ok);
    assert!(
        compile_program(
            &source.replace("RETURN contact.number", "PASS"),
            "rules.gwt"
        )
        .is_err()
    );
    let source = source.replace(
        "ELSE\n      RETURN contact.number",
        "WHEN the kind is phone\n      RETURN contact.number",
    );
    assert!(program(&source).run_scenario("Main", Default::default()).ok);
}

#[test]
fn invalid_or_nonexhaustive_branches_and_escaping_fields_are_rejected() {
    let prefix = format!("{CONTACT}WHEN inspect <contact>\n  GIVEN contact is Contact\n");
    for (body, code) in [
        (
            "  DEPENDING ON contact\n    WHEN the kind is email\n      PASS\n",
            "incomplete_depending",
        ),
        (
            "  DEPENDING ON contact\n    WHEN the kind is fax\n      PASS\n",
            "one_of_kind",
        ),
        (
            "  DEPENDING ON contact\n    WHEN the kind is email\n      PASS\n    WHEN the kind is email\n      PASS\n",
            "duplicate_kind",
        ),
        (
            "  DEPENDING ON contact\n    WHEN the kind is email\n      PASS\n    WHEN the kind is phone\n      PASS\n    ELSE\n      PASS\n",
            "unreachable_else",
        ),
        (
            "  DEPENDING ON contact\n    WHEN the kind is email\n      print contact.number\n    ELSE\n      PASS\n",
            "one_of_field",
        ),
        (
            "  DEPENDING ON contact\n    WHEN the kind is email\n      set contact.kind to \"phone\"\n    ELSE\n      PASS\n",
            "kind_readonly",
        ),
        (
            "  DEPENDING ON contact\n    WHEN the kind is email\n      PASS\n    ELSE\n      PASS\n  print contact.address\n",
            "one_of_field",
        ),
    ] {
        assert_eq!(
            compile_program(&format!("{prefix}{body}"), "rules.gwt")
                .unwrap_err()
                .code,
            code,
            "{body}"
        );
    }
}

#[test]
fn branch_guards_release_after_return_and_value_arguments_are_isolated() {
    let source = aliased(
        "  DEPENDING ON selected\n    WHEN the kind is email\n      replace (selected) with replacement\n      REQUIRE selected.address == \"before\"\n    ELSE\n      PASS\n  set alias to replacement\n",
        "WHEN replace <target> with <value>\n  GIVEN target is Contact\n  AND value is Contact\n  set target to value\n",
    );
    assert!(
        program(&source)
            .run_request("change", &input("phone"), Default::default())
            .ok
    );
    // A copied narrowed binding cannot be passed as mutable state to a wider contract.
    let bad = source.replace(
        "replace (selected) with replacement",
        "LET copy be selected\n      replace copy with replacement",
    );
    assert_eq!(
        compile_program(&bad, "rules.gwt").unwrap_err().code,
        "argument_type"
    );
    let source = aliased(
        "  LET description be describe selected\n  set alias to replacement\n",
        "WHEN describe <contact>\n  GIVEN contact is Contact\n  THEN returns text\n  DEPENDING ON contact\n    WHEN the kind is email\n      RETURN contact.address\n    ELSE\n      RETURN contact.number\n",
    );
    assert!(
        program(&source)
            .run_request("change", &input("phone"), Default::default())
            .ok
    );
}

#[test]
fn caught_failure_releases_guards_before_later_kind_changes() {
    let source = format!(
        "{CONTACT}WHEN reject <contact>\n  GIVEN contact is Contact\n  DEPENDING ON contact\n    WHEN the kind is email\n      REQUIRE false\n    ELSE\n      PASS\nGIVEN contact is Contact\n  kind: \"email\"\n  address: \"before\"\nGIVEN replacement is Contact\n  kind: \"phone\"\n  number: \"555\"\nWHEN reject contact\nTHEN fails with \"assertion_failed\"\nWHEN set contact to replacement\nTHEN contact == replacement\n"
    );
    let run = program(&source).run_scenario("Main", Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
}

#[test]
fn narrowed_payload_mutation_and_collection_items_keep_valid_contracts() {
    let source = format!(
        "{CONTACT}WHEN clean <contacts>\n  GIVEN contacts is list<Contact>\n  FOR contact in contacts\n    DEPENDING ON contact\n      WHEN the kind is email\n        set contact.address to \"updated\"\n      ELSE\n        set contact.number to \"new number\"\nGIVEN email is Contact\n  kind: \"email\"\n  address: \"old\"\nGIVEN phone is Contact\n  kind: \"phone\"\n  number: \"old\"\nGIVEN contacts is [email, phone]\nWHEN clean contacts\n"
    );
    let run = program(&source).run_scenario("Main", Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(
        run.state["contacts"],
        json!([{"kind":"email","address":"updated"},{"kind":"phone","number":"new number"}])
    );
}

#[test]
fn resource_failure_never_publishes_a_kind_changing_write() {
    let source = aliased(
        "  DEPENDING ON selected\n    WHEN the kind is email\n      set alias to replacement\n    ELSE\n      PASS\n",
        "",
    );
    let p = program(&source);
    for steps in 0..40 {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let run = p.run_request("change", &input("phone"), limits);
        assert!(!run.ok);
        if !run.state.is_null() && run.state.get("contact").is_some() {
            assert_eq!(run.state["contact"]["kind"], "email");
        }
    }
}

#[test]
fn nested_refinement_can_return_a_complete_declared_contract() {
    let source = format!(
        "{CONTACT}RECORD Outer is one of\n  left:\n    child: Contact\n  right:\n    child: Contact\nWHEN copy <outer>\n  GIVEN outer is Outer\n  THEN returns Outer\n  DEPENDING ON outer.child\n    WHEN the kind is email\n      REQUIRE outer.child.address != \"\"\n      RETURN outer\n    ELSE\n      RETURN outer\nGIVEN outer is Outer\n  kind: \"left\"\n  child:\n    kind: \"email\"\n    address: \"a\"\nWHEN LET result be copy outer\nTHEN result == outer\n"
    );
    let run = program(&source).run_scenario("Main", Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
}

#[test]
fn expanded_kind_branches_keep_original_unicode_source_evidence() {
    let source = format!("# café 😀\n{CONTACT}WHEN inspect <contact>\n  GIVEN contact is Contact\n  DEPENDING ON contact\n    WHEN the kind is email\n      print contact.address\n    ELSE\n      print contact.number\nSCENARIO route <address>\nGIVEN contact is Contact\n  kind: \"email\"\n  address: <address>\nWHEN inspect contact\nTHEN prints [<address>]\nEXAMPLES\n  | address |\n  | \"café\" |\n  | \"😀\" |\n").replace('\n', "\r\n");
    let p = program(&source);
    for scenario in p.test_scenarios(Default::default()) {
        assert!(scenario.execution.ok, "{:?}", scenario.execution.diagnostic);
        explain_execution(&scenario.execution, p.source_bundle().unwrap()).unwrap();
        let branch = scenario
            .execution
            .events
            .iter()
            .find(|e| e.operation == "kind branch")
            .unwrap();
        assert_eq!(
            &source[branch.span.start..branch.span.end],
            "WHEN the kind is email"
        );
        let case = gwt_core::capture_scenario(&p, &scenario.name, Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
    }
}
