use gwt_core::{
    ProgramLimits, SourceBundle, capture_request, compile_bundle, compile_program,
    explain_execution, format_source, replay_case, scenario_from_case,
};
use serde_json::{Value, json};
use std::collections::BTreeMap;

fn source(scale: u32, mode: &str) -> String {
    format!(
        "REQUEST divide values\n  GIVEN numerator is decimal\n  GIVEN denominator is decimal\n  GIVEN result is 99.0\n  WHEN divide numerator by denominator rounded to {scale} places using {mode} into result\n  OUTPUT result is decimal\n"
    )
}
fn bundled(source: &str) -> gwt_core::CompiledProgram {
    compile_bundle(&SourceBundle {
        entry: "rules.gwt".into(),
        modules: BTreeMap::from([("rules.gwt".into(), source.into())]),
    })
    .unwrap()
}
#[test]
fn independent_decimal_oracle_covers_all_policies_signs_midpoints_and_recurring_quotients() {
    let fixtures: Value =
        serde_json::from_str(include_str!("fixtures/rounded_division.json")).unwrap();
    let mut count = 0;
    for mode in [
        "half_even",
        "half_away_from_zero",
        "toward_zero",
        "floor",
        "ceiling",
    ] {
        for scale in 0..3 {
            let program = bundled(&source(scale, mode));
            for row in fixtures["cases"]
                .as_array()
                .unwrap()
                .iter()
                .filter(|row| row["mode"] == mode && row["scale"] == scale)
            {
                let input = json!({"numerator":row["numerator"],"denominator":row["denominator"]});
                let run = program.run_request("divide values", &input, ProgramLimits::default());
                assert!(run.ok, "{row}: {:?}", run.diagnostic);
                assert_eq!(run.result, Some(json!({"result":row["expected"]})), "{row}");
                let event = run
                    .events
                    .iter()
                    .find(|event| event.operation == "rounded division")
                    .unwrap();
                assert_eq!(
                    event.value,
                    json!({"mode":mode,"scale":scale,"result":row["expected"]})
                );
                assert_eq!(event.inputs.len(), 2);
                explain_execution(&run, program.source_bundle().unwrap()).unwrap();
                count += 1;
            }
        }
    }
    assert_eq!(count, 630);
}
#[test]
fn invalid_modes_scales_operands_and_destinations_are_static_errors() {
    let base = source(2, "half_even");
    for (candidate, code) in [
        (base.replace("half_even", "automatic"), "rounding_mode"),
        (base.replace("2 places", "-1 places"), "rounding_scale"),
        (base.replace("2 places", "513 places"), "rounding_scale"),
        (
            base.replace("2 places", "numerator places"),
            "rounding_scale",
        ),
        (base.replace("numerator by", "true by"), "rounding_type"),
        (
            base.replace("99.0", "99")
                .replace("OUTPUT result is decimal", "OUTPUT result is integer"),
            "rounding_type",
        ),
        (
            base.replace(" rounded to 2 places using half_even", ""),
            "rounding_syntax",
        ),
    ] {
        assert_eq!(
            compile_program(&candidate, "bad.gwt").unwrap_err().code,
            code
        );
    }
    assert_eq!(
        compile_program(
            "WHEN divide <value>\n  GIVEN value is integer\n  PASS\n",
            "reserved.gwt"
        )
        .unwrap_err()
        .code,
        "behavior_name"
    );
}
#[test]
fn failures_budgets_and_operand_errors_cannot_write_the_destination() {
    let program = bundled(&source(2, "half_even"));
    let good = json!({"numerator":"1","denominator":"3"});
    let zero = program.run_request(
        "divide values",
        &json!({"numerator":"1","denominator":"0"}),
        ProgramLimits::default(),
    );
    assert_eq!(zero.diagnostic.unwrap().code, "division_by_zero");
    assert_eq!(zero.state["result"], "99");
    assert!(
        !zero
            .events
            .iter()
            .any(|e| e.operation == "rounded division" || e.operation == "set")
    );
    let full = program.run_request("divide values", &good, ProgramLimits::default());
    for steps in 0..=full.steps {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        let run = program.run_request("divide values", &good, limits);
        if run.ok {
            assert_eq!(run.result, full.result);
        } else {
            assert_eq!(run.diagnostic.unwrap().code, "execution_limit");
        }
        if run.state["result"] == "0.33" {
            assert!(run.events.iter().any(|e| e.operation == "set"));
        }
    }
    for bytes in [0, 100, 500, 1000, 2000] {
        let mut limits = ProgramLimits::default();
        limits.execution.evidence_bytes = bytes;
        let run = program.run_request("divide values", &good, limits);
        if !run.ok {
            assert_eq!(run.diagnostic.unwrap().code, "evidence_limit");
        }
        if run.state["result"] == "0.33" {
            assert!(run.events.iter().any(|e| e.operation == "set"));
        }
    }
    let exact = bundled(
        &source(2, "half_even")
            .replace("divide numerator by", "divide (numerator / denominator) by"),
    );
    let run = exact.run_request("divide values", &good, ProgramLimits::default());
    assert_eq!(run.diagnostic.unwrap().code, "nonterminating_decimal");
    assert_eq!(run.state["result"], "99");
}
#[test]
fn extreme_scales_exact_values_and_digit_overflow_remain_bounded() {
    let p = bundled(&source(512, "half_even"));
    let run = p.run_request(
        "divide values",
        &json!({"numerator":"1","denominator":"2"}),
        ProgramLimits::default(),
    );
    assert!(run.ok);
    assert_eq!(run.result, Some(json!({"result":"0.5"})));
    let p = bundled(&source(0, "half_even"));
    let large = "9".repeat(512);
    let run = p.run_request(
        "divide values",
        &json!({"numerator":large,"denominator":"0.1"}),
        ProgramLimits::default(),
    );
    assert_eq!(run.diagnostic.unwrap().code, "numeric_limit");
    assert_eq!(run.state["result"], "99");
    let run = p.run_request(
        "divide values",
        &json!({"numerator":"-1","denominator":"3"}),
        ProgramLimits::default(),
    );
    assert_eq!(run.result, Some(json!({"result":"0"})));
}
#[test]
fn source_evidence_replay_generation_and_formatter_preserve_the_rounding_policy() {
    let s = source(2, "half_even")
        .replace("REQUEST", "# café 😀\nREQUEST")
        .replace('\n', "\r\n");
    let p = bundled(&s);
    let case = capture_request(
        &p,
        "divide values",
        &json!({"numerator":"1","denominator":"3"}),
        ProgramLimits::default(),
    )
    .unwrap();
    assert!(replay_case(&case).unwrap().verified);
    let generated = scenario_from_case(&case, "captured rounding").unwrap();
    let generated_program = compile_bundle(generated.source_bundle()).unwrap();
    assert!(
        generated_program
            .run_scenario(generated.name(), ProgramLimits::default())
            .ok
    );
    let formatted = format_source(&s, "rules.gwt").unwrap();
    assert!(
        formatted
            .text
            .contains("rounded to 2 places using half_even")
    );
    let p = bundled(&formatted.text);
    let run = p.run_request("divide values", case.input(), ProgramLimits::default());
    assert_eq!(run.result, Some(json!({"result":"0.33"})));
    let explanation = explain_execution(&run, p.source_bundle().unwrap()).unwrap();
    assert!(
        explanation
            .steps
            .iter()
            .any(|s| s.operation == "rounded division" && s.source.text.contains("half_even"))
    );
}
#[test]
fn public_quote_example_runs_all_scenarios_and_exposes_the_rounding_change() {
    let s = include_str!("../../../examples/native_rounded_division/rules.gwt");
    let p = bundled(s);
    let scenarios = p.test_scenarios(ProgramLimits::default());
    assert_eq!(scenarios.len(), 8);
    assert!(scenarios.iter().all(|s| s.execution.ok), "{scenarios:?}");
    let input = json!({"total":"10.05","units":2});
    let before = p.run_request("quote unit price", &input, ProgramLimits::default());
    let after = bundled(&s.replace("half_even", "half_away_from_zero")).run_request(
        "quote unit price",
        &input,
        ProgramLimits::default(),
    );
    assert_eq!(before.result, Some(json!({"price":"5.02"})));
    assert_eq!(after.result, Some(json!({"price":"5.03"})));
}

