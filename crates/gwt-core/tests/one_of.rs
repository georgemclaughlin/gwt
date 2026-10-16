use gwt_core::{
    ProgramLimits, SourceBundle, Type, capture_request, compile_bundle, compile_expression,
    compile_program, explain_execution, format_source, replay_case, scenario_from_case,
    validate_bundle,
};
use serde_json::json;
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/native_one_of/rules.gwt");
const TYPES: &str = "RECORD Contact is one of\n  email:\n    label: text\n    address: text\n    note: optional<text>\n  phone:\n    label: text\n    number: text\nTYPE Recipient is Contact\n";
fn program(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
fn email() -> serde_json::Value {
    json!({"kind":"email","label":"Accounts","address":"a@example.test"})
}
fn phone() -> serde_json::Value {
    json!({"kind":"phone","label":"Reception","number":"555-0100"})
}

#[test]
fn named_kinds_enforce_closed_payloads_and_normalize_only_active_optional_fields() {
    let program = program(SOURCE);
    for input in [email(), phone()] {
        let run = program.run_request(
            "plan contact",
            &json!({"contact":input}),
            Default::default(),
        );
        assert!(run.ok, "{:?}", run.diagnostic);
        let contact = &run.result.as_ref().unwrap()["contact"];
        assert_eq!(contact["kind"], input["kind"]);
        assert_eq!(
            run.result.as_ref().unwrap()["plan"],
            json!({"channel":input["kind"],"label":input["label"]})
        );
        if input["kind"] == "email" {
            assert_eq!(contact.as_object().unwrap().len(), 4);
            assert_eq!(contact["note"], serde_json::Value::Null);
            assert!(contact.get("number").is_none());
        } else {
            assert_eq!(contact, &input);
            assert!(contact.get("note").is_none());
        }
        explain_execution(&run, program.source_bundle().unwrap()).unwrap();
    }
    for (input, code) in [
        (json!({}), "one_of_kind"),
        (json!({"kind":null}), "one_of_kind"),
        (json!({"kind":true}), "one_of_kind"),
        (json!({"kind":"fax"}), "one_of_kind"),
        (json!({"kind":"email","label":"A"}), "missing_input"),
        (
            json!({"kind":"email","label":"A","address":"a","number":"5"}),
            "unknown_input",
        ),
        (
            json!({"kind":"phone","label":"A","number":"5","note":null}),
            "unknown_input",
        ),
        (json!({"kind":"phone","label":"A","number":5}), "input_type"),
    ] {
        let run = program.run_request(
            "plan contact",
            &json!({"contact":input}),
            Default::default(),
        );
        assert!(!run.ok);
        assert_eq!(run.diagnostic.unwrap().code, code);
        assert!(run.events.is_empty());
        assert_eq!(run.state, json!({}));
    }
}

#[test]
fn explicit_initializers_support_nested_values_lists_and_common_field_mutation() {
    let source = format!(
        "{TYPES}RECORD Batch\n  primary: Recipient\n  contacts: list<Recipient>\n  backup: optional<Recipient>\nGIVEN contact is Recipient\n  kind: \"email\"\n  label: \"A\"\n  address: \"a@example.test\"\nGIVEN batch is Batch\n  primary:\n    kind: \"phone\"\n    label: \"B\"\n    number: \"555\"\n  contacts: [contact]\nWHEN set contact.label to \"changed\"\nWHEN print batch.primary.kind\nTHEN contact.label == \"changed\"\nAND batch.primary.label == \"B\"\nAND batch.backup is absent\n"
    );
    let formatted = format_source(&source, "rules.gwt").unwrap();
    assert!(!format_source(&formatted.text, "rules.gwt").unwrap().changed);
    let run = program(&formatted.text).run_scenario("Main", Default::default());
    assert!(run.ok, "{:?}", run.diagnostic);
    assert_eq!(run.output, [json!("phone")]);
    assert_eq!(run.state["batch"]["contacts"][0]["label"], "A");
    assert!(run.state["batch"]["primary"].get("address").is_none());
}

#[test]
fn kind_and_noncommon_fields_cannot_be_mutated_or_aliased_without_narrowing() {
    let setup = format!(
        "{TYPES}GIVEN contact is Contact\n  kind: \"email\"\n  label: \"A\"\n  address: \"a\"\n"
    );
    for (step, code) in [
        ("WHEN set contact.kind to \"phone\"\n", "kind_readonly"),
        ("WHEN print contact.address\n", "one_of_field"),
        ("WHEN set contact.address to \"b\"\n", "one_of_field"),
        (
            "WHEN change contact.kind\nWHEN change <tag>\n  GIVEN tag is \"email\" | \"phone\"\n  set tag to \"phone\"\n",
            "kind_readonly",
        ),
    ] {
        assert_eq!(
            compile_program(&(setup.clone() + step), "bad.gwt")
                .unwrap_err()
                .code,
            code
        );
    }
    // Copying the discriminator into a behavior does not alias the record.
    let source = setup
        + "WHEN change (contact.kind)\nTHEN contact.kind == \"email\"\nWHEN change <tag>\n  GIVEN tag is \"email\" | \"phone\"\n  set tag to \"phone\"\n";
    assert!(program(&source).run_scenario("Main", Default::default()).ok);
    let differing = "RECORD Item is one of\n  left:\n    value: integer\n  right:\n    value: text\nREQUEST inspect\n  GIVEN item is Item\n  WHEN print item.value\n  OUTPUT item is Item\n";
    assert_eq!(
        compile_program(differing, "bad.gwt").unwrap_err().code,
        "one_of_field"
    );
}

#[test]
fn malformed_kinds_and_ambiguous_source_initialization_are_rejected() {
    for (source, code) in [
        ("RECORD Item is one of\n", "empty_one_of"),
        ("RECORD Item is one of\n  a:\n", "empty_record"),
        (
            "RECORD Item is one of\n  a:\n    kind: text\n",
            "kind_field",
        ),
        (
            "RECORD Item is one of\n  a:\n    x: text\n  a:\n    y: text\n",
            "duplicate_kind",
        ),
        ("RECORD Item is one of\n  a\n    x: text\n", "kind_syntax"),
        (
            "RECORD Item is one of\n  a:\n    next: Item\n",
            "recursive_type",
        ),
    ] {
        assert_eq!(
            compile_program(source, "bad.gwt").unwrap_err().code,
            code,
            "{source}"
        );
    }
    for (fields, code) in [
        ("  label: \"A\"\n", "kind_initializer"),
        ("  kind: \"fax\"\n", "one_of_kind"),
        ("  kind: tag\n", "kind_initializer"),
        ("  kind: \"email\"\n  label: \"A\"\n", "missing_field"),
        (
            "  kind: \"phone\"\n  label: \"A\"\n  number: \"5\"\n  address: \"a\"\n",
            "unknown_field",
        ),
        ("  kind: \"email\"\n  kind: \"phone\"\n", "duplicate_field"),
    ] {
        let source = format!("{TYPES}GIVEN tag is \"email\"\nGIVEN item is Contact\n{fields}");
        assert_eq!(
            compile_program(&source, "bad.gwt").unwrap_err().code,
            code,
            "{source}"
        );
    }
}

#[test]
fn complete_replacement_is_atomic_and_the_public_scenarios_have_expected_results() {
    let program = program(SOURCE);
    let report = validate_bundle(program.source_bundle().unwrap(), Default::default());
    assert!(report.ok);
    assert_eq!(report.results.len(), 3);
    assert_eq!(report.evidence.unwrap().scenario_expectations.passed, 8);
    let name = "changing kind replaces the complete value";
    let run = program.run_scenario(name, Default::default());
    assert!(run.ok);
    assert_eq!(run.state["contact"]["kind"], "phone");
    assert!(run.state["contact"].get("address").is_none());
    for steps in 0..run.steps {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let limited = program.run_scenario(name, limits);
        if let Some(contact) = limited.state.get("contact") {
            if contact["kind"] == "email" {
                assert!(contact.get("address").is_some() && contact.get("number").is_none());
            } else {
                assert_eq!(contact["kind"], "phone");
                assert!(contact.get("number").is_some() && contact.get("address").is_none());
            }
        }
    }
}

#[test]
fn nested_one_of_capture_replay_and_generated_scenarios_preserve_active_payloads() {
    let source = format!(
        "{TYPES}RECORD Batch\n  contacts: list<Recipient>\n  backup: optional<Recipient>\nREQUEST inspect batch\n  GIVEN batch is Batch\n  WHEN inspect batch\n  OUTPUT batch is Batch\nWHEN inspect <batch>\n  GIVEN batch is Batch\n  FOR contact in batch.contacts\n    print contact.kind\n"
    );
    let program = program(&source);
    for backup in [serde_json::Value::Null, email(), phone()] {
        let input = json!({"batch":{"contacts":[email(),phone()],"backup":backup}});
        let case = capture_request(&program, "inspect batch", &input, Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
        let generated = scenario_from_case(&case, "captured contacts").unwrap();
        let candidate = compile_bundle(generated.source_bundle()).unwrap();
        let runs = candidate.test_scenarios(Default::default());
        assert_eq!(runs.len(), 1);
        assert!(runs[0].execution.ok, "{:?}", runs[0].execution.diagnostic);
        assert_eq!(runs[0].execution.output, [json!("email"), json!("phone")]);
    }
}

#[test]
fn host_declared_one_of_types_share_validation_and_resource_limits() {
    let ty = Type::OneOf(BTreeMap::from([
        (
            "email".into(),
            BTreeMap::from([("label".into(), Type::Text), ("address".into(), Type::Text)]),
        ),
        (
            "phone".into(),
            BTreeMap::from([("label".into(), Type::Text), ("number".into(), Type::Text)]),
        ),
    ]));
    let expression = compile_expression(
        "contact.kind == \"email\" and contact.label == \"Accounts\"",
        "host",
        BTreeMap::from([("contact".into(), ty.clone())]),
    )
    .unwrap();
    assert_eq!(
        expression
            .evaluate(&json!({"contact":email()}), Default::default())
            .unwrap()
            .result,
        Some(json!(true))
    );
    assert!(
        expression
            .evaluate(&json!({"contact":{"kind":"fax"}}), Default::default())
            .is_err()
    );
    let guarded = compile_expression(
        "contact is present and contact.kind == \"email\"",
        "host",
        BTreeMap::from([("contact".into(), Type::Optional(Box::new(ty.clone())))]),
    )
    .unwrap();
    assert_eq!(
        guarded
            .evaluate(&json!({}), Default::default())
            .unwrap()
            .result,
        Some(json!(false))
    );
    assert_eq!(
        guarded
            .evaluate(&json!({"contact":email()}), Default::default())
            .unwrap()
            .result,
        Some(json!(true))
    );
    for invalid in [
        Type::OneOf(BTreeMap::new()),
        Type::OneOf(BTreeMap::from([("empty".into(), BTreeMap::new())])),
        Type::OneOf(BTreeMap::from([(
            "tag".into(),
            BTreeMap::from([("kind".into(), Type::Text)]),
        )])),
    ] {
        assert!(
            compile_expression(
                "value == value",
                "host",
                BTreeMap::from([("value".into(), invalid)])
            )
            .is_err()
        );
    }
    let huge = Type::OneOf(
        (0..5000)
            .map(|index| {
                (
                    format!("k{index}"),
                    BTreeMap::from([("value".into(), Type::Integer)]),
                )
            })
            .collect(),
    );
    assert_eq!(
        compile_expression(
            "value.kind",
            "host",
            BTreeMap::from([("value".into(), huge)])
        )
        .unwrap_err()
        .code,
        "type_limit"
    );
    let list = compile_expression(
        "values == values",
        "host",
        BTreeMap::from([("values".into(), Type::List(Box::new(ty)))]),
    )
    .unwrap();
    assert_eq!(
        list.evaluate(&json!({"values":vec![phone();6000]}), Default::default())
            .unwrap_err()
            .code,
        "input_limit"
    );
}
