//! Standalone consumer probe; compiled against the extracted Cargo artifact.
use gwt_core::{
    Corpus, CorpusEntry, ProgramLimits, RegressionScope, SourceBundle, capture_request,
    compile_bundle, test_corpus,
};
use serde_json::json;
use std::{collections::BTreeMap, fs};

fn main() {
    let source = fs::read_to_string(std::env::args().nth(1).expect("invoice source")).unwrap();
    let bundle = |source: String| SourceBundle {
        entry: "invoice.gwt".into(),
        modules: BTreeMap::from([("invoice.gwt".into(), source)]),
    };
    let program = compile_bundle(&bundle(source.clone())).unwrap();
    let case = capture_request(&program, "price invoice", &json!({}), ProgramLimits::default()).unwrap();
    assert_eq!(case.observed()["ok"], false);
    let corpus = Corpus::new(vec![CorpusEntry {
        id: "missing-input".into(),
        label: "missing invoice stays rejected".into(),
        case: json!(case),
    }]).unwrap();
    let unchanged = test_corpus(&corpus, &program, RegressionScope::Execution).unwrap();
    assert!(unchanged.passed);
    assert_eq!(unchanged.review.totals.candidate_failed, 1);
    let moved = compile_bundle(&bundle(format!("# source moved\n{source}"))).unwrap();
    let outcomes = test_corpus(&corpus, &moved, RegressionScope::OutcomesAndState).unwrap();
    assert!(outcomes.passed);
    let execution = test_corpus(&corpus, &moved, RegressionScope::Execution).unwrap();
    assert!(!execution.passed);
    println!("{}", json!({"unchanged": unchanged, "movedOutcomes": outcomes, "movedExecution": execution}));
}
