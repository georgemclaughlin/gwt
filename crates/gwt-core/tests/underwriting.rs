use gwt_core::{SourceBundle, capture_request, compare_case, compile_bundle, replay_case};
use serde_json::{Value as Json, json};
use std::collections::BTreeMap;

const SOURCE: &str = include_str!("../../../examples/loan_underwriting/native_rules.gwt");
const REQUEST: &str = "underwrite loan";

fn bundle(source: &str) -> SourceBundle {
    SourceBundle {
        entry: "native_rules.gwt".into(),
        modules: BTreeMap::from([("native_rules.gwt".into(), source.into())]),
    }
}
fn fixtures() -> Vec<Json> {
    serde_json::from_str(include_str!("fixtures/underwriting.json")).unwrap()
}

#[test]
fn independent_rational_quotients_match_all_native_threshold_and_precedence_results() {
    let p = compile_bundle(&bundle(SOURCE)).unwrap();
    let rows = fixtures();
    assert_eq!(rows.len(), 1072);
    for row in rows {
        let result = p.run_request(REQUEST, &row["input"], Default::default());
        assert!(result.ok, "{}: {:?}", row["id"], result.diagnostic);
        assert_eq!(result.result.unwrap(), row["expected"], "{}", row["id"]);
    }
    let scenarios = p.test_scenarios(Default::default());
    assert_eq!(scenarios.len(), 15);
    assert!(scenarios.iter().all(|s| s.execution.ok));
}

#[test]
fn captured_exact_boundaries_detect_changed_inequalities_and_replay() {
    let p = compile_bundle(&bundle(SOURCE)).unwrap();
    let rows = fixtures();
    for (old, new) in [
        (
            "ratio.numerator <= 0.36 * ratio.denominator",
            "ratio.numerator < 0.36 * ratio.denominator",
        ),
        (
            "ratio.numerator <= 0.90 * ratio.denominator",
            "ratio.numerator < 0.90 * ratio.denominator",
        ),
        (
            "RETURN ratio.numerator <= limit * ratio.denominator",
            "RETURN ratio.numerator < limit * ratio.denominator",
        ),
        (
            "RETURN ratio.numerator >= minimum * ratio.denominator",
            "RETURN ratio.numerator > minimum * ratio.denominator",
        ),
        (
            "application.credit_score < 700",
            "application.credit_score <= 700",
        ),
    ] {
        assert!(SOURCE.contains(old));
        let faulty = compile_bundle(&bundle(&SOURCE.replace(old, new))).unwrap();
        let row = rows
            .iter()
            .find(|r| {
                faulty
                    .run_request(REQUEST, &r["input"], Default::default())
                    .result
                    .as_ref()
                    != Some(&r["expected"])
            })
            .expect("independent corpus must contain a policy fault witness");
        let case = capture_request(&p, REQUEST, &row["input"], Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
        assert!(
            compare_case(&case, &faulty)
                .unwrap()
                .changes
                .unwrap()
                .outcome
        );
    }
}

#[test]
fn invalid_denominators_fail_before_ratio_writes_and_failed_cases_replay() {
    let p = compile_bundle(&bundle(SOURCE)).unwrap();
    let original = &fixtures()[0]["input"];
    for (field, value) in [
        ("annual_income", "0"),
        ("annual_income", "-1"),
        ("home_price", "0"),
        ("home_price", "-1"),
        ("down_payment", "100000"),
        ("down_payment", "100001"),
    ] {
        let mut input = original.clone();
        input["application"][field] = json!(value);
        let result = p.run_request(REQUEST, &input, Default::default());
        assert!(!result.ok);
        assert_eq!(result.diagnostic.as_ref().unwrap().code, "assertion_failed");
        assert_eq!(result.state["decision"]["principal"], "0");
        for field in ["dti", "ltv", "reserve_months"] {
            assert_eq!(
                result.state["decision"][field],
                json!({"numerator":"0","denominator":"1"})
            );
        }
        let case = capture_request(&p, REQUEST, &input, Default::default()).unwrap();
        assert!(replay_case(&case).unwrap().verified);
    }
    // Calling a ratio helper directly cannot bypass its positive-denominator rule.
    let wrapper = "\nREQUEST inspect ratio\n  GIVEN ratio is ExactRatio\n  WHEN within ratio limit 0.43\n  OUTPUT ratio is ExactRatio\n";
    let helper = compile_bundle(&bundle(&(SOURCE.to_owned() + wrapper))).unwrap();
    for denominator in ["0", "-1"] {
        let result = helper.run_request(
            "inspect ratio",
            &json!({"ratio":{"numerator":"1","denominator":denominator}}),
            Default::default(),
        );
        assert_eq!(result.diagnostic.unwrap().code, "assertion_failed");
    }
}