#[test]
fn traversal_aliases_and_example_rows_keep_rounding_and_source_locations() {
    let s = "WHEN halve <price>\n  GIVEN price is decimal\n  divide price by 2 rounded to 2 places using half_even into price\nSCENARIO copied argument\nGIVEN price is 0.05\nWHEN halve (price)\nTHEN price == 0.05\nSCENARIO shared argument\nGIVEN price is 0.05\nWHEN halve price\nTHEN price == 0.02\nWHEN halve each <prices>\n  GIVEN prices is list<decimal>\n  FOR price in prices\n    divide price by 2 rounded to 2 places using half_even into price\nSCENARIO list aliases\nGIVEN prices is [0.05, -0.05]\nWHEN halve each prices\nTHEN prices == [0.02, -0.02]\nSCENARIO row\nGIVEN price is <amount>\nWHEN divide price by 2 rounded to 2 places using half_even into price\nTHEN price == <expected>\nEXAMPLES\n  | amount | expected |\n  | 0.05 | 0.02 |\n  | -0.05 | -0.02 |\n";
    let p = bundled(s);
    let runs = p.test_scenarios(ProgramLimits::default());
    assert_eq!(runs.len(), 5);
    for run in runs {
        assert!(run.execution.ok, "{:?}", run.execution.diagnostic);
        explain_execution(&run.execution, p.source_bundle().unwrap()).unwrap();
    }
}
