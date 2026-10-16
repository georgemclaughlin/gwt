use gwt_core::{Limits, ProgramLimits, compile_program};
use serde_json::{Value, json};
use std::{fs, path::PathBuf};

const REFUND: &str = include_str!("../../../examples/refund_review/stage3.gwt");
const INVOICE: &str = include_str!("fixtures/invoice.gwt");

fn facts() -> Value {
    json!({"facts":{"days":46,"damaged":true,"receipt":false,"clearance":false,"member":false}})
}

#[test]
fn refund_programs_pass_all_independently_specified_acceptance_probes() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let manifest_path = root.join("evaluations/maintenance/manifest.json");
    let manifest: Value =
        serde_json::from_str(&fs::read_to_string(&manifest_path).unwrap()).unwrap();
    let mut count = 0;
    for case in manifest["cases"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|case| case["kind"] == "maintain")
    {
        let path = manifest_path
            .parent()
            .unwrap()
            .join(case["gold"]["gwt"].as_str().unwrap());
        let source = fs::read_to_string(&path).unwrap();
        let program = compile_program(&source, &path.to_string_lossy()).unwrap();
        for probe in case["probes"].as_array().unwrap() {
            let execution = program.run_request(
                case["request"].as_str().unwrap(),
                &probe["input"],
                ProgramLimits::default(),
            );
            assert!(execution.ok, "{}: {:?}", case["id"], execution.diagnostic);
            assert_eq!(
                execution.result.as_ref(),
                Some(&probe["expected"]),
                "{} input {}",
                case["id"],
                probe["input"]
            );
            count += 1;
        }
    }
    assert_eq!(count, 336);
}

#[test]
fn existing_program_scenarios_execute_without_python() {
    for (name, source, count) in [
        (
            "stage0",
            include_str!("../../../examples/refund_review/stage0.gwt"),
            4,
        ),
        (
            "stage1",
            include_str!("../../../examples/refund_review/stage1.gwt"),
            4,
        ),
        (
            "stage2",
            include_str!("../../../examples/refund_review/stage2.gwt"),
            4,
        ),
        ("stage3", REFUND, 4),
        (
            "support",
            include_str!("../../../examples/deployable_api/rules.gwt"),
            1,
        ),
        ("hello", include_str!("../../../examples/hello.gwt"), 1),
        ("invoice", INVOICE, 2),
    ] {
        let program =
            compile_program(source, name).unwrap_or_else(|error| panic!("{name}: {error}"));
        let runs = program.test_scenarios(ProgramLimits::default());
        assert_eq!(runs.len(), count, "{name}");
        for run in runs {
            assert!(
                run.execution.ok,
                "{name}/{}: {:?}",
                run.name, run.execution.diagnostic
            );
        }
    }
}

#[test]
fn exact_invoice_results_and_boundary_failures_are_independent_of_scenarios() {
    let program = compile_program(INVOICE, "invoice.gwt").unwrap();
    for (price, quantity, expected) in [
        ("0.1", 3, "0.36"),
        ("19.95", 2, "47.88"),
        (
            "123456789012345678901234567890.1",
            1,
            "148148146814814814681481481468.12",
        ),
    ] {
        let run = program.run_request(
            "price invoice",
            &json!({"invoice":{"unit_price":price,"quantity":quantity}}),
            ProgramLimits::default(),
        );
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(
            run.result.unwrap(),
            json!({"decision":{"total":expected,"status":"priced"}})
        );
        assert!(
            run.state.get("subtotal").is_none(),
            "behavior locals must not leak into request state"
        );
    }
    let failed = program.run_request(
        "price invoice",
        &json!({"invoice":{"unit_price":"2","quantity":0}}),
        ProgramLimits::default(),
    );
    assert!(!failed.ok);
    assert!(failed.result.is_none());
    assert_eq!(failed.diagnostic.unwrap().code, "assertion_failed");
    assert_eq!(failed.state["decision"]["status"], "new");
}

