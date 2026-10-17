use gwt_core::{
    CallableKind, ExpectationKind, ExpectationOutcome as Outcome, SourceBundle, ValidationOptions,
    ValidationReport, ValidationStatus, compile_bundle, format_source, validate_bundle,
};
use std::collections::BTreeMap;

fn source(text: &str) -> SourceBundle {
    SourceBundle {
        entry: "main.gwt".into(),
        modules: BTreeMap::from([(
            "main.gwt".into(),
            format_source(text, "main.gwt").unwrap().text,
        )]),
    }
}
fn validate(bundle: &SourceBundle) -> ValidationReport {
    let report = validate_bundle(bundle, ValidationOptions::default());
    assert_eq!(report.check.status, ValidationStatus::Passed, "{report:?}");
    report
}
fn warning(report: &ValidationReport, code: &str) -> bool {
    report.warnings.iter().any(|warning| warning.code == code)
}

#[test]
fn contracts_and_when_assertions_do_not_substitute_for_scenario_expectations() {
    let bundle = source(
        "WHEN check <amount>\n  GIVEN amount is integer\n  REQUIRE amount > 0\nREQUEST check\n  GIVEN amount is integer\n  WHEN check amount\n  OUTPUT amount is integer\n  THEN amount > 0\nSCENARIO calls\nGIVEN amount is 1\nREQUEST check\nWHEN REQUIRE amount > 0\n",
    );
    let report = validate(&bundle);
    assert!(report.ok);
    assert!(report.results[0].expectations.is_empty());
    let evidence = report.evidence.as_ref().unwrap();
    assert_eq!(evidence.scenario_expectations.declared, 0);
    assert_eq!(evidence.scenarios_without_expectations, ["calls"]);
    assert_eq!(evidence.callables.len(), 2);
    for callable in &evidence.callables {
        assert_eq!(callable.recorded_entries, 1);
        assert_eq!(callable.scenarios_with_entries, 1);
    }
    assert!(warning(&report, "scenarios_without_expectations"));
    assert!(!warning(&report, "unobserved_callables"));
    // The runtime really did record three successful assertions; none is a
    // scenario THEN. Reporting those as three scenario expectations would lie.
    let execution = compile_bundle(&bundle)
        .unwrap()
        .run_scenario("calls", Default::default());
    assert_eq!(
        execution
            .events
            .iter()
            .filter(|event| event.operation == "assert")
            .count(),
        3
    );
}

#[test]
fn condition_print_and_failure_expectations_track_own_outcomes_and_event_ids() {
    let bundle = source(
        "WHEN refuse <amount>\n  GIVEN amount is integer\n  REQUIRE amount > 0\nSCENARIO expectations\nGIVEN amount is 0\nWHEN refuse amount\nTHEN fails with \"assertion_failed\"\nAND amount == 0\nWHEN print amount\nTHEN prints [0]\nAND false\nAND true\n",
    );
    let report = validate(&bundle);
    assert!(!report.ok);
    let result = &report.results[0];
    let kinds: Vec<_> = result.expectations.iter().map(|item| item.kind).collect();
    assert_eq!(
        kinds,
        [
            ExpectationKind::Failure,
            ExpectationKind::Condition,
            ExpectationKind::PrintedOutput,
            ExpectationKind::Condition,
            ExpectationKind::Condition
        ]
    );
    let outcomes: Vec<_> = result
        .expectations
        .iter()
        .map(|item| item.outcome)
        .collect();
    assert_eq!(
        outcomes,
        [
            Outcome::Passed,
            Outcome::Passed,
            Outcome::Passed,
            Outcome::Failed,
            Outcome::NotObserved
        ]
    );
    let totals = &report.evidence.as_ref().unwrap().scenario_expectations;
    assert_eq!(
        (
            totals.declared,
            totals.passed,
            totals.failed,
            totals.not_observed
        ),
        (5, 3, 1, 1)
    );
    let execution = compile_bundle(&bundle)
        .unwrap()
        .run_scenario("expectations", Default::default());
    for item in &result.expectations {
        if let Some(id) = item.event {
            assert_eq!(execution.events[id - 1].span, item.span);
        } else {
            assert_eq!(item.outcome, Outcome::NotObserved);
        }
    }
    assert!(warning(&report, "unobserved_expectations"));
    assert!(!warning(&report, "scenarios_without_expectations"));
    assert_eq!(result.diagnostic.as_ref().unwrap().code, "assertion_failed");
}

