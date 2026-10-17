use serde::Deserialize;
use serde_json::Value;
use std::{collections::BTreeMap, io::Read, path::Path};
#[derive(Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Request {
    entry: String,
    import_root: Option<String>,
    documents: Vec<Document>,
    query: Option<gwt_core::EditorQuery>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Document {
    path: String,
    text: String,
}

pub(crate) fn run() -> Result<(bool, Value), Box<dyn std::error::Error>> {
    request(false)
}

pub(crate) fn complete() -> Result<(bool, Value), Box<dyn std::error::Error>> {
    request(true)
}

fn request(completion: bool) -> Result<(bool, Value), Box<dyn std::error::Error>> {
    let mut bytes = Vec::new();
    std::io::stdin()
        .take(8 * 1_048_576 + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 8 * 1_048_576 {
        return Err("editor request exceeds eight MiB".into());
    }
    let request: Request = serde_json::from_slice(&bytes)?;
    let mut overlays = BTreeMap::new();
    for document in request.documents {
        if overlays.insert(document.path, document.text).is_some() {
            return Err("duplicate editor document path".into());
        }
    }
    if completion {
        let query = request
            .query
            .as_ref()
            .ok_or("completion requires a query")?;
        let report = gwt_core::complete_editor(
            Path::new(&request.entry),
            request.import_root.as_deref().map(Path::new),
            &overlays,
            query,
        );
        return Ok((report.ok, serde_json::to_value(report)?));
    }
    let report = gwt_core::check_editor_query(
        Path::new(&request.entry),
        request.import_root.as_deref().map(Path::new),
        &overlays,
        request.query.as_ref(),
    );
    Ok((report.ok, serde_json::to_value(report)?))
}