#[test]
fn branch_and_mutation_evidence_matches_the_actual_refund_decision() {
    let program = compile_program(REFUND, "refund.gwt").unwrap();
    let input = facts();
    let run = program.run_request("assess refund", &input, ProgramLimits::default());
    assert!(run.ok);
    let tests: Vec<_> = run
        .events
        .iter()
        .filter(|event| event.operation == "branch")
        .collect();
    assert_eq!(tests.len(), 2);
    assert_eq!(tests[0].value["selected"], false);
    assert_eq!(
        &REFUND[tests[0].span.start..tests[0].span.end],
        "facts.clearance"
    );
    assert_eq!(tests[1].value["selected"], true);
    assert_eq!(
        &REFUND[tests[1].span.start..tests[1].span.end],
        "facts.damaged"
    );
    assert!(
        !run.events
            .iter()
            .any(|event| event.operation == "read facts.receipt")
    );
    assert!(
        run.events
            .iter()
            .any(|event| event.operation == "branch skipped")
    );
    let changes: Vec<_> = run
        .events
        .iter()
        .filter(|event| event.operation == "set")
        .collect();
    assert_eq!(changes.len(), 2);
    assert_eq!(
        changes[0].value,
        json!({"path":"decision.status","sourcePath":"decision.status","before":"rejected","after":"approved"})
    );
    assert_eq!(changes[1].value["after"], "damaged");
    for event in &run.events {
        assert_eq!(event.span.file, "refund.gwt");
        assert!(
            event
                .inputs
                .iter()
                .all(|id| *id < event.sequence && *id > 0)
        );
        assert!(!REFUND[event.span.start..event.span.end].is_empty());
        let prefix = &REFUND[..event.span.start];
        assert_eq!(
            event.span.line,
            prefix.bytes().filter(|b| *b == b'\n').count() + 1
        );
    }
    assert_eq!(input, facts());
    let second = program.run_request("assess refund", &input, ProgramLimits::default());
    assert_eq!(
        serde_json::to_value(run).unwrap(),
        serde_json::to_value(second).unwrap()
    );
}

#[test]
fn request_contract_rejection_does_not_execute_or_initialize_state() {
    let program = compile_program(REFUND, "refund.gwt").unwrap();
    let mut input = facts();
    input["facts"]["days"] = json!(true);
    let run = program.run_request("assess refund", &input, ProgramLimits::default());
    assert!(!run.ok);
    assert_eq!(run.steps, 0);
    assert!(run.events.is_empty());
    assert_eq!(run.state, json!({}));
    assert_eq!(run.diagnostic.unwrap().code, "input_type");
}

#[test]
fn invalid_destinations_and_unselected_invalid_branches_fail_checking() {
    for (source, code) in [
        (REFUND.replace("set decision.status to \"approved\"", "set decision.status to \"lost\""), "assignment_type"),
        (REFUND.replace("set decision.reason to \"expired\"", "set decision.unknown to \"expired\""), "unknown_field"),
        (REFUND.replace("WHEN facts.clearance", "WHEN facts.days"), "condition_type"),
        (REFUND.replace("    ELSE\n      set decision.status to \"rejected\"\n      set decision.reason to \"expired\"", ""), "incomplete_decision"),
        (REFUND.replace("      set decision.reason to \"expired\"", "      set decision.reason to missing"), "unknown_name"),
    ] {
        assert_eq!(compile_program(&source, "bad.gwt").unwrap_err().code, code);
    }
}

#[test]
fn local_scope_and_aliasing_have_explicit_behavior() {
    let source = r#"RECORD Counter
  value: integer
WHEN increment <first> alongside <second>
  GIVEN first is Counter
  AND second is Counter
  LET increment be 1
  set first.value to first.value + increment
  set second.value to second.value + increment
SCENARIO shared cell
GIVEN counter is Counter
  value: 0
WHEN increment counter alongside counter
THEN counter.value == 2
"#;
    let program = compile_program(source, "alias.gwt").unwrap();
    let runs = program.test_scenarios(ProgramLimits::default());
    assert!(runs[0].execution.ok);
    assert_eq!(runs[0].execution.state, json!({"counter":{"value":2}}));
    let invalid = source.replace(
        "  set second.value to second.value + increment",
        "  IF true\n    LET private be 1\n  set second.value to private",
    );
    assert_eq!(
        compile_program(&invalid, "scope.gwt").unwrap_err().code,
        "unknown_name"
    );
}

