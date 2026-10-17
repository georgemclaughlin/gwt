//! Compiled as a separate consumer of the extracted package, outside the GWT workspace.
use gwt_core::{
    ExecutionCase, ProgramLimits, SourceBundle, capture_request, capture_scenario, compile_bundle,
    engine_identity, explain_execution, replay_case,
};
use serde_json::{Value as Json, json};
use std::{fs, sync::Arc, thread};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let path = std::env::args().nth(1).expect("source bundle path");
    let bundle: SourceBundle = serde_json::from_str(&fs::read_to_string(path)?)?;
    let program = Arc::new(compile_bundle(&bundle)?);
    assert_eq!(program.request_names(), ["price invoice"]);
    let inspection = program.inspect().to_json()?;
    assert_eq!(inspection["kind"], "gwt.native-inspection");
    assert_eq!(inspection["programIdentity"], json!(program.identity()));
    assert_eq!(
        inspection["requests"][0]["requiredInputs"],
        json!(["invoice"])
    );
    assert_eq!(
        inspection["requests"][0]["inputs"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        inspection["requests"][0]["inputs"][0]["type"],
        json!({"kind":"record","value":{"quantity":{"kind":"integer"},"unit_price":{"kind":"decimal"}}})
    );
    assert_eq!(inspection["requests"][0]["outputs"][0]["name"], "decision");
    assert_eq!(inspection["scenarios"].as_array().unwrap().len(), 2);

    let inputs = [
        (
            "normal",
            r#"{"invoice":{"unit_price":"19.95","quantity":2}}"#,
            Some("47.88"),
            None,
        ),
        (
            "three-units",
            r#"{"invoice":{"unit_price":"10.25","quantity":3}}"#,
            Some("36.9"),
            None,
        ),
        (
            "zero-price",
            r#"{"invoice":{"unit_price":"0.00","quantity":1}}"#,
            Some("0"),
            None,
        ),
        (
            "small-decimal",
            r#"{"invoice":{"unit_price":"0.1","quantity":3}}"#,
            Some("0.36"),
            None,
        ),
        (
            "integer-price",
            r#"{"invoice":{"unit_price":12,"quantity":1}}"#,
            Some("14.4"),
            None,
        ),
        (
            "beyond-js-integer",
            r#"{"invoice":{"unit_price":"0.25","quantity":9007199254740993}}"#,
            Some("2702159776422297.9"),
            None,
        ),
        (
            "beyond-machine-integer",
            r#"{"invoice":{"unit_price":"0.25","quantity":123456789012345678901234567890}}"#,
            Some("37037036703703703670370370367"),
            None,
        ),
        (
            "negative-price",
            r#"{"invoice":{"unit_price":"-1","quantity":1}}"#,
            None,
            Some("assertion_failed"),
        ),
        (
            "zero-quantity",
            r#"{"invoice":{"unit_price":"1","quantity":0}}"#,
            None,
            Some("assertion_failed"),
        ),
        ("missing-invoice", "{}", None, Some("missing_input")),
        (
            "boolean-quantity",
            r#"{"invoice":{"unit_price":"1","quantity":true}}"#,
            None,
            Some("input_type"),
        ),
        (
            "fractional-json-number",
            r#"{"invoice":{"unit_price":1.25,"quantity":1}}"#,
            None,
            Some("input_type"),
        ),
        (
            "extra-field",
            r#"{"invoice":{"unit_price":"1","quantity":1,"extra":true}}"#,
            None,
            Some("unknown_input"),
        ),
        (
            "missing-quantity",
            r#"{"invoice":{"unit_price":"1"}}"#,
            None,
            Some("missing_input"),
        ),
    ];
    let mut records = Vec::new();
    for (id, raw, total, failure) in inputs {
        let input: Json = serde_json::from_str(raw)?;
        let original = input.clone();
        let execution = program.run_request("price invoice", &input, ProgramLimits::default());
        assert_eq!(
            execution.ok,
            total.is_some(),
            "{id}: {:?}",
            execution.diagnostic
        );
        if let Some(total) = total {
            assert_eq!(
                execution.result.as_ref().unwrap(),
                &json!({"decision":{"status":"priced","total":total}}),
                "{id}"
            );
        } else {
            assert!(execution.result.is_none());
            assert_eq!(
                execution.diagnostic.as_ref().unwrap().code,
                failure.unwrap(),
                "{id}"
            );
        }
        assert_eq!(input, original, "the host input must not be mutated");
        let explanation = explain_execution(&execution, &bundle)?;
        assert_eq!(explanation.steps.len(), execution.events.len());
        let case = capture_request(&program, "price invoice", &input, ProgramLimits::default())?;
        assert_eq!(&json!(execution), case.observed());
        assert!(replay_case(&ExecutionCase::from_json(&case.to_json())?)?.verified);
        records.push(json!({"id":id,"input":input,"case":case,"expectedTotal":total,"expectedFailure":failure}));
    }
    let baseline = records[0]["input"].clone();
    for (id, steps, evidence, expected) in [
        ("zero-steps", 0, 1_048_576, "execution_limit"),
        ("zero-evidence", 100_000, 0, "evidence_limit"),
    ] {
        let mut limits = ProgramLimits::default();
        limits.execution.steps = steps;
        limits.execution.evidence_bytes = evidence;
        let case = capture_request(&program, "price invoice", &baseline, limits)?;
        assert_eq!(case.observed()["diagnostic"]["code"], expected);
        assert!(replay_case(&case)?.verified);
        records.push(json!({"id":id,"input":baseline,"case":case,"expectedFailure":expected}));
    }
    for scenario in program.test_scenarios(ProgramLimits::default()) {
        assert!(scenario.execution.ok, "{}", scenario.name);
        let case = capture_scenario(&program, &scenario.name, ProgramLimits::default())?;
        assert_eq!(&json!(scenario.execution), case.observed());
        assert!(replay_case(&case)?.verified);
        records.push(json!({"id":scenario.name,"case":case}));
    }
    let unknown = program.run_request("not a request", &json!({}), ProgramLimits::default());
    assert_eq!(unknown.diagnostic.unwrap().code, "unknown_request");
    // Exercise the public profiling API from the separately packaged library.
    // Account for bytes independently using the ordinary captured observation.
    for row in &mut records {
        let record = &row["case"]["record"];
        let limits = serde_json::from_value(record["limits"].clone())?;
        let report = if let Some(name) = record["request"].as_str() {
            program.profile_request(name, &record["input"], limits)?
        } else {
            program.profile_scenario(record["scenario"].as_str().unwrap(), limits)?
        }
        .to_json()?;
        let observed = &record["observed"];
        assert_eq!(report["ok"], observed["ok"]);
        assert_eq!(report["steps"], observed["steps"]);
        assert_eq!(report["diagnostic"], observed["diagnostic"]);
        assert_eq!(report["limits"], record["limits"]);
        let events = observed["events"].as_array().unwrap();
        let mut bytes = 0;
        let mut value_bytes = 0;
        for event in events {
            bytes += serde_json::to_vec(event)?.len();
            value_bytes += serde_json::to_vec(&event["value"])?.len();
        }
        assert_eq!(
            report["evidence"],
            json!({"events":events.len(),"bytes":bytes,
            "valueBytes":value_bytes,"metadataBytes":bytes-value_bytes})
        );
        row["profile"] = report;
    }
    // Share a single compiled program. Only invocation-local runtime values are mutable.
    let expected = Arc::new(records.clone());
    let workers: Vec<_> = (0..4)
        .map(|_| {
            let program = Arc::clone(&program);
            let expected = Arc::clone(&expected);
            thread::spawn(move || {
                for _ in 0..4 {
                    for row in expected.iter() {
                        let record = &row["case"]["record"];
                        let limits = serde_json::from_value(record["limits"].clone()).unwrap();
                        let run = if let Some(name) = record["request"].as_str() {
                            program.run_request(name, &record["input"], limits)
                        } else {
                            program.run_scenario(record["scenario"].as_str().unwrap(), limits)
                        };
                        assert_eq!(json!(run), record["observed"], "{}", row["id"]);
                    }
                }
            })
        })
        .collect();
    for worker in workers {
        worker.join().expect("host worker");
    }
    assert_eq!(records.len(), 18);
    println!(
        "{}",
        json!({"version":gwt_core::version_info(),"inspection":inspection,"engine":engine_identity(),"bundle":bundle,"records":records,"sharedProgramThreads":4,"concurrentExecutions":288,"allIndependentExpectationsPassed":true})
    );
    Ok(())
}
