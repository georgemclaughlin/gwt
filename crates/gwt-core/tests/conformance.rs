use gwt_core::{Limits, Type, compile_expression, compile_expression_at, source::Span};
use serde_json::{Value, json};
use std::collections::BTreeMap;

#[test]
fn independent_expression_fixtures() {
    let fixtures: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/expressions.json")).unwrap();
    for fixture in fixtures {
        let id = fixture["id"].as_str().unwrap();
        let source = fixture["source"].as_str().unwrap();
        let types = serde_json::from_value(fixture["types"].clone()).unwrap();
        let compiled = compile_expression(source, id, types);
        if fixture["phase"] == "check" {
            assert_eq!(compiled.unwrap_err().code, fixture["error"], "{id}");
            continue;
        }
        let compiled = compiled.unwrap_or_else(|error| panic!("{id}: {error}"));
        let evaluated = compiled.evaluate(&fixture["input"], Limits::default());
        if fixture["phase"] == "input" {
            assert_eq!(evaluated.unwrap_err().code, fixture["error"], "{id}");
            continue;
        }
        let evaluated = evaluated.unwrap_or_else(|error| panic!("{id}: {error}"));
        if fixture["phase"] == "runtime" {
            assert!(!evaluated.ok, "{id}");
            assert!(evaluated.result.is_none(), "{id}");
            assert_eq!(evaluated.diagnostic.unwrap().code, fixture["error"], "{id}");
        } else {
            assert!(evaluated.ok, "{id}: {:?}", evaluated.diagnostic);
            assert_eq!(evaluated.result.unwrap(), fixture["result"], "{id}");
            assert_eq!(
                serde_json::to_value(compiled.expression().result_type()).unwrap(),
                fixture["type"],
                "{id}"
            );
        }
    }
}

#[test]
fn evidence_links_only_executed_operands_and_exact_source_slices() {
    let source = "true or (1 / 0 == 0)";
    let compiled = compile_expression(source, "rule.gwt", BTreeMap::new()).unwrap();
    let evaluated = compiled.evaluate(&json!({}), Limits::default()).unwrap();
    assert!(evaluated.ok);
    assert_eq!(evaluated.steps, 2);
    assert_eq!(evaluated.events.len(), 2);
    let event = evaluated.events.last().unwrap();
    assert_eq!(event.inputs, [1]);
    assert_eq!(event.operation, "or");
    let skipped = event.skipped.as_ref().unwrap();
    assert_eq!(&source[skipped.start..skipped.end], "(1 / 0 == 0)");
    assert_eq!(evaluated.events[0].value, true);
    for event in &evaluated.events {
        assert!(event.inputs.iter().all(|id| *id < event.sequence));
        assert_eq!(event.span.file, "rule.gwt");
        assert!(source.is_char_boundary(event.span.start));
        assert!(source.is_char_boundary(event.span.end));
    }
}

#[test]
fn runtime_failure_retains_prior_evidence_without_inventing_result() {
    let compiled = compile_expression("1 + (2 / 0)", "failure.gwt", BTreeMap::new()).unwrap();
    let evaluated = compiled.evaluate(&json!({}), Limits::default()).unwrap();
    assert!(!evaluated.ok);
    assert_eq!(evaluated.events.len(), 3);
    assert!(evaluated.result.is_none());
    let diagnostic = evaluated.diagnostic.unwrap();
    assert_eq!(diagnostic.code, "division_by_zero");
    assert_eq!(diagnostic.span.start, 4);
    assert_eq!(diagnostic.span.end, 11);
}

#[test]
fn source_offsets_use_bytes_and_columns_use_unicode_characters() {
    let source = "\"☕\" == missing";
    let span = Span {
        file: "unicode.gwt".into(),
        start: 100,
        end: 100 + source.len(),
        line: 9,
        column: 7,
    };
    let diagnostic = compile_expression_at(source, span, BTreeMap::new()).unwrap_err();
    assert_eq!(diagnostic.code, "unknown_name");
    assert_eq!(diagnostic.span.start, 109);
    assert_eq!(diagnostic.span.line, 9);
    assert_eq!(diagnostic.span.column, 14);
}

#[test]
fn reusable_checked_program_has_no_input_or_budget_leak() {
    let compiled = compile_expression(
        "amount + 1",
        "repeat.gwt",
        BTreeMap::from([("amount".into(), Type::Integer)]),
    )
    .unwrap();
    let input = json!({"amount":2});
    let first = compiled.evaluate(&input, Limits::default()).unwrap();
    let second = compiled
        .evaluate(&json!({"amount":8}), Limits::default())
        .unwrap();
    let third = compiled.evaluate(&input, Limits::default()).unwrap();
    assert_eq!(first.result, Some(json!(3)));
    assert_eq!(second.result, Some(json!(9)));
    assert_eq!(
        serde_json::to_value(&first).unwrap(),
        serde_json::to_value(&third).unwrap()
    );
    assert_eq!(input, json!({"amount":2}));
}

