use gwt_core::{
    Corpus, CorpusEntry, Limits, ProgramLimits, SourceBundle, Type, capture_request,
    compile_bundle, compile_expression, compile_program, explain_execution, render_review_html,
    review_corpus,
};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;
const RESERVATION: &str = include_str!("../../../examples/native_reservation/rules.gwt");
fn source(body: &str) -> String {
    format!(
        "RECORD Box\n  values: list<integer>\n  total: integer\n  names: list<text>\nREQUEST apply\n  GIVEN box is Box\n  WHEN update box\n  OUTPUT box is Box\nWHEN update <box>\n  GIVEN box is Box\n{body}\n"
    )
}
fn input(values: Json) -> Json {
    json!({"box":{"values":values,"total":0,"names":[]}})
}
fn run(body: &str, values: Json) -> gwt_core::ProgramExecution {
    compile_program(&source(body), "collections.gwt")
        .unwrap()
        .run_request("apply", &input(values), ProgramLimits::default())
}
fn bundled(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}

#[test]
fn list_literals_infer_consistent_types_and_compare_structurally() {
    for (source, expected) in [
        ("[1, 2, 3]", json!([1, 2, 3])),
        ("[1, 2.5]", json!(["1", "2.5"])),
        ("[1, 2] == [1.0, 2.0]", json!(true)),
        ("[[1], []] == [[1.0], []]", json!(true)),
        ("[] == [1]", json!(false)),
        ("[1] != []", json!(true)),
        ("[\"a\",\"b\"] contains \"b\"", json!(true)),
        ("[1, 2] contains 2.0", json!(true)),
        ("[[], [1, 2]]", json!([[], [1, 2]])),
    ] {
        let expression = compile_expression(source, "list.gwt", BTreeMap::new())
            .unwrap_or_else(|e| panic!("{source}: {e}"));
        let result = expression.evaluate(&json!({}), Limits::default()).unwrap();
        assert!(result.ok, "{source}: {:?}", result.diagnostic);
        assert_eq!(result.result.unwrap(), expected);
    }
    for source in ["[]", "[1, true]", "[1,,2]", "[1,2", "[[]]", "[1] == [true]"] {
        assert!(
            compile_expression(source, "bad.gwt", BTreeMap::new()).is_err(),
            "{source}"
        );
    }
    let nested = format!("{}1{}", "[".repeat(50), "]".repeat(50));
    assert!(compile_expression(&nested, "nested.gwt", BTreeMap::new()).is_ok());
}

#[test]
fn typed_empty_lists_and_quoted_step_separators_work_at_boundaries() {
    let execution = run(
        "  set box.values to []\n  append 4 to box.values\n  append \"send to review, then in storage\" to box.names\n  set box.names to [\"keep to inspect\"]",
        json!([1, 2]),
    );
    assert!(execution.ok, "{:?}", execution.diagnostic);
    assert_eq!(
        execution.result.unwrap(),
        json!({"box":{"values":[4],"total":0,"names":["keep to inspect"]}})
    );
    let union = "RECORD State\n  names: list<\"a\" | \"b\">\nREQUEST go\n  GIVEN state is State\n  WHEN update state\n  OUTPUT state is State\nWHEN update <state>\n  GIVEN state is State\n  set state.names to [\"a\"]\n  REQUIRE state.names contains \"a\"\n";
    let execution = compile_program(union, "union.gwt").unwrap().run_request(
        "go",
        &json!({"state":{"names":[]}}),
        ProgramLimits::default(),
    );
    assert!(execution.ok);
    assert!(
        compile_program(
            &union.replace("set state.names to [\"a\"]", "set state.names to [\"c\"]"),
            "bad.gwt"
        )
        .is_err()
    );
}