#[test]
fn nested_record_paths_can_be_passed_to_typed_behaviors() {
    let source = r#"RECORD Counter
  value: integer
RECORD Wrapper
  counter: Counter
WHEN increment <counter>
  GIVEN counter is Counter
  set counter.value to counter.value + 1
SCENARIO nested
GIVEN wrapper is Wrapper
  counter:
    value: 3
WHEN increment wrapper.counter
THEN wrapper.counter.value == 4
"#;
    let run = compile_program(source, "nested.gwt")
        .unwrap()
        .test_scenarios(ProgramLimits::default())
        .remove(0)
        .execution;
    assert!(run.ok);
    assert!(run.events.iter().any(|event| event.operation == "set" && event.value["path"] == "wrapper.counter.value"));
}

#[test]
fn budgets_apply_across_expressions_statements_and_recursive_calls() {
    let program = compile_program(REFUND, "refund.gwt").unwrap();
    let run = program.run_request(
        "assess refund",
        &facts(),
        ProgramLimits {
            execution: Limits {
                steps: 8,
                ..Limits::default()
            },
            ..ProgramLimits::default()
        },
    );
    assert!(!run.ok);
    assert_eq!(run.steps, 8);
    assert_eq!(run.diagnostic.unwrap().code, "execution_limit");
    let recursive = "WHEN recur\n  recur\nSCENARIO recurse\nWHEN recur\n";
    let program = compile_program(recursive, "recursive.gwt").unwrap();
    let run = program
        .test_scenarios(ProgramLimits {
            call_depth: 3,
            ..ProgramLimits::default()
        })
        .remove(0)
        .execution;
    assert!(!run.ok);
    assert_eq!(run.diagnostic.unwrap().code, "call_depth");
    assert_eq!(
        run.events
            .iter()
            .filter(|event| event.operation == "enter behavior")
            .count(),
        3
    );
}

#[test]
fn evidence_limit_refuses_a_mutation_before_committing_it() {
    let program = compile_program(REFUND, "refund.gwt").unwrap();
    let complete = program.run_request("assess refund", &facts(), ProgramLimits::default());
    let before_write: usize = complete
        .events
        .iter()
        .take_while(|event| event.operation != "set")
        .map(|event| serde_json::to_vec(event).unwrap().len())
        .sum();
    let run = program.run_request(
        "assess refund",
        &facts(),
        ProgramLimits {
            execution: Limits {
                evidence_bytes: before_write,
                ..Limits::default()
            },
            ..ProgramLimits::default()
        },
    );
    assert!(!run.ok);
    assert_eq!(run.diagnostic.unwrap().code, "evidence_limit");
    assert_eq!(run.state["decision"]["status"], "rejected");
    assert!(!run.events.iter().any(|event| event.operation == "set"));
}

#[test]
fn failures_expose_prior_committed_state_without_successful_outputs() {
    let changed = REFUND.replace(
        "set decision.reason to \"damaged\"",
        "set decision.reason to \"damaged\"\n      REQUIRE false",
    );
    let program = compile_program(&changed, "failure.gwt").unwrap();
    let run = program.run_request("assess refund", &facts(), ProgramLimits::default());
    assert!(!run.ok);
    assert!(run.result.is_none());
    assert_eq!(run.state["decision"]["reason"], "damaged");
    assert_eq!(run.events.last().unwrap().operation, "assert");
    assert_eq!(run.events.last().unwrap().value, false);
    assert_eq!(run.diagnostic.unwrap().code, "assertion_failed");
}

