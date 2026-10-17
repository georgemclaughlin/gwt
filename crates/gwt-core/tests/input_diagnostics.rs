use gwt_core::{Limits, ProgramLimits, Type, compile_expression, compile_program};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

fn input_error(ty: Type, value: Json) -> gwt_core::source::Diagnostic {
    compile_expression(
        "value",
        "contract.gwt",
        BTreeMap::from([("value".into(), ty)]),
    )
    .unwrap()
    .evaluate(&json!({"value":value}), Limits::default())
    .unwrap_err()
}

#[test]
fn expected_contract_and_actual_json_kind_are_reported_without_echoing_values() {
    for (ty, value, expected) in [
        (
            Type::Boolean,
            json!(1),
            "field 'value': expected boolean; found JSON number",
        ),
        (
            Type::Integer,
            json!(true),
            "field 'value': expected integer; found JSON boolean",
        ),
        (
            Type::Text,
            json!([]),
            "field 'value': expected text; found JSON array",
        ),
        (
            Type::Integer,
            json!({}),
            "field 'value': expected integer; found JSON object",
        ),
        (
            Type::Integer,
            Json::Null,
            "field 'value': expected integer; found JSON null",
        ),
        (
            Type::Boolean,
            json!("secret text"),
            "field 'value': expected boolean; found JSON string",
        ),
        (
            Type::Integer,
            json!(1.5),
            "field 'value': expected integer; found JSON number",
        ),
    ] {
        let error = input_error(ty, value);
        assert_eq!(error.code, "input_type");
        assert_eq!(error.message, expected);
        assert_eq!(error.span.file, "contract.gwt");
    }
    let e = compile_expression(
        "value",
        "c",
        BTreeMap::from([("value".into(), Type::Integer)]),
    )
    .unwrap();
    assert_eq!(
        e.evaluate(&json!({}), Limits::default())
            .unwrap_err()
            .message,
        "field 'value': required input is missing; expected integer"
    );
}

#[test]
fn decimal_guidance_preserves_exact_input_rules_and_malformed_number_codes() {
    let error = input_error(Type::Decimal, json!(0.1));
    assert_eq!(error.code, "input_type");
    assert_eq!(
        error.message,
        "field 'value': expected decimal; found JSON number; decimal inputs use quoted base-10 text or a JSON integer"
    );
    let e = compile_expression(
        "value * 3",
        "c",
        BTreeMap::from([("value".into(), Type::Decimal)]),
    )
    .unwrap();
    for (value, expected) in [(json!("0.1"), json!("0.3")), (json!(2), json!("6"))] {
        let run = e
            .evaluate(&json!({"value":value}), Limits::default())
            .unwrap();
        assert_eq!(serde_json::to_value(run).unwrap()["result"], expected);
    }
    for text in ["1e2", "NaN", "not a number"] {
        assert_eq!(
            input_error(Type::Decimal, json!(text)).code,
            "invalid_number"
        );
    }
    assert_eq!(
        input_error(Type::Decimal, json!("1".repeat(513))).code,
        "numeric_limit"
    );
}

#[test]
fn nested_list_and_optional_record_failures_keep_precise_breadcrumbs_and_no_execution() {
    let source = "RECORD Line\n  count: integer\nRECORD Facts\n  lines: list<optional<Line>>\nREQUEST inspect\n  GIVEN facts is Facts\n  WHEN print \"executed\"\n  OUTPUT facts is Facts\n";
    let program = compile_program(source, "contract.gwt").unwrap();
    for (input, code, message) in [
        (
            json!({"facts":{"lines":[null,{"count":true}]}}),
            "input_type",
            "field 'facts': field 'lines': item 1: field 'count': expected integer; found JSON boolean",
        ),
        (
            json!({"facts":{"lines":[null,{}]}}),
            "missing_input",
            "field 'facts': field 'lines': item 1: field 'count': required input is missing; expected integer",
        ),
        (
            json!({"facts":{"lines":[null,{"extra":1}]}}),
            "unknown_input",
            "field 'facts': field 'lines': item 1: field \"extra\" is outside the record contract",
        ),
    ] {
        let run = program.run_request("inspect", &input, ProgramLimits::default());
        assert!(!run.ok);
        assert!(run.events.is_empty());
        assert!(run.output.is_empty());
        assert_eq!(run.state, json!({}));
        let error = run.diagnostic.unwrap();
        assert_eq!(error.code, code);
        assert_eq!(error.message, message);
        assert_eq!(&source[error.span.start..error.span.end], "REQUEST inspect");
    }
    let run = program.run_request(
        "inspect",
        &json!({"facts":{"lines":[null,{"count":3}]}}),
        ProgramLimits::default(),
    );
    assert!(run.ok);
    assert_eq!(run.output, vec![json!("executed")]);
}

#[test]
fn kind_diagnostics_distinguish_missing_wrong_type_and_unknown_tag() {
    let ty = Type::OneOf(BTreeMap::from([
        (
            "email".into(),
            BTreeMap::from([("address".into(), Type::Text)]),
        ),
        (
            "phone".into(),
            BTreeMap::from([("number".into(), Type::Text)]),
        ),
    ]));
    for (value, expected) in [
        (
            json!({}),
            "field 'value': one-of record requires a text field 'kind'; found missing value",
        ),
        (
            json!({"kind":null}),
            "field 'value': one-of record requires a text field 'kind'; found JSON null",
        ),
        (
            json!({"kind":false}),
            "field 'value': one-of record requires a text field 'kind'; found JSON boolean",
        ),
        (
            json!({"kind":"pager"}),
            "field 'value': unknown one-of kind \"pager\"; expected \"email\" | \"phone\"",
        ),
    ] {
        let error = input_error(ty.clone(), value);
        assert_eq!(error.code, "one_of_kind");
        assert_eq!(error.message, expected);
    }
    let e = compile_expression("value.kind", "c", BTreeMap::from([("value".into(), ty)])).unwrap();
    assert!(
        e.evaluate(
            &json!({"value":{"kind":"email","address":"a"}}),
            Limits::default()
        )
        .is_ok()
    );
}

#[test]
fn untrusted_keys_tags_and_large_contract_descriptions_are_bounded_and_escaped() {
    let key = "bad\n\"😀".repeat(10000);
    let error = input_error(Type::Record(BTreeMap::new()), json!({key.clone():1}));
    assert_eq!(error.code, "unknown_input");
    assert!(error.message.len() < 1200);
    assert!(!error.message.contains('\n'));
    assert!(error.message.contains("\\n"));
    assert!(error.message.contains('…'));
    let ty = Type::OneOf(BTreeMap::from([(
        "ok".into(),
        BTreeMap::from([("flag".into(), Type::Boolean)]),
    )]));
    let error = input_error(ty, json!({"kind":key}));
    assert_eq!(error.code, "one_of_kind");
    assert!(error.message.len() < 1200);
    assert!(!error.message.contains('\n'));
    assert!(error.message.contains("expected \"ok\""));
    let ty = Type::Record(
        (0..1000)
            .map(|i| (format!("field_{i:04}"), Type::Integer))
            .collect(),
    );
    let error = input_error(ty, json!(false));
    assert!(error.message.len() < 1200);
    assert!(error.message.contains('…'));
    assert!(error.message.ends_with("found JSON boolean"));
}
