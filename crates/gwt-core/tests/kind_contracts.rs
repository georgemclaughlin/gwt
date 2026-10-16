use gwt_core::{
    SourceBundle, capture_request, compile_bundle, compile_program, explain_execution,
    format_source, replay_case, scenario_from_case, validate_bundle,
};
use serde_json::json;
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_kind_contracts/rules.gwt");
const CONTACT: &str = "RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\nTYPE Recipient is Contact\nTYPE Email is Recipient of kind email\n";
fn bundle(source: &str) -> SourceBundle {
    SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    }
}
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&bundle(source)).unwrap()
}

#[test]
fn named_contracts_support_exhaustive_dispatch_and_independent_results() {
    let p = program(SOURCE);
    let report = validate_bundle(&bundle(SOURCE), Default::default());
    assert!(report.ok, "{report:?}");
    assert_eq!(p.scenario_names().len(), 5);
    assert_eq!(
        serde_json::to_value(report).unwrap()["evidence"]["scenarioExpectations"]["passed"],
        10
    );
    for threshold in [-1, 29, 30, 31] {
        let input = json!({"expression":{"kind":"comparison","left":10,"right":20,"threshold":threshold,"then_text":"above","else_text":"not above"}});
        let run = p.run_request("evaluate expression", &input, Default::default());
        assert_eq!(
            run.result,
            Some(json!({"result":{"total":30,"text":if 30>threshold {"above"}else{"not above"}}}))
        );
        explain_execution(&run, p.source_bundle().unwrap()).unwrap();
        let case = capture_request(&p, "evaluate expression", &input, Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
    }
    assert!(!format_source(SOURCE, "rules.gwt").unwrap().changed);
}

#[test]
fn selected_request_contracts_reject_other_kinds_before_execution_and_generate_scenarios() {
    let source = format!(
        "{CONTACT}TYPE Emails is list<Email>\nRECORD Batch\n  contacts: Emails\n  backup: optional<Contact of kind phone>\nREQUEST update\n  GIVEN batch is Batch\n  GIVEN email is Contact of kind email\n  WHEN rewrite email\n  OUTPUT batch is Batch\n  AND email is Email\nWHEN rewrite <email>\n  GIVEN email is Email\n  set email.address to \"updated\"\n"
    );
    let p = program(&source);
    let input = json!({"batch":{"contacts":[{"kind":"email","address":"a"}]},"email":{"kind":"email","address":"b"}});
    let run = p.run_request("update", &input, Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.result.as_ref().unwrap()["email"]["address"], "updated");
    let case = capture_request(&p, "update", &input, Default::default()).unwrap();
    let generated = scenario_from_case(&case, "typed contact").unwrap();
    let regenerated = compile_bundle(generated.source_bundle()).unwrap();
    assert!(
        regenerated
            .run_scenario(generated.name(), Default::default())
            .ok
    );
    for bad in [
        json!({"kind":"phone","number":"5"}),
        json!({"address":"a"}),
        json!({"kind":"email","number":"5"}),
    ] {
        let mut bad_input = input.clone();
        bad_input["email"] = bad;
        let run = p.run_request("update", &bad_input, Default::default());
        assert!(!run.ok);
        assert!(run.events.is_empty());
    }
}

#[test]
fn subtype_calls_require_proof_and_aliases_cannot_widen_the_contract() {
    let source = format!(
        "{CONTACT}WHEN rewrite <email>\n  GIVEN email is Email\n  set email.address to \"updated\"\nWHEN inspect <contact>\n  GIVEN contact is Contact\n  DEPENDING ON contact\n    WHEN the kind is email\n      rewrite contact\n    ELSE\n      PASS\nGIVEN contact is Contact\n  kind: \"email\"\n  address: \"old\"\nWHEN inspect contact\nTHEN contact.kind == \"email\"\n"
    );
    let run = program(&source).run_scenario("Main", Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.state["contact"]["address"], "updated");
    let bad = source.replace("WHEN inspect contact\nTHEN", "WHEN rewrite contact\nTHEN");
    assert_eq!(
        compile_program(&bad, "rules.gwt").unwrap_err().code,
        "argument_type"
    );
    let wide = format!(
        "{CONTACT}WHEN widen <contact>\n  GIVEN contact is Contact\n  PASS\nGIVEN email is Email\n  kind: \"email\"\n  address: \"a\"\nWHEN widen email\n"
    );
    assert_eq!(
        compile_program(&wide, "rules.gwt").unwrap_err().code,
        "argument_type"
    );
    assert!(
        program(&wide.replace("widen email", "widen (email)"))
            .run_scenario("Main", Default::default())
            .ok
    );
}

#[test]
fn invalid_selections_and_kind_changing_mutations_are_rejected() {
    for (declaration, code) in [
        ("TYPE Bad is Contact of kind fax\n", "one_of_kind"),
        ("TYPE Bad is Email of kind phone\n", "one_of_kind"),
        ("TYPE Bad is text of kind email\n", "kind_type"),
        ("TYPE Bad is Bad of kind email\n", "recursive_type"),
    ] {
        assert_eq!(
            compile_program(&format!("{CONTACT}{declaration}"), "rules.gwt")
                .unwrap_err()
                .code,
            code
        );
    }
    let setup = format!("{CONTACT}GIVEN email is Email\n  kind: \"email\"\n  address: \"a\"\n");
    assert_eq!(
        compile_program(
            &(setup.clone() + "WHEN set email.kind to \"phone\"\n"),
            "rules.gwt"
        )
        .unwrap_err()
        .code,
        "kind_readonly"
    );
    assert_eq!(
        compile_program(
            &setup.replace("kind: \"email\"", "kind: \"phone\""),
            "rules.gwt"
        )
        .unwrap_err()
        .code,
        "one_of_kind"
    );
    let source = format!(
        "{CONTACT}TYPE Again is Email of kind email\nTYPE Text is \"Contact of kind email\"\nGIVEN email is Again\n  kind: \"email\"\n  address: \"a\"\nTHEN email.address == \"a\"\n"
    );
    assert!(program(&source).run_scenario("Main", Default::default()).ok);
}

#[test]
fn a_kind_specific_helper_cannot_invalidate_its_payload_through_another_alias() {
    let source = format!(
        "{CONTACT}REQUEST change\n  GIVEN contact is Contact\n  GIVEN replacement is Contact\n  WHEN act contact with contact and replacement\n  OUTPUT contact is Contact\nWHEN act <selected> with <alias> and <replacement>\n  GIVEN selected is Contact\n  AND alias is Contact\n  AND replacement is Contact\n  DEPENDING ON selected\n    WHEN the kind is email\n      rewrite selected through alias with replacement\n    ELSE\n      PASS\nWHEN rewrite <email> through <alias> with <replacement>\n  GIVEN email is Email\n  AND alias is Contact\n  AND replacement is Contact\n  set alias to replacement\n  print email.address\n"
    );
    let p = program(&source);
    for (replacement, expected) in [
        (json!({"kind":"email","address":"after"}), true),
        (json!({"kind":"phone","number":"5"}), false),
    ] {
        let run = p.run_request(
            "change",
            &json!({"contact":{"kind":"email","address":"before"},"replacement":replacement}),
            Default::default(),
        );
        assert_eq!(run.ok, expected);
        if expected {
            assert_eq!(run.output, vec![json!("after")]);
        } else {
            assert_eq!(run.diagnostic.unwrap().code, "kind_mutation");
            assert_eq!(
                run.state["contact"],
                json!({"kind":"email","address":"before"})
            );
            assert!(!run.events.iter().any(|event| event.operation == "set"));
        }
    }
}