#[test]
fn loops_mutate_source_items_in_order_and_keep_locals_scoped() {
    let execution = run(
        "  FOR item in box.values WHERE item > 1\n    LET increment be item\n    add increment to box.total\n    set item to item * 10",
        json!([1, 2, 3]),
    );
    assert!(execution.ok, "{:?}", execution.diagnostic);
    assert_eq!(
        execution.result.unwrap()["box"],
        json!({"values":[1,20,30],"total":5,"names":[]})
    );
    let paths: Vec<_> = execution
        .events
        .iter()
        .filter(|event| event.operation == "set")
        .map(|event| event.value["path"].as_str().unwrap())
        .collect();
    assert_eq!(paths, ["box.values[1]", "box.values[2]"]);
    let execution = run(
        "  FOR item in box.values\n    IF item == 1\n      FIND later in box.values WHERE later == 2\n        set later to 9\n      ELSE\n        PASS\n    add item to box.total",
        json!([1, 2]),
    );
    assert!(execution.ok, "{:?}", execution.diagnostic);
    assert_eq!(execution.result.unwrap()["box"]["total"], 10);
    let execution = run("  FOR item in [box.total]\n    set item to 9", json!([1]));
    assert!(execution.ok);
    assert_eq!(execution.result.unwrap()["box"]["total"], 0);
}

#[test]
fn find_selects_first_match_and_releases_the_collection_before_missing_body() {
    let execution = run(
        "  FIND item in box.values WHERE item > 1\n    set item to 20\n  ELSE\n    append 10 to box.values",
        json!([1, 2, 3]),
    );
    assert!(execution.ok);
    assert_eq!(
        execution.result.unwrap()["box"]["values"],
        json!([1, 20, 3])
    );
    assert_eq!(
        execution
            .events
            .iter()
            .filter(|event| event.operation == "collection item")
            .count(),
        2
    );
    assert!(
        execution
            .events
            .iter()
            .any(|event| event.operation == "branch skipped")
    );
    let execution = run(
        "  FIND item in box.values WHERE item > 1\n    set item to 20\n  ELSE\n    append 10 to box.values",
        json!([]),
    );
    assert!(execution.ok, "{:?}", execution.diagnostic);
    assert_eq!(execution.result.unwrap()["box"]["values"], json!([10]));
}

#[test]
fn collection_shape_cannot_change_through_direct_or_aliased_mutation() {
    for body in [
        "  FOR item in box.values\n    append 9 to box.values",
        "  FOR item in box.values\n    set box.values to []",
        "  FOR item in box.values\n    set box to box",
    ] {
        let execution = run(body, json!([1, 2]));
        assert!(!execution.ok);
        assert_eq!(execution.diagnostic.unwrap().code, "collection_mutation");
        assert_eq!(execution.state["box"]["values"], json!([1, 2]));
        assert!(
            !execution
                .events
                .iter()
                .any(|event| matches!(event.operation.as_str(), "set" | "append item"))
        );
    }
    let source = source("  FOR item in box.values\n    resize box")
        + "WHEN resize <alias>\n  GIVEN alias is Box\n  append 9 to alias.values\n";
    let execution = compile_program(&source, "alias.gwt").unwrap().run_request(
        "apply",
        &input(json!([1, 2])),
        ProgramLimits::default(),
    );
    assert_eq!(execution.diagnostic.unwrap().code, "collection_mutation");
    let execution = run(
        "  FOR item in box.values\n    FIND missing in box.values WHERE missing == 100\n      PASS\n    ELSE\n      append 9 to box.values",
        json!([1, 2]),
    );
    assert_eq!(execution.diagnostic.unwrap().code, "collection_mutation");
    assert_eq!(execution.state["box"]["values"], json!([1, 2]));
}

#[test]
fn collection_type_errors_and_inaccessible_names_fail_before_execution() {
    assert!(
        compile_program(
            &RESERVATION.replace(
                "sum line.quantity in order.lines",
                "sum line.quantity + 1 in order.lines"
            ),
            "bad-projection.gwt"
        )
        .is_err()
    );
    for body in [
        "  FOR item in 1\n    PASS",
        "  FOR item in box.values WHERE item\n    PASS",
        "  FIND item in box.values WHERE item > 0\n    PASS",
        "  FIND item in box.values WHERE item > 0\n    PASS\n  ELSE\n    add item to box.total",
        "  FOR item in box.values\n    LET scratch be item\n  add scratch to box.total",
        "  FOR box in box.values\n    PASS",
        "  append true to box.values",
        "  count box.values into box.names",
        "  sum box.names into box.total",
        "  sum item.bad in box.values into box.total",
        "  add 0.5 to box.total",
        "  set box.values to [true]",
        "  FOR item in box.values\n    IF false\n      set item to \"bad\"",
    ] {
        assert!(compile_program(&source(body), "bad.gwt").is_err(), "{body}");
    }
}

