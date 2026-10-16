use gwt_core::{ProgramLimits, Type, compile_expression, compile_program};
use std::collections::BTreeMap;

#[test]
fn expression_errors_name_the_actual_operator_and_language_types() {
    for (source, expected) in [
        ("not 1", "operator 'not' requires boolean; found integer"),
        ("-true", "operator '-' requires a number; found boolean"),
        (
            "1 + true",
            "operator '+' does not accept integer and boolean",
        ),
        (
            "1 is present",
            "presence checks require an optional value; found integer",
        ),
    ] {
        let error = compile_expression(source, "rule.gwt", BTreeMap::new()).unwrap_err();
        assert_eq!(error.code, "type_mismatch");
        assert_eq!(error.message, expected);
        assert_eq!(&source[error.span.start..error.span.end], source);
    }
}

#[test]
fn assignment_condition_and_collection_errors_report_expected_and_actual_types() {
    for (source, code, expected) in [
        (
            "GIVEN count is 1\nWHEN set count to true\n",
            "assignment_type",
            "cannot assign boolean; expected integer",
        ),
        (
            "WHEN inspect <count>\n  GIVEN count is integer\n  IF count\n    PASS\n",
            "condition_type",
            "a condition must be boolean; found integer",
        ),
        (
            "WHEN inspect <count>\n  GIVEN count is integer\n  FOR item in count\n    PASS\n",
            "collection_type",
            "collection operation requires a list; found integer",
        ),
    ] {
        let error = compile_program(source, "rule.gwt").unwrap_err();
        assert_eq!(error.code, code);
        assert_eq!(error.message, expected);
    }
}

#[test]
fn optional_record_hints_identify_the_unproven_path_and_the_guard_repairs_it() {
    let prefix = "RECORD Customer\n  age: integer\nRECORD Facts\n  customer: optional<Customer>\nWHEN inspect <facts>\n  GIVEN facts is Facts\n";
    let broken = format!("{prefix}  print facts.customer.age\n");
    let error = compile_program(&broken, "rule.gwt").unwrap_err();
    assert_eq!(error.code, "type_mismatch");
    assert_eq!(
        error.message,
        "cannot access field 'age' through optional path 'facts.customer'; establish 'facts.customer is present' before accessing fields"
    );
    assert_eq!(
        &broken[error.span.start..error.span.end],
        "facts.customer.age"
    );
    compile_program(
        &format!("{prefix}  IF facts.customer is present\n    print facts.customer.age\n"),
        "rule.gwt",
    )
    .unwrap();
    let error = compile_program(
        &format!("{prefix}  set facts.customer.age to 1\n"),
        "rule.gwt",
    )
    .unwrap_err();
    assert_eq!(error.code, "invalid_path");
    assert!(error.message.contains("'facts.customer is present'"));
    compile_program(
        &format!("{prefix}  IF facts.customer is present\n    set facts.customer.age to 1\n"),
        "rule.gwt",
    )
    .unwrap();
    // Guarding a scalar cannot make it a record; do not offer that false repair.
    let types = BTreeMap::from([("amount".into(), Type::Optional(Box::new(Type::Integer)))]);
    let error = compile_expression("amount.age", "rule.gwt", types).unwrap_err();
    assert_eq!(
        error.message,
        "cannot access field 'age' from 'amount' (optional<integer>); field access requires a record"
    );
    assert!(!error.message.contains("is present"));
}

#[test]
fn shared_argument_hint_is_conditional_and_explains_the_copy_semantics() {
    let header = "WHEN bump <amount>\n  GIVEN amount is decimal\n  add 1 to amount\n";
    let source = format!("{header}GIVEN price is 2\nWHEN bump price\n");
    let error = compile_program(&source, "rule.gwt").unwrap_err();
    assert_eq!(error.code, "argument_type");
    assert_eq!(&source[error.span.start..error.span.end], "price");
    assert_eq!(
        error.message,
        "parameter 'amount' requires decimal; argument 'price' has integer; shared state arguments must have matching types; to pass a copy instead, write (price); changes to the copy do not update the original"
    );
    let fixed = compile_program(&source.replace("bump price", "bump (price)"), "rule.gwt").unwrap();
    let run = fixed.test_scenarios(ProgramLimits::default()).remove(0);
    assert!(run.execution.ok);
    assert_eq!(run.execution.state["price"], 2);
    let bad = format!("{header}GIVEN price is true\nWHEN bump price\n");
    let error = compile_program(&bad, "rule.gwt").unwrap_err();
    assert_eq!(error.code, "argument_type");
    assert!(error.message.contains("argument 'price' has boolean"));
    assert!(!error.message.contains("copy"));
    assert!(compile_program(&bad.replace("bump price", "bump (price)"), "rule.gwt").is_err());
}

#[test]
fn structural_diagnostics_distinguish_same_named_variant_payloads_and_bound_large_types() {
    let one = |ty| {
        Type::OneOf(BTreeMap::from([(
            "email".into(),
            BTreeMap::from([("address".into(), ty)]),
        )]))
    };
    let types = BTreeMap::from([
        ("left".into(), one(Type::Text)),
        ("right".into(), one(Type::Integer)),
    ]);
    let error = compile_expression("left == right", "rule.gwt", types).unwrap_err();
    assert_eq!(
        error.message,
        "operator '==' does not accept one of { email: { address: text } } and one of { email: { address: integer } }"
    );
    let wide = Type::Record(
        (0..1000)
            .map(|i| {
                (
                    format!("field_{i:04}"),
                    Type::TextUnion(vec!["😀".repeat(30)]),
                )
            })
            .collect(),
    );
    let error = compile_expression(
        "value + true",
        "rule.gwt",
        BTreeMap::from([("value".into(), wide)]),
    )
    .unwrap_err();
    assert!(error.message.contains('…'));
    assert!(error.message.len() < 1200);
    assert!(error.message.ends_with("and boolean"));
    assert!(!error.message.contains("TextUnion"));
}
