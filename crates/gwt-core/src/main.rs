use gwt_core::{
    Corpus, CorpusEntry, ExecutionCase, Limits, MAX_CASE_BYTES, MAX_CORPUS_BYTES,
    MAX_DECISIONS_BYTES, ReviewDecisions, Type, assess_decisions, capture_request,
    capture_scenario, compare_case, compile_expression, compile_file, render_review_html,
    replay_case, review_corpus, scenario_from_case,
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs, io::Read, path::Path, process::ExitCode};
mod corpus_migration_cli;
mod editor_cli;
mod formatter_cli;
mod limits_cli;
mod migration_cli;
mod outline_cli;
mod regression_cli;
mod validation_cli;

fn read_bounded(path: &str, maximum: usize) -> Result<String, Box<dyn std::error::Error>> {
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take(maximum as u64 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > maximum {
        return Err(format!("{path}: file exceeds {maximum} bytes").into());
    }
    Ok(String::from_utf8(bytes)?)
}

fn main() -> ExitCode {
    match run() {
        Ok((ok, payload)) => {
            println!("{payload}");
            if ok {
                ExitCode::SUCCESS
            } else {
                ExitCode::FAILURE
            }
        }
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}

fn profile_payload(
    report: gwt_core::source::Result<gwt_core::ExecutionProfile>,
) -> Result<(bool, Value), Box<dyn std::error::Error>> {
    match report.and_then(|report| report.to_json().map(|payload| (report.ok, payload))) {
        Ok(result) => Ok(result),
        Err(error) => Ok((
            false,
            json!({"ok":false,"phase":"profile","diagnostic":error}),
        )),
    }
}

fn run() -> Result<(bool, Value), Box<dyn std::error::Error>> {
    let mut args: Vec<_> = std::env::args().skip(1).collect();
    if args
        .first()
        .is_some_and(|command| matches!(command.as_str(), "version" | "--version" | "-V"))
    {
        if args.len() != 1 && !(args.len() == 2 && args[0] == "version" && args[1] == "--json") {
            return Err("usage: gwt version [--json] | --version | -V".into());
        }
        return Ok((true, serde_json::to_value(gwt_core::version_info())?));
    }
    if args.first().is_some_and(|command| command == "test-cases") {
        return regression_cli::run(&args[1..]);
    }
    if args
        .first()
        .is_some_and(|command| command == "complete-editor")
    {
        if args.len() != 1 {
            return Err("usage: gwt complete-editor < snapshot.json".into());
        }
        return editor_cli::complete();
    }
    if args
        .first()
        .is_some_and(|command| command == "outline-editor")
    {
        if args.len() != 1 {
            return Err("usage: gwt outline-editor < snapshot.json".into());
        }
        return outline_cli::run();
    }
    if args.first().is_some_and(|command| command == "validate") {
        return validation_cli::run(&args[1..]);
    }
    if args
        .first()
        .is_some_and(|command| command == "format-editor")
    {
        if args.len() != 1 {
            return Err("usage: gwt format-editor < snapshot.json".into());
        }
        return formatter_cli::editor();
    }
    if args.first().is_some_and(|command| command == "format") {
        return formatter_cli::file(&args[1..]);
    }
    if args
        .first()
        .is_some_and(|command| command == "check-editor")
    {
        if args.len() != 1 {
            return Err("usage: gwt check-editor < snapshot.json".into());
        }
        return editor_cli::run();
    }
    if args.first().is_some_and(|command| {
        matches!(
            command.as_str(),
            "migrate-corpus" | "assess-corpus-migration" | "export-corpus-migration"
        )
    }) {
        return corpus_migration_cli::run(&args);
    }
    if args.first().is_some_and(|command| {
        matches!(
            command.as_str(),
            "migrate" | "assess-migration" | "export-migration"
        )
    }) {
        return migration_cli::run(&args);
    }
    if args.len() == 1 && matches!(args[0].as_str(), "--help" | "-h") {
        return Ok((
            true,
            json!({"usage": ["gwt version [--json] | --version | -V", "gwt run|capture|profile ENTRY.gwt [--import-root DIRECTORY] [--limits FILE.json] (exactly one entry scenario)", "gwt validate FILE.gwt [--import-root DIRECTORY] [--limits FILE.json] [--allow-no-scenarios] [--html NEW_REPORT.html]", "gwt format FILE.gwt [--check | --write]", "gwt format-editor < snapshot.json", "gwt outline-editor < snapshot.json", "gwt check-editor < snapshot.json", "gwt complete-editor < snapshot.json","gwt expression EXPRESSION TYPES.json INPUT.json", "gwt check FILE.gwt [--import-root DIRECTORY]", "gwt inspect FILE.gwt [--import-root DIRECTORY]", "gwt test FILE.gwt [--import-root DIRECTORY] [--limits FILE.json]", "gwt profile FILE.gwt [--request NAME --input INPUT.json | --scenario NAME] [--import-root DIRECTORY] [--limits FILE.json]", "gwt run FILE.gwt --request NAME --input INPUT.json [--import-root DIRECTORY] [--limits FILE.json]", "gwt capture FILE.gwt --request NAME --input INPUT.json [--import-root DIRECTORY] [--limits FILE.json]", "gwt run FILE.gwt --scenario NAME [--import-root DIRECTORY] [--limits FILE.json]", "gwt capture FILE.gwt --scenario NAME [--import-root DIRECTORY] [--limits FILE.json]", "gwt replay CASE.json", "gwt migrate CASE.json --previous-engine EXECUTABLE [--timeout-ms MILLISECONDS] [--html NEW_REVIEW.html] [--decision-template NEW_FILE.json]", "gwt assess-migration CASE.json --previous-engine EXECUTABLE --decision DECISION.json [--timeout-ms MILLISECONDS]", "gwt export-migration CASE.json --previous-engine EXECUTABLE --decision DECISION.json --output NEW_CASE.json [--timeout-ms MILLISECONDS]", "gwt scenario-from-case CASE.json [--name NAME] [--output NEW_DIRECTORY]", "gwt compare CASE.json --candidate FILE.gwt [--import-root DIRECTORY]", "gwt corpus CASE.json ...", "gwt test-cases CORPUS.json --candidate FILE.gwt --match outcomes-and-state|execution [--import-root DIRECTORY]", "gwt migrate-corpus CORPUS.json --engines ENGINES.json [--timeout-ms MILLISECONDS] [--html NEW_REVIEW.html] [--decisions-template NEW_FILE.json]", "gwt assess-corpus-migration CORPUS.json --engines ENGINES.json --decisions DECISIONS.json [--timeout-ms MILLISECONDS]", "gwt export-corpus-migration CORPUS.json --engines ENGINES.json --decisions DECISIONS.json --output NEW_CORPUS.json [--timeout-ms MILLISECONDS]", "gwt review CORPUS.json --candidate FILE.gwt [--html REVIEW.html] [--decisions-template NEW_FILE.json] [--import-root DIRECTORY]", "gwt assess-review CORPUS.json --candidate FILE.gwt --decisions DECISIONS.json [--import-root DIRECTORY]"], "status": "experimental native language subset; see docs/native-semantics.md"}),
        ));
    }
    if args
        .first()
        .is_some_and(|command| command == "scenario-from-case")
    {
        if args.len() < 2 || args.len() % 2 != 0 {
            return Err(
                "usage: gwt scenario-from-case CASE.json [--name NAME] [--output NEW_DIRECTORY]"
                    .into(),
            );
        }
        let mut options = BTreeMap::new();
        for pair in args[2..].chunks_exact(2) {
            if !matches!(pair[0].as_str(), "--name" | "--output")
                || options.insert(pair[0].as_str(), pair[1].as_str()).is_some()
            {
                return Err("unknown or duplicate scenario option".into());
            }
        }
        let case = match ExecutionCase::from_json(&read_bounded(&args[1], MAX_CASE_BYTES)?) {
            Ok(case) => case,
            Err(error) => {
                return Ok((
                    false,
                    json!({"ok":false,"phase":"load-case","diagnostic":error}),
                ));
            }
        };
        let generated = match scenario_from_case(
            &case,
            options
                .get("--name")
                .copied()
                .unwrap_or("recorded request outcome"),
        ) {
            Ok(generated) => generated,
            Err(error) => {
                return Ok((
                    false,
                    json!({"ok":false,"phase":"scenario-generation","diagnostic":error}),
                ));
            }
        };
        if let Some(destination) = options.get("--output") {
            write_generated_bundle(Path::new(destination), generated.source_bundle())?;
        }
        return Ok((true, serde_json::to_value(generated)?));
    }
    if args.first().is_some_and(|command| command == "corpus") {
        if args.len() < 2 || args.len() > 257 {
            return Err("usage: gwt corpus CASE.json ... (1 to 256 files)".into());
        }
        let mut entries = Vec::new();
        let mut bytes = 0;
        for path in &args[1..] {
            let source = read_bounded(path, MAX_CASE_BYTES.min(MAX_CORPUS_BYTES - bytes))?;
            bytes += source.len();
            let name = Path::new(path)
                .file_stem()
                .and_then(|name| name.to_str())
                .ok_or("case filename must be UTF-8")?;
            entries.push(CorpusEntry {
                id: name.into(),
                label: name.into(),
                case: serde_json::from_str(&source).unwrap_or(Value::String(source)),
            });
        }
        return match Corpus::new(entries) {
            Ok(corpus) => Ok((true, serde_json::to_value(corpus)?)),
            Err(error) => Ok((
                false,
                json!({"ok":false,"phase":"corpus","diagnostic":error}),
            )),
        };
    }
    if args
        .first()
        .is_some_and(|command| matches!(command.as_str(), "review" | "assess-review"))
    {
        if args.len() < 4 || args.len() % 2 != 0 {
            return Err("usage: gwt review CORPUS.json --candidate FILE.gwt [--html REVIEW.html] [--import-root DIRECTORY]".into());
        }
        let mut options = BTreeMap::new();
        for pair in args[2..].chunks_exact(2) {
            if !matches!(
                pair[0].as_str(),
                "--candidate" | "--html" | "--import-root" | "--decisions" | "--decisions-template"
            ) || options.insert(pair[0].as_str(), pair[1].as_str()).is_some()
            {
                return Err("unknown or duplicate review option".into());
            }
        }
        if (args[0] == "review" && options.contains_key("--decisions"))
            || (args[0] == "assess-review"
                && (!options.contains_key("--decisions")
                    || options.contains_key("--html")
                    || options.contains_key("--decisions-template")))
        {
            return Err("assess-review requires --decisions; --html and --decisions-template belong to review".into());
        }
        let candidate_path = options
            .get("--candidate")
            .ok_or("review requires --candidate FILE.gwt")?;
        let corpus = match Corpus::from_json(&read_bounded(&args[1], MAX_CORPUS_BYTES)?) {
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
        let report = match review_corpus(&corpus, &candidate) {
            Ok(report) => report,
            Err(error) => {
                return Ok((
                    false,
                    json!({"ok":false,"phase":"review","diagnostic":error}),
                ));
            }
        };
        if args[0] == "assess-review" {
            let decisions = match ReviewDecisions::from_json(&read_bounded(
                options["--decisions"],
                MAX_DECISIONS_BYTES,
            )?) {
                Ok(decisions) => decisions,
                Err(error) => {
                    return Ok((
                        false,
                        json!({"ok":false,"phase":"decisions","diagnostic":error}),
                    ));
                }
            };
            return match assess_decisions(&report, &decisions) {
                Ok(assessment) => Ok((assessment.all_accepted, serde_json::to_value(assessment)?)),
                Err(error) => Ok((
                    false,
                    json!({"ok":false,"phase":"decisions","diagnostic":error}),
                )),
            };
        }
        if let Some(path) = options.get("--decisions-template") {
            let template = ReviewDecisions::pending(&report)?;
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path)?;
            std::io::Write::write_all(&mut file, template.to_json().as_bytes())?;
        }
        if let Some(path) = options.get("--html") {
            let html = match render_review_html(&report) {
                Ok(html) => html,
                Err(error) => {
                    return Ok((
                        false,
                        json!({"ok":false,"phase":"render","diagnostic":error}),
                    ));
                }
            };
            fs::write(path, html)?;
        }
        return Ok((report.complete, serde_json::to_value(report)?));
    }
    if args
        .first()
        .is_some_and(|command| matches!(command.as_str(), "replay" | "compare"))
    {
        let root = if args.len() >= 4 && args[args.len() - 2] == "--import-root" {
            let root = args.pop().unwrap();
            args.pop();
            Some(root)
        } else {
            None
        };
        if (args[0] == "replay" && (args.len() != 2 || root.is_some()))
            || (args[0] == "compare" && (args.len() != 4 || args[2] != "--candidate"))
        {
            return Err("usage: gwt replay CASE.json; or gwt compare CASE.json --candidate FILE.gwt [--import-root DIRECTORY]".into());
        }
        let case = match ExecutionCase::from_json(&read_bounded(&args[1], MAX_CASE_BYTES)?) {
            Ok(case) => case,
            Err(error) => {
                return Ok((
                    false,
                    json!({"ok":false,"phase":"load-case","diagnostic":error}),
                ));
            }
        };
        if args[0] == "replay" {
            return match replay_case(&case) {
                Ok(report) => Ok((report.verified, serde_json::to_value(report)?)),
                Err(error) => Ok((
                    false,
                    json!({"ok":false,"phase":"replay","diagnostic":error}),
                )),
            };
        }
        let candidate = match compile_file(Path::new(&args[3]), root.as_deref().map(Path::new)) {
            Ok(program) => program,
            Err(error) => {
                return Ok((
                    false,
                    json!({"ok":false,"phase":"candidate-check","diagnostic":error}),
                ));
            }
        };
        return match compare_case(&case, &candidate) {
            Ok(report) => Ok((report.baseline.verified, serde_json::to_value(report)?)),
            Err(error) => Ok((
                false,
                json!({"ok":false,"phase":"compare","diagnostic":error}),
            )),
        };
    }
    if args.first().is_some_and(|command| {
        matches!(
            command.as_str(),
            "check" | "inspect" | "test" | "run" | "capture" | "profile"
        )
    }) {
        let mut import_root = None;
        let mut limits_path = None;
        while args.len() >= 4 {
            let destination = match args[args.len() - 2].as_str() {
                "--import-root" => &mut import_root,
                "--limits" => &mut limits_path,
                _ => break,
            };
            if destination.is_some() || args.last().unwrap().starts_with("--") {
                return Err("duplicate option or missing --import-root/--limits value".into());
            }
            *destination = args.pop();
            args.pop();
        }
        let selected_run = matches!(args[0].as_str(), "run" | "capture" | "profile");
        let request_form = args.len() == 6 && args[2] == "--request" && args[4] == "--input";
        let scenario_form = args.len() == 4 && args[2] == "--scenario";
        let entry_form = selected_run && args.len() == 2;
        if args.len() < 2
            || (selected_run && !request_form && !scenario_form && !entry_form)
            || (!selected_run && args.len() != 2)
            || (limits_path.is_some() && matches!(args[0].as_str(), "check" | "inspect"))
        {
            return Err("usage: gwt inspect|check FILE.gwt [--import-root DIRECTORY]; test FILE.gwt [--import-root DIRECTORY] [--limits FILE.json]; or run|capture|profile FILE.gwt [--request NAME --input INPUT.json | --scenario NAME] [--import-root DIRECTORY] [--limits FILE.json]; omitting a target requires exactly one entry scenario".into());
        }
        let limits = limits_path
            .as_deref()
            .map(limits_cli::read)
            .transpose()?
            .unwrap_or_default();
        let program = match compile_file(Path::new(&args[1]), import_root.as_deref().map(Path::new))
        {
            Ok(program) => program,
            Err(error) => {
                return Ok((
                    false,
                    json!({"ok":false,"phase":"check","diagnostic":error}),
                ));
            }
        };
        return match args[0].as_str() {
            "inspect" => match program.inspect().to_json() {
                Ok(report) => Ok((true, report)),
                Err(error) => Ok((
                    false,
                    json!({"ok":false,"phase":"inspect","diagnostic":error}),
                )),
            },
            "check" => Ok((
                true,
                json!({"ok":true,"requests":program.request_names(),"scenarios":program.scenario_names(),"programIdentity":program.identity()}),
            )),
            "test" => {
                let scenarios = program.test_scenarios(limits);
                let ok =
                    !scenarios.is_empty() && scenarios.iter().all(|scenario| scenario.execution.ok);
                Ok((
                    ok,
                    json!({"ok":ok,"scenarioCount":scenarios.len(),"scenarios":scenarios,"programIdentity":program.identity(),"limits":limits}),
                ))
            }
            _ if scenario_form || entry_form => {
                let name = if scenario_form {
                    args[3].as_str()
                } else {
                    match program.single_scenario() {
                        Ok(name) => name,
                        Err(error) => {
                            return Ok((
                                false,
                                json!({"ok":false,"phase":"selection","diagnostic":error,"scenarios":program.scenario_names(),"requests":program.request_names()}),
                            ));
                        }
                    }
                };
                if args[0] == "capture" {
                    return match capture_scenario(&program, name, limits) {
                        Ok(case) => Ok((true, serde_json::to_value(case)?)),
                        Err(error) => Ok((
                            false,
                            json!({"ok":false,"phase":"capture","diagnostic":error}),
                        )),
                    };
                }
                if args[0] == "profile" {
                    return profile_payload(program.profile_scenario(name, limits));
                }
                let run = program.run_scenario(name, limits);
                Ok((run.ok, serde_json::to_value(run)?))
            }
            _ => {
                let input: Value = serde_json::from_str(&read_bounded(&args[5], 1_048_576)?)?;
                if args[0] == "capture" {
                    return match capture_request(&program, &args[3], &input, limits) {
                        Ok(case) => Ok((true, serde_json::to_value(case)?)),
                        Err(error) => Ok((
                            false,
                            json!({"ok":false,"phase":"capture","diagnostic":error}),
                        )),
                    };
                }
                if args[0] == "profile" {
                    return profile_payload(program.profile_request(&args[3], &input, limits));
                }
                let result = program.run_request(&args[3], &input, limits);
                Ok((result.ok, serde_json::to_value(result)?))
            }
        };
    }
    if args.len() != 4 || args[0] != "expression" {
        return Err("use gwt --help for supported commands".into());
    }
    let types: BTreeMap<String, Type> = serde_json::from_str(&fs::read_to_string(&args[2])?)?;
    let inputs: Value = serde_json::from_str(&fs::read_to_string(&args[3])?)?;
    let compiled = match compile_expression(&args[1], "<expression>", types) {
        Ok(value) => value,
        Err(error) => {
            return Ok((
                false,
                json!({"ok":false,"phase":"check","diagnostic":error}),
            ));
        }
    };
    match compiled.evaluate(&inputs, Limits::default()) {
        Ok(result) => Ok((result.ok, serde_json::to_value(result)?)),
        Err(error) => Ok((
            false,
            json!({"ok":false,"phase":"input","diagnostic":error}),
        )),
    }
}

// A new destination prevents overwriting source or user-maintained expectations.
// Validate the complete artifact before creating any files.
fn write_generated_bundle(
    destination: &Path,
    source: &gwt_core::SourceBundle,
) -> Result<(), Box<dyn std::error::Error>> {
    for path in source.modules.keys() {
        if source
            .modules
            .keys()
            .any(|other| other.starts_with(&(path.clone() + "/")))
        {
            return Err("source bundle has conflicting file/directory paths".into());
        }
    }
    fs::create_dir(destination).map_err(|error| {
        format!(
            "cannot create new scenario directory {}: {error}",
            destination.display()
        )
    })?;
    let result = (|| -> Result<(), Box<dyn std::error::Error>> {
        for (path, content) in &source.modules {
            let path = destination.join(path);
            fs::create_dir_all(path.parent().expect("module parent"))?;
            // No existing files, including unexpected symlinks, are replaced.
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path)?;
            std::io::Write::write_all(&mut file, content.as_bytes())?;
        }
        Ok(())
    })();
    result.map_err(|error| {
        format!(
            "scenario export failed; partial files remain in {}: {error}",
            destination.display()
        )
        .into()
    })
}
