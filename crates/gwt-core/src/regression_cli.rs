use gwt_core::{Corpus, MAX_CORPUS_BYTES, RegressionScope, compile_file, test_corpus};
use serde_json::{Value, json};
use std::path::Path;

pub fn run(args: &[String]) -> Result<(bool, Value), Box<dyn std::error::Error>> {
    let usage = "usage: gwt test-cases CORPUS.json --candidate FILE.gwt --match outcomes-and-state|execution [--import-root DIRECTORY]";
    if args.len() < 5 || args.len() % 2 != 1 {
        return Err(usage.into());
    }
    let options = super::cli_options::paired(
        &args[1..],
        |option| matches!(option, "--candidate" | "--match" | "--import-root"),
        usage,
    )?;
    let candidate_path = options.get("--candidate").ok_or(usage)?;
    let scope = match options.get("--match").copied() {
        Some("outcomes-and-state") => RegressionScope::OutcomesAndState,
        Some("execution") => RegressionScope::Execution,
        _ => return Err(usage.into()),
    };
    let corpus = match Corpus::from_json(&super::read_bounded(&args[0], MAX_CORPUS_BYTES)?) {
        Ok(corpus) => corpus,
        Err(error) => {
            return Ok((
                false,
                json!({"ok":false,"phase":"corpus","diagnostic":error}),
            ));
        }
    };
    let candidate = match compile_file(
        Path::new(candidate_path),
        options.get("--import-root").map(Path::new),
    ) {
        Ok(candidate) => candidate,
        Err(error) => {
            return Ok((
                false,
                json!({"ok":false,"phase":"candidate-check","diagnostic":error}),
            ));
        }
    };
    match test_corpus(&corpus, &candidate, scope) {
        Ok(report) => Ok((report.passed, serde_json::to_value(report)?)),
        Err(error) => Ok((
            false,
            json!({"ok":false,"phase":"regression","diagnostic":error}),
        )),
    }
}
