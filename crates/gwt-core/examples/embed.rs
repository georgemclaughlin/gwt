//! Compile frozen source once; the host supplies facts and owns external effects.
use gwt_core::{ProgramLimits, SourceBundle, compile_bundle};
use serde_json::json;
use std::collections::BTreeMap;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let source = SourceBundle {
        entry: "invoice.gwt".into(),
        modules: BTreeMap::from([(
            "invoice.gwt".into(),
            include_str!("../tests/fixtures/invoice.gwt").into(),
        )]),
    };
    let program = compile_bundle(&source)?;
    for scenario in program.test_scenarios(ProgramLimits::default()) {
        assert!(scenario.execution.ok, "{}", scenario.name);
    }
    // Exact decimal strings avoid passing a rounded host floating-point value.
    let facts = json!({"invoice":{"unit_price":"19.95","quantity":2}});
    let result = program.run_request("price invoice", &facts, ProgramLimits::default());
    if !result.ok {
        return Err(result
            .diagnostic
            .expect("failed execution diagnostic")
            .into());
    }
    assert_eq!(
        result.result.as_ref().unwrap()["decision"]["total"],
        "47.88"
    );
    println!("{}", serde_json::to_string(&result)?);
    Ok(())
}
