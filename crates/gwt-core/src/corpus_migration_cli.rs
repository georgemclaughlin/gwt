//! Explicit operator-provided engine map; no executable paths are read from cases.
use gwt_core::{
    Corpus, CorpusMigrationDecisions, MAX_CORPUS_BYTES, MAX_DECISIONS_BYTES,
    assess_corpus_migration, corpus_integrity, prepare_corpus_migration, promote_corpus_migration,
    render_corpus_migration_html,
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    time::Duration,
};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct EngineFile {
    kind: String,
    schema_version: u32,
    engines: Vec<Engine>,
}
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Engine {
    source_digest: String,
    executable: String,
}

fn diagnostic(code: &str, message: impl Into<String>) -> gwt_core::source::Diagnostic {
    gwt_core::source::Diagnostic::new(
        code,
        message,
        &gwt_core::source::Span {
            file: "<corpus-migration>".into(),
            start: 0,
            end: 0,
            line: 1,
            column: 1,
        },
    )
}
fn engines(path: &str) -> Result<BTreeMap<String, PathBuf>, Box<dyn std::error::Error>> {
    let file: EngineFile = serde_json::from_str(&super::read_bounded(path, 65_536)?)?;
    if file.kind != "gwt.native-migration-engines"
        || file.schema_version != 1
        || file.engines.len() > 256
    {
        return Err("expected migration-engines schema 1 with at most 256 engine mappings".into());
    }
    let mut mappings = BTreeMap::new();
    for engine in file.engines {
        let digest = &engine.source_digest;
        if digest.len() != 71
            || !digest.starts_with("sha256:")
            || !digest[7..]
                .bytes()
                .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
            || engine.executable.is_empty()
            || engine.executable.len() > 4096
            || engine.executable.chars().any(char::is_control)
        {
            return Err(
                "engine mappings require a SHA-256 source digest and an explicit executable path"
                    .into(),
            );
        }
        let executable = Path::new(path)
            .parent()
            .unwrap_or(Path::new("."))
            .join(engine.executable);
        if mappings.insert(engine.source_digest, executable).is_some() {
            return Err("duplicate engine source digest".into());
        }
    }
    Ok(mappings)
}
pub(crate) fn run(args: &[String]) -> Result<(bool, Value), Box<dyn std::error::Error>> {
    let command = args[0].as_str();
    if args.len() < 4 || args.len() % 2 != 0 {
        return Err("corpus migration requires CORPUS.json and paired options; see --help".into());
    }
    let mut options = BTreeMap::new();
    for pair in args[2..].chunks_exact(2) {
        let allowed = matches!(pair[0].as_str(), "--engines" | "--timeout-ms")
            || match command {
                "migrate-corpus" => matches!(pair[0].as_str(), "--html" | "--decisions-template"),
                "assess-corpus-migration" => pair[0] == "--decisions",
                "export-corpus-migration" => matches!(pair[0].as_str(), "--decisions" | "--output"),
                _ => false,
            };
        if !allowed || options.insert(pair[0].as_str(), pair[1].as_str()).is_some() {
            return Err("unknown or duplicate corpus migration option".into());
        }
    }
    let mappings = engines(
        options
            .get("--engines")
            .ok_or("requires --engines ENGINES.json")?,
    )?;
    if command != "migrate-corpus" && !options.contains_key("--decisions") {
        return Err("assessment/export requires --decisions".into());
    }
    if command == "export-corpus-migration" && !options.contains_key("--output") {
        return Err("export requires --output NEW_CORPUS.json".into());
    }
    let timeout = options
        .get("--timeout-ms")
        .map_or(Ok(30_000_u64), |value| value.parse())?;
    if !(1..=60_000).contains(&timeout) {
        return Err("per-case migration timeout must be 1 to 60000 milliseconds".into());
    }
    let corpus = Corpus::from_json(&super::read_bounded(&args[1], MAX_CORPUS_BYTES)?)?;
    let report = prepare_corpus_migration(&corpus, |case| {
        let executable = mappings.get(&case.engine().source_digest).ok_or_else(|| {
            diagnostic(
                "migration_engine_missing",
                format!(
                    "no explicitly selected executable for {}",
                    case.engine().source_digest
                ),
            )
        })?;
        super::migration_cli::replay_previous_engine(
            executable,
            case,
            Duration::from_millis(timeout),
        )
        .map_err(|message| {
            diagnostic(
                "migration_previous_replay",
                message.chars().take(4096).collect::<String>(),
            )
        })
    })?;
    if command == "migrate-corpus" {
        let html = options
            .get("--html")
            .map(|_| render_corpus_migration_html(&report))
            .transpose()?;
        if let Some(path) = options.get("--html") {
            super::migration_cli::write_new(path, html.as_ref().unwrap())?;
        }
        if let Some(path) = options.get("--decisions-template") {
            super::migration_cli::write_new(
                path,
                &CorpusMigrationDecisions::pending(&report).to_json(),
            )?;
        }
        return Ok((report.complete(), serde_json::to_value(report)?));
    }
    let decisions = CorpusMigrationDecisions::from_json(&super::read_bounded(
        options["--decisions"],
        MAX_DECISIONS_BYTES,
    )?)?;
    let assessment = match assess_corpus_migration(&report, &decisions) {
        Ok(assessment) => assessment,
        Err(error) => {
            return Ok((
                false,
                json!({"ok":false,"phase":"assess-corpus-migration","diagnostic":error}),
            ));
        }
    };
    if command == "assess-corpus-migration" {
        return Ok((true, serde_json::to_value(assessment)?));
    }
    if !assessment.all_accepted {
        return Ok((
            false,
            json!({"ok":false,"phase":"export-corpus-migration","message":"every corpus entry requires acceptance before export","assessment":assessment}),
        ));
    }
    let (promoted, assessment) = promote_corpus_migration(&report, &decisions)?;
    super::migration_cli::write_new(options["--output"], &promoted.to_json())?;
    Ok((
        true,
        json!({"kind":"gwt.native-corpus-migration-export","schemaVersion":1,"output":options["--output"],"corpusIntegrity":corpus_integrity(&promoted),"assessment":assessment}),
    ))
}