#[test]
fn evaluation_and_resource_failures_leave_expectations_without_recorded_outcomes() {
    let bundle = source("SCENARIO division\nGIVEN divisor is 0\nTHEN 1 / divisor > 0\nAND true\n");
    let report = validate(&bundle);
    assert!(!report.ok);
    assert_eq!(
        report.results[0].diagnostic.as_ref().unwrap().code,
        "division_by_zero"
    );
    assert!(
        report.results[0]
            .expectations
            .iter()
            .all(|item| item.outcome == Outcome::NotObserved && item.event.is_none())
    );
    assert_eq!(
        report
            .evidence
            .as_ref()
            .unwrap()
            .scenario_expectations
            .failed,
        0
    );
    // The first expectation was attempted, so absence of its outcome must not
    // be described as proof that the statement was never reached.
    assert!(
        report
            .warnings
            .iter()
            .any(|warning| warning.message.contains("before or during evaluation"))
    );
    let mut options = ValidationOptions::default();
    options.limits.execution.evidence_bytes = 0;
    let report = validate_bundle(&source("SCENARIO bounded\nTHEN true\n"), options);
    assert!(!report.ok);
    assert_eq!(
        report.results[0].expectations[0].outcome,
        Outcome::NotObserved
    );
    assert!(report.results[0].expectations[0].event.is_none());
    assert!(
        report.results[0]
            .diagnostic
            .as_ref()
            .unwrap()
            .code
            .contains("limit")
    );
}

#[test]
fn background_and_example_expectations_remain_per_scenario_with_original_spans() {
    let bundle = source(
        "# 😀 café\nBACKGROUND\nGIVEN seed is 10\nTHEN seed == 10\nSCENARIO rows\nGIVEN increment is <value>\nTHEN seed + increment == <total>\nAND true\nEXAMPLES\n  | value | total |\n  | 2 | 12 |\n  | 3 | 0 |\n",
    );
    let text = bundle.modules["main.gwt"].replace('\n', "\r\n");
    let bundle = SourceBundle {
        entry: "main.gwt".into(),
        modules: BTreeMap::from([("main.gwt".into(), text.clone())]),
    };
    let report = validate(&bundle);
    assert!(!report.ok);
    assert_eq!(report.results.len(), 2);
    assert_eq!(report.results[0].name, "rows example 1");
    assert_eq!(report.results[1].name, "rows example 2");
    assert_eq!(report.results[0].expectations.len(), 3);
    assert!(
        report.results[0]
            .expectations
            .iter()
            .all(|item| item.outcome == Outcome::Passed)
    );
    assert_eq!(
        report.results[1]
            .expectations
            .iter()
            .map(|item| item.outcome)
            .collect::<Vec<_>>(),
        [Outcome::Passed, Outcome::Failed, Outcome::NotObserved]
    );
    for result in &report.results {
        for (item, expected) in result.expectations.iter().zip([
            "THEN seed == 10",
            "THEN seed + increment == <total>",
            "AND true",
        ]) {
            assert_eq!(item.span.file, "main.gwt");
            assert_eq!(&text[item.span.start..item.span.end], expected);
        }
    }
    let totals = &report.evidence.as_ref().unwrap().scenario_expectations;
    assert_eq!(
        (
            totals.declared,
            totals.passed,
            totals.failed,
            totals.not_observed
        ),
        (6, 4, 1, 1)
    );
}

#[test]
fn call_inventory_uses_declarations_and_counts_nested_repeated_and_unobserved_calls() {
    let mut bundle = source(
        "USE \"helpers.gwt\"\nREQUEST repeat\n  GIVEN amount is integer\n  WHEN twice amount\n  OUTPUT amount is integer\nSCENARIO first\nGIVEN amount is 0\nREQUEST repeat\nTHEN amount == 2\nSCENARIO second\nGIVEN amount is 4\nWHEN increment amount\nTHEN amount == 5\n",
    );
    bundle.modules.insert("helpers.gwt".into(), "WHEN increment <amount>\n  GIVEN amount is integer\n  add 1 to amount\nWHEN twice <amount>\n  GIVEN amount is integer\n  increment amount\n  increment amount\nWHEN unused <amount>\n  GIVEN amount is integer\n  PASS\nSCENARIO imported only\nGIVEN amount is 0\nWHEN unused amount\nTHEN true\n".into());
    let report = validate(&bundle);
    assert!(report.ok, "{report:?}");
    let calls = &report.evidence.as_ref().unwrap().callables;
    let lookup = |prefix: &str| {
        calls
            .iter()
            .find(|item| item.name.starts_with(prefix))
            .unwrap()
    };
    assert_eq!(
        (
            lookup("increment").recorded_entries,
            lookup("increment").scenarios_with_entries
        ),
        (3, 2)
    );
    assert_eq!(
        (
            lookup("twice").recorded_entries,
            lookup("twice").scenarios_with_entries
        ),
        (1, 1)
    );
    assert_eq!(
        (
            lookup("unused").recorded_entries,
            lookup("unused").scenarios_with_entries
        ),
        (0, 0)
    );
    assert_eq!(
        (
            lookup("repeat").recorded_entries,
            lookup("repeat").scenarios_with_entries
        ),
        (1, 1)
    );
    assert_eq!(lookup("repeat").kind, CallableKind::Request);
    assert_eq!(lookup("increment").kind, CallableKind::Behavior);
    assert_eq!(lookup("increment").definition.file, "helpers.gwt");
    assert_eq!(lookup("repeat").definition.file, "main.gwt");
    for call in calls {
        let text = &bundle.modules[&call.definition.file];
        let declaration = &text[call.definition.start..call.definition.end];
        assert!(
            declaration.starts_with(if call.kind == CallableKind::Behavior {
                "WHEN "
            } else {
                "REQUEST "
            })
        );
    }
    assert!(warning(&report, "unobserved_callables"));
    // Imported scenarios neither contribute assertions nor mark helpers called.
    assert_eq!(
        report
            .evidence
            .as_ref()
            .unwrap()
            .scenario_expectations
            .declared,
        2
    );
}

