use gwt_core::{CompiledProgram, ProgramLimits, compare_policies, compile_program};
use serde_json::{Value, json};
use std::{fmt::Write, process::Command};

const BASELINE: &str = include_str!("../../../examples/native_delivery/rules.gwt");
const CANDIDATE: &str = include_str!("../../../examples/native_review_walkthrough/candidate.gwt");
const REQUEST: &str = "quote delivery";

fn program(source: &str) -> CompiledProgram {
    compile_program(source, "rules.gwt").unwrap()
}

fn diff(baseline: &str, candidate: &str) -> Value {
    compare_policies(&program(baseline), &program(candidate), REQUEST).unwrap()
}

fn native(program: &CompiledProgram, input: &Value) -> Value {
    let run = program.run_request(REQUEST, input, ProgramLimits::default());
    match run.diagnostic {
        None => json!({"output":run.result.unwrap()}),
        Some(d) => json!({"rejection":d.code}),
    }
}

#[test]
fn walkthrough_reports_exact_bounds_and_replayable_witnesses() {
    let report = diff(BASELINE, CANDIDATE);
    assert_eq!(report["regionsCompared"], 10);
    assert_eq!(report["changedRegions"], 1);
    let change = &report["changes"][0];
    assert_eq!(
        change["where"],
        json!([
            {"field":"parcel.member","equals":false},
            {"field":"parcel.weight_grams","min":"1001","max":"1500"}
        ])
    );
    assert_eq!(change["baseline"]["output"]["quote"]["fee"], 9);
    assert_eq!(change["candidate"]["output"]["quote"]["fee"], 5);
    for (i, weight) in [1001, 1500].iter().enumerate() {
        let input = &change["witnesses"][i];
        assert_eq!(
            input,
            &json!({"parcel":{"member":false,"weight_grams":weight}})
        );
        assert_eq!(native(&program(BASELINE), input), change["baseline"]);
        assert_eq!(native(&program(CANDIDATE), input), change["candidate"]);
    }
}

#[test]
fn singleton_change_is_invisible_to_every_saved_example() {
    let mutant = CANDIDATE.replacen("    WHEN parcel.weight_grams <= 1500",
        "    WHEN parcel.weight_grams == 1237\n      set quote.fee to 99\n    WHEN parcel.weight_grams <= 1500", 1);
    let before = program(CANDIDATE);
    let after = program(&mutant);
    let cases: Value = serde_json::from_str(include_str!(
        "../../../examples/native_review_walkthrough/cases.json"
    ))
    .unwrap();
    for case in cases.as_array().unwrap() {
        assert_eq!(
            native(&before, &case["input"]),
            native(&after, &case["input"])
        );
    }
    let report = compare_policies(&before, &after, REQUEST).unwrap();
    assert_eq!(report["changedRegions"], 1);
    let change = &report["changes"][0];
    assert_eq!(
        change["where"][1],
        json!({"field":"parcel.weight_grams","min":"1237","max":"1237"})
    );
    let input = json!({"parcel":{"weight_grams":1237,"member":false}});
    assert_eq!(change["witnesses"], json!([input]));
    assert_eq!(change["candidate"], native(&after, &input));
    assert_eq!(change["candidate"]["output"]["quote"]["fee"], 99);
}

#[test]
fn rejection_boundary_and_equivalent_spelling() {
    let changed = CANDIDATE.replace(
        "REQUIRE parcel.weight_grams > 0",
        "REQUIRE 0 <= parcel.weight_grams",
    );
    let report = diff(CANDIDATE, &changed);
    assert_eq!(report["changedRegions"], 2);
    for change in report["changes"].as_array().unwrap() {
        assert_eq!(
            change["where"][1],
            json!({"field":"parcel.weight_grams","min":"0","max":"0"})
        );
        assert_eq!(change["baseline"], json!({"rejection":"assertion_failed"}));
        assert!(change["candidate"]["output"].is_object());
    }
    let equivalent = CANDIDATE.replace("parcel.weight_grams <= 1500", "1501 > parcel.weight_grams");
    assert_eq!(diff(CANDIDATE, &equivalent)["changes"], json!([]));
}

fn predicate_policy(condition: &str, fee: u8) -> String {
    format!(
        r"PROGRAM threshold

REQUEST quote delivery
  GIVEN x is integer
  GIVEN y is integer
  GIVEN fee is 0
  WHEN rate x and y into fee
  OUTPUT fee is integer

WHEN rate <x> and <y> into <fee>
  GIVEN x is integer
  AND y is integer
  AND fee is integer
  IF {condition}
    set fee to {fee}
"
    )
}