#[test]
fn count_sum_and_arithmetic_use_exact_values_and_empty_sum_zero() {
    let execution = run(
        "  count box.values into box.total\n  REQUIRE box.total == 3\n  sum box.values into box.total\n  subtract 1 from box.total",
        json!([1, 2, 3]),
    );
    assert!(execution.ok);
    assert_eq!(execution.result.unwrap()["box"]["total"], 5);
    assert_eq!(
        execution
            .events
            .iter()
            .filter(|event| event.operation == "sum item")
            .map(|event| event.value["subtotal"].clone())
            .collect::<Vec<_>>(),
        vec![json!(1), json!(3), json!(6)]
    );
    let execution = run("  sum box.values into box.total", json!([]));
    assert!(execution.ok);
    assert_eq!(execution.result.unwrap()["box"]["total"], 0);
    let decimal = source("  sum box.values into box.total")
        .replace("list<integer>", "list<decimal>")
        .replace("total: integer", "total: decimal");
    let program = compile_program(&decimal, "decimal.gwt").unwrap();
    let result = program.run_request(
        "apply",
        &json!({"box":{"values":["0.1","0.2"],"total":"0","names":[]}}),
        ProgramLimits::default(),
    );
    assert!(result.ok);
    assert_eq!(result.result.unwrap()["box"]["total"], "0.3");
    let result = program.run_request(
        "apply",
        &json!({"box":{"values":["9".repeat(512),"1"],"total":"0","names":[]}}),
        ProgramLimits::default(),
    );
    assert_eq!(result.diagnostic.unwrap().code, "numeric_limit");
    assert_eq!(result.state["box"]["total"], "0");
    assert!(!result.events.iter().any(|event| event.operation == "sum"));
}

#[test]
fn constructed_values_and_collection_work_respect_explicit_limits() {
    let expression = compile_expression(
        &format!("[{}]", vec!["text"; 150].join(",")),
        "growth.gwt",
        BTreeMap::from([("text".into(), Type::Text)]),
    )
    .unwrap();
    let result = expression
        .evaluate(
            &json!({"text":"x".repeat(10000)}),
            Limits {
                evidence_bytes: 32 * 1_048_576,
                ..Limits::default()
            },
        )
        .unwrap();
    assert_eq!(result.diagnostic.unwrap().code, "value_limit");
    let expression = compile_expression(
        "items == items",
        "equality.gwt",
        BTreeMap::from([("items".into(), Type::List(Box::new(Type::Integer)))]),
    )
    .unwrap();
    let result = expression
        .evaluate(
            &json!({"items":(0..100).collect::<Vec<_>>()}),
            Limits {
                steps: 10,
                ..Limits::default()
            },
        )
        .unwrap();
    assert_eq!(result.diagnostic.unwrap().code, "execution_limit");
    let program =
        compile_program(&source("  FOR item in box.values\n    PASS"), "budget.gwt").unwrap();
    let result = program.run_request(
        "apply",
        &input(json!((0..100).collect::<Vec<_>>())),
        ProgramLimits {
            execution: Limits {
                steps: 10,
                ..Limits::default()
            },
            ..ProgramLimits::default()
        },
    );
    assert_eq!(result.diagnostic.unwrap().code, "execution_limit");
    assert!(result.steps <= 10);
    assert!(
        result
            .events
            .iter()
            .filter(|event| event.operation == "collection item")
            .count()
            < 100
    );
}

