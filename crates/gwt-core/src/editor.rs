//! One bounded editor snapshot check; no scenario or behavior is executed.
use crate::editor_navigation::{EditorNavigation, EditorQuery, navigate};
use crate::{ProgramIdentity, bundle::load_editor_bundle, compile_bundle, source::Diagnostic};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, path::Path};

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EditorCheck {
    pub kind: &'static str,
    pub schema_version: u32,
    pub ok: bool,
    pub requests: Vec<String>,
    pub scenarios: Vec<String>,
    pub program_identity: Option<ProgramIdentity>,
    pub diagnostic: Option<Diagnostic>,
    /// Exact text used for the diagnostic's byte offsets, even for a load/parse failure.
    pub diagnostic_source: Option<String>,
    /// Only files actually read in the reachable closure, keyed by portable path.
    pub checked_sources: BTreeMap<String, String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub navigation: Option<EditorNavigation>,
}

pub fn check_editor(
    entry: &Path,
    root: Option<&Path>,
    overlays: &BTreeMap<String, String>,
) -> EditorCheck {
    check_editor_query(entry, root, overlays, None)
}

pub fn check_editor_query(
    entry: &Path,
    root: Option<&Path>,
    overlays: &BTreeMap<String, String>,
    query: Option<&EditorQuery>,
) -> EditorCheck {
    let mut observed = BTreeMap::new();
    let result = load_editor_bundle(entry, root, overlays, Some(&mut observed))
        .and_then(|bundle| compile_bundle(&bundle));
    let mut report = EditorCheck {
        kind: "gwt.native-editor-check",
        schema_version: 1,
        ok: result.is_ok(),
        requests: Vec::new(),
        scenarios: Vec::new(),
        program_identity: None,
        diagnostic: None,
        diagnostic_source: None,
        navigation: None,
        checked_sources: observed
            .iter()
            .map(|(path, text)| {
                (
                    path.clone(),
                    format!("sha256:{:x}", Sha256::digest(text.as_bytes())),
                )
            })
            .collect(),
    };
    match result {
        Ok(program) => {
            report.requests = program
                .request_names()
                .into_iter()
                .map(str::to_owned)
                .collect();
            report.scenarios = program
                .scenario_names()
                .into_iter()
                .map(str::to_owned)
                .collect();
            report.program_identity = program.identity().cloned();
            if let Some(query) = query {
                if observed
                    .get(&query.path)
                    .is_some_and(|text| text.is_char_boundary(query.byte_offset))
                {
                    report.navigation = Some(navigate(&program, query, &observed));
                } else {
                    report.ok = false;
                    report.diagnostic = Some(Diagnostic::new(
                        "editor_query",
                        "query must name a checked module and a valid UTF-8 byte offset",
                        &program.span,
                    ));
                    report.diagnostic_source = observed.get(&program.span.file).cloned();
                }
            }
        }
        Err(diagnostic) => {
            report.diagnostic_source = observed.get(&diagnostic.span.file).cloned();
            report.diagnostic = Some(diagnostic);
        }
    }
    report
}
