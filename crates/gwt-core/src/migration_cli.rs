//! Run only the explicitly selected, trusted previous engine on a frozen case copy.
use gwt_core::{ExecutionCase, MAX_BASELINE_REPLAY_BYTES};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    sync::{
        atomic::{AtomicU64, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

static SEQUENCE: AtomicU64 = AtomicU64::new(0);
const MAX_EXECUTABLE_BYTES: usize = 256 * 1_048_576;

pub(crate) fn run(
    args: &[String],
) -> Result<(bool, serde_json::Value), Box<dyn std::error::Error>> {
    use gwt_core::{
        MAX_CASE_BYTES, MAX_MIGRATION_DECISION_BYTES, MigrationDecision, assess_migration,
        prepare_migration, render_migration_html,
    };
    use serde_json::json;
    let command = args[0].as_str();
    if args.len() < 4 || args.len() % 2 != 0 {
        return Err("migration requires CASE.json and paired options; see --help".into());
    }
    let options = super::cli_options::paired(
        &args[2..],
        |option| {
            matches!(option, "--previous-engine" | "--timeout-ms")
                || match command {
                    "migrate" => matches!(option, "--html" | "--decision-template"),
                    "assess-migration" => option == "--decision",
                    "export-migration" => matches!(option, "--decision" | "--output"),
                    _ => false,
                }
        },
        "unknown or duplicate migration option",
    )?;
    let executable = options
        .get("--previous-engine")
        .ok_or("requires --previous-engine")?;
    if command != "migrate" && !options.contains_key("--decision") {
        return Err("migration assessment/export requires --decision".into());
    }
    if command == "export-migration" && !options.contains_key("--output") {
        return Err("migration export requires --output NEW_CASE.json".into());
    }
    let timeout = options
        .get("--timeout-ms")
        .map_or(Ok(30_000_u64), |value| value.parse())?;
    if !(1..=60_000).contains(&timeout) {
        return Err("migration timeout must be 1 to 60000 milliseconds".into());
    }
    let case = match ExecutionCase::from_json(&super::read_bounded(&args[1], MAX_CASE_BYTES)?) {
        Ok(case) => case,
        Err(error) => {
            return Ok((
                false,
                json!({"ok":false,"phase":"load-case","diagnostic":error}),
            ));
        }
    };
    let (response, digest) = match replay_previous_engine(
        Path::new(executable),
        &case,
        Duration::from_millis(timeout),
    ) {
        Ok(result) => result,
        Err(message) => {
            return Ok((
                false,
                json!({"ok":false,"phase":"previous-engine-replay","message":message}),
            ));
        }
    };
    let proposal = match prepare_migration(&case, &response, &digest) {
        Ok(proposal) => proposal,
        Err(error) => {
            return Ok((
                false,
                json!({"ok":false,"phase":"migration","diagnostic":error}),
            ));
        }
    };
    if command == "migrate" {
        // Render before writing any optional artifacts so presentation errors leave no template.
        let html = options
            .get("--html")
            .map(|_| render_migration_html(&proposal))
            .transpose()?;
        if let Some(path) = options.get("--html") {
            write_new(path, html.as_ref().expect("requested HTML"))?;
        }
        if let Some(path) = options.get("--decision-template") {
            write_new(path, &MigrationDecision::pending(&proposal).to_json())?;
        }
        return Ok((
            proposal.candidate().is_some(),
            serde_json::to_value(proposal)?,
        ));
    }
    let decision = match MigrationDecision::from_json(&super::read_bounded(
        options["--decision"],
        MAX_MIGRATION_DECISION_BYTES,
    )?) {
        Ok(decision) => decision,
        Err(error) => {
            return Ok((
                false,
                json!({"ok":false,"phase":"load-decision","diagnostic":error}),
            ));
        }
    };
    let assessment = match assess_migration(&proposal, &decision) {
        Ok(assessment) => assessment,
        Err(error) => {
            return Ok((
                false,
                json!({"ok":false,"phase":"assess-migration","diagnostic":error}),
            ));
        }
    };
    if command == "assess-migration" {
        return Ok((true, serde_json::to_value(assessment)?));
    }
    if !assessment.accepted {
        return Ok((
            false,
            json!({"ok":false,"phase":"export-migration","message":"export requires acceptance of this exact proposal","assessment":assessment}),
        ));
    }
    let candidate = proposal.candidate().expect("accepted candidate");
    write_new(options["--output"], &candidate.to_json())?;
    Ok((
        true,
        json!({"kind":"gwt.native-migration-export","schemaVersion":1,"output":options["--output"],"caseIntegrity":candidate.integrity(),"assessment":assessment}),
    ))
}

pub(crate) fn write_new(path: &str, text: &str) -> std::io::Result<()> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(text.as_bytes())?;
    file.sync_all()
}

struct Scratch(PathBuf);
impl Scratch {
    fn create() -> Result<Self, String> {
        for _ in 0..128 {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|error| error.to_string())?
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "gwt-engine-migration-{}-{nonce}-{}",
                std::process::id(),
                SEQUENCE.fetch_add(1, Ordering::Relaxed)
            ));
            let mut builder = fs::DirBuilder::new();
            #[cfg(unix)]
            {
                use std::os::unix::fs::DirBuilderExt;
                builder.mode(0o700);
            }
            match builder.create(&path) {
                Ok(()) => return Ok(Self(path)),
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error.to_string()),
            }
        }
        Err("could not create a private migration directory".into())
    }
}
impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

