use gwt_core::{ProgramLimits, compile_program, format_source};
use serde_json::json;

fn error(source: &str, code: &str, spelling: &str) {
    let error = compile_program(source, "casing.gwt").expect_err("must fail");
    assert_eq!(error.code, code);
    assert!(
        error
            .message
            .contains(&format!("did you mean '{spelling}'?")),
        "{error}"
    );
    assert!(error.span.end > error.span.start);
}

#[test]
fn hints_follow_failed_resolution_and_keep_diagnostic_codes() {
    error(
        "GIVEN total is 0\nWHEN SET total to 2\n",
        "unknown_behavior",
        "set",
    );
    error(
        "WHEN compute\n  let total be 2\nWHEN compute\n",
        "unknown_behavior",
        "LET",
    );
    error(
        "WHEN compute\n  THEN returns integer\n  return 2\nWHEN LET total be compute\n",
        "unknown_behavior",
        "RETURN",
    );
    error(
        "GIVEN total is 0\nwhen set total to 2\n",
        "unsupported_statement",
        "WHEN",
    );
    error("THEN TRUE\n", "unknown_name", "true");
    error("THEN true AND true\n", "unexpected_token", "and");
}

#[test]
fn legal_case_distinct_names_and_keyword_fields_keep_their_meaning() {
    let source = "RECORD parcel\n  WHEN: integer\nWHEN SET <target> to <value>\n  GIVEN target is integer\n  AND value is integer\n  set target to value + 100\nSCENARIO distinct\nGIVEN total is 0\nGIVEN TRUE is true\nGIVEN item is parcel\n  WHEN: 3\nWHEN SET total to 2\nTHEN total == 102\nAND TRUE\nAND item.WHEN == 3\n";
    let compiled = compile_program(source, "names.gwt").unwrap();
    let run = &compiled.test_scenarios(ProgramLimits::default())[0].execution;
    assert!(run.ok);
    assert_eq!(run.state["total"], json!(102));
}

#[test]
fn valid_named_call_argument_errors_do_not_get_spelling_hints() {
    let source = "WHEN SET <target>\n  GIVEN target is integer\n  PASS\nWHEN SET true\n";
    let error = compile_program(source, "names.gwt").err().unwrap();
    assert!(!error.message.contains("did you mean"), "{error}");
}

#[test]
fn reserved_heads_are_independently_pinned_including_legacy_reservations() {
    for word in [
        "set",
        "add",
        "subtract",
        "append",
        "count",
        "sum",
        "divide",
        "print",
        "find",
        "exists",
        "LET",
        "RETURN",
        "PASS",
        "REQUIRE",
        "IF",
        "ELSE",
        "FOR",
        "FIND",
        "DECIDE",
        "DEPENDING",
    ] {
        let source = format!("WHEN {word} domain\n  PASS\nTHEN true\n");
        let error = compile_program(&source, "reserved.gwt").err().unwrap();
        assert_eq!(
            error.code,
            if word == "LET" {
                "unexpected_block"
            } else {
                "behavior_name"
            },
            "{word}: {error}"
        );
    }
}

#[test]
fn both_filter_spellings_work_and_formatting_never_case_folds() {
    for filter in ["WHERE", "where"] {
        let source = format!(
            "WHEN total <items> into <result>\n  GIVEN items is list<integer>\n  AND result is integer\n  FOR item in items {filter} item > 0\n    AND add item to result\nGIVEN result is 0\nWHEN total [1, -1, 2] into result\nTHEN result == 3\n"
        );
        let formatted = format_source(&source, "filters.gwt").unwrap();
        assert_eq!(formatted.text, source);
        assert!(
            compile_program(&formatted.text, "filters.gwt")
                .unwrap()
                .test_scenarios(ProgramLimits::default())[0]
                .execution
                .ok
        );
    }
    let source = "WHEN pick <flag> into <result>\n  GIVEN flag is boolean\n  AND result is integer\n  DEPENDING  ON flag\n    WHEN the value is true\n      AND set result to 1\n    WHEN the value is false\n      PASS\nGIVEN result is 0\nWHEN pick true into result\nTHEN result == 1\n";
    let formatted = format_source(source, "dispatch.gwt").unwrap();
    assert!(formatted.text.contains("DEPENDING ON flag"));
    assert!(
        !format_source(&formatted.text, "dispatch.gwt")
            .unwrap()
            .changed
    );
    assert!(
        compile_program(&formatted.text, "dispatch.gwt")
            .unwrap()
            .test_scenarios(ProgramLimits::default())[0]
            .execution
            .ok
    );
}
