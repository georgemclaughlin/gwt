use gwt_core::compile_program;
use serde_json::Value;

#[test]
fn language_choices_have_specific_refusals_and_independent_migration_results() {
    let cases: Vec<Value> =
        serde_json::from_str(include_str!("fixtures/language_choices.json")).unwrap();
    assert_eq!(cases.len(), 30);
    let mut accepted = 0;
    let mut successful = 0;
    for mut row in cases {
        // Preserve the historical probe fixture. The finite-contract extension
        // changes these two current expectations, not the old captured results.
        if row["id"] == "numeric-literal-union" {
            row["nativeCheckDiagnostic"] = "argument_type".into();
        } else if row["id"] == "boolean-literal-union" {
            row["nativeCheck"] = true.into();
        }
        let id = row["id"].as_str().unwrap();
        let compiled = compile_program(row["source"].as_str().unwrap(), &format!("{id}.gwt"));
        assert_eq!(compiled.is_ok(), row["nativeCheck"], "{id}: {compiled:?}");
        if !row["nativeCheck"].as_bool().unwrap() {
            assert_eq!(
                compiled.unwrap_err().code,
                row["nativeCheckDiagnostic"],
                "{id}"
            );
            continue;
        }
        accepted += 1;
        let program = compiled.unwrap();
        let result = if let Some(request) = row.get("request") {
            program.run_request(request.as_str().unwrap(), &row["input"], Default::default())
        } else {
            program.run_scenario("Main", Default::default())
        };
        assert_eq!(
            result.ok,
            row.get("nativeRun").is_none_or(|v| v.as_bool().unwrap()),
            "{id}: {:?}",
            result.diagnostic
        );
        successful += usize::from(result.ok);
        if let Some(state) = row.get("expectedState") {
            assert_eq!(&result.state, state, "{id}");
        }
        if let Some(expected) = row.get("expectedResult") {
            assert_eq!(result.result.as_ref(), Some(expected), "{id}");
        }
        if let Some(code) = row.get("diagnostic") {
            assert_eq!(
                result.diagnostic.unwrap().code,
                code.as_str().unwrap(),
                "{id}"
            );
        }
    }
    assert_eq!(accepted, 18);
    assert_eq!(successful, 16);
}
