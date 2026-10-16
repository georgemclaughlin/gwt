use gwt_core::format_source;
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::Path,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    file: String,
    text: String,
}

fn report(source: &str, file: &str) -> Value {
    let digest = format!("sha256:{:x}", Sha256::digest(source.as_bytes()));
    match format_source(source, file) {
        Ok(formatted) => {
            json!({"kind":"gwt.native-format","schemaVersion":1,"ok":true,"sourceDigest":digest,"changed":formatted.changed,"text":formatted.text,"diagnostic":null})
        }
        Err(diagnostic) => {
            json!({"kind":"gwt.native-format","schemaVersion":1,"ok":false,"sourceDigest":digest,"changed":false,"text":null,"diagnostic":diagnostic})
        }
    }
}

pub(crate) fn editor() -> Result<(bool, Value), Box<dyn std::error::Error>> {
    let mut bytes = Vec::new();
    std::io::stdin()
        .take(8 * 1_048_576 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 8 * 1_048_576 {
        return Err("formatter request exceeds eight MiB".into());
    }
    let request: Snapshot = serde_json::from_slice(&bytes)?;
    if request.file.len() > 4096 {
        return Err("formatter filename exceeds 4096 bytes".into());
    }
    let result = report(&request.text, &request.file);
    Ok((result["ok"] == true, result))
}

pub(crate) fn file(args: &[String]) -> Result<(bool, Value), Box<dyn std::error::Error>> {
    if !(args.len() == 1 || (args.len() == 2 && matches!(args[1].as_str(), "--check" | "--write")))
    {
        return Err("usage: gwt-native format FILE.gwt [--check | --write]".into());
    }
    let path = Path::new(&args[0]);
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() {
        return Err("format requires a regular file; symlinks are not followed".into());
    }
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take(1_048_577)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 1_048_576 {
        return Err("format source exceeds one MiB".into());
    }
    let source = String::from_utf8(bytes)?;
    let mut result = report(&source, &args[0]);
    let mode = args.get(1).map(String::as_str).unwrap_or("preview");
    result["mode"] = json!(mode.trim_start_matches("--"));
    if result["ok"] == false {
        return Ok((false, result));
    }
    if mode == "--check" && result["changed"] == true {
        result["ok"] = json!(false);
        return Ok((false, result));
    }
    if mode == "--write" && result["changed"] == true {
        if metadata.permissions().readonly() {
            return Err("format refuses to replace a read-only file".into());
        }
        write(path, &source, result["text"].as_str().unwrap(), &metadata)?;
    }
    Ok((true, result))
}

fn write(
    path: &Path,
    original: &str,
    formatted: &str,
    metadata: &fs::Metadata,
) -> Result<(), Box<dyn std::error::Error>> {
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let mut temporary = None;
    for attempt in 0..32 {
        let candidate = parent.join(format!(".gwt-format-{}-{attempt}.tmp", std::process::id()));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&candidate)
        {
            Ok(file) => {
                temporary = Some((candidate, file));
                break;
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => (),
            Err(error) => return Err(error.into()),
        }
    }
    let (temporary, mut file) = temporary.ok_or("cannot create formatter temporary file")?;
    let outcome = (|| -> Result<(), Box<dyn std::error::Error>> {
        file.write_all(formatted.as_bytes())?;
        file.set_permissions(metadata.permissions())?;
        file.sync_all()?;
        drop(file);
        let regular = fs::symlink_metadata(path)?.is_file();
        let mut current = Vec::new();
        if regular {
            fs::File::open(path)?
                .take(original.len() as u64 + 1)
                .read_to_end(&mut current)?;
        }
        if !regular || current != original.as_bytes() {
            return Err("source changed during formatting; retry on the current file".into());
        }
        fs::rename(&temporary, path)?;
        Ok(())
    })();
    if outcome.is_err() {
        let _ = fs::remove_file(temporary);
    }
    outcome
}