#[test]
fn invalid_source_structure_and_unsupported_constructs_are_never_silently_skipped() {
    for (source, code) in [
        (
            "RECORD Thing\n  value: integer\nRECORD Thing\n  value: text\n",
            "duplicate_type",
        ),
        ("TYPE A is B\nTYPE B is A\n", "recursive_type"),
        (
            "RECORD Thing\n  value: integer\n  value: text\n",
            "duplicate_field",
        ),
        (
            "GIVEN value is 1\nSCENARIO mixed\nTHEN true\n",
            "mixed_scenarios",
        ),
        ("SCENARIO tabs\n\tGIVEN value is 1\n", "indentation"),
        (
            "REQUEST empty\n  GIVEN value is integer\n",
            "missing_execution",
        ),
        ("WHEN broken <value>\n  PASS\n", "parameter_contract"),
        (
            "SCENARIO unsupported\nUSE \"module.gwt\"\n",
            "imports_require_bundle",
        ),
        (
            "WHEN set <x>\n  GIVEN x is integer\n  PASS\n",
            "behavior_name",
        ),
    ] {
        assert_eq!(
            compile_program(source, "bad.gwt").unwrap_err().code,
            code,
            "{source}"
        );
    }
}

#[test]
fn optional_fields_normalize_in_requests_and_record_initializers() {
    let source = r#"RECORD Facts
  amount: optional<decimal>
  receipt: boolean
RECORD Decision
  accepted: boolean
REQUEST review
  GIVEN facts is Facts
  GIVEN decision is Decision
    accepted: false
  WHEN review facts into decision
  OUTPUT decision is Decision
WHEN review <facts> into <decision>
  GIVEN facts is Facts
  AND decision is Decision
  set decision.accepted to facts.amount is present and facts.amount > 10
SCENARIO absent
GIVEN facts is Facts
  receipt: true
REQUEST review
THEN decision.accepted == false
"#;
    let program = compile_program(source, "optional.gwt").unwrap();
    for (mut facts, expected) in [
        (json!({}), false),
        (json!({"amount":null}), false),
        (json!({"amount":"11"}), true),
    ] {
        facts["receipt"] = json!(true);
        let run = program.run_request("review", &json!({"facts":facts}), ProgramLimits::default());
        assert!(run.ok, "{:?}", run.diagnostic);
        assert_eq!(run.result.unwrap()["decision"]["accepted"], expected);
    }
    assert!(
        program.test_scenarios(ProgramLimits::default())[0]
            .execution
            .ok
    );
}

#[test]
fn source_spans_survive_crlf_comments_and_and_continuations() {
    let source = "PROGRAM unicode\r\n\r\nGIVEN greeting is \"☕ # café\" # comment\r\nWHEN print greeting\r\nTHEN greeting == \"☕ # café\"\r\nAND true\r\n";
    let run = compile_program(source, "unicode.gwt")
        .unwrap()
        .test_scenarios(ProgramLimits::default())
        .remove(0)
        .execution;
    assert!(run.ok);
    assert_eq!(run.output, [json!("☕ # café")]);
    let assertions: Vec<_> = run
        .events
        .iter()
        .filter(|event| event.operation == "assert")
        .collect();
    assert_eq!(assertions.len(), 2);
    assert_eq!(assertions[1].span.line, 6);
    for event in run.events {
        assert!(source.is_char_boundary(event.span.start));
        assert!(source.is_char_boundary(event.span.end));
        assert!(!source[event.span.start..event.span.end].contains('\r'));
    }
}

#[test]
fn branch_nesting_and_calls_share_a_hard_execution_depth_limit() {
    let source = "WHEN recur\n  IF true\n    recur\nSCENARIO recursive\nWHEN recur\n";
    let run = compile_program(source, "depth.gwt")
        .unwrap()
        .test_scenarios(ProgramLimits {
            call_depth: usize::MAX,
            ..ProgramLimits::default()
        })
        .remove(0)
        .execution;
    assert!(!run.ok);
    assert_eq!(run.diagnostic.unwrap().code, "call_depth");
    assert!(run.steps < 200);
}

#[test]
fn structural_text_union_contracts_do_not_depend_on_literal_order() {
    let source = r#"TYPE First is "ready" | "new"
TYPE Second is "new" | "ready"
WHEN approve <status>
  GIVEN status is First
  set status to "ready"
REQUEST approve
  GIVEN status is Second
  WHEN approve status
  OUTPUT status is Second
"#;
    let run = compile_program(source, "union.gwt").unwrap().run_request(
        "approve",
        &json!({"status":"new"}),
        ProgramLimits::default(),
    );
    assert!(run.ok);
    assert_eq!(run.result, Some(json!({"status":"ready"})));
}
