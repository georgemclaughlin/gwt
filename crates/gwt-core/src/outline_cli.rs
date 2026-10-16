use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::io::Read;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    file: String,
    text: String,
}

pub(crate) fn run() -> Result<(bool, Value), Box<dyn std::error::Error>> {
    let mut bytes = Vec::new();
    std::io::stdin()
        .take(8 * 1_048_576 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 8 * 1_048_576 {
        return Err("outline request exceeds eight MiB".into());
    }
    let request: Snapshot = serde_json::from_slice(&bytes)?;
    if request.file.len() > 4096 {
        return Err("outline filename exceeds 4096 bytes".into());
    }
    let digest = format!("sha256:{:x}", Sha256::digest(request.text.as_bytes()));
    let (ok, symbols, diagnostic) = match gwt_core::outline_source(&request.text, &request.file) {
        Ok(symbols) => (true, symbols, None),
        Err(error) => (false, Vec::new(), Some(error)),
    };
    Ok((
        ok,
        json!({"kind":"gwt.native-outline", "schemaVersion":1,
        "ok":ok, "sourceDigest":digest, "symbols":symbols, "diagnostic":diagnostic}),
    ))
}