#[test]
fn resource_limits_are_diagnostics_and_do_not_claim_success() {
    let compiled = compile_expression("1 + 2", "budget.gwt", BTreeMap::new()).unwrap();
    for limits in [
        Limits {
            steps: 1,
            ..Limits::default()
        },
        Limits {
            evidence_bytes: 1,
            ..Limits::default()
        },
    ] {
        let evaluated = compiled.evaluate(&json!({}), limits).unwrap();
        assert!(!evaluated.ok);
        assert!(evaluated.result.is_none());
        assert!(matches!(
            evaluated.diagnostic.unwrap().code.as_str(),
            "execution_limit" | "evidence_limit"
        ));
    }
    let huge = "9".repeat(513);
    assert_eq!(
        compile_expression(&huge, "numeric.gwt", BTreeMap::new())
            .unwrap_err()
            .code,
        "numeric_limit"
    );
    let deep = format!("{}true{}", "(".repeat(100), ")".repeat(100));
    assert_eq!(
        compile_expression(&deep, "deep.gwt", BTreeMap::new())
            .unwrap_err()
            .code,
        "expression_limit"
    );
    let left = std::iter::repeat_n("1", 100)
        .collect::<Vec<_>>()
        .join(" + ");
    assert_eq!(
        compile_expression(&left, "deep.gwt", BTreeMap::new())
            .unwrap_err()
            .code,
        "expression_limit"
    );
    let product = format!("{} * 10", "9".repeat(512));
    let compiled = compile_expression(&product, "numeric.gwt", BTreeMap::new()).unwrap();
    assert_eq!(
        compiled
            .evaluate(&json!({}), Limits::default())
            .unwrap()
            .diagnostic
            .unwrap()
            .code,
        "numeric_limit"
    );
}

#[test]
fn collection_work_is_metered() {
    let compiled = compile_expression(
        "items contains 9",
        "scan.gwt",
        BTreeMap::from([("items".into(), Type::List(Box::new(Type::Integer)))]),
    )
    .unwrap();
    let evaluated = compiled
        .evaluate(
            &json!({"items":[1,2,3,4,5]}),
            Limits {
                steps: 5,
                ..Limits::default()
            },
        )
        .unwrap();
    assert_eq!(evaluated.diagnostic.unwrap().code, "execution_limit");
    assert_eq!(evaluated.steps, 5);
}

#[test]
fn nested_optional_guards_are_checked_and_short_circuit() {
    let types: BTreeMap<String, Type> = serde_json::from_value(json!({"customer":{"kind":"optional","value":{"kind":"record","value":{"age":{"kind":"optional","value":{"kind":"integer"}}}}}})).unwrap();
    let source = "customer is present and customer.age is present and customer.age >= 18";
    let compiled = compile_expression(source, "nested.gwt", types.clone()).unwrap();
    for (input, expected) in [
        (json!({}), false),
        (json!({"customer":{}}), false),
        (json!({"customer":{"age":18}}), true),
    ] {
        assert_eq!(
            compiled.evaluate(&input, Limits::default()).unwrap().result,
            Some(json!(expected))
        );
    }
    assert!(compile_expression("customer.age >= 18", "nested.gwt", types).is_err());
}

#[test]
fn negated_absence_guard_refines_the_present_path() {
    let types = BTreeMap::from([("value".into(), Type::Optional(Box::new(Type::Integer)))]);
    let compiled =
        compile_expression("not (value is absent) and value > 2", "guard.gwt", types).unwrap();
    assert_eq!(
        compiled
            .evaluate(&json!({"value":3}), Limits::default())
            .unwrap()
            .result,
        Some(json!(true))
    );
}

#[test]
fn malformed_sources_are_reported_without_panics() {
    for source in [
        "",
        "1 +",
        "(true",
        "true)",
        "a.",
        "!true",
        "1 = 2",
        "\"unterminated",
        "\"\\q\"",
        "1.2.3",
        "1e9",
        "[1,,2]",
        "true\nfalse",
        "true # comment\nfalse",
    ] {
        assert!(
            compile_expression(source, "bad.gwt", BTreeMap::new()).is_err(),
            "{source}"
        );
    }
}

#[test]
fn invalid_input_identifies_the_field_and_deep_input_fails_before_serializing() {
    let types = BTreeMap::from([(
        "facts".into(),
        Type::Record(BTreeMap::from([("days".into(), Type::Integer)])),
    )]);
    let compiled = compile_expression("facts.days > 0", "input.gwt", types).unwrap();
    let error = compiled
        .evaluate(&json!({"facts":{"days":true}}), Limits::default())
        .unwrap_err();
    assert!(error.message.contains("field 'facts': field 'days'"));
    let mut input = json!(0);
    for _ in 0..100 {
        input = Value::Array(vec![input]);
    }
    assert_eq!(
        compiled
            .evaluate(&input, Limits::default())
            .unwrap_err()
            .code,
        "input_limit"
    );
}

#[test]
fn invalid_source_anchor_is_diagnosed() {
    let span = Span {
        file: "source.gwt".into(),
        start: usize::MAX,
        end: 0,
        line: 1,
        column: 1,
    };
    assert_eq!(
        compile_expression_at("1", span, BTreeMap::new())
            .unwrap_err()
            .code,
        "invalid_source_span"
    );
}