#[test]
fn comparisons_and_cartesian_products_match_native_execution() {
    for op in ["<", "<=", "==", "!=", ">=", ">"] {
        for condition in [
            format!("x {op} -2 and y >= 1"),
            format!("-2 {op} x and y >= 1"),
        ] {
            let a = program(&predicate_policy(&condition, 1));
            let b = program(&predicate_policy(&condition, 2));
            let report = compare_policies(&a, &b, REQUEST).unwrap();
            for x in -4..=2 {
                for y in -1..=3 {
                    let input = json!({"x":x,"y":y});
                    let matches: Vec<_> = report["changes"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .filter(|change| {
                            change["where"].as_array().unwrap().iter().all(|c| {
                                let n = input[c["field"].as_str().unwrap()].as_i64().unwrap();
                                c["min"].as_str().is_none_or(|lo| n >= lo.parse().unwrap())
                                    && c["max"].as_str().is_none_or(|hi| n <= hi.parse().unwrap())
                            })
                        })
                        .collect();
                    let baseline = native(&a, &input);
                    let candidate = native(&b, &input);
                    assert_eq!(
                        matches.len(),
                        usize::from(baseline != candidate),
                        "{condition}, {input}"
                    );
                    if let [change] = matches[..] {
                        assert_eq!(change["baseline"], baseline);
                        assert_eq!(change["candidate"], candidate);
                    }
                }
            }
        }
    }
}

#[test]
fn largest_integer_is_a_replayable_singleton() {
    let max = "9".repeat(512);
    let policy = |fee| predicate_policy(&format!("x == {max}"), fee);
    let report = diff(&policy(1), &policy(2));
    assert_eq!(report["changedRegions"], 1);
    let change = &report["changes"][0];
    assert_eq!(
        change["where"][0],
        json!({"field":"x","min":max,"max":null})
    );
    assert_eq!(change["witnesses"][0]["x"].to_string(), max);
}

#[test]
fn refuses_unsupported_programs_and_excessive_partitions() {
    for source in [
        CANDIDATE.replace("set quote.fee to 5", "set quote.fee to parcel.weight_grams"),
        CANDIDATE.replace("set quote.fee to 5", "set parcel.weight_grams to 5"),
        CANDIDATE.replace(
            "parcel.weight_grams <= 1500",
            "parcel.weight_grams + 1 <= 1501",
        ),
        CANDIDATE.replace("  OUTPUT quote is Quote", "  OUTPUT parcel is Parcel"),
        predicate_policy("x == y", 1),
    ] {
        let compiled = program(&source);
        let err = compare_policies(&compiled, &compiled, REQUEST).unwrap_err();
        assert_eq!(err.code, "policy_diff_unsupported");
        assert!(err.span.line > 1);
    }
    let mut fields = String::new();
    for i in 0..11 {
        writeln!(fields, "  GIVEN flag{i} is boolean").unwrap();
    }
    let p = program(&format!(
        r"PROGRAM cap
REQUEST quote delivery
{fields}  GIVEN fee is 1
  WHEN unchanged
  OUTPUT fee is integer

WHEN unchanged
  PASS
"
    ));
    assert!(
        compare_policies(&p, &p, REQUEST)
            .unwrap_err()
            .message
            .contains("1024")
    );
}

#[test]
fn cli_reports_source_excerpts_and_returns_nonzero_for_unknown_request() {
    let run = |args: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_gwt"))
            .args([
                "policy-diff",
                "../../examples/native_delivery/rules.gwt",
                "../../examples/native_review_walkthrough/candidate.gwt",
                "--request",
            ])
            .args(args)
            .output()
            .unwrap()
    };
    let result = run(&[REQUEST, "--text"]);
    let report = String::from_utf8(result.stdout).unwrap();
    assert!(result.status.success(), "{report}");
    assert!(report.contains("1 of 10 regions changed"));
    assert!(report.contains("candidate.gwt:31  parcel.weight_grams <= 1500 -> true"));
    let result = run(&["missing"]);
    assert!(!result.status.success());
    let report: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(report["ok"], false);
    assert_eq!(report["diagnostic"]["code"], "unknown_request");
    assert!(report.get("changedRegions").is_none());
}

#[test]
fn evidence_exhaustion_at_the_widest_input_is_inconclusive() {
    let mut source = String::from(
        r"PROGRAM limit
REQUEST quote
  GIVEN x is integer
  GIVEN fee is 0
  WHEN check x
  OUTPUT fee is integer
WHEN check <x>
  GIVEN x is integer
",
    );
    source.push_str(&"  REQUIRE x >= 0\n".repeat(1000));
    let p = program(&source);
    assert!(
        p.run_request("quote", &json!({"x":0}), ProgramLimits::default())
            .ok
    );
    let err = compare_policies(&p, &p, "quote").unwrap_err();
    assert_eq!(err.code, "policy_diff_inconclusive");
    assert!(err.message.contains("evidence_limit"));
}

#[test]
fn tracks_a_nested_input_alias_across_two_calls() {
    let policy = |comparison: &str| {
        format!(
            r"PROGRAM nested
RECORD Parcel
  info:
    grams: integer
REQUEST quote delivery
  GIVEN p is Parcel
  GIVEN fee is 0
  WHEN rate p into fee
  OUTPUT fee is integer
WHEN rate <parcel> into <amount>
  GIVEN parcel is Parcel
  AND amount is integer
  apply parcel.info.grams to amount
WHEN apply <weight> to <result>
  GIVEN weight is integer
  AND result is integer
  IF {comparison}
    set result to 5
"
        )
    };
    let report = diff(&policy("weight <= 1000"), &policy("1500 >= weight"));
    assert_eq!(report["changedRegions"], 1);
    let change = &report["changes"][0];
    assert_eq!(
        change["where"],
        json!([{"field":"p.info.grams","min":"1001","max":"1500"}])
    );
    assert_eq!(change["witnesses"][0], json!({"p":{"info":{"grams":1001}}}));
}

#[test]
fn different_input_contracts_return_a_diagnostic() {
    let original = predicate_policy("x < 1", 1);
    let modified = original.replacen(
        "GIVEN y is integer",
        "GIVEN extra is boolean\n  GIVEN y is integer",
        1,
    );
    let d = compare_policies(&program(&original), &program(&modified), REQUEST).unwrap_err();
    assert_eq!(d.code, "policy_diff_unsupported");
    assert!(d.message.contains("input contracts differ"));
}