pub(crate) fn replay_previous_engine(
    path: &Path,
    case: &ExecutionCase,
    timeout: Duration,
) -> Result<(String, String), String> {
    if !fs::metadata(path)
        .map_err(|error| error.to_string())?
        .is_file()
    {
        return Err("previous engine must be an executable file".into());
    }
    let scratch = Scratch::create()?;
    let executable = scratch.0.join(if cfg!(windows) {
        "previous-engine.exe"
    } else {
        "previous-engine"
    });
    let mut input = fs::File::open(path)
        .map_err(|error| error.to_string())?
        .take(MAX_EXECUTABLE_BYTES as u64 + 1);
    let mut output = fs::File::create_new(&executable).map_err(|error| error.to_string())?;
    let mut total = 0;
    let mut hash = Sha256::new();
    let mut buffer = [0_u8; 65536];
    loop {
        let count = input.read(&mut buffer).map_err(|error| error.to_string())?;
        if count == 0 {
            break;
        }
        total += count;
        if total > MAX_EXECUTABLE_BYTES {
            return Err("previous executable exceeds 256 MiB".into());
        }
        output
            .write_all(&buffer[..count])
            .map_err(|error| error.to_string())?;
        hash.update(&buffer[..count]);
    }
    drop(output);
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o500))
            .map_err(|error| error.to_string())?;
    }
    let digest = format!("sha256:{:x}", hash.finalize());
    let case_path = scratch.0.join("original.case.json");
    fs::File::create_new(&case_path)
        .and_then(|mut file| file.write_all(case.to_json().as_bytes()))
        .map_err(|error| error.to_string())?;
    let mut child = Command::new(&executable)
        .arg("replay")
        .arg(&case_path)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("could not execute previous engine: {error}"))?;
    let (sender, receiver) = mpsc::channel();
    let stdout = child.stdout.take().expect("piped stdout");
    let stderr = child.stderr.take().expect("piped stderr");
    for (index, mut stream, limit) in [
        (
            0,
            Box::new(stdout) as Box<dyn Read + Send>,
            MAX_BASELINE_REPLAY_BYTES,
        ),
        (1, Box::new(stderr) as Box<dyn Read + Send>, 65536),
    ] {
        let sender = sender.clone();
        thread::spawn(move || {
            let mut bytes = Vec::new();
            let result = stream
                .by_ref()
                .take(limit as u64 + 1)
                .read_to_end(&mut bytes)
                .map_err(|error| error.to_string())
                .and_then(|_| {
                    if bytes.len() > limit {
                        Err("previous engine output exceeded its byte limit".into())
                    } else {
                        String::from_utf8(bytes).map_err(|error| error.to_string())
                    }
                });
            let _ = sender.send((index, result));
        });
    }
    drop(sender);
    let started = Instant::now();
    let mut streams = [None, None];
    let result = (|| {
        loop {
            while let Ok((index, result)) = receiver.try_recv() {
                streams[index] = Some(result?);
            }
            if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
                if streams.iter().all(Option::is_some) {
                    let response = streams[0].take().unwrap();
                    if !status.success() {
                        // Keep rejection details bounded even if a mismatched replay is large.
                        let details = if streams[1].as_ref().unwrap().is_empty() {
                            &response
                        } else {
                            streams[1].as_ref().unwrap()
                        };
                        return Err(format!(
                            "previous engine replay exited {status}: {}",
                            details.chars().take(4096).collect::<String>()
                        ));
                    }
                    return Ok((response, digest));
                }
            }
            if started.elapsed() >= timeout {
                return Err("previous engine replay timed out".into());
            }
            thread::sleep(Duration::from_millis(10));
        }
    })();
    if result.is_err() {
        let _ = child.kill();
        let _ = child.wait();
    }
    result
}