#[test]
fn stopped_calls_are_observations_not_proof_of_completed_or_successful_behavior() {
    let bundle = source(
        "WHEN fail <value>\n  GIVEN value is integer\n  REQUIRE value > 0\nWHEN never called <value>\n  GIVEN value is integer\n  PASS\nSCENARIO fails\nGIVEN value is 0\nWHEN fail value\nTHEN true\n",
    );
    let report = validate(&bundle);
    assert!(!report.ok);
    let calls = &report.evidence.as_ref().unwrap().callables;
    assert_eq!(calls[0].recorded_entries, 1);
    assert_eq!(calls[0].scenarios_with_entries, 1);
    assert_eq!(calls[1].recorded_entries, 0);
    assert_eq!(
        report.results[0].expectations[0].outcome,
        Outcome::NotObserved
    );
    let mut options = ValidationOptions::default();
    options.limits.execution.steps = 0;
    let report = validate_bundle(&bundle, options);
    assert!(
        report
            .evidence
            .as_ref()
            .unwrap()
            .callables
            .iter()
            .all(|item| item.recorded_entries == 0)
    );
    assert!(warning(&report, "unobserved_callables"));
}

#[test]
fn declaration_only_and_invalid_sources_distinguish_no_observations_from_no_inventory() {
    let bundle = source("WHEN unused <value>\n  GIVEN value is integer\n  PASS\n");
    let report = validate_bundle(
        &bundle,
        ValidationOptions {
            allow_no_scenarios: true,
            ..Default::default()
        },
    );
    assert!(report.ok);
    assert_eq!(report.scenarios.status, ValidationStatus::NotExercised);
    assert_eq!(report.evidence.as_ref().unwrap().callables.len(), 1);
    assert_eq!(
        report.evidence.as_ref().unwrap().callables[0].recorded_entries,
        0
    );
    assert!(warning(&report, "unobserved_callables"));
    let report = validate_bundle(
        &source("SCENARIO invalid\nTHEN missing == 1\n"),
        ValidationOptions::default(),
    );
    assert!(!report.ok);
    assert!(report.evidence.is_none());
    assert!(report.warnings.is_empty());
    assert_eq!(report.scenarios.status, ValidationStatus::Skipped);
}

#[test]
fn print_and_expected_failure_mismatches_and_background_failure_have_exact_outcomes() {
    let bundle = source(
        "SCENARIO wrong print\nWHEN print 1\nTHEN prints [2]\nSCENARIO missing failure\nWHEN print 1\nTHEN fails with \"assertion_failed\"\nSCENARIO expected action assertion\nWHEN REQUIRE false\nTHEN fails with \"assertion_failed\"\nAND true\n",
    );
    let report = validate(&bundle);
    assert!(!report.ok);
    assert_eq!(report.results[0].expectations[0].outcome, Outcome::Failed);
    assert_eq!(
        report.results[0].diagnostic.as_ref().unwrap().code,
        "print_assertion_failed"
    );
    assert_eq!(report.results[1].expectations[0].outcome, Outcome::Failed);
    assert_eq!(
        report.results[1].diagnostic.as_ref().unwrap().code,
        "failure_assertion_failed"
    );
    assert_eq!(report.results[2].expectations.len(), 2);
    assert!(
        report.results[2]
            .expectations
            .iter()
            .all(|item| item.outcome == Outcome::Passed)
    );
    let totals = &report.evidence.as_ref().unwrap().scenario_expectations;
    assert_eq!(
        (
            totals.declared,
            totals.passed,
            totals.failed,
            totals.not_observed
        ),
        (4, 2, 2, 0)
    );
    assert!(!warning(&report, "unobserved_expectations"));
    let report = validate(&source(
        "BACKGROUND\nTHEN false\nSCENARIO first\nTHEN true\nSCENARIO second\nTHEN true\n",
    ));
    for result in &report.results {
        assert_eq!(
            result
                .expectations
                .iter()
                .map(|item| item.outcome)
                .collect::<Vec<_>>(),
            [Outcome::Failed, Outcome::NotObserved]
        );
    }
    let totals = &report.evidence.as_ref().unwrap().scenario_expectations;
    assert_eq!(
        (
            totals.declared,
            totals.passed,
            totals.failed,
            totals.not_observed
        ),
        (4, 0, 2, 2)
    );
}