#[test]
fn reservation_workflow_matches_independent_expected_cases_and_embedded_scenarios() {
    let program = compile_program(RESERVATION, "reservation.gwt").unwrap();
    let scenarios = program.test_scenarios(ProgramLimits::default());
    assert_eq!(scenarios.len(), 3);
    assert!(scenarios.iter().all(|scenario| scenario.execution.ok));
    for available in 0..=5 {
        for quantity in 1..=6 {
            let input = json!({"order":{"lines":[{"sku":"widget","quantity":quantity},{"sku":"unknown","quantity":1}]},"inventory":{"items":[{"sku":"widget","available":available}]}});
            let result = program.run_request("reserve order", &input, ProgramLimits::default());
            assert!(result.ok, "{:?}", result.diagnostic);
            let reserved = if available >= quantity { quantity } else { 0 };
            assert_eq!(
                result.result.unwrap(),
                json!({"decision":{"line_count":2,"requested":quantity+1,"reserved":reserved,"remaining":available-reserved,"missing":["unknown"],"shortages":if reserved==0{vec!["widget"]}else{vec![]}},"inventory":{"items":[{"sku":"widget","available":available-reserved}]}})
            );
            assert_eq!(input["inventory"]["items"][0]["available"], available);
        }
    }
    let repeated = json!({"order":{"lines":[{"sku":"widget","quantity":3},{"sku":"widget","quantity":3}]},"inventory":{"items":[{"sku":"widget","available":5}]}});
    let result = program.run_request("reserve order", &repeated, ProgramLimits::default());
    assert!(result.ok);
    assert_eq!(
        result.result.unwrap()["decision"],
        json!({"line_count":2,"requested":6,"reserved":3,"remaining":2,"missing":[],"shortages":["widget"]})
    );
    let invalid = json!({"order":{"lines":[{"sku":"widget","quantity":3},{"sku":"widget","quantity":0}]},"inventory":{"items":[{"sku":"widget","available":5}]}});
    let result = program.run_request("reserve order", &invalid, ProgramLimits::default());
    assert_eq!(result.diagnostic.unwrap().code, "assertion_failed");
    assert_eq!(result.state["inventory"], invalid["inventory"]);
    let duplicate_stock = json!({"order":{"lines":[{"sku":"widget","quantity":3}]},"inventory":{"items":[{"sku":"widget","available":1},{"sku":"widget","available":5}]}});
    let result = program.run_request("reserve order", &duplicate_stock, ProgramLimits::default());
    assert!(result.ok);
    let result = result.result.unwrap();
    assert_eq!(result["decision"]["reserved"], 0);
    assert_eq!(result["decision"]["shortages"], json!(["widget"]));
    assert_eq!(result["inventory"], duplicate_stock["inventory"]);
}

#[test]
fn collection_evidence_survives_capture_replay_and_review() {
    let baseline = bundled(RESERVATION);
    let input = json!({"order":{"lines":[{"sku":"widget","quantity":5}]},"inventory":{"items":[{"sku":"widget","available":5}]}});
    let case =
        capture_request(&baseline, "reserve order", &input, ProgramLimits::default()).unwrap();
    let corpus = Corpus::new(vec![CorpusEntry {
        id: "last units".into(),
        label: "Exact stock boundary".into(),
        case: json!(case),
    }])
    .unwrap();
    let candidate = bundled(&RESERVATION.replace(
        "stock.available >= line.quantity",
        "stock.available > line.quantity",
    ));
    let report = review_corpus(&corpus, &candidate).unwrap();
    assert!(report.complete);
    assert_eq!(report.totals.outcome_changed, 1);
    let candidate_run = report.cases[0]
        .comparison
        .as_ref()
        .unwrap()
        .candidate
        .as_ref()
        .unwrap();
    assert_eq!(
        candidate_run.result.as_ref().unwrap()["decision"]["reserved"],
        0
    );
    let explanation = explain_execution(candidate_run, candidate.source_bundle().unwrap()).unwrap();
    assert!(
        explanation
            .steps
            .iter()
            .any(|step| step.operation == "collection selection"
                && step.summary == "Item selected for the body.")
    );
    let html = render_review_html(&report).unwrap();
    assert!(html.contains("Started collection traversal with fixed membership."));
    assert!(html.contains("Recorded state change"));
}
